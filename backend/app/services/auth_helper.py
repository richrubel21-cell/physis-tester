"""
services/auth_helper.py
-----------------------
One-shot login against physis.onrender.com /api/auth/signin using the
Physis Tester's configured test account credentials.

Deliberately synchronous + module-cached: called during batch setup, once
per batch (not per run), so a cache miss is cheap. On any failure the
whole tester should still run its build+validity tests — customization
just gets skipped for that batch, marked "auth_unavailable".

Env vars (both required, both set in the Render dashboard for
physis-tester-docker):
  PHYSIS_TEST_USER_EMAIL     — the test account's Supabase email
  PHYSIS_TEST_USER_PASSWORD  — its password

If either is missing this returns None and the customization phase
degrades to a clearly-labelled skip. The tester never falls back to
running as the wrong account.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger("physis_tester")

PHYSIS_BASE_URL = "https://physis.onrender.com"
SIGNIN_TIMEOUT  = 15  # seconds

# Cache the Bearer for 45 min. Supabase tokens are ~1h by default; we
# refresh a little early so a long batch doesn't die mid-run on expiry.
_TOKEN_TTL_SECONDS = 45 * 60
_cache: dict = {"token": None, "email": None, "expires_at": 0.0}


def _creds() -> tuple[Optional[str], Optional[str]]:
    email = (os.getenv("PHYSIS_TEST_USER_EMAIL") or "").strip()
    pwd   = (os.getenv("PHYSIS_TEST_USER_PASSWORD") or "").strip()
    if not email or not pwd:
        return None, None
    return email, pwd


def get_test_bearer(force_refresh: bool = False) -> Optional[str]:
    """Return a Bearer access_token for the configured test account, or
    None if unavailable. Cached across calls; force_refresh=True skips
    the cache (use after seeing a 401 from a protected endpoint)."""
    now = time.time()
    if not force_refresh and _cache["token"] and now < _cache["expires_at"]:
        return _cache["token"]

    email, pwd = _creds()
    if not email or not pwd:
        logger.warning(
            "[auth_helper] PHYSIS_TEST_USER_EMAIL / _PASSWORD not set — "
            "customization phase will be skipped this batch"
        )
        return None

    try:
        with httpx.Client(timeout=SIGNIN_TIMEOUT) as client:
            resp = client.post(
                f"{PHYSIS_BASE_URL}/api/auth/signin",
                json={"email": email, "password": pwd},
                headers={"Content-Type": "application/json"},
            )
    except Exception as exc:
        logger.error("[auth_helper] signin request crashed: %s", exc)
        return None

    if resp.status_code != 200:
        logger.error(
            "[auth_helper] signin failed HTTP %s — body=%s",
            resp.status_code, resp.text[:200],
        )
        return None

    try:
        data  = resp.json()
        token = data.get("access_token")
    except Exception as exc:
        logger.error("[auth_helper] signin returned non-JSON: %s", exc)
        return None

    if not token:
        logger.error("[auth_helper] signin returned no access_token: %s", str(data)[:200])
        return None

    _cache["token"]      = token
    _cache["email"]      = email
    _cache["expires_at"] = now + _TOKEN_TTL_SECONDS
    logger.info("[auth_helper] signed in as %s (bearer cached %.0fmin)",
                email, _TOKEN_TTL_SECONDS / 60)
    return token


def cached_email() -> Optional[str]:
    """Which account the cached bearer belongs to. Used for logging."""
    return _cache.get("email")
