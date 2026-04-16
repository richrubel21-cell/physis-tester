import httpx
import json
import time

PHYSIS_BASE_URL = "https://physis.onrender.com"
BUILD_TIMEOUT = 30
STREAM_TIMEOUT = 120

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
    "complexity": "simple",
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
}

async def run_single(description: str) -> dict:
    result = {
        "status": "error",
        "build_time_seconds": None,
        "live_url": None,
        "error_message": None,
        "physis_response": None,
    }

    start = time.time()

    try:
        async with httpx.AsyncClient(timeout=BUILD_TIMEOUT) as client:
            payload = {**BASE_PAYLOAD, "userInput": description}
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
                return result

        # Step 2: Consume the SSE stream
        stream_url = f"{PHYSIS_BASE_URL}/build/{build_id}/stream"
        sse_events = []

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

        except httpx.TimeoutException:
            result["status"] = "failed"
            result["error_message"] = f"Stream timeout after {STREAM_TIMEOUT}s for build {build_id}"
            result["build_time_seconds"] = round(time.time() - start, 2)
            result["physis_response"] = json.dumps(sse_events[-5:]) if sse_events else None
            return result

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

                    if live_url:
                        result["status"] = "passed"
                        result["live_url"] = live_url
                    elif build_status in ("completed", "success", "done", "partial", "started"):
                        result["status"] = "passed"
                    elif build_status in ("failed", "error"):
                        result["status"] = "failed"
                        result["error_message"] = f"Build status: {build_status}. Raw: {status_raw[:300]}"
                    else:
                        result["status"] = "failed"
                        result["error_message"] = f"Build status: {build_status}. Raw: {status_raw[:500]}"

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

    return result
