from fastapi import APIRouter

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

@router.get("/status")
def status():
    return {"message": "Orchestrator is managed via /runs/batch — start a batch there."}
