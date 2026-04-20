import httpx
import json
import random
import time

# Direct print() for all log lines — Python's logging module silently
# drops records when no handler is attached anywhere in the logger
# hierarchy, which is the default state under uvicorn for application
# loggers. print(..., flush=True) goes straight to stdout so Render's
# Live Tail catches every line without any logging.basicConfig
# arrangement (PYTHONUNBUFFERED=1 is set in the Dockerfile, but
# explicit flush belt-and-suspenders against env-var changes).

# Validity sweep — same 7 tests we run on every ecosystem app, now run on
# every single-app build too once a live_url is available. Imported lazily
# inside run_single() to avoid touching the import path if anything in
# ecosystem_simulator breaks at import time.

PHYSIS_BASE_URL = "https://physis.onrender.com"
BUILD_TIMEOUT = 30
STREAM_TIMEOUT = 120

# Complexity is picked at call time per build so a single batch exercises
# Physis's simple / medium / advanced code paths. Matches the Physis
# BuildRequest contract and the complexity values scenario_generator uses.
COMPLEXITY_OPTIONS = ["simple", "medium", "advanced"]

BASE_PAYLOAD = {
    # Required BuildRequest fields — still sent as defaults because the
    # Pydantic model on the Physis side validates min_length >= 1. The
    # questionnaire's new auto-inference steps don't ask the user for
    # these anymore, but the API contract still requires them.
    "generates": "web app",
    "targetUser": "General users",
    "outputFormat": "web application",
    "outputLength": "full",
    "specialRules": "none",
    "interactionStyle": "simple and intuitive",
    "usageFrequency": "daily",
    "toneStyle": "friendly",
    "themeColor": "blue",
    "successMeasure": "user can complete the main task easily",
    "selectedName": "",
    "selectedTagline": "",
    "selectedSubdomain": "",

    # New questionnaire-flow fields introduced in the Patent #18–#20 sweep.
    #
    # preferred_name — Mary's opening question: "What would you like me to
    #   call you?". Sent under both the plain key (as spec'd) and
    #   user_preferred_name (the canonical BuildRequest field name) so the
    #   answer survives Pydantic validation either way.
    # io_skipped / input_fields / output_fields — skip the visual IO Builder
    #   step and let Physis infer fields from the description.
    # teach_ai_skipped / teach_ai_summary — always skip the Teach Your AI
    #   upload step; simulated runs carry no personal context.
    # join_ecosystem — always decline the ecosystem opt-in (only asked to
    #   returning builders with 2+ apps; simulator is always a first build).
    "preferred_name":      "Tester",
    "user_preferred_name": "Tester",
    "io_skipped":          True,
    "input_fields":        [],
    "output_fields":       [],
    "teach_ai_skipped":    True,
    "teach_ai_summary":    "",
    "join_ecosystem":      False,

    # T&C is enforced server-side on /build (security hardening — the
    # checkbox in the real questionnaire UI is just a UI gate; the
    # backend rejects with 400 if terms_accepted isn't True). The tester
    # is an internal test harness running against a staging-equivalent
    # endpoint, so it auto-accepts on every simulated build. Both the
    # single-app run_single() and ecosystem _build_payload_for_app()
    # spread BASE_PAYLOAD into their POST body, so this single source
    # of truth covers both pipelines.
    "terms_accepted":      True,
}

async def run_single(description: str) -> dict:
    result = {
        "status": "error",
        "build_time_seconds": None,
        "live_url": None,
        "error_message": None,
        "physis_response": None,
        # Proof score (tests_passed) read off the SSE final event or the
        # /status response. 0 means "not captured" — Promote-to-Template
        # gates on >= 18 so an unset proof_score keeps the button hidden.
        "proof_score":        0,
        # Validity defaults — overwritten by the validity sweep below if
        # the build returns a live_url. Kept on every result so update_run
        # can persist them without conditional checks.
        "validity_score":     0,
        "validity_passed":    False,
        "validity_tests":     None,
        "app_works":          False,
        "powered_by_physis":  False,
    }

    start = time.time()
    desc_preview = (description or "").strip().replace("\n", " ")[:80]
    print(f"[simulator] [build] start scenario: {desc_preview!r}", flush=True)

    try:
        async with httpx.AsyncClient(timeout=BUILD_TIMEOUT) as client:
            payload = {
                **BASE_PAYLOAD,
                "userInput":  description,
                "complexity": random.choice(COMPLEXITY_OPTIONS),
            }
            response = await client.post(
                f"{PHYSIS_BASE_URL}/build",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 422:
                result["status"] = "failed"
                result["error_message"] = f"Validation error (422): {response.text[:500]}"
                result["build_time_seconds"] = round(time.time() - start, 2)
                return result

            if response.status_code != 200:
                result["status"] = "failed"
                result["error_message"] = f"HTTP {response.status_code} on POST /build: {response.text[:300]}"
                result["build_time_seconds"] = round(time.time() - start, 2)
                return result

            try:
                build_data = response.json()
                build_id = (
                    build_data.get("build_id")
                    or build_data.get("id")
                    or build_data.get("buildId")
                )
            except Exception:
                build_id = None

            if not build_id:
                result["status"] = "failed"
                result["error_message"] = f"POST /build returned 200 but no build_id found. Response: {response.text[:300]}"
                result["build_time_seconds"] = round(time.time() - start, 2)
                print(f"[simulator] [build] {desc_preview!r} — no build_id returned", flush=True)
                return result

        print(f"[simulator] [build] {desc_preview!r} — build_id={build_id}", flush=True)

        # Step 2: Consume the SSE stream
        stream_url = f"{PHYSIS_BASE_URL}/build/{build_id}/stream"
        sse_events = []
        # Track the last stage_number we logged so we emit one INFO
        # line per stage TRANSITION instead of one per SSE event
        # (Physis emits multiple events per stage — start, status,
        # final). With 8 stages this is at most 8 log lines per build.
        last_stage_logged = None

        try:
            timeout = httpx.Timeout(10.0, read=STREAM_TIMEOUT)
            async with httpx.AsyncClient(timeout=timeout) as stream_client:
                async with stream_client.stream("GET", stream_url) as stream:
                    async for line in stream.aiter_lines():
                        if not line.strip():
                            continue
                        if line.startswith("data:"):
                            raw = line[5:].strip()
                            sse_events.append(raw)
                            try:
                                ev = json.loads(raw)
                            except Exception:
                                continue
                            if not isinstance(ev, dict):
                                continue
                            stage_num  = ev.get("stage_number")
                            stage_name = ev.get("stage")
                            if stage_num is not None and stage_num != last_stage_logged:
                                last_stage_logged = stage_num
                                print(
                                    f"[simulator] [build] {build_id} — stage {stage_num}/"
                                    f"{ev.get('total_stages') or '?'}: {stage_name or '(unknown)'}",
                                    flush=True,
                                )

        except httpx.TimeoutException:
            result["status"] = "failed"
            result["error_message"] = f"Stream timeout after {STREAM_TIMEOUT}s for build {build_id}"
            result["build_time_seconds"] = round(time.time() - start, 2)
            result["physis_response"] = json.dumps(sse_events[-5:]) if sse_events else None
            return result

        # Walk the SSE events newest-first looking for the final stage
        # event Physis emits (it carries tests_passed / tests_total). The
        # first one we find with tests_passed wins; this becomes the
        # Promote-to-Template proof_score gate.
        for raw in reversed(sse_events):
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            if not isinstance(ev, dict):
                continue
            tp = ev.get("tests_passed")
            if isinstance(tp, int) and tp > 0:
                result["proof_score"] = tp
                break

        # Step 3: Poll /status for the final result
        status_url = f"{PHYSIS_BASE_URL}/build/{build_id}/status"
        try:
            async with httpx.AsyncClient(timeout=15) as status_client:
                status_response = await status_client.get(status_url)
                status_raw = status_response.text
                result["physis_response"] = status_raw[:5000]

                try:
                    status_data = status_response.json()
                    live_url = (
                        status_data.get("live_url")
                        or status_data.get("url")
                        or status_data.get("deployed_url")
                        or status_data.get("deployment_url")
                        or status_data.get("site_url")
                        or status_data.get("app_url")
                        or status_data.get("subdomain")
                    )

                    build_status = (
                        status_data.get("status")
                        or status_data.get("state")
                        or status_data.get("build_status")
                    )

                    elapsed = round(time.time() - start, 2)
                    result["build_time_seconds"] = elapsed

                    # Fallback proof_score capture from /status — the SSE
                    # walk above is the primary source, but if the stream
                    # was cut short the final event lives on /status as
                    # last_event with the same tests_passed shape.
                    if not result.get("proof_score"):
                        last_ev = status_data.get("last_event") or {}
                        tp = last_ev.get("tests_passed") if isinstance(last_ev, dict) else None
                        if isinstance(tp, int) and tp > 0:
                            result["proof_score"] = tp

                    # Capture last_event + the new non-PII error_type
                    # field that physis surfaces on every final SSE
                    # event. last_event is persisted as a JSON string so
                    # the dashboard can show the structured failure
                    # without re-parsing error_message.
                    last_ev = status_data.get("last_event") or {}
                    if isinstance(last_ev, dict):
                        result["last_event"] = json.dumps(last_ev)
                        et = last_ev.get("error_type")
                        if isinstance(et, str) and et.strip():
                            result["error_type"] = et

                    if live_url:
                        result["status"] = "passed"
                        result["live_url"] = live_url
                    elif build_status in ("completed", "success", "done", "partial", "started"):
                        result["status"] = "passed"
                    elif build_status in ("failed", "error"):
                        result["status"] = "failed"
                        # Truncation bumped 300→1500 chars so the
                        # error_type field at the end of last_event
                        # survives the cut. Anything bigger is in
                        # physis_response (5000-char window above).
                        result["error_message"] = f"Build status: {build_status}. Raw: {status_raw[:1500]}"
                    else:
                        result["status"] = "failed"
                        result["error_message"] = f"Build status: {build_status}. Raw: {status_raw[:1500]}"

                except json.JSONDecodeError:
                    result["status"] = "failed"
                    result["error_message"] = f"Status endpoint returned non-JSON: {status_raw[:300]}"
                    result["build_time_seconds"] = round(time.time() - start, 2)

        except Exception as e:
            result["status"] = "failed"
            result["error_message"] = f"Status check failed: {str(e)}"
            result["build_time_seconds"] = round(time.time() - start, 2)

    except httpx.ConnectError:
        result["status"] = "error"
        result["error_message"] = "Cannot connect to physis.onrender.com — backend may be down or sleeping"
        result["build_time_seconds"] = round(time.time() - start, 2)

    except Exception as e:
        result["status"] = "error"
        result["error_message"] = f"Unexpected error: {str(e)}"
        result["build_time_seconds"] = round(time.time() - start, 2)

    # Validity sweep (tests 30–36). Runs on every build that produced a
    # live_url. Phase B (Batch #22 follow-up): the validity sweep now
    # GATES the run's overall status — a deploy that landed a live URL
    # but failed the validity sweep is no longer counted as "passed",
    # because that's exactly the situation that produced the Run #58
    # vs Batch #22 mismatch ("APP BROKEN 0/7" inside a 5/5-passed
    # batch). Yes this lowers historical pass rates; that's the point.
    if result.get("live_url"):
        try:
            from .ecosystem_simulator import run_validity_tests
            validity = await run_validity_tests(result["live_url"])
        except Exception as exc:
            try:
                from .ecosystem_simulator import run_validity_tests_blank
                validity = run_validity_tests_blank(f"Validity runner crashed: {exc}")
            except Exception:
                validity = None
        if validity:
            result["validity_score"]    = int(validity.get("validity_score") or 0)
            result["validity_passed"]   = bool(validity.get("validity_passed"))
            # validity_tests is stored as a JSON string so the Run.validity_tests
            # Text column receives a directly persistable value.
            result["validity_tests"]    = json.dumps(validity.get("validity_tests") or [])
            result["app_works"]         = bool(validity.get("app_works"))
            result["powered_by_physis"] = bool(validity.get("powered_by_physis"))

        # Phase B gate — runs only when status was "passed" coming in
        # (i.e. the build actually produced a live_url). validity_passed
        # absent or False downgrades. Deploy-failed runs are unaffected.
        if result.get("status") == "passed" and not result.get("validity_passed"):
            result["status"] = "failed"
            score = result.get("validity_score") or 0
            result["error_message"] = (
                f"Validity sweep failed (score {score}/7 — see validity_tests for details)"
            )

    # Final outcome log line — INFO on pass, ERROR on failure. duration
    # is already set on the result dict in every code path.
    final_status = result.get("status") or "unknown"
    final_dur    = result.get("build_time_seconds") or 0.0
    if final_status == "passed":
        print(
            f"[simulator] [build] {desc_preview!r} — PASSED in {final_dur:.1f}s "
            f"(live_url={result.get('live_url')})",
            flush=True,
        )
    else:
        err = (result.get("error_message") or "(no error message)")[:160]
        print(
            f"[simulator] [build] {desc_preview!r} — {final_status.upper()} "
            f"in {final_dur:.1f}s ({err})",
            flush=True,
        )

    return result
