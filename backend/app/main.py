import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from .database import engine, Base
from .routes import scenarios, simulator, runs, analytics, orchestrator, products
from .routes.mary import router as mary_router
from .routes.ecosystem import router as ecosystem_router

Base.metadata.create_all(bind=engine)


# ─── Lightweight column migration ──────────────────────────────────────────
# create_all() only creates tables — it never adds columns to ones that
# already exist. The validity / proof-score columns added in recent
# releases would stay missing in any DB that pre-dates them, so we ALTER
# TABLE here at startup.
#
# Two production lessons baked into this version:
#   1. Use BOOLEAN DEFAULT FALSE — *not* DEFAULT 0. SQLite accepts the
#      integer form, but Postgres rejects it with "invalid input syntax
#      for type boolean", which used to abort the whole migration mid-way
#      (root cause of the "Batch not found" regression in commit 0e5243d).
#   2. Each ALTER runs in its OWN transaction. On Postgres, once any
#      statement in a transaction errors, every later statement in that
#      same transaction also errors with InFailedSqlTransaction — so a
#      single bad ALTER under one big `engine.begin()` would silently
#      drop every subsequent column add and the whole transaction would
#      rollback. Per-statement transactions make the migration robust to
#      one bad column without losing the rest.
def _ensure_columns():
    inspector = inspect(engine)
    plans = [
        ("runs", [
            ("proof_score",        "INTEGER DEFAULT 0"),
            ("validity_score",     "INTEGER DEFAULT 0"),
            ("validity_passed",    "BOOLEAN DEFAULT FALSE"),
            ("validity_tests",     "TEXT"),
            ("app_works",          "BOOLEAN DEFAULT FALSE"),
            ("powered_by_physis",  "BOOLEAN DEFAULT FALSE"),
        ]),
        ("ecosystem_runs", [
            ("validity_score",        "INTEGER DEFAULT 0"),
            ("validity_passed",       "BOOLEAN DEFAULT FALSE"),
            ("all_powered_by_physis", "BOOLEAN DEFAULT FALSE"),
        ]),
    ]
    for table, cols in plans:
        try:
            existing = {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            # Table doesn't exist yet — create_all() will handle it.
            continue
        for name, ddl in cols:
            if name in existing:
                continue
            try:
                # Per-column transaction: a failed ALTER on one column
                # never poisons the next column's ADD.
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
            except Exception as exc:
                # Already added by another worker, or non-fatal — log
                # only at print so a missing migration never crashes
                # the API on boot.
                print(f"[migration] {table}.{name}: {exc}")


_ensure_columns()

app = FastAPI(title="Physis Tester", version="1.0.0")

allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://physis-tester.pages.dev",
    os.getenv("FRONTEND_URL", ""),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in allowed_origins if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scenarios.router)
app.include_router(simulator.router)
app.include_router(runs.router)
app.include_router(analytics.router)
app.include_router(orchestrator.router)
app.include_router(products.router)
app.include_router(mary_router)
app.include_router(ecosystem_router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "Physis Tester"}
