from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.simulator import run_single
from ..services.run_service import create_run, update_run
from ..services.artifact_service import store_artifact

router = APIRouter(prefix="/simulator", tags=["simulator"])

class SingleRunRequest(BaseModel):
    description: str

@router.post("/run")
async def run_one(body: SingleRunRequest, db: Session = Depends(get_db)):
    """Submit a single description to Physis and return the result."""
    run = create_run(db, description=body.description)
    sim_result = await run_single(body.description)
    updated = update_run(db, run.id, sim_result)

    if sim_result.get("physis_response"):
        store_artifact(run.id, body.description, sim_result["physis_response"])

    return {
        "run_id": updated.id,
        "status": updated.status,
        "build_time_seconds": updated.build_time_seconds,
        "live_url": updated.live_url,
        "error_message": updated.error_message,
    }
