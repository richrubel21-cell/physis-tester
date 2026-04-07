from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.scenario_generator import generate_scenarios
from ..services.run_service import save_scenarios, get_scenarios

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

@router.post("/generate")
def generate(
    count: int = Query(default=10, ge=1, le=50),
    use_ai: bool = Query(default=True),
    db: Session = Depends(get_db)
):
    """Generate scenarios (seed + optional AI variation) and save them to DB."""
    scenarios = generate_scenarios(count=count, use_ai=use_ai)
    saved = save_scenarios(db, scenarios)
    return {
        "generated": len(saved),
        "scenarios": [
            {
                "id": s.id,
                "description": s.description,
                "category": s.category,
                "complexity": s.complexity,
                "source": s.source,
            }
            for s in saved
        ]
    }

@router.get("/")
def list_scenarios(limit: int = 50, db: Session = Depends(get_db)):
    scenarios = get_scenarios(db, limit=limit)
    return {
        "total": len(scenarios),
        "scenarios": [
            {
                "id": s.id,
                "description": s.description,
                "category": s.category,
                "complexity": s.complexity,
                "source": s.source,
                "created_at": s.created_at.isoformat(),
            }
            for s in scenarios
        ]
    }
