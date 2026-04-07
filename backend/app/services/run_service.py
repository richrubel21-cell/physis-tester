from datetime import datetime
from sqlalchemy.orm import Session
from ..models import Run, Batch, Scenario

# ── Batch helpers ──────────────────────────────────────────────

def create_batch(db: Session, total: int) -> Batch:
    batch = Batch(status="running", total=total, started_at=datetime.utcnow())
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch

def get_batch(db: Session, batch_id: int) -> Batch:
    return db.query(Batch).filter(Batch.id == batch_id).first()

def get_all_batches(db: Session, limit: int = 20) -> list[Batch]:
    return db.query(Batch).order_by(Batch.started_at.desc()).limit(limit).all()

def finish_batch(db: Session, batch_id: int):
    batch = get_batch(db, batch_id)
    if not batch:
        return
    runs = db.query(Run).filter(Run.batch_id == batch_id).all()
    batch.completed = len(runs)
    batch.passed = sum(1 for r in runs if r.status == "passed")
    batch.failed = sum(1 for r in runs if r.status in ("failed", "error"))
    batch.status = "completed"
    batch.finished_at = datetime.utcnow()
    db.commit()

# ── Run helpers ────────────────────────────────────────────────

def create_run(db: Session, description: str, batch_id: int = None, scenario_id: int = None) -> Run:
    run = Run(
        description=description,
        batch_id=batch_id,
        scenario_id=scenario_id,
        status="running",
        started_at=datetime.utcnow()
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

def update_run(db: Session, run_id: int, sim_result: dict) -> Run:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        return None
    run.status = sim_result["status"]
    run.build_time_seconds = sim_result["build_time_seconds"]
    run.live_url = sim_result["live_url"]
    run.error_message = sim_result["error_message"]
    run.physis_response = sim_result["physis_response"]
    run.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(run)
    return run

def get_run(db: Session, run_id: int) -> Run:
    return db.query(Run).filter(Run.id == run_id).first()

def get_runs(db: Session, batch_id: int = None, limit: int = 50) -> list[Run]:
    q = db.query(Run)
    if batch_id:
        q = q.filter(Run.batch_id == batch_id)
    return q.order_by(Run.started_at.desc()).limit(limit).all()

# ── Scenario helpers ───────────────────────────────────────────

def save_scenarios(db: Session, scenarios: list[dict]) -> list[Scenario]:
    saved = []
    for s in scenarios:
        scenario = Scenario(
            description=s["description"],
            category=s.get("category", "general"),
            complexity=s.get("complexity", "medium"),
            source=s.get("source", "seed"),
        )
        db.add(scenario)
        saved.append(scenario)
    db.commit()
    for s in saved:
        db.refresh(s)
    return saved

def get_scenarios(db: Session, limit: int = 50) -> list[Scenario]:
    return db.query(Scenario).order_by(Scenario.created_at.desc()).limit(limit).all()
