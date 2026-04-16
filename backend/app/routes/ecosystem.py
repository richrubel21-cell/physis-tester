"""
Ecosystem Tester routes.

POST /ecosystem/batch       — kick off an ecosystem batch (full or sequential)
GET  /ecosystem/batch/{id}  — batch status + per-run results
GET  /ecosystem/batches     — list all ecosystem batches
GET  /ecosystem/analytics   — aggregate stats across every ecosystem run

Mirrors the shape of the existing /runs endpoints so the frontend can reuse
its table / stat card patterns without special cases.
"""

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import SessionLocal, get_db
from ..models import EcosystemBatch, EcosystemRun
from ..services.ecosystem_scenarios import get_ecosystem_scenarios, pool_size
from ..services.ecosystem_simulator import run_single_ecosystem

router = APIRouter(prefix="/ecosystem", tags=["ecosystem"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class EcosystemBatchRequest(BaseModel):
    scenario_count: int = 5           # how many business scenarios to run
    app_count:      int = 3           # 3 or 7 — applied to every scenario in the batch
    type:           str = "full"      # "full" | "sequential"


# ─────────────────────────────────────────────────────────────────────────────
# Background runner
# ─────────────────────────────────────────────────────────────────────────────

async def _run_batch_background(batch_id: int, type_: str, app_count: int, scenarios: list[dict]) -> None:
    """
    Run every ecosystem scenario, writing per-scenario outcomes to
    ecosystem_runs as they complete. Each scenario gets its own
    EcosystemRun row. Final batch counters are rolled up at the end.
    """
    db: Session = SessionLocal()
    try:
        batch = db.query(EcosystemBatch).filter(EcosystemBatch.id == batch_id).first()
        if not batch:
            return
        batch.status = "running"
        db.commit()

        for scenario in scenarios:
            description = scenario["description"]
            run = EcosystemRun(
                batch_id              = batch_id,
                business_description  = description,
                app_count             = app_count,
                type                  = type_,
                status                = "running",
                created_at            = datetime.utcnow(),
            )
            db.add(run)
            db.commit()
            db.refresh(run)
            run_id = run.id

            try:
                result = await run_single_ecosystem(description, app_count, type_)
            except Exception as exc:
                result = {
                    "status":             "error",
                    "apps_planned":       0,
                    "apps_built":         0,
                    "apps_deployed":      0,
                    "apps_integrated":    0,
                    "passed":             False,
                    "fail_reason":        f"simulator crashed: {exc}",
                    "total_time_seconds": None,
                    "app_urls":           [],
                    "apps_detail":        [],
                    "apps_planned_json":  [],
                    "error_message":      str(exc),
                }

            # Reload run (session may have seen it evicted)
            run = db.query(EcosystemRun).filter(EcosystemRun.id == run_id).first()
            if run is None:
                continue

            run.status             = result["status"]
            run.apps_planned       = result["apps_planned"]
            run.apps_built         = result["apps_built"]
            run.apps_deployed      = result["apps_deployed"]
            run.apps_integrated    = result["apps_integrated"]
            run.passed             = bool(result["passed"])
            run.fail_reason        = result.get("fail_reason")
            run.total_time_seconds = result.get("total_time_seconds")
            run.app_urls           = json.dumps(result.get("app_urls")          or [])
            run.apps_detail        = json.dumps(result.get("apps_detail")       or [])
            run.apps_planned_json  = json.dumps(result.get("apps_planned_json") or [])
            run.error_message      = result.get("error_message")
            run.completed_at       = datetime.utcnow()
            db.commit()

        # Roll up final batch stats
        runs = db.query(EcosystemRun).filter(EcosystemRun.batch_id == batch_id).all()
        passed = sum(1 for r in runs if r.passed)
        failed = sum(1 for r in runs if not r.passed)
        build_times = [r.total_time_seconds for r in runs if r.total_time_seconds]

        batch = db.query(EcosystemBatch).filter(EcosystemBatch.id == batch_id).first()
        if batch:
            batch.pass_count     = passed
            batch.fail_count     = failed
            batch.pass_rate      = round((passed / len(runs) * 100), 1) if runs else 0.0
            batch.avg_build_time = round(sum(build_times) / len(build_times), 2) if build_times else None
            batch.status         = "completed"
            batch.completed_at   = datetime.utcnow()
            db.commit()
    except Exception as exc:
        print(f"Ecosystem batch {batch_id} background task crashed: {exc}")
        batch = db.query(EcosystemBatch).filter(EcosystemBatch.id == batch_id).first()
        if batch:
            batch.status = "failed"
            batch.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/batch")
async def start_ecosystem_batch(body: EcosystemBatchRequest, db: Session = Depends(get_db)):
    """Pick N scenarios from the pool, start a batch, return the batch_id immediately."""
    if body.app_count not in (3, 7):
        raise HTTPException(status_code=400, detail="app_count must be 3 or 7")
    if body.type not in ("full", "sequential"):
        raise HTTPException(status_code=400, detail="type must be 'full' or 'sequential'")
    if body.scenario_count <= 0 or body.scenario_count > 50:
        raise HTTPException(status_code=400, detail="scenario_count must be between 1 and 50")

    scenarios = get_ecosystem_scenarios(count=body.scenario_count)
    if not scenarios:
        raise HTTPException(status_code=500, detail="ecosystem scenario pool is empty")

    batch = EcosystemBatch(
        type           = body.type,
        status         = "pending",
        scenario_count = len(scenarios),
        app_count      = body.app_count,
        started_at     = datetime.utcnow(),
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    batch_id = batch.id

    asyncio.create_task(
        _run_batch_background(batch_id, body.type, body.app_count, scenarios)
    )

    return {
        "batch_id":       batch_id,
        "scenario_count": len(scenarios),
        "app_count":      body.app_count,
        "type":           body.type,
        "status":         batch.status,
        "message":        f"Ecosystem batch started with {len(scenarios)} scenarios "
                          f"({body.app_count} apps each, {body.type} mode). "
                          f"Poll /ecosystem/batch/{batch_id} for progress.",
    }


def _serialize_run(run: EcosystemRun) -> dict:
    """Expand stored JSON blobs back to real objects for the frontend."""
    def _decode(raw):
        if not raw:
            return []
        try:
            return json.loads(raw)
        except Exception:
            return []

    return {
        "run_id":               run.id,
        "business_description": run.business_description,
        "app_count":            run.app_count,
        "type":                 run.type,
        "status":               run.status,
        "apps_planned":         run.apps_planned,
        "apps_built":           run.apps_built,
        "apps_deployed":        run.apps_deployed,
        "apps_integrated":      run.apps_integrated,
        "passed":               run.passed,
        "fail_reason":          run.fail_reason,
        "total_time_seconds":   run.total_time_seconds,
        "app_urls":             _decode(run.app_urls),
        "apps_detail":          _decode(run.apps_detail),
        "apps_planned_json":    _decode(run.apps_planned_json),
        "error_message":        run.error_message,
        "created_at":           run.created_at.isoformat() if run.created_at else None,
        "completed_at":         run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/batch/{batch_id}")
def get_ecosystem_batch(batch_id: int, db: Session = Depends(get_db)):
    """Return batch progress plus every run that's attached to it."""
    batch = db.query(EcosystemBatch).filter(EcosystemBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Ecosystem batch not found")

    runs = (
        db.query(EcosystemRun)
        .filter(EcosystemRun.batch_id == batch_id)
        .order_by(EcosystemRun.id.asc())
        .all()
    )

    completed = sum(1 for r in runs if r.status in ("passed", "failed", "error"))

    return {
        "batch_id":       batch.id,
        "type":           batch.type,
        "status":         batch.status,
        "scenario_count": batch.scenario_count,
        "app_count":      batch.app_count,
        "completed":      completed,
        "pass_count":     batch.pass_count,
        "fail_count":     batch.fail_count,
        "pass_rate":      batch.pass_rate,
        "avg_build_time": batch.avg_build_time,
        "started_at":     batch.started_at.isoformat()    if batch.started_at    else None,
        "completed_at":   batch.completed_at.isoformat()  if batch.completed_at  else None,
        "runs":           [_serialize_run(r) for r in runs],
    }


@router.get("/batches")
def list_ecosystem_batches(db: Session = Depends(get_db)):
    """Reverse-chronological list of every ecosystem batch ever run."""
    batches = (
        db.query(EcosystemBatch)
        .order_by(EcosystemBatch.started_at.desc())
        .limit(50)
        .all()
    )
    return {
        "batches": [
            {
                "batch_id":       b.id,
                "type":           b.type,
                "status":         b.status,
                "scenario_count": b.scenario_count,
                "app_count":      b.app_count,
                "pass_count":     b.pass_count,
                "fail_count":     b.fail_count,
                "pass_rate":      b.pass_rate,
                "avg_build_time": b.avg_build_time,
                "started_at":     b.started_at.isoformat()   if b.started_at   else None,
                "completed_at":   b.completed_at.isoformat() if b.completed_at else None,
            }
            for b in batches
        ]
    }


@router.get("/analytics")
def ecosystem_analytics(db: Session = Depends(get_db)):
    """
    Aggregate ecosystem stats for the dashboard tile row:
      - total attempts
      - pass rate split by mode (full vs sequential)
      - avg completion time split by app_count
      - most common failure reason
    """
    all_runs = db.query(EcosystemRun).all()
    total    = len(all_runs)

    full_runs        = [r for r in all_runs if r.type == "full"]
    sequential_runs  = [r for r in all_runs if r.type == "sequential"]
    full_pass_rate   = round(sum(1 for r in full_runs       if r.passed) / len(full_runs) * 100, 1) if full_runs else 0.0
    seq_pass_rate    = round(sum(1 for r in sequential_runs if r.passed) / len(sequential_runs) * 100, 1) if sequential_runs else 0.0

    three_runs       = [r for r in all_runs if r.app_count == 3 and r.total_time_seconds]
    seven_runs       = [r for r in all_runs if r.app_count == 7 and r.total_time_seconds]
    avg_3app         = round(sum(r.total_time_seconds for r in three_runs) / len(three_runs), 1) if three_runs else None
    avg_7app         = round(sum(r.total_time_seconds for r in seven_runs) / len(seven_runs), 1) if seven_runs else None

    # Most common failure reason — group by a first-word heuristic since
    # fail_reason strings are free-form.
    reason_counts: dict[str, int] = {}
    for r in all_runs:
        if r.passed or not r.fail_reason:
            continue
        # Prefer the app name prefix if present: "AppName: message"
        reason = r.fail_reason.split(":", 1)[-1].strip().lower()
        reason = reason[:80] if reason else "unknown"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    most_common_failure = (
        max(reason_counts.items(), key=lambda kv: kv[1])[0]
        if reason_counts else None
    )

    return {
        "total_ecosystem_runs":    total,
        "full_pass_rate":          full_pass_rate,
        "sequential_pass_rate":    seq_pass_rate,
        "avg_3app_time_seconds":   avg_3app,
        "avg_7app_time_seconds":   avg_7app,
        "most_common_failure":     most_common_failure,
        "pool_size":               pool_size(),
    }
