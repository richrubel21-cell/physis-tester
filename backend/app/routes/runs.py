import asyncio
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

    runs = get_runs(db, batch_id=batch_id, limit=200)

    return {
        "batch_id": batch.id,
        "status": batch.status,
        "total": batch.total,
        "completed": batch.completed,
        "passed": batch.passed,
        "failed": batch.failed,
        "started_at": batch.started_at.isoformat(),
        "finished_at": batch.finished_at.isoformat() if batch.finished_at else None,
        "runs": [
            {
                "run_id": r.id,
                "description": r.description,
                "status": r.status,
                "build_time_seconds": r.build_time_seconds,
                "live_url": r.live_url,
                "error_message": r.error_message,
                "started_at": r.started_at.isoformat(),
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in runs
        ]
    }

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
