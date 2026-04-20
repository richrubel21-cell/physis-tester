import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db, SessionLocal
from ..models import Scenario
from ..services.run_service import create_batch, get_batch, get_all_batches, get_runs, get_scenarios, save_scenarios
from ..services.orchestrator import run_batch
from ..services.scenario_generator import generate_scenarios

router = APIRouter(prefix="/runs", tags=["runs"])

class BatchRequest(BaseModel):
    count: int = 10
    use_ai: bool = True
    scenario_ids: list[int] = []  # optional: use specific saved scenarios

@router.post("/batch")
async def start_batch(body: BatchRequest, db: Session = Depends(get_db)):
    """
    Generate scenarios (or use provided IDs) and kick off a batch run.
    Returns batch_id immediately — poll /runs/batch/{id} for progress.
    """
    if body.scenario_ids:
        scenarios = db.query(Scenario).filter(Scenario.id.in_(body.scenario_ids)).all()
        descriptions = [s.description for s in scenarios]
    else:
        raw = generate_scenarios(count=body.count, use_ai=body.use_ai)
        saved = save_scenarios(db, raw)
        descriptions = [s.description for s in saved]

    batch = create_batch(db, total=len(descriptions))
    batch_id = batch.id  # capture before closing scope

    async def run_in_background():
        bg_db = SessionLocal()
        try:
            await run_batch(bg_db, batch_id, descriptions)
        except Exception as e:
            print(f"Batch {batch_id} failed: {e}")
        finally:
            bg_db.close()

    # asyncio.create_task correctly schedules a coroutine on the running event loop
    asyncio.create_task(run_in_background())

    return {
        "batch_id": batch_id,
        "total": batch.total,
        "status": batch.status,
        "message": f"Batch started with {batch.total} scenarios. Poll /runs/batch/{batch_id} for progress."
    }

@router.get("/batch/{batch_id}")
def get_batch_status(batch_id: int, db: Session = Depends(get_db)):
    """Poll this to get batch progress and all run results."""
    batch = get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Defensive: if the runs table is mid-migration (e.g. a fresh deploy
    # where the proof_score / validity_* columns haven't ALTER'd in yet),
    # SQLAlchemy's SELECT will reference columns that don't exist in
    # Postgres and the query raises ProgrammingError. We don't want that
    # to 500 the whole batch monitor — the user should still see the
    # batch metadata while the migration finishes. Catch broadly, log,
    # and fall back to an empty runs list.
    try:
        runs = get_runs(db, batch_id=batch_id, limit=200)
    except Exception as exc:
        print(f"[runs] get_runs failed for batch {batch_id}: {exc}")
        try:
            db.rollback()
        except Exception:
            pass
        runs = []

    serialized_runs = []
    for r in runs:
        try:
            serialized_runs.append({
                "run_id":             r.id,
                "description":        r.description,
                "status":             r.status,
                "build_time_seconds": r.build_time_seconds,
                "live_url":           r.live_url,
                "error_message":      r.error_message,
                "started_at":         r.started_at.isoformat() if r.started_at else None,
                "finished_at":        r.finished_at.isoformat() if r.finished_at else None,
                # Proof score (tests_passed / 21) gates Promote-to-Template.
                # Defaulted via getattr so older DBs missing the column still
                # serialize cleanly.
                "proof_score":        int(getattr(r, "proof_score", 0) or 0),
                # Validity sweep (tests 30–36). validity_tests is stored as
                # a JSON string; surface it as a parsed list so the
                # AppValidityPanel renders correctly.
                "validity_score":     int(getattr(r, "validity_score", 0) or 0),
                "validity_passed":    bool(getattr(r, "validity_passed", False)),
                "validity_tests":     _decode_validity_tests(getattr(r, "validity_tests", None)),
                "app_works":          bool(getattr(r, "app_works", False)),
                "powered_by_physis":  bool(getattr(r, "powered_by_physis", False)),
                # Functional sweep (tests 37–46). functional_tests +
                # functional_failure_screenshots are JSON strings; both
                # decode back to lists for the dashboard.
                "functional_score":               int(getattr(r, "functional_score", 0) or 0),
                "functional_passed":              bool(getattr(r, "functional_passed", False)),
                "functional_tests":               _decode_validity_tests(getattr(r, "functional_tests", None)),
                "journey_passed":                 bool(getattr(r, "journey_passed", False)),
                "all_apps_output_passed":         bool(getattr(r, "all_apps_output_passed", False)),
                "functional_failure_screenshots": _decode_validity_tests(
                    getattr(r, "functional_failure_screenshots", None)
                ),
            })
        except Exception as exc:
            # One bad row shouldn't blank the whole batch — drop it and
            # keep rendering the rest.
            print(f"[runs] serialize failed for run {getattr(r, 'id', '?')}: {exc}")

    return {
        "batch_id":    batch.id,
        "status":      batch.status,
        "total":       batch.total,
        "completed":   batch.completed,
        "passed":      batch.passed,
        "failed":      batch.failed,
        "started_at":  batch.started_at.isoformat()  if batch.started_at  else None,
        "finished_at": batch.finished_at.isoformat() if batch.finished_at else None,
        "runs":        serialized_runs,
    }


def _decode_validity_tests(raw):
    """validity_tests is persisted as a JSON string; the frontend
    expects an array of test dicts. Defensive decode for any caller."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []

@router.get("/")
def list_batches(db: Session = Depends(get_db)):
    """List all batches with summary stats."""
    batches = get_all_batches(db)
    return {
        "batches": [
            {
                "batch_id": b.id,
                "status": b.status,
                "total": b.total,
                "completed": b.completed,
                "passed": b.passed,
                "failed": b.failed,
                "started_at": b.started_at.isoformat(),
                "finished_at": b.finished_at.isoformat() if b.finished_at else None,
            }
            for b in batches
        ]
    }
