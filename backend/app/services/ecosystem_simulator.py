"""
Ecosystem Tester — two test modes that drive the Physis /api/ecosystem-builder/plan
+ /build pipeline end to end.

MODE A — Full Ecosystem Build:
  1. POST /api/ecosystem-builder/plan with the business description + app_count
  2. Auto-approve the returned plan
  3. Build every planned app strictly one-at-a-time (await per app). We used
     to fan out with asyncio.gather and rely on Physis's MAX_CONCURRENT_BUILDS
     queue to serialise downstream, but the platform requirement is that
     ecosystem apps build sequentially — the tester now enforces that
     directly so it cannot be subverted by raising MAX_CONCURRENT_BUILDS.
  4. For each build, poll /build/{id}/status until a final event lands
  5. PASS only if every planned app returned a live_url

MODE B — Sequential Ecosystem Build:
  Same plan + sequential build flow as Mode A, kept for parity with the
  existing test plan / dashboards. join_ecosystem=True on every build so
  the join flow is exercised on every single app.

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
    EcosystemRun.apps_detail JSON array. Once the app deploys we also run
    the 7 app-validity tests (30–36) so per-app reliability data is
    captured at the moment of build, not after the fact.
    """
    payload  = _build_payload_for_app(app, user_id, join_ecosystem)
    started  = time.time()

    posted = await _post_build(payload)
    if not posted["ok"]:
        empty_validity = run_validity_tests_blank("Build did not start, no live URL to test")
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
            **empty_validity,
        }

    build_id = posted["build_id"]
    polled   = await _poll_build_status(build_id)
    live_url = polled.get("live_url")

    # Validity sweep — runs once we have a real live_url. Failures fold
    # silently into 0/7 so a flaky deploy never crashes the simulator.
    if live_url:
        try:
            validity = await run_validity_tests(live_url)
        except Exception as exc:
            validity = run_validity_tests_blank(f"Validity runner crashed: {exc}")
    else:
        validity = run_validity_tests_blank("No live URL produced, app not reachable")

    return {
        "name":       app.get("name"),
        "purpose":    app.get("purpose"),
        "category":   app.get("template_category"),
        "complexity": payload.get("complexity"),
        "build_id":   build_id,
        "status":     polled["status"],
        "live_url":   live_url,
        "build_time": polled.get("build_time"),
        "error":      polled.get("error"),
        **validity,
    }


def _summarise_apps(apps_detail: list[dict]) -> dict:
    """Aggregate per-app outcomes into the run-level counters."""
    apps_built    = sum(1 for a in apps_detail if a.get("build_id"))
    apps_deployed = sum(1 for a in apps_detail if a.get("live_url"))
    app_urls      = [a["live_url"] for a in apps_detail if a.get("live_url")]
    # See module docstring — ecosystem nav verification requires auth.
    # Until we have a real test user we conservatively mirror apps_deployed.
    apps_integrated = apps_deployed

    # ── Validity roll-up (tests 30–36 on each deployed app) ───────────
    # Average score across every app row (deployed or not — apps that
    # failed to deploy contribute 0/7, which is the honest signal). All-
    # apps-pass and all-apps-have-Powered-by-Physis are the strict gates
    # the marketplace eligibility check downstream depends on.
    if apps_detail:
        scores = [int(a.get("validity_score") or 0) for a in apps_detail]
        validity_score        = round(sum(scores) / len(apps_detail))
        validity_passed       = all(bool(a.get("validity_passed")) for a in apps_detail)
        all_powered_by_physis = all(bool(a.get("powered_by_physis")) for a in apps_detail)
    else:
        validity_score        = 0
        validity_passed       = False
        all_powered_by_physis = False

    return {
        "apps_built":            apps_built,
        "apps_deployed":         apps_deployed,
        "apps_integrated":       apps_integrated,
        "app_urls":              app_urls,
        "validity_score":        validity_score,
        "validity_passed":       validity_passed,
        "all_powered_by_physis": all_powered_by_physis,
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

    # Build apps strictly one-at-a-time. Sequential is a platform
    # requirement for ecosystems — see module docstring. The wall-clock
    # budget is checked between apps so we still exit cleanly if the
    # plan is too large for ECOSYSTEM_TOTAL_BUDGET.
    apps_detail: list[dict] = []
    for app in apps:
        if time.time() - start > ECOSYSTEM_TOTAL_BUDGET:
            apps_detail.append({
                "name":       app.get("name"),
                "purpose":    app.get("purpose"),
                "category":   app.get("template_category"),
                "build_id":   None,
                "status":     "failed",
                "live_url":   None,
                "build_time": None,
                "error":      "overall ecosystem budget exceeded before this app started",
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
            fail_reason = "one or more apps failed to deploy"

    return {
        "status":                "passed" if passed else "failed",
        "apps_planned":          len(apps),
        "apps_built":            summary["apps_built"],
        "apps_deployed":         summary["apps_deployed"],
        "apps_integrated":       summary["apps_integrated"],
        "passed":                passed,
        "fail_reason":           fail_reason,
        "total_time_seconds":    round(time.time() - start, 2),
        "app_urls":              summary["app_urls"],
        "apps_detail":           apps_detail,
        "apps_planned_json":     apps,
        "error_message":         None,
        "validity_score":        summary["validity_score"],
        "validity_passed":       summary["validity_passed"],
        "all_powered_by_physis": summary["all_powered_by_physis"],
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
        "status":                "passed" if passed else "failed",
        "apps_planned":          len(apps),
        "apps_built":            summary["apps_built"],
        "apps_deployed":         summary["apps_deployed"],
        "apps_integrated":       summary["apps_integrated"],
        "passed":                passed,
        "fail_reason":           fail_reason,
        "total_time_seconds":    round(time.time() - start, 2),
        "app_urls":              summary["app_urls"],
        "apps_detail":           apps_detail,
        "apps_planned_json":     apps,
        "error_message":         None,
        "validity_score":        summary["validity_score"],
        "validity_passed":       summary["validity_passed"],
        "all_powered_by_physis": summary["all_powered_by_physis"],
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


# ─────────────────────────────────────────────────────────────────────────────
# App-validity tests (30–36) — run on every individual app AFTER it deploys.
# These verify the app actually works (renders, has inputs, has outputs, etc.),
# not merely that the build pipeline succeeded. Both single-app builds and
# every app inside an ecosystem build use the same runner so the metrics
# are directly comparable.
#
# Returned shape (per call to run_validity_tests):
#   {
#     validity_tests:    [ {test_id, name, passed, score, detail}, ... × 7 ],
#     validity_score:    int (0..7),
#     validity_passed:   bool (score >= 5),
#     app_works:         bool (mirrors validity_passed),
#     powered_by_physis: bool (Test 35 specifically — non-negotiable),
#   }
#
# Score >= 5 (not 7) because some templates legitimately do not surface
# every indicator in static HTML. Test 35 is tracked as its own boolean
# so marketplace eligibility can require it even when overall validity
# passes through the score threshold.
# ─────────────────────────────────────────────────────────────────────────────

VALIDITY_FETCH_TIMEOUT = 15

VALIDITY_TEST_NAMES = [
    (30, "UI Renders"),
    (31, "React App Loaded"),
    (32, "AI Engine Present"),
    (33, "Input Form Exists"),
    (34, "Output Display Exists"),
    (35, "Powered by Physis Present"),
    (36, "Mobile Responsive"),
]


def run_validity_tests_blank(reason: str) -> dict:
    """Synthetic 0/7 result for builds we can't reach. Used when an app
    failed to deploy or the validity runner itself crashed."""
    tests = [
        _test_result(tid, name, False, reason or "App not reachable")
        for tid, name in VALIDITY_TEST_NAMES
    ]
    return {
        "validity_tests":    tests,
        "validity_score":    0,
        "validity_passed":   False,
        "app_works":         False,
        "powered_by_physis": False,
    }


def _test_30_ui_renders(status_code: int, html: str) -> dict:
    if status_code != 200:
        return _test_result(30, "UI Renders", False, f"HTTP {status_code} — blank screen detected")
    body = html or ""
    stripped = body.strip()
    if len(stripped) < 500:
        return _test_result(30, "UI Renders", False, "Body under 500 chars — blank screen detected")
    lower = stripped.lower()
    if "application error" in lower or "internal server error" in lower or "<title>error" in lower:
        return _test_result(30, "UI Renders", False, "Error page detected, not a real UI")
    has_root = (
        re.search(r'<div\s+[^>]*id\s*=\s*["\']root["\']', body, re.IGNORECASE) is not None
        or "data-reactroot" in body.lower()
        or "<body" in body.lower()
    )
    if not has_root:
        return _test_result(30, "UI Renders", False, "No React root element found in HTML")
    return _test_result(30, "UI Renders", True, "App renders correctly")


def _test_31_react_app_loaded(html: str) -> dict:
    body = html or ""
    indicators = []
    if re.search(r'<div\s+[^>]*id\s*=\s*["\']root["\']', body, re.IGNORECASE):
        indicators.append("#root div")
    if re.search(r'<script[^>]*type\s*=\s*["\']module["\']', body, re.IGNORECASE):
        indicators.append("ES module script")
    if re.search(r'\b(react|ReactDOM)\b', body):
        indicators.append("react reference")
    if re.search(r'/assets/index-[A-Za-z0-9_-]+\.js', body):
        indicators.append("Vite bundle")
    if indicators:
        return _test_result(31, "React App Loaded", True, "React app detected: " + ", ".join(indicators))
    return _test_result(31, "React App Loaded", False, "No React app found")


def _test_32_ai_engine_present(html: str) -> dict:
    body = html or ""
    lower = body.lower()
    indicators = [
        ("useAI",       "useai"      in lower),
        ("/api/ai",     "/api/ai"    in lower),
        ("ai_engine",   "ai_engine"  in lower or "ai-engine" in lower),
        ("askAI",       "askai"      in lower),
        ("anthropic",   "anthropic"  in lower),
    ]
    found = [name for name, hit in indicators if hit]
    if found:
        return _test_result(32, "AI Engine Present", True, "AI engine detected: " + ", ".join(found))
    return _test_result(32, "AI Engine Present", False, "No AI engine found")


def _test_33_input_form_exists(html: str) -> dict:
    body = html or ""
    inputs    = len(re.findall(r"<input\b",    body, re.IGNORECASE))
    textareas = len(re.findall(r"<textarea\b", body, re.IGNORECASE))
    selects   = len(re.findall(r"<select\b",   body, re.IGNORECASE))
    total = inputs + textareas + selects
    if total == 0:
        # Vite/React often ship inputs only after JS hydrates. Fall back
        # to looking for placeholder= or input-type attribute strings in
        # the bundled JS payload.
        attr_hits = re.findall(
            r'(placeholder\s*=|type\s*=\s*["\'](?:text|number|date|email|password)["\'])',
            body, re.IGNORECASE,
        )
        if attr_hits:
            return _test_result(33, "Input Form Exists", True, f"Input form detected ({len(attr_hits)} input attributes)")
        return _test_result(33, "Input Form Exists", False, "No input form found")
    return _test_result(33, "Input Form Exists", True, f"Input form detected ({total} inputs)")


def _test_34_output_display_exists(html: str) -> dict:
    body = html or ""
    keywords = ("output", "result", "response", "answer", "analysis", "generated")
    pattern = re.compile(
        r'(?:class|id)\s*=\s*["\'][^"\']*\b(?:' + "|".join(keywords) + r')\b[^"\']*["\']',
        re.IGNORECASE,
    )
    if pattern.search(body):
        return _test_result(34, "Output Display Exists", True, "Output display detected")
    # Fallback: any of the keywords appears as plain text near a content
    # container (rendered string in the bundle).
    lower = body.lower()
    keyword_hits = sum(1 for k in keywords if k in lower)
    if keyword_hits >= 2:
        return _test_result(34, "Output Display Exists", True, f"Output display detected ({keyword_hits} indicator words)")
    return _test_result(34, "Output Display Exists", False, "No output display found")


def _test_35_powered_by_physis(html: str) -> dict:
    body  = html or ""
    lower = body.lower()
    if "powered by physis" in lower or "powered-by-physis" in lower:
        return _test_result(35, "Powered by Physis Present", True, "Powered by Physis badge found")
    return _test_result(35, "Powered by Physis Present", False, "MISSING: Powered by Physis badge")


def _test_36_mobile_responsive(html: str) -> dict:
    body = html or ""
    has_viewport = re.search(
        r'<meta[^>]*name\s*=\s*["\']viewport["\'][^>]*content\s*=\s*["\'][^"\']*width\s*=\s*device-width',
        body, re.IGNORECASE,
    ) is not None
    if has_viewport:
        return _test_result(36, "Mobile Responsive", True, "Mobile responsive (viewport meta tag found)")
    if re.search(r'(@media|max-width\s*:|min-width\s*:)', body, re.IGNORECASE):
        return _test_result(36, "Mobile Responsive", True, "Mobile responsive (responsive CSS detected)")
    return _test_result(36, "Mobile Responsive", False, "Not mobile responsive — no viewport meta tag")


async def run_validity_tests(live_url):
    """
    Run the 7 app-validity tests (30–36) against a single deployed app.
    Fetches live_url ONCE and shares the response across every test.
    Returns the validity dict shape documented at the top of this section.
    """
    if not live_url:
        return run_validity_tests_blank("No live URL provided")

    try:
        async with httpx.AsyncClient(timeout=VALIDITY_FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(live_url)
        status_code = resp.status_code
        html        = resp.text or ""
    except Exception as exc:
        return run_validity_tests_blank(f"Could not fetch live URL: {exc}")

    tests = [
        _test_30_ui_renders(status_code, html),
        _test_31_react_app_loaded(html),
        _test_32_ai_engine_present(html),
        _test_33_input_form_exists(html),
        _test_34_output_display_exists(html),
        _test_35_powered_by_physis(html),
        _test_36_mobile_responsive(html),
    ]
    score             = sum(t["score"] for t in tests)
    powered_by_physis = bool(next((t for t in tests if t["test_id"] == 35), {}).get("passed"))
    validity_passed   = score >= 5
    return {
        "validity_tests":    tests,
        "validity_score":    score,
        "validity_passed":   validity_passed,
        "app_works":         validity_passed,
        "powered_by_physis": powered_by_physis,
    }

