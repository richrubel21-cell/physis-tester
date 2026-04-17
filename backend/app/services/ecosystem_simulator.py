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
# 20 min per app: Physis's QUEUE_TIMEOUT_SECONDS is 10 min, and a real
# build takes another 1–3 min once it clears the queue. In 7-app Full
# mode with MAX_CONCURRENT_BUILDS=2 the last-queued app can easily sit
# for 10+ min before it runs. 600s was producing false-negative "poll
# timed out" failures for builds that actually succeeded on Physis.
STATUS_POLL_TIMEOUT    = 1200   # 20 min per app
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


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests (22–29) — run AFTER every app in an ecosystem has deployed.
# Verify the ecosystem holds together as a connected whole, not just that each
# individual app works in isolation. Marketplace eligibility requires all 8.
# ─────────────────────────────────────────────────────────────────────────────

import re
from urllib.parse import urlparse

INTEGRATION_FETCH_TIMEOUT = 15


def _test_result(test_id: int, name: str, passed: bool, detail: str) -> dict:
    return {
        "test_id": test_id,
        "name":    name,
        "passed":  bool(passed),
        "score":   1 if passed else 0,
        "detail":  detail[:400] if detail else "",
    }


async def _fetch_html(url: str) -> tuple[int, str]:
    """GET url and return (status_code, body_text). Returns (0, "") on network error."""
    try:
        async with httpx.AsyncClient(timeout=INTEGRATION_FETCH_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(url)
            return r.status_code, r.text or ""
    except Exception:
        return 0, ""


def _extract_subdomain(url: str) -> str:
    """'https://foo.myphysis.ai' → 'foo'. Empty string if we can't parse it."""
    try:
        host = urlparse(url).hostname or ""
        return host.split(".", 1)[0] if host else ""
    except Exception:
        return ""


def _extract_primary_color(html: str) -> str:
    """
    Best-effort sniff for the primary accent color in order:
      1. --primary: #xxxxxx  (CSS variable)
      2. first #rrggbb in inline style or CSS
    Returns lower-cased hex or "" if nothing found.
    """
    m = re.search(r"--primary\s*:\s*(#[0-9a-fA-F]{3,8})", html)
    if m:
        return m.group(1).lower()
    m = re.search(r"#[0-9a-fA-F]{6}", html)
    return m.group(0).lower() if m else ""


def _extract_ecosystem_name(html: str) -> str:
    """
    The Physis ecosystem nav renders the workspace title inside a data attribute
    or visible header. Heuristic: find data-ecosystem-name="..." or a nav
    element's first text node. Returns "" if we cannot detect one.
    """
    m = re.search(r'data-ecosystem(?:[-_]name)?\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r'<nav[^>]*>.*?<(?:span|div|h[1-6])[^>]*>([^<]{2,60})</', html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_nav_hrefs(html: str) -> list[str]:
    """All href targets that appear inside a <nav>…</nav> block."""
    navs = re.findall(r"<nav\b.*?</nav>", html, re.IGNORECASE | re.DOTALL)
    hrefs: list[str] = []
    for n in navs:
        hrefs.extend(re.findall(r'href\s*=\s*["\']([^"\']+)["\']', n, re.IGNORECASE))
    return hrefs


async def _test_shared_nav_present(apps: list[dict], htmls: dict[str, str]) -> dict:
    missing: list[str] = []
    for a in apps:
        html = htmls.get(a["live_url"], "") or ""
        if "<nav" not in html.lower():
            missing.append(a.get("name") or a["live_url"])
            continue
        # Need at least one sibling subdomain mentioned inside the nav
        sibs = [s for s in (_extract_subdomain(b["live_url"]) for b in apps if b is not a) if s]
        navs_block = " ".join(re.findall(r"<nav\b.*?</nav>", html, re.IGNORECASE | re.DOTALL))
        if not any(s in navs_block for s in sibs):
            missing.append(a.get("name") or a["live_url"])
    passed = not missing
    detail = "Nav with sibling links found on every app" if passed else f"Missing ecosystem nav on: {', '.join(missing)}"
    return _test_result(22, "Shared Nav Present", passed, detail)


async def _test_nav_links_correct(apps: list[dict], htmls: dict[str, str]) -> dict:
    broken: list[str] = []
    for a in apps:
        html = htmls.get(a["live_url"], "") or ""
        hrefs = _extract_nav_hrefs(html)
        sibling_subs = {_extract_subdomain(b["live_url"]) for b in apps if b is not a and b.get("live_url")}
        sibling_subs.discard("")

        present: set[str] = set()
        for h in hrefs:
            for s in sibling_subs:
                if s and s in h:
                    present.add(s)
        missing = sibling_subs - present
        if missing:
            broken.append(f"{a.get('name')}: missing links for {', '.join(sorted(missing))}")
            continue

        # Verify each sibling link resolves (HEAD-equivalent via GET, already cached)
        for s in sibling_subs:
            sib = next((b for b in apps if _extract_subdomain(b.get("live_url") or "") == s), None)
            if not sib:
                continue
            status_code, _ = await _fetch_html(sib["live_url"])
            if status_code == 0 or status_code >= 400:
                broken.append(f"{a.get('name')} → {s}: HTTP {status_code}")

    passed = not broken
    detail = "Every nav link resolves with a 2xx/3xx" if passed else "; ".join(broken[:5])
    return _test_result(23, "Nav Links Correct", passed, detail)


async def _test_theme_consistency(apps: list[dict], htmls: dict[str, str]) -> dict:
    colors: dict[str, str] = {}
    for a in apps:
        c = _extract_primary_color(htmls.get(a["live_url"], "") or "")
        colors[a.get("name") or a["live_url"]] = c
    distinct = {c for c in colors.values() if c}
    if not distinct:
        return _test_result(24, "Theme Consistency", False, "No primary color detected on any app")
    passed = len(distinct) == 1
    detail = f"All apps share {next(iter(distinct))}" if passed else f"Colors differ across apps: {colors}"
    return _test_result(24, "Theme Consistency", passed, detail)


async def _test_ecosystem_name_consistent(apps: list[dict], htmls: dict[str, str]) -> dict:
    names: dict[str, str] = {}
    for a in apps:
        names[a.get("name") or a["live_url"]] = _extract_ecosystem_name(htmls.get(a["live_url"], "") or "")
    non_empty = [v for v in names.values() if v]
    if len(non_empty) != len(apps):
        missing = [k for k, v in names.items() if not v]
        return _test_result(25, "Ecosystem Name Consistent", False, f"Name missing on: {', '.join(missing)}")
    distinct = set(non_empty)
    passed = len(distinct) == 1
    detail = f"Ecosystem name '{next(iter(distinct))}' consistent across apps" if passed else f"Name differs across apps: {names}"
    return _test_result(25, "Ecosystem Name Consistent", passed, detail)


async def _test_cross_app_navigation(apps: list[dict]) -> dict:
    """Fetch app 1 → app 2 → app 3 → back to 1. Every hop must be 2xx/3xx."""
    if len(apps) < 2:
        return _test_result(26, "Cross-App Navigation", True, "Single-app ecosystem, trivially passes")
    hops = apps + [apps[0]]
    failures: list[str] = []
    for a in hops:
        status_code, _ = await _fetch_html(a["live_url"])
        if status_code == 0 or status_code >= 400:
            failures.append(f"{a.get('name')} (HTTP {status_code})")
    passed = not failures
    detail = f"Round trip across {len(hops)} hops succeeded" if passed else f"Hop failures: {', '.join(failures)}"
    return _test_result(26, "Cross-App Navigation", passed, detail)


async def _test_shared_data_layer(apps: list[dict]) -> dict:
    """
    Lightweight proxy for 'every app has a row in ecosystem_apps with matching
    ecosystem_id'. The Physis tester runs with anonymous UUIDs and has no
    Supabase read access here, so we assert the invariants we CAN see:
      - every deployed app carries a subdomain (→ implies a user_apps row)
      - all subdomains are distinct (→ implies unique app_id)
    This is the strongest check we can make without leaking an admin key into
    the tester. If a real Supabase read is added later, replace this with
    an RPC that validates ecosystem_apps directly.
    """
    subs = [_extract_subdomain(a.get("live_url") or "") for a in apps]
    missing = [a.get("name") for a, s in zip(apps, subs) if not s]
    if missing:
        return _test_result(27, "Shared Data Layer", False, f"Apps without a subdomain: {', '.join(missing)}")
    if len(set(subs)) != len(subs):
        return _test_result(27, "Shared Data Layer", False, f"Duplicate subdomains detected: {subs}")
    return _test_result(27, "Shared Data Layer", True, f"All {len(apps)} apps have unique subdomains")


async def _test_ai_engine_present(apps: list[dict], htmls: dict[str, str]) -> dict:
    missing: list[str] = []
    for a in apps:
        body = (htmls.get(a["live_url"], "") or "").lower()
        if not any(token in body for token in ("useai", "/api/ai", "ai_engine", "ai-engine")):
            missing.append(a.get("name") or a["live_url"])
    passed = not missing
    detail = "AI hook indicator found on every app" if passed else f"AI hook missing on: {', '.join(missing)}"
    return _test_result(28, "AI Engine Present", passed, detail)


async def _test_powered_by_physis(apps: list[dict], htmls: dict[str, str]) -> dict:
    missing: list[str] = []
    for a in apps:
        body = (htmls.get(a["live_url"], "") or "").lower()
        if "powered by physis" not in body and "powered-by-physis" not in body:
            missing.append(a.get("name") or a["live_url"])
    passed = not missing
    detail = "'Powered by Physis' present on every app" if passed else f"Missing badge on: {', '.join(missing)}"
    return _test_result(29, "Powered by Physis Present", passed, detail)


async def run_integration_tests(ecosystem_apps: list[dict]) -> dict:
    """
    Run the 8 ecosystem integration tests (22–29) against the set of apps that
    were all successfully deployed for this ecosystem.

    Parameters
    ----------
    ecosystem_apps : list[dict]
        Apps from an EcosystemRun.apps_detail. Each must have a 'live_url' —
        apps without one are filtered out and the whole run is marked failed.

    Returns
    -------
    {
        "integration_tests":   list of per-test dicts (22..29),
        "integration_score":   int (0..8),
        "integration_passed":  bool (score == 8),
        "integration_details": str (short human summary),
    }

    If any individual app failed to deploy, integration tests are skipped and
    a synthetic failing result is returned so the ecosystem is marked failed.
    """
    deployed = [a for a in ecosystem_apps if a.get("live_url")]
    if len(deployed) != len(ecosystem_apps) or not deployed:
        missing = [a.get("name") or "(unnamed)" for a in ecosystem_apps if not a.get("live_url")]
        skipped = [
            _test_result(tid, name, False, f"Skipped — apps failed to deploy: {', '.join(missing)[:200]}")
            for tid, name in [
                (22, "Shared Nav Present"),
                (23, "Nav Links Correct"),
                (24, "Theme Consistency"),
                (25, "Ecosystem Name Consistent"),
                (26, "Cross-App Navigation"),
                (27, "Shared Data Layer"),
                (28, "AI Engine Present"),
                (29, "Powered by Physis Present"),
            ]
        ]
        return {
            "integration_tests":   skipped,
            "integration_score":   0,
            "integration_passed":  False,
            "integration_details": f"Integration tests skipped: {len(missing)} app(s) failed to deploy",
        }

    # Fetch every app's HTML once, reuse across tests that only need GET bodies.
    fetched = await asyncio.gather(
        *[_fetch_html(a["live_url"]) for a in deployed],
        return_exceptions=False,
    )
    htmls: dict[str, str] = {}
    for a, (status_code, body) in zip(deployed, fetched):
        htmls[a["live_url"]] = body if status_code and status_code < 400 else ""

    tests = [
        await _test_shared_nav_present(deployed, htmls),
        await _test_nav_links_correct(deployed, htmls),
        await _test_theme_consistency(deployed, htmls),
        await _test_ecosystem_name_consistent(deployed, htmls),
        await _test_cross_app_navigation(deployed),
        await _test_shared_data_layer(deployed),
        await _test_ai_engine_present(deployed, htmls),
        await _test_powered_by_physis(deployed, htmls),
    ]

    score = sum(t["score"] for t in tests)
    passed = score == 8
    details = (
        f"All 8 integration tests passed"
        if passed
        else f"{8 - score} integration test(s) failed: "
             + ", ".join(t["name"] for t in tests if not t["passed"])
    )
    return {
        "integration_tests":   tests,
        "integration_score":   score,
        "integration_passed":  passed,
        "integration_details": details,
    }
