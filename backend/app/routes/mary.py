"""
routes/mary.py
--------------
FastAPI routes for Mary testing vertical in Physis Tester.
Generates AI-varied prompts, stores results in DB, supports polling.
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..models import MaryBatch, MaryRun
from ..services.mary_runner import create_mary_batch, run_mary_batch
from ..services.mary_prompt_generator import generate_mary_prompts

router = APIRouter(prefix="/mary", tags=["mary"])


class MaryBatchRequest(BaseModel):
    count:  int  = 10
    use_ai: bool = True


@router.post("/batch")
async def start_mary_batch(body: MaryBatchRequest, db: Session = Depends(get_db)):
    """
    Generate prompts and kick off a Mary batch.
    Returns batch_id immediately — poll GET /mary/batch/{id} for progress.
    """
    prompts = generate_mary_prompts(count=body.count, use_ai=body.use_ai)
    if not prompts:
        raise HTTPException(status_code=500, detail="Failed to generate Mary prompts.")

    batch    = create_mary_batch(db, total=len(prompts), use_ai=body.use_ai)
    batch_id = batch.id

    async def run_in_background():
        bg_db = SessionLocal()
        try:
            await run_mary_batch(bg_db, batch_id, prompts)
        except Exception as e:
            print(f"Mary batch {batch_id} failed: {e}")
            bg_batch = bg_db.query(MaryBatch).filter(MaryBatch.id == batch_id).first()
            if bg_batch:
                bg_batch.status = "failed"
                bg_db.commit()
        finally:
            bg_db.close()

    asyncio.create_task(run_in_background())

    return {
        "batch_id": batch_id,
        "total":    batch.total,
        "status":   batch.status,
        "message":  f"Mary batch started with {batch.total} prompts. Poll /mary/batch/{batch_id} for progress.",
    }


@router.get("/batch/{batch_id}")
def get_mary_batch(batch_id: int, db: Session = Depends(get_db)):
    """Poll this endpoint to get Mary batch progress and all run results."""
    batch = db.query(MaryBatch).filter(MaryBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Mary batch not found")

    runs = db.query(MaryRun).filter(MaryRun.batch_id == batch_id).all()

    return {
        "batch_id":    batch.id,
        "status":      batch.status,
        "total":       batch.total,
        "completed":   batch.completed,
        "passed":      batch.passed,
        "failed":      batch.failed,
        "pass_rate":   batch.pass_rate,
        "use_ai":      batch.use_ai,
        "started_at":  batch.started_at.isoformat(),
        "finished_at": batch.finished_at.isoformat() if batch.finished_at else None,
        "runs": [
            {
                "run_id":                r.id,
                "screen":                r.screen,
                "prompt":                r.prompt,
                "prompt_type":           r.prompt_type,
                "source":                r.source,
                "status":                r.status,
                "response_text":         r.response_text,
                "responded_ok":          r.responded_ok,
                "speakable_ok":          r.speakable_ok,
                "context_ok":            r.context_ok,
                "persona_ok":            r.persona_ok,
                "length_ok":             r.length_ok,
                "helpful_ok":            r.helpful_ok,
                "tone_ok":               r.tone_ok,
                "score":                 r.score,
                "overall_pass":          r.overall_pass,
                "error_message":         r.error_message,
                "response_time_seconds": r.response_time_seconds,
            }
            for r in runs
        ],
    }


@router.get("/")
def list_mary_batches(db: Session = Depends(get_db)):
    """List all Mary batches with summary stats."""
    batches = db.query(MaryBatch).order_by(MaryBatch.id.desc()).limit(50).all()
    return {
        "batches": [
            {
                "batch_id":    b.id,
                "status":      b.status,
                "total":       b.total,
                "completed":   b.completed,
                "passed":      b.passed,
                "failed":      b.failed,
                "pass_rate":   b.pass_rate,
                "use_ai":      b.use_ai,
                "started_at":  b.started_at.isoformat(),
                "finished_at": b.finished_at.isoformat() if b.finished_at else None,
            }
            for b in batches
        ]
    }
