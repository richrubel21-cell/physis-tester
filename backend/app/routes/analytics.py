from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..models import Run, Batch

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    """Overall stats across all runs."""
    total_runs = db.query(Run).count()
    passed = db.query(Run).filter(Run.status == "passed").count()
    failed = db.query(Run).filter(Run.status == "failed").count()
    errors = db.query(Run).filter(Run.status == "error").count()

    avg_build_time = db.query(func.avg(Run.build_time_seconds)).filter(
        Run.build_time_seconds.is_not(None)
    ).scalar()

    fastest = db.query(func.min(Run.build_time_seconds)).filter(
        Run.build_time_seconds.is_not(None), Run.status == "passed"
    ).scalar()

    slowest = db.query(func.max(Run.build_time_seconds)).filter(
        Run.build_time_seconds.is_not(None)
    ).scalar()

    pass_rate = round((passed / total_runs * 100), 1) if total_runs > 0 else 0

    return {
        "total_runs": total_runs,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "pass_rate_percent": pass_rate,
        "avg_build_time_seconds": round(avg_build_time, 2) if avg_build_time else None,
        "fastest_build_seconds": round(fastest, 2) if fastest else None,
        "slowest_build_seconds": round(slowest, 2) if slowest else None,
    }

@router.get("/failures")
def failure_breakdown(limit: int = 20, db: Session = Depends(get_db)):
    """Recent failures with error messages for debugging."""
    failures = db.query(Run).filter(
        Run.status.in_(["failed", "error"])
    ).order_by(Run.started_at.desc()).limit(limit).all()

    return {
        "total_failures": len(failures),
        "failures": [
            {
                "run_id": r.id,
                "description": r.description,
                "status": r.status,
                "error_message": r.error_message,
                "build_time_seconds": r.build_time_seconds,
                "started_at": r.started_at.isoformat(),
            }
            for r in failures
        ]
    }

@router.get("/batch/{batch_id}")
def batch_analytics(batch_id: int, db: Session = Depends(get_db)):
    """Analytics scoped to a single batch."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        return {"error": "Batch not found"}

    runs = db.query(Run).filter(Run.batch_id == batch_id).all()
    build_times = [r.build_time_seconds for r in runs if r.build_time_seconds]

    return {
        "batch_id": batch_id,
        "pass_rate_percent": round((batch.passed / batch.total * 100), 1) if batch.total > 0 else 0,
        "avg_build_time_seconds": round(sum(build_times) / len(build_times), 2) if build_times else None,
        "status_breakdown": {
            "passed": batch.passed,
            "failed": batch.failed,
            "total": batch.total,
        }
    }
