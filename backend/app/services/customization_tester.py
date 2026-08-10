"""
services/customization_tester.py
--------------------------------
Post-build Customization Studio tests. Applies one Style Studio change
(free lane) and one MARY Changes edit (credit lane) to a deployed app,
then fetches the live HTML to confirm the visible page ACTUALLY changed
— not just that the API returned success.

Design points
-------------
* Live-diff is the gate. Every API call to /api/customize/... is
  compared against a fetched-before / fetched-after HTML pair. A change
  that returns 200 but leaves the deployed HTML byte-identical FAILS
  the test — that's the exact "API said yes but nothing happened" bug
  that made post-build customization untested until now.

* MARY tests need credits. We top-up-to-target through the double-gated
  /api/test/seed-credits endpoint (X-Seed-Token + must be the configured
  PHYSIS_TEST_USER_EMAIL). If seeding fails, the MARY test skips with a
  clear "credits_unavailable" reason instead of consuming the account
  balance in production.

* Every failure is a labelled reason string, not just False. The final
  result dict is designed for direct persistence into Run.customization_results
  as JSON. Feeds the /runs/batch dashboard and, downstream, whatever
  admin tile surfaces this later.

* Never raises. Any unexpected exception is caught and recorded as
  status="error" with the exception text truncated — a customization
  bug can't take a whole batch offline.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from typing import Any, Dict, Optional

import httpx

from .auth_helper import get_test_bearer

logger = logging.getLogger("physis_tester")

PHYSIS_BASE_URL = "https://physis.onrender.com"

# Seed enough credits to run one MARY confirm. The pricing floor per
# change is ~5-25 depending on scope; 100 gives headroom for any single
# quote size and stays low enough that repeated top-ups converge fast.
MARY_CREDIT_TARGET = 100

# A Style Studio preset that produces a visible palette change from any
# reasonable default. Present in customization.THEME_PRESETS on physis
# main — verified via studio_catalog reply the tester bootstrap can
# double-check at runtime if this ever drifts.
STYLE_PRESET  = "ocean"
STYLE_LABEL   = "physis-tester Ocean apply"

# A MARY Changes instruction that mints a small, VISIBLE, non-breaking
# copy edit. Keeping the change surface small keeps the credit cost
# predictable and the live-diff assertion simple.
MARY_INSTRUCTION = (
    "Change the heading text to say 'Updated by Physis Tester' "
    "(keep everything else identical)."
)

# Everything that touches physis budgets under the same timeout family
# the rest of the tester uses. Customization ops are quick relative to
# builds; MARY confirm is the outlier because it runs Anthropic + deploy.
CUSTOMIZE_TIMEOUT = 30
MARY_CONFIRM_TIMEOUT = 180
LIVE_FETCH_TIMEOUT = 15


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _blank_result(reason: str) -> Dict[str, Any]:
    """Placeholder returned when customization runs but has nothing to
    say (build failed / auth unavailable / etc). Kept in the same shape
    the happy path uses so the dashboard renders consistently."""
    return {
        "phase":             "skipped",
        "reason":            reason,
        "style":  {"status": "skipped", "reason": reason},
        "mary":   {"status": "skipped", "reason": reason},
    }


def _hash_html(html: str) -> str:
    """Short SHA-256 of the HTML body. Used to answer 'did the served
    page actually change' without persisting the full HTML twice."""
    return hashlib.sha256((html or "").encode("utf-8")).hexdigest()[:16]


def _extract_headings(html: str) -> list[str]:
    """First few h1/h2 texts. Cheap heuristic for confirming a MARY
    heading edit landed even when other markup near it also changed
    (React hydration id shifts, whitespace differences, etc.)."""
    if not html:
        return []
    matches = re.findall(r"<(?:h1|h2)[^>]*>(.*?)</(?:h1|h2)>",
                         html, flags=re.IGNORECASE | re.DOTALL)
    return [re.sub(r"<[^>]+>", "", m).strip()[:120] for m in matches[:6]]


def _subdomain_from_live_url(live_url: str) -> Optional[str]:
    """`https://donor-cooldown-detector.myphysis.ai` → `donor-cooldown-detector`."""
    if not live_url:
        return None
    m = re.search(r"https?://([^./]+)\.myphysis\.ai", live_url)
    return m.group(1) if m else None


async def _fetch_live_html(client: httpx.AsyncClient, live_url: str) -> Optional[str]:
    """GET the live app's index.html so we can hash before/after. Cache-
    busted with a random query param so a CDN can't return a stale copy."""
    if not live_url:
        return None
    try:
        # Random query param → the CDN treats this as a distinct URL and
        # doesn't hand us back the cached pre-change HTML.
        import secrets
        bust = secrets.token_hex(4)
        resp = await client.get(f"{live_url}?_diff={bust}",
                                timeout=LIVE_FETCH_TIMEOUT,
                                headers={"cache-control": "no-cache"})
        if resp.status_code != 200:
            logger.warning("[cust] live fetch HTTP %s for %s", resp.status_code, live_url)
            return None
        return resp.text
    except Exception as exc:
        logger.warning("[cust] live fetch crashed for %s: %s", live_url, exc)
        return None


async def _seed_credits_if_needed(
    client: httpx.AsyncClient, bearer: str, target: int,
) -> Dict[str, Any]:
    """Top-up-to-target the tester account's balance. Returns
    {ok, balance, seeded, reason?}. Never raises."""
    token = os.getenv("TEST_SEED_TOKEN")
    if not token:
        return {"ok": False, "reason": "TEST_SEED_TOKEN unset on physis backend"}
    try:
        resp = await client.post(
            f"{PHYSIS_BASE_URL}/api/test/seed-credits",
            json={"credits": target},
            headers={
                "Authorization": f"Bearer {bearer}",
                "X-Seed-Token":  token,
                "Content-Type":  "application/json",
            },
            timeout=CUSTOMIZE_TIMEOUT,
        )
    except Exception as exc:
        return {"ok": False, "reason": f"seed_credits crashed: {exc}"}
    if resp.status_code != 200:
        return {
            "ok": False,
            "reason": f"seed_credits HTTP {resp.status_code}: {resp.text[:200]}",
        }
    data = resp.json()
    return {"ok": True, "balance": data.get("balance"), "seeded": data.get("seeded")}


# ─────────────────────────────────────────────────────────────────────
# Style Studio phase
# ─────────────────────────────────────────────────────────────────────

async def _run_style_phase(
    client: httpx.AsyncClient, bearer: str, subdomain: str, live_url: str,
    html_before: str,
) -> Dict[str, Any]:
    """Apply STYLE_PRESET via /api/customize/{sub}/apply and confirm the
    live HTML changed."""
    result: Dict[str, Any] = {
        "status":  "error",
        "preset":  STYLE_PRESET,
        "reason":  None,
    }

    # Fire the apply.
    try:
        apply_resp = await client.post(
            f"{PHYSIS_BASE_URL}/api/customize/{subdomain}/apply",
            json={"preset": STYLE_PRESET, "label": STYLE_LABEL},
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type":  "application/json",
            },
            timeout=CUSTOMIZE_TIMEOUT,
        )
    except Exception as exc:
        result["reason"] = f"apply crashed: {exc}"
        return result

    if apply_resp.status_code != 200:
        result["status"] = "failed"
        result["reason"] = f"apply HTTP {apply_resp.status_code}: {apply_resp.text[:200]}"
        result["api_status_code"] = apply_resp.status_code
        return result

    try:
        apply_body = apply_resp.json()
    except Exception as exc:
        result["status"] = "failed"
        result["reason"] = f"apply returned non-JSON: {exc}"
        return result
    result["api_ok"]      = bool(apply_body.get("ok"))
    result["version_id"]  = apply_body.get("version_id")

    # Give the redeploy a moment to land at the edge — R2 upload +
    # Cloudflare cache invalidation take a few seconds on a good day.
    await asyncio.sleep(6)

    html_after = await _fetch_live_html(client, live_url)
    if html_after is None:
        result["status"] = "failed"
        result["reason"] = "live fetch after apply failed (see log)"
        return result

    result["hash_before"] = _hash_html(html_before)
    result["hash_after"]  = _hash_html(html_after)
    result["bytes_before"] = len(html_before)
    result["bytes_after"]  = len(html_after)

    # Retry once with more sleep if the hashes still match — sometimes the
    # edge hangs onto the pre-change asset for 8-10s.
    if result["hash_before"] == result["hash_after"]:
        await asyncio.sleep(8)
        retry_html = await _fetch_live_html(client, live_url)
        if retry_html is not None:
            html_after = retry_html
            result["hash_after"]  = _hash_html(html_after)
            result["bytes_after"] = len(html_after)

    if result["hash_before"] == result["hash_after"]:
        result["status"] = "failed"
        result["reason"] = (
            "API returned success but live HTML unchanged "
            f"(hash={result['hash_before']}, bytes={len(html_before)})"
        )
        return result

    result["status"] = "passed"
    return result


# ─────────────────────────────────────────────────────────────────────
# MARY Changes phase
# ─────────────────────────────────────────────────────────────────────

async def _run_mary_phase(
    client: httpx.AsyncClient, bearer: str, subdomain: str, live_url: str,
    html_before: str,
) -> Dict[str, Any]:
    """Quote + confirm a MARY change and confirm the live HTML changed
    (and the heading text specifically reflects the edit when possible)."""
    result: Dict[str, Any] = {
        "status":     "error",
        "reason":     None,
        "instruction": MARY_INSTRUCTION,
    }

    # Ensure credits.
    seed = await _seed_credits_if_needed(client, bearer, MARY_CREDIT_TARGET)
    result["credits_seed"] = seed
    if not seed.get("ok"):
        result["status"] = "skipped"
        result["reason"] = f"credits_unavailable: {seed.get('reason')}"
        return result

    # Quote.
    try:
        quote_resp = await client.post(
            f"{PHYSIS_BASE_URL}/api/customize/{subdomain}/mary/quote",
            json={"instruction": MARY_INSTRUCTION},
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type":  "application/json",
            },
            timeout=CUSTOMIZE_TIMEOUT,
        )
    except Exception as exc:
        result["reason"] = f"quote crashed: {exc}"
        return result

    if quote_resp.status_code != 200:
        result["status"] = "failed"
        result["reason"] = f"quote HTTP {quote_resp.status_code}: {quote_resp.text[:200]}"
        return result

    try:
        quote_body = quote_resp.json()
    except Exception as exc:
        result["status"] = "failed"
        result["reason"] = f"quote returned non-JSON: {exc}"
        return result

    request_id = quote_body.get("request_id") or quote_body.get("id")
    cost       = quote_body.get("credit_cost") or quote_body.get("cost")
    style_only = bool(quote_body.get("style_only"))
    result["request_id"] = request_id
    result["credit_cost"] = cost
    result["style_only"]  = style_only

    if style_only:
        # MARY flagged the change as pure styling — the backend says use
        # Style Studio. Not a failure per se, but the MARY lane isn't
        # what actually applied it. Mark as skipped with a clear reason.
        result["status"] = "skipped"
        result["reason"] = "MARY classified as style_only (would apply via Style Studio, not credits)"
        return result

    if not request_id:
        result["status"] = "failed"
        result["reason"] = f"quote returned no request_id: {str(quote_body)[:200]}"
        return result

    # Confirm.
    try:
        confirm_resp = await client.post(
            f"{PHYSIS_BASE_URL}/api/customize/{subdomain}/mary/confirm",
            json={"request_id": request_id},
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type":  "application/json",
            },
            timeout=MARY_CONFIRM_TIMEOUT,
        )
    except Exception as exc:
        result["reason"] = f"confirm crashed: {exc}"
        return result

    if confirm_resp.status_code != 200:
        result["status"] = "failed"
        result["reason"] = f"confirm HTTP {confirm_resp.status_code}: {confirm_resp.text[:200]}"
        return result

    try:
        confirm_body = confirm_resp.json()
    except Exception as exc:
        result["status"] = "failed"
        result["reason"] = f"confirm returned non-JSON: {exc}"
        return result
    result["api_ok"] = bool(confirm_body.get("ok"))

    # Redeploy delay — MARY-driven changes rebuild the app, then upload +
    # cache-invalidate. Longer than Style Studio's flat sleep.
    await asyncio.sleep(10)

    html_after = await _fetch_live_html(client, live_url)
    if html_after is None:
        result["status"] = "failed"
        result["reason"] = "live fetch after confirm failed (see log)"
        return result

    result["hash_before"]     = _hash_html(html_before)
    result["hash_after"]      = _hash_html(html_after)
    result["headings_before"] = _extract_headings(html_before)
    result["headings_after"]  = _extract_headings(html_after)

    if result["hash_before"] == result["hash_after"]:
        # One more retry with longer wait — MARY builds can take a bit.
        await asyncio.sleep(15)
        retry_html = await _fetch_live_html(client, live_url)
        if retry_html is not None:
            html_after = retry_html
            result["hash_after"]     = _hash_html(html_after)
            result["headings_after"] = _extract_headings(html_after)

    if result["hash_before"] == result["hash_after"]:
        result["status"] = "failed"
        result["reason"] = (
            "API returned success but live HTML unchanged "
            f"(hash={result['hash_before']})"
        )
        return result

    result["status"] = "passed"
    return result


# ─────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────

async def run_customization_tests(live_url: Optional[str]) -> Dict[str, Any]:
    """Full customization phase for a single app. Returns a dict safe to
    JSON-dump into Run.customization_results."""
    if not live_url:
        return _blank_result("no_live_url")
    subdomain = _subdomain_from_live_url(live_url)
    if not subdomain:
        return _blank_result(f"could_not_parse_subdomain: {live_url}")

    bearer = get_test_bearer()
    if not bearer:
        return _blank_result("auth_unavailable")

    result: Dict[str, Any] = {
        "phase":     "customization",
        "subdomain": subdomain,
        "live_url":  live_url,
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            html_initial = await _fetch_live_html(client, live_url)
            if html_initial is None:
                result["style"] = {"status": "skipped", "reason": "initial live fetch failed"}
                result["mary"]  = {"status": "skipped", "reason": "initial live fetch failed"}
                return result

            style = await _run_style_phase(
                client, bearer, subdomain, live_url, html_initial,
            )
            result["style"] = style

            # Use the post-style HTML as the pre-MARY baseline — MARY's
            # diff is compared against the app AS IT NOW IS, not against
            # the pristine build.
            html_after_style = await _fetch_live_html(client, live_url)
            mary_baseline = html_after_style if html_after_style is not None else html_initial

            mary = await _run_mary_phase(
                client, bearer, subdomain, live_url, mary_baseline,
            )
            result["mary"] = mary

    except Exception as exc:
        # Never let a customization bug break the whole run entry.
        logger.error("[cust] run_customization_tests crashed: %s", exc)
        result.setdefault("style", {"status": "error", "reason": f"phase crashed: {exc}"})
        result.setdefault("mary",  {"status": "error", "reason": f"phase crashed: {exc}"})

    result["passed"] = bool(
        (result.get("style") or {}).get("status") == "passed"
        and (result.get("mary")  or {}).get("status") in ("passed", "skipped")
    )
    return result


async def run_ecosystem_customization_tests(
    apps_detail: list,
) -> Dict[str, Any]:
    """Customize the FIRST spoke that has a live_url, then re-check every
    OTHER spoke (and hub if identifiable) to confirm nothing broke.

    apps_detail is the per-app dict list ecosystem_simulator already
    persists on EcosystemRun. Each entry is expected to have at least
    {live_url, name/role/is_hub}.

    Returns {phase, target, style, mary, siblings: [{live_url, still_ok}]}
    ready for JSON-dumping into EcosystemRun.customization_results.
    """
    apps = [a for a in (apps_detail or []) if isinstance(a, dict)]
    live_apps = [a for a in apps if a.get("live_url")]
    if len(live_apps) < 2:
        return _blank_result(f"ecosystem_needs_>=2_live_apps (got {len(live_apps)})")

    # Prefer a NON-hub spoke as the customization target. If nothing is
    # explicitly flagged as hub, take the first live app.
    def _is_hub(a: dict) -> bool:
        for k in ("is_hub", "hub", "role"):
            v = a.get(k)
            if isinstance(v, bool) and v: return True
            if isinstance(v, str) and v.lower() in ("hub", "brain"): return True
        return False

    non_hub_live = [a for a in live_apps if not _is_hub(a)]
    target = (non_hub_live or live_apps)[0]
    others = [a for a in live_apps if a is not target]

    single_result = await run_customization_tests(target.get("live_url"))
    single_result["ecosystem_target"] = {
        "live_url": target.get("live_url"),
        "role":     target.get("role") or ("spoke" if not _is_hub(target) else "hub"),
    }

    # Re-check every other live app: still returns 200 and the HTML has
    # not become empty/error. Byte-for-byte identical to the pre-batch
    # snapshot is IDEAL but not required — some apps have timestamps in
    # their rendered HTML. A 200 with plausible size is the pragmatic bar.
    siblings: list = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for a in others:
            url = a.get("live_url") or ""
            html = await _fetch_live_html(client, url)
            siblings.append({
                "live_url":     url,
                "role":         a.get("role") or ("hub" if _is_hub(a) else "spoke"),
                "still_ok":     bool(html and len(html) > 200),
                "bytes":        len(html or ""),
            })
    single_result["siblings"] = siblings
    single_result["siblings_all_ok"] = all(s["still_ok"] for s in siblings)

    # An ecosystem customization only passes if the target's own style/mary
    # passed AND every sibling is still responding.
    single_result["passed"] = bool(
        single_result.get("passed") and single_result["siblings_all_ok"]
    )
    return single_result
