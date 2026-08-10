import io
import os
import sys

# Force line buffering on stdout/stderr before anything else imports
# or writes. PYTHONUNBUFFERED=1 in the Dockerfile should already do
# this, but a misconfigured env or a third-party module that re-opens
# the streams can defeat it. Re-wrapping the underlying buffers with
# line_buffering=True is idempotent and survives env-var changes —
# every newline-terminated write hits the FD immediately, which is
# what Render's log collector needs.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, line_buffering=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from .database import engine, Base
from .routes import scenarios, simulator, runs, analytics, orchestrator, products
from .routes.mary import router as mary_router
from .routes.ecosystem import router as ecosystem_router
from .routes.functional import router as functional_router
from .routes.admin import router as admin_router, cleanup_orphans_at_startup

# Hardcoded short hash of the commit being built into the Docker
# image. Bump on every commit that ships substantive code so a quick
# `grep "[physis-tester] starting"` in Render Live Tail confirms which
# revision is actually running. Stops us misdiagnosing "the new code
# isn't taking effect" when really the image just hasn't rebuilt.
VERSION_TAG = "test33-customization-studio"
print(f"[physis-tester] starting {VERSION_TAG}", flush=True)

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
            # Structured failure capture — added when physis started
            # surfacing a non-PII error_type on the final SSE event.
            # last_event holds the full final event JSON; error_type
            # is the closed-set bucket the dashboard filters on.
            ("last_event",                     "TEXT"),
            ("error_type",                     "VARCHAR(64)"),
            # Customization Studio results — JSON dict from
            # services/customization_tester.run_customization_tests
            # (Style Studio + MARY Changes + live-HTML diff).
            ("customization_results",          "TEXT"),
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
            # Customization Studio results for the chosen target spoke +
            # sibling health snapshots. JSON dict from
            # services/customization_tester.run_ecosystem_customization_tests.
            ("customization_results",       "TEXT"),
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
app.include_router(admin_router)


# Orphaned-batch janitor. A batch in 'running' that survives a worker
# restart (redeploy mid-run) stays 'running' forever without this — the
# dashboard then shows perpetually-active batches that never reconcile.
# Runs once on every boot so a redeploy auto-recovers anything orphaned
# by the deploy that died.
@app.on_event("startup")
def _startup_cleanup_orphans():
    cleanup_orphans_at_startup()


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
