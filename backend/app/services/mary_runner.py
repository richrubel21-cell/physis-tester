"""
services/mary_runner.py
------------------------
Mary testing service for the Physis Tester.
Fires canned prompts at POST /mary on physis.onrender.com,
scores each response, and returns structured results.
Called by routes/mary.py.
"""

import httpx
import re
import time
from datetime import datetime, timezone

PHYSIS_BASE_URL = "https://physis.onrender.com"
MARY_TIMEOUT = 20

MARY_SYSTEM_PROMPT = (
    "You are Mary, the friendly AI guide for Physis — an AI factory that builds custom AI web tools "
    "from plain English descriptions. You appear as a gold and purple monarch butterfly. "
    "You are warm, encouraging, and concise. You help users understand what to do on each screen. "
    "You never use markdown, bullet points, or code blocks in your responses — only plain conversational sentences. "
    "Keep responses under 3 sentences. Always stay in character as Mary the butterfly guide."
)

# Canned prompts per screen context.
# Each entry: (screen, prompt, required_keywords)
# required_keywords: at least one must appear in the response to pass context check.
MARY_TEST_CASES = [
    (
        "welcome",
        "Hi Mary, what is this place and what can I do here?",
        ["build", "tool", "create", "ai", "physis", "describe", "idea"],
    ),
    (
        "questionnaire",
        "What am I supposed to do on this page?",
        ["question", "describe", "answer", "tell", "fill", "build", "tool", "idea"],
    ),
    (
        "naming",
        "How do I pick a good name for my tool?",
        ["name", "brand", "choose", "pick", "call", "tool"],
    ),
    (
        "building",
        "What is happening right now while I wait?",
        ["build", "generat", "deploy", "creat", "working", "almost", "moment", "ready"],
    ),
    (
        "complete",
        "My tool is live — what should I do next?",
        ["try", "share", "use", "live", "visit", "link", "open", "tool"],
    ),
]


def _has_markdown(text: str) -> bool:
    """Detect markdown or code that would sound bad when spoken aloud."""
    patterns = [
        r"```",
        r"^\s*[-*]\s",
        r"^\s*\d+\.\s",
        r"\*\*",
        r"#{1,6}\s",
        r"\[.+\]\(.+\)",
    ]
    for pat in patterns:
        if re.search(pat, text, re.MULTILINE):
            return True
    return False


def _check_context(response_text: str, keywords: list) -> bool:
    """Check if response references the correct screen context."""
    lower = response_text.lower()
    return any(kw.lower() in lower for kw in keywords)


def _score_response(response_text: str, keywords: list) -> dict:
    """
    Score a single Mary response on 4 criteria.
    Returns individual scores and overall pass/fail.
    """
    responded_ok = bool(response_text and len(response_text.strip()) > 10)
    speakable_ok = responded_ok and not _has_markdown(response_text)
    context_ok   = responded_ok and _check_context(response_text, keywords)

    persona_words = [
        "i", "you", "your", "help", "here", "can", "will",
        "let", "ready", "glad", "welcome", "exciting", "wonderful",
        "great", "love", "happy", "butterfly", "mary", "physis",
    ]
    persona_ok = responded_ok and any(w in response_text.lower() for w in persona_words)

    score        = sum([responded_ok, speakable_ok, context_ok, persona_ok])
    overall_pass = score >= 3  # must pass at least 3 of 4

    return {
        "responded_ok": responded_ok,
        "speakable_ok": speakable_ok,
        "context_ok":   context_ok,
        "persona_ok":   persona_ok,
        "score":        score,
        "overall_pass": overall_pass,
    }


async def run_mary_batch() -> dict:
    """
    Run all Mary test cases and return a structured result dict.
    Called by routes/mary.py POST /mary/batch.
    """
    results = []
    passed  = 0
    failed  = 0
    start   = time.time()

    for screen, prompt, keywords in MARY_TEST_CASES:
        case_start  = time.time()
        case_result = {
            "screen":                screen,
            "prompt":                prompt,
            "response_text":         None,
            "responded_ok":          False,
            "speakable_ok":          False,
            "context_ok":            False,
            "persona_ok":            False,
            "score":                 0,
            "overall_pass":          False,
            "error_message":         None,
            "response_time_seconds": None,
        }

        try:
            async with httpx.AsyncClient(timeout=MARY_TIMEOUT) as client:
                response = await client.post(
                    f"{PHYSIS_BASE_URL}/mary",
                    json={
                        "question": prompt,
                        "screen":   screen,
                        "system":   MARY_SYSTEM_PROMPT,
                        "history":  [],
                    },
                    headers={"Content-Type": "application/json"},
                )

            case_result["response_time_seconds"] = round(time.time() - case_start, 2)

            if response.status_code != 200:
                case_result["error_message"] = f"HTTP {response.status_code}: {response.text[:200]}"
                failed += 1
                results.append(case_result)
                continue

            data          = response.json()
            response_text = (data.get("answer") or "").strip()
            case_result["response_text"] = response_text

            scores = _score_response(response_text, keywords)
            case_result.update(scores)

            if case_result["overall_pass"]:
                passed += 1
            else:
                failed += 1
                if not scores["responded_ok"]:
                    case_result["error_message"] = "Mary returned an empty response."
                elif not scores["speakable_ok"]:
                    case_result["error_message"] = "Response contains markdown — not speakable."
                elif not scores["context_ok"]:
                    case_result["error_message"] = f"Response did not reference screen context ({screen})."
                elif not scores["persona_ok"]:
                    case_result["error_message"] = "Response did not sound like Mary (no persona markers)."

        except httpx.TimeoutException:
            case_result["error_message"]         = f"Mary did not respond within {MARY_TIMEOUT}s."
            case_result["response_time_seconds"] = round(time.time() - case_start, 2)
            failed += 1
        except Exception as e:
            case_result["error_message"]         = f"Unexpected error: {str(e)}"
            case_result["response_time_seconds"] = round(time.time() - case_start, 2)
            failed += 1

        results.append(case_result)

    total_time = round(time.time() - start, 2)
    pass_rate  = round((passed / len(MARY_TEST_CASES)) * 100) if MARY_TEST_CASES else 0

    return {
        "total":               len(MARY_TEST_CASES),
        "passed":              passed,
        "failed":              failed,
        "pass_rate":           pass_rate,
        "total_time_seconds":  total_time,
        "results":             results,
        "tested_at":           datetime.now(timezone.utc).isoformat(),
    }
