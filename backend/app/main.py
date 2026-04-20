import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from .database import engine, Base
from .routes import scenarios, simulator, runs, analytics, orchestrator, products
from .routes.mary import router as mary_router
from .routes.ecosystem import router as ecosystem_router
from .routes.functional import router as functional_router

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
    # IMPORTANT — every column added to a model AFTER its table was first
    # created via Base.metadata.create_all() must be listed here, otherwise
    # the prod DB schema drifts from the ORM and any SELECT involving the
    # missing column raises UndefinedColumn.
    #
    # Audit done 2026-04-19 against models.py: every later-added column on
    # Run / EcosystemBatch / EcosystemRun is now covered. Scenario / Batch /
    # MaryBatch / MaryRun have never gained a column post-creation, so
    # they don't need entries.
    plans = [
        ("runs", [
            ("proof_score",                    "INTEGER DEFAULT 0"),
            ("validity_score",                 "INTEGER DEFAULT 0"),
            ("validity_passed",                "BOOLEAN DEFAULT FALSE"),
            ("validity_tests",                 "TEXT"),
            ("app_works",                      "BOOLEAN DEFAULT FALSE"),
            ("powered_by_physis",              "BOOLEAN DEFAULT FALSE"),
            # Functional tests (37–46) — Phase 1 schema.
            ("functional_score",               "INTEGER DEFAULT 0"),
            ("functional_passed",              "BOOLEAN DEFAULT FALSE"),
            ("functional_tests",               "TEXT"),
            ("journey_passed",                 "BOOLEAN DEFAULT FALSE"),
            ("all_apps_output_passed",         "BOOLEAN DEFAULT FALSE"),
            ("functional_failure_screenshots", "TEXT"),
        ]),
        # ecosystem_batches gained marketplace_eligible after the batch
        # rollup landed. Missing column was triggering UndefinedColumn on
        # /ecosystem/batches and /ecosystem/analytics — caught in prod.
        ("ecosystem_batches", [
            ("marketplace_eligible", "BOOLEAN DEFAULT FALSE"),
        ]),
        ("ecosystem_runs", [
            # Integration tests (22–29) — added when the 8 cross-ecosystem
            # tests landed (commit 9e0b64d). Never made it into a migration.
            ("integration_score",           "INTEGER DEFAULT 0"),
            ("integration_passed",          "BOOLEAN DEFAULT FALSE"),
            ("integration_results",         "TEXT"),
            ("integration_details",         "TEXT"),
            # Per-app validity rollup (tests 30–36).
            ("validity_score",              "INTEGER DEFAULT 0"),
            ("validity_passed",             "BOOLEAN DEFAULT FALSE"),
            ("all_powered_by_physis",       "BOOLEAN DEFAULT FALSE"),
            # Functional rollup across every app + cross-ecosystem tests.
            ("functional_score",            "INTEGER DEFAULT 0"),
            ("functional_passed",           "BOOLEAN DEFAULT FALSE"),
            ("all_apps_output_passed",      "BOOLEAN DEFAULT FALSE"),
            ("ecosystem_functional_tests",  "TEXT"),
            # Per-ecosystem marketplace eligibility — also added later,
            # also never migrated.
            ("marketplace_eligible",        "BOOLEAN DEFAULT FALSE"),
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
app.include_router(functional_router)


# Browser cleanup on shutdown so a uvicorn restart doesn't orphan the
# chromium process. Lazy-imported because functional_tester imports
# playwright lazily; this hook is a no-op when playwright isn't
# available (dev machines that haven't run `playwright install`).
@app.on_event("shutdown")
async def _shutdown_close_browser():
    try:
        from .services.functional_tester import close_browser
        await close_browser()
    except Exception as exc:
        print(f"[shutdown] browser close skipped: {exc}")

@app.get("/health")
def health():
    return {"status": "ok", "service": "Physis Tester"}
