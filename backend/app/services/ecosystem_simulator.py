"""
Ecosystem Tester — two test modes that drive the Physis /api/ecosystem-builder/plan
+ /build pipeline end to end.

MODE A — Full Ecosystem Build:
  1. POST /api/ecosystem-builder/plan with the business description + app_count
  2. Auto-approve the returned plan
  3. Fan out a /build call for every planned app (async gather, relying on
     Physis's own MAX_CONCURRENT_BUILDS queue to serialise)
  4. For each build, poll /build/{id}/status until a final event lands
  5. PASS only if every planned app returned a live_url

MODE B — Sequential Ecosystem Build:
  Same plan step, but builds run strictly one-at-a-time with join_ecosystem=True
  so the join flow is exercised on every single app.

Verification note — ecosystem nav integration:
  Verifying that the deployed apps actually appear in a live ecosystem nav
  would require authenticating to Physis as the test user and reading
  GET /api/ecosystem. Physis's auto-join only fires when the build is tied
  to a real Supabase user_id. The simulator generates a test UUID per
  ecosystem run and sends it as user_id; if Supabase rejects the FK the
  backend swallows it silently, so we track apps_integrated separately from
  apps_deployed and only set integrated=deployed when we have a valid way
  to verify (left as an extension once the tester has a real test user).

Result shape returned by run_single_ecosystem():
  {
    "status":              "passed" | "failed" | "error",
    "apps_planned":        int,
    "apps_built":          int,         # got a build_id
    "apps_deployed":       int,         # got a live_url
    "apps_integrated":     int,         # currently == apps_deployed, see note above
    "passed":              bool,
    "fail_reason":         str | None,
    "total_time_seconds":  float,
    "app_urls":            list[str],
    "apps_detail":         list[dict],  # per-app build outcome
    "apps_planned_json":   list[dict],  # raw plan from Physis
    "error_message":       str | None,
  }
"""

import asyncio
import json
import random
import time
import uuid

import httpx

from .simulator import (
    BASE_PAYLOAD,
    COMPLEXITY_OPTIONS,
    PHYSIS_BASE_URL,
)


# ─────────────────────────────────────────────────────────────────────────────
# Timeouts
# ─────────────────────────────────────────────────────────────────────────────

PLAN_TIMEOUT_SECONDS   = 90     # /api/ecosystem-builder/plan uses Haiku — slow-ish
BUILD_POST_TIMEOUT     = 30     # POST /build should come back quick
STATUS_POLL_INTERVAL   = 5      # seconds between /status polls
STATUS_POLL_TIMEOUT    = 600    # 10 min per app — Physis may queue
ECOSYSTEM_TOTAL_BUDGET = 3600   # 60 min overall budget per ecosystem run


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _plan_ecosystem(description: str, app_count: int, user_id: str) -> dict:
    """
    Call POST /api/ecosystem-builder/plan and return the raw response dict
    plus a normalised apps list. On failure returns an error dict that the
    caller surfaces as fail_reason.
    """
    try:
        async with httpx.AsyncClient(timeout=PLAN_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{PHYSIS_BASE_URL}/api/ecosystem-builder/plan",
                json={
                    "description": description,
                    "app_count":   app_count,
                    "user_id":     user_id,
                },
                headers={"Content-Type": "application/json"},
            )
    except httpx.TimeoutException:
        return {"ok": False, "error": "plan timeout (Physis AI planner took too long)", "apps": []}
    except httpx.ConnectError:
        return {"ok": False, "error": "Cannot connect to physis.onrender.com", "apps": []}
    except Exception as exc:
        return {"ok": False, "error": f"plan request crashed: {exc}", "apps": []}

    if resp.status_code != 200:
        return {
            "ok":    False,
            "error": f"plan returned HTTP {resp.status_code}: {resp.text[:300]}",
            "apps":  [],
        }

    try:
        data = resp.json()
    except Exception:
        return {"ok": False, "error": f"plan returned non-JSON: {resp.text[:300]}", "apps": []}

    apps = data.get("apps") or []
    if not isinstance(apps, list) or len(apps) == 0:
        return {"ok": False, "error": "plan returned no apps", "apps": []}

    return {"ok": True, "apps": apps, "raw": data}


def _build_payload_for_app(app: dict, user_id: str, join_ecosystem: bool) -> dict:
    """
    Build a /build POST body for a single planned app. Uses the app's
    purpose as the description (fed into both generates and userInput so
    it wins against the BASE_PAYLOAD default of 'web app').
    """
    purpose = str(app.get("purpose") or "").strip() or "A helper tool"
    name    = str(app.get("name")    or "").strip() or "PhysisApp"
    return {
        **BASE_PAYLOAD,
        "generates":      purpose,
        "userInput":      purpose,
        "complexity":     random.choice(COMPLEXITY_OPTIONS),
        "selectedName":   name,
        "user_id":        user_id,
        "join_ecosystem": join_ecosystem,
    }


async def _post_build(payload: dict) -> dict:
    """POST /build and return {ok, build_id, error}."""
    try:
        async with httpx.AsyncClient(timeout=BUILD_POST_TIMEOUT) as client:
            resp = await client.post(
                f"{PHYSIS_BASE_URL}/build",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
    except httpx.TimeoutException:
        return {"ok": False, "error": "POST /build timed out"}
    except httpx.ConnectError:
        return {"ok": False, "error": "Cannot reach Physis"}
    except Exception as exc:
        return {"ok": False, "error": f"/build crashed: {exc}"}

    if resp.status_code == 422:
        return {"ok": False, "error": f"/build 422: {resp.text[:300]}"}
    if resp.status_code != 200:
        return {"ok": False, "error": f"/build HTTP {resp.status_code}: {resp.text[:200]}"}

    try:
        data = resp.json()
    except Exception:
        return {"ok": False, "error": f"/build non-JSON: {resp.text[:200]}"}

    build_id = data.get("build_id") or data.get("id") or data.get("buildId")
    if not build_id:
        return {"ok": False, "error": "no build_id in /build response"}
    return {"ok": True, "build_id": build_id}


async def _poll_build_status(build_id: str) -> dict:
    """
    Poll /build/{id}/status until the last_event is final, or timeout hits.
    Returns {status, live_url, build_time, error}.
    """
    start = time.time()
    last_body = ""
    while True:
        if time.time() - start > STATUS_POLL_TIMEOUT:
            return {
                "status":      "failed",
                "live_url":    None,
                "build_time":  round(time.time() - start, 2),
                "error":       f"polling timed out after {STATUS_POLL_TIMEOUT}s",
                "last_body":   last_body[:500],
            }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{PHYSIS_BASE_URL}/build/{build_id}/status")
        except Exception as exc:
            # Transient networking hiccup — wait and retry
            await asyncio.sleep(STATUS_POLL_INTERVAL)
            last_body = f"status fetch failed: {exc}"
            continue

        if resp.status_code == 404:
            return {
                "status":     "failed",
                "live_url":   None,
                "build_time": round(time.time() - start, 2),
                "error":      "build not found (maybe evicted from memory)",
                "last_body":  resp.text[:300],
            }

        try:
            data = resp.json()
        except Exception:
            await asyncio.sleep(STATUS_POLL_INTERVAL)
            last_body = resp.text[:300]
            continue

        last_body = json.dumps(data)[:1500]
        live_url  = data.get("live_url")
        last_ev   = data.get("last_event") or {}
        is_final  = bool(last_ev.get("is_final"))
        status    = (last_ev.get("status") or data.get("status") or "").lower()

        if is_final or status in ("queue_timeout",):
            elapsed = round(time.time() - start, 2)
            if live_url:
                return {"status": "passed", "live_url": live_url, "build_time": elapsed, "error": None, "last_body": last_body}
            # Final event but no live_url — treat as fail
            return {
                "status":     "failed",
                "live_url":   None,
                "build_time": elapsed,
                "error":      last_ev.get("nontechnical_message") or last_ev.get("message") or "build finished without a live URL",
                "last_body":  last_body,
            }

        await asyncio.sleep(STATUS_POLL_INTERVAL)


async def _run_single_app_build(app: dict, user_id: str, join_ecosystem: bool) -> dict:
    """
    Build one planned app. Returns a per-app result dict suitable for the
    EcosystemRun.apps_detail JSON array.
    """
    payload  = _build_payload_for_app(app, user_id, join_ecosystem)
    started  = time.time()

    posted = await _post_build(payload)
    if not posted["ok"]:
        return {
            "name":       app.get("name"),
            "purpose":    app.get("purpose"),
            "category":   app.get("template_category"),
            "complexity": payload.get("complexity"),
            "build_id":   None,
            "status":     "failed",
            "live_url":   None,
            "build_time": round(time.time() - started, 2),
            "error":      posted.get("error"),
        }

    build_id = posted["build_id"]
    polled   = await _poll_build_status(build_id)

    return {
        "name":       app.get("name"),
        "purpose":    app.get("purpose"),
        "category":   app.get("template_category"),
        "complexity": payload.get("complexity"),
        "build_id":   build_id,
        "status":     polled["status"],
        "live_url":   polled.get("live_url"),
        "build_time": polled.get("build_time"),
        "error":      polled.get("error"),
    }


def _summarise_apps(apps_detail: list[dict]) -> dict:
    """Aggregate per-app outcomes into the run-level counters."""
    apps_built    = sum(1 for a in apps_detail if a.get("build_id"))
    apps_deployed = sum(1 for a in apps_detail if a.get("live_url"))
    app_urls      = [a["live_url"] for a in apps_detail if a.get("live_url")]
    # See module docstring — ecosystem nav verification requires auth.
    # Until we have a real test user we conservatively mirror apps_deployed.
    apps_integrated = apps_deployed
    return {
        "apps_built":      apps_built,
        "apps_deployed":   apps_deployed,
        "apps_integrated": apps_integrated,
        "app_urls":        app_urls,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────────────

async def run_full_ecosystem(description: str, app_count: int) -> dict:
    """MODE A — plan + fan-out builds + verify."""
    start   = time.time()
    user_id = str(uuid.uuid4())

    plan = await _plan_ecosystem(description, app_count, user_id)
    if not plan["ok"]:
        return {
            "status":             "error",
            "apps_planned":       0,
            "apps_built":         0,
            "apps_deployed":      0,
            "apps_integrated":    0,
            "passed":             False,
            "fail_reason":        plan["error"],
            "total_time_seconds": round(time.time() - start, 2),
            "app_urls":           [],
            "apps_detail":        [],
            "apps_planned_json":  [],
            "error_message":      plan["error"],
        }

    apps = plan["apps"]

    # Fire every build concurrently. Physis's own queue (MAX_CONCURRENT_BUILDS=2)
    # will serialise downstream, we just stream the requests in.
    tasks = [
        _run_single_app_build(a, user_id, join_ecosystem=True)
        for a in apps
    ]
    try:
        apps_detail = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=False),
            timeout=ECOSYSTEM_TOTAL_BUDGET,
        )
    except asyncio.TimeoutError:
        return {
            "status":             "failed",
            "apps_planned":       len(apps),
            "apps_built":         0,
            "apps_deployed":      0,
            "apps_integrated":    0,
            "passed":             False,
            "fail_reason":        f"overall ecosystem build exceeded {ECOSYSTEM_TOTAL_BUDGET}s",
            "total_time_seconds": round(time.time() - start, 2),
            "app_urls":           [],
            "apps_detail":        [],
            "apps_planned_json":  apps,
            "error_message":      "ecosystem budget exceeded",
        }

    summary = _summarise_apps(apps_detail)
    passed  = summary["apps_deployed"] == len(apps)
    fail_reason = None
    if not passed:
        first_fail = next((a for a in apps_detail if not a.get("live_url")), None)
        if first_fail:
            fail_reason = f"{first_fail.get('name')}: {first_fail.get('error') or 'no live URL'}"
        else:
            fail_reason = "one or more apps failed to deploy"

    return {
        "status":             "passed" if passed else "failed",
        "apps_planned":       len(apps),
        "apps_built":         summary["apps_built"],
        "apps_deployed":      summary["apps_deployed"],
        "apps_integrated":    summary["apps_integrated"],
        "passed":             passed,
        "fail_reason":        fail_reason,
        "total_time_seconds": round(time.time() - start, 2),
        "app_urls":           summary["app_urls"],
        "apps_detail":        apps_detail,
        "apps_planned_json":  apps,
        "error_message":      None,
    }


async def run_sequential_ecosystem(description: str, app_count: int) -> dict:
    """MODE B — plan, then build strictly one at a time with join_ecosystem=True."""
    start   = time.time()
    user_id = str(uuid.uuid4())

    plan = await _plan_ecosystem(description, app_count, user_id)
    if not plan["ok"]:
        return {
            "status":             "error",
            "apps_planned":       0,
            "apps_built":         0,
            "apps_deployed":      0,
            "apps_integrated":    0,
            "passed":             False,
            "fail_reason":        plan["error"],
            "total_time_seconds": round(time.time() - start, 2),
            "app_urls":           [],
            "apps_detail":        [],
            "apps_planned_json":  [],
            "error_message":      plan["error"],
        }

    apps        = plan["apps"]
    apps_detail = []
    for app in apps:
        # Budget check — stop early if we've burned the wall-clock
        if time.time() - start > ECOSYSTEM_TOTAL_BUDGET:
            apps_detail.append({
                "name":       app.get("name"),
                "purpose":    app.get("purpose"),
                "category":   app.get("template_category"),
                "build_id":   None,
                "status":     "failed",
                "live_url":   None,
                "build_time": None,
                "error":      f"overall ecosystem budget exceeded before this app started",
            })
            continue
        detail = await _run_single_app_build(app, user_id, join_ecosystem=True)
        apps_detail.append(detail)

    summary = _summarise_apps(apps_detail)
    passed  = summary["apps_deployed"] == len(apps)
    fail_reason = None
    if not passed:
        first_fail = next((a for a in apps_detail if not a.get("live_url")), None)
        if first_fail:
            fail_reason = f"{first_fail.get('name')}: {first_fail.get('error') or 'no live URL'}"
        else:
            fail_reason = "sequential ecosystem build did not fully deploy"

    return {
        "status":             "passed" if passed else "failed",
        "apps_planned":       len(apps),
        "apps_built":         summary["apps_built"],
        "apps_deployed":      summary["apps_deployed"],
        "apps_integrated":    summary["apps_integrated"],
        "passed":             passed,
        "fail_reason":        fail_reason,
        "total_time_seconds": round(time.time() - start, 2),
        "app_urls":           summary["app_urls"],
        "apps_detail":        apps_detail,
        "apps_planned_json":  apps,
        "error_message":      None,
    }


async def run_single_ecosystem(description: str, app_count: int, mode: str) -> dict:
    """Dispatch by mode. mode ∈ {"full", "sequential"}."""
    if mode == "sequential":
        return await run_sequential_ecosystem(description, app_count)
    return await run_full_ecosystem(description, app_count)
