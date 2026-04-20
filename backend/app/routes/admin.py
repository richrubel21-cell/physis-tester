"""
Admin routes — cleanup of orphaned batches.

A batch is orphaned when its row sat in status='running' through a
worker restart (e.g. a redeploy mid-run). Without a janitor those
rows stay 'running' forever and pollute the dashboard.

Phase D of the Batch #22 audit fixes (Issue 4):
  * cleanup_orphans(db) — plain helper, callable from anywhere.
    Flips any batches / ecosystem_batches in 'running' state for
    >= 30 minutes to 'failed' and stamps the finish timestamp.
  * POST /admin/cleanup-orphans — HTTP surface for the same logic,
    protected by a Bearer-token gate (TESTER_ADMIN_TOKEN env var).
  * The startup hook in main.py calls cleanup_orphans() on every
    boot so a redeploy auto-recovers anything orphaned by the
    deploy that died.

Auth model: TESTER_ADMIN_TOKEN env var holds the shared secret. The
gate is fail-closed — when the env var is unset, every request is
rejected with 503. This mirrors the _require_admin pattern in the
main physis backend (api.py).
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..models import Batch, EcosystemBatch


router = APIRouter(prefix="/admin", tags=["admin"])

# How long a batch must sit in 'running' before we consider it orphaned.
# 30 minutes is comfortably longer than any real single-app build (60-90s)
# AND longer than the longest ecosystem run we've seen (~7 minutes).
ORPHAN_AGE = timedelta(minutes=30)


def cleanup_orphans(db: Session) -> dict:
    """Flip stale 'running' batches to 'failed' on both the singles
    and the ecosystem tables. Returns counts of rows touched per
    table. Designed to be called either from the HTTP endpoint OR
    from the startup hook, so it must NOT depend on FastAPI Depends
    machinery — caller passes the session in."""
    cutoff = datetime.utcnow() - ORPHAN_AGE
    now    = datetime.utcnow()

    # synchronize_session=False because we're not reading the rows
    # back into ORM identity-mapped instances after the update;
    # avoids a noisy SAWarning on bulk updates.
    cleaned_batches = (
        db.query(Batch)
          .filter(Batch.status == "running", Batch.started_at < cutoff)
          .update(
              {Batch.status: "failed", Batch.finished_at: now},
              synchronize_session=False,
          )
    )
    cleaned_eco = (
        db.query(EcosystemBatch)
          .filter(EcosystemBatch.status == "running", EcosystemBatch.started_at < cutoff)
          .update(
              {EcosystemBatch.status: "failed", EcosystemBatch.completed_at: now},
              synchronize_session=False,
          )
    )
    db.commit()
    return {
        "cleaned_batches":           int(cleaned_batches or 0),
        "cleaned_ecosystem_batches": int(cleaned_eco     or 0),
    }


def cleanup_orphans_at_startup() -> None:
    """Wrapper used by main.py's startup hook so the route file
    owns the session lifecycle for this side path. Errors are
    swallowed and printed — a failed cleanup must NOT prevent the
    app from booting."""
    db = SessionLocal()
    try:
        result = cleanup_orphans(db)
        if result["cleaned_batches"] or result["cleaned_ecosystem_batches"]:
            print(
                f"[startup-cleanup] cleaned "
                f"{result['cleaned_batches']} stale batches + "
                f"{result['cleaned_ecosystem_batches']} stale ecosystem_batches"
            )
    except Exception as exc:
        print(f"[startup-cleanup] failed (non-fatal): {exc}")
    finally:
        db.close()


def _require_admin_token(authorization: Optional[str] = Header(None)) -> None:
    """Bearer-token gate. Reads TESTER_ADMIN_TOKEN at REQUEST time
    (not module-import time) so a Render env-var change is picked
    up on the next request without needing a code redeploy.

    Fail-closed: no env var configured = every request is rejected
    with 503. This is intentional — we never want a misconfigured
    deploy to silently expose admin endpoints."""
    expected = os.getenv("TESTER_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="TESTER_ADMIN_TOKEN not configured on this service",
        )
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")
    if parts[1] != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token")


@router.post("/cleanup-orphans")
def admin_cleanup_orphans(
    db: Session = Depends(get_db),
    _:  None    = Depends(_require_admin_token),
) -> dict:
    """Manually trigger the orphan-cleanup sweep. Useful when the
    user notices stale 'running' batches in the dashboard before
    the next service restart fires the startup hook automatically.

    Auth: Authorization: Bearer <TESTER_ADMIN_TOKEN>

    Response: {cleaned_batches: N, cleaned_ecosystem_batches: M}"""
    return cleanup_orphans(db)
