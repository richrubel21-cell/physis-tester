import httpx
import json
import time

PHYSIS_BASE_URL = "https://physis.onrender.com"
BUILD_TIMEOUT = 30    # POST /build should respond quickly with a build_id
STREAM_TIMEOUT = 120  # SSE stream can take up to 90s

# Realistic simulated user persona sent with every build request.
# These map to the BuildRequest schema fields seen in /docs.
# userInput is the only field that varies per scenario.
BASE_PAYLOAD = {
    "generates": "web app",
    "targetUser": "general user",
    "outputFormat": "web application",
    "outputLength": "full",
    "specialRules": "",
    "interactionStyle": "simple and intuitive",
    "usageFrequency": "daily",
    "toneStyle": "friendly",
    "themeColor": "blue",
    "complexity": "medium",
    "selectedName": "",
    "selectedTagline": "",
    "selectedSubdomain": "",
}

async def run_single(description: str) -> dict:
    """
    Full Physis build flow:
      1. POST /build  → get build_id
      2. GET  /build/{build_id}/stream  → consume SSE until done, capture live_url
    """
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
            # ── Step 1: Create the build ──────────────────────────
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

            # Extract build_id from response
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
                # Some builds return {} and embed ID in headers or stream
                result["status"] = "failed"
                result["error_message"] = f"POST /build returned 200 but no build_id found. Response: {response.text[:300]}"
                result["build_time_seconds"] = round(time.time() - start, 2)
                return result

        # ── Step 2: Stream the build result ───────────────────────
        stream_url = f"{PHYSIS_BASE_URL}/build/{build_id}/stream"
        sse_events = []
        live_url = None
        stream_error = None

        try:
            timeout = httpx.Timeout(10.0, read=STREAM_TIMEOUT)
            async with httpx.AsyncClient(timeout=timeout) as stream_client:
                async with stream_client.stream("GET", stream_url) as stream:
                    async for line in stream.aiter_lines():
                        if not line.strip():
                            continue

                        # SSE lines start with "data: "
                        if line.startswith("data:"):
                            raw = line[5:].strip()
                            sse_events.append(raw)
                            try:
                                event = json.loads(raw)
                                # Look for live_url in any event
                                live_url = (
                                    live_url
                                    or event.get("live_url")
                                    or event.get("url")
                                    or event.get("deployed_url")
                                    or event.get("deployment_url")
                                )
                                # Detect terminal error events
                                if event.get("type") == "error" or event.get("error"):
                                    stream_error = event.get("error") or event.get("message") or "Build error in stream"
                            except json.JSONDecodeError:
                                pass  # non-JSON SSE line, skip

        except httpx.TimeoutException:
            result["status"] = "failed"
            result["error_message"] = f"Stream timeout after {STREAM_TIMEOUT}s for build {build_id}"
            result["build_time_seconds"] = round(time.time() - start, 2)
            result["physis_response"] = json.dumps(sse_events[-5:]) if sse_events else None
            return result

        # ── Evaluate result ───────────────────────────────────────
        elapsed = round(time.time() - start, 2)
        result["build_time_seconds"] = elapsed
        result["physis_response"] = json.dumps(sse_events[-10:])[:5000]  # last 10 events, capped

        if stream_error:
            result["status"] = "failed"
            result["error_message"] = stream_error
        elif live_url:
            result["status"] = "passed"
            result["live_url"] = live_url
        else:
            # Stream completed but no live_url — treat as failed
            result["status"] = "failed"
            result["error_message"] = "Build stream completed but no live_url was returned"

    except httpx.ConnectError:
        result["status"] = "error"
        result["error_message"] = "Cannot connect to physis.onrender.com — backend may be down or sleeping"
        result["build_time_seconds"] = round(time.time() - start, 2)

    except Exception as e:
        result["status"] = "error"
        result["error_message"] = f"Unexpected error: {str(e)}"
        result["build_time_seconds"] = round(time.time() - start, 2)

    return result
