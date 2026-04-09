"""
services/mary_runner.py
------------------------
Mary testing service for the Physis Tester.
Generates AI-varied prompts, fires them at POST /mary on physis.onrender.com,
scores each response on 7 criteria, and stores results in Supabase via SQLAlchemy.
Called by routes/mary.py.
"""

import httpx
import re
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from ..models import MaryBatch, MaryRun
from .mary_prompt_generator import generate_mary_prompts

PHYSIS_BASE_URL = "https://physis.onrender.com"
MARY_TIMEOUT    = 20

MARY_SYSTEM_PROMPT = (
    "You are Mary, the friendly AI guide for Physis — an AI factory that builds custom AI web tools "
    "from plain English descriptions. You appear as a gold and purple monarch butterfly. "
    "You are warm, encouraging, and concise. You help users understand what to do on each screen. "
    "You never use markdown, bullet points, or code blocks in your responses — only plain conversational sentences. "
    "Keep responses under 3 sentences. Always stay in character as Mary the butterfly guide."
)

SCREEN_KEYWORDS = {
    "welcome":       ["build", "tool", "create", "ai", "physis", "describe", "idea", "make", "start", "factory"],
    "questionnaire": ["question", "describe", "answer", "tell", "fill", "build", "tool", "idea", "detail", "step"],
    "naming":        ["name", "brand", "choose", "pick", "call", "tool", "url", "subdomain", "identity"],
    "building":      ["build", "generat", "deploy", "creat", "working", "almost", "moment", "ready", "test", "code"],
    "complete":      ["try", "share", "use", "live", "visit", "link", "open", "tool", "built", "done", "ready"],
}

HELPFUL_WORDS = [
    "you can", "try", "consider", "recommend", "suggest", "for example",
    "tip", "go ahead", "feel free", "happy to", "let me",
    "start by", "next step", "first step", "simply", "just describe",
]

WARM_WORDS = [
    "wonderful", "great", "love", "excited", "happy", "glad", "welcome",
    "absolutely", "certainly", "of course", "pleasure", "delight",
    "fantastic", "amazing", "perfect", "brilliant", "beautiful",
    "warm", "here for you", "got you", "with you",
]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _has_markdown(text: str) -> bool:
    patterns = [r"```", r"^\s*[-*]\s", r"^\s*\d+\.\s", r"\*\*", r"#{1,6}\s", r"\[.+\]\(.+\)"]
    for pat in patterns:
        if re.search(pat, text, re.MULTILINE):
            return True
    return False


def _check_context(response_text: str, screen: str) -> bool:
    keywords = SCREEN_KEYWORDS.get(screen, [])
    lower = response_text.lower()
    return any(kw.lower() in lower for kw in keywords)


def _check_length(response_text: str) -> bool:
    """Response should be 20-150 words — not too terse, not a wall of text."""
    words = response_text.split()
    return 20 <= len(words) <= 150


def _check_helpful(response_text: str) -> bool:
    """Contains at least one actionable or guidance word."""
    lower = response_text.lower()
    return any(w in lower for w in HELPFUL_WORDS)


def _check_tone(response_text: str) -> bool:
    """Contains warm/encouraging language or clear persona markers."""
    lower = response_text.lower()
    persona_phrases = [
        "i am", "i'm", "i can", "i will", "i'd", "i'll",
        "you can", "you're", "you are", "your tool", "your idea",
        "help you", "here to help", "here for you",
        "glad to", "happy to", "let me",
        "mary", "physis", "butterfly",
    ]
    has_persona = any(phrase in lower for phrase in persona_phrases)
    has_warmth  = any(w in lower for w in WARM_WORDS)
    return has_persona or has_warmth


def _score_response(response_text: str, screen: str) -> dict:
    """
    Score a Mary response on 7 criteria.
    Pass threshold: >= 5 of 7.
    """
    responded_ok = bool(response_text and len(response_text.strip()) > 10)
    speakable_ok = responded_ok and not _has_markdown(response_text)
    context_ok   = responded_ok and _check_context(response_text, screen)
    persona_ok   = responded_ok and any(
        w in response_text.lower()
        for w in ["i", "you", "your", "help", "here", "mary", "physis"]
    )
    length_ok    = responded_ok and _check_length(response_text)
    helpful_ok   = responded_ok and _check_helpful(response_text)
    tone_ok      = responded_ok and _check_tone(response_text)

    score        = sum([responded_ok, speakable_ok, context_ok, persona_ok,
                        length_ok, helpful_ok, tone_ok])
    overall_pass = score >= 5   # must pass at least 5 of 7

    return {
        "responded_ok": responded_ok,
        "speakable_ok": speakable_ok,
        "context_ok":   context_ok,
        "persona_ok":   persona_ok,
        "length_ok":    length_ok,
        "helpful_ok":   helpful_ok,
        "tone_ok":      tone_ok,
        "score":        score,
        "overall_pass": overall_pass,
    }


def _build_failure_reason(scores: dict, screen: str) -> str:
    if not scores["responded_ok"]:  return "Mary returned an empty response."
    if not scores["speakable_ok"]:  return "Response contains markdown — not speakable."
    if not scores["length_ok"]:     return "Response too short or too long for conversational use."
    if not scores["context_ok"]:    return f"Response did not reference screen context ({screen})."
    if not scores["helpful_ok"]:    return "Response contained no actionable guidance."
    if not scores["tone_ok"]:       return "Response lacked warm or encouraging tone."
    if not scores["persona_ok"]:    return "Response did not sound like Mary."
    return "Response did not meet pass threshold (5/7 criteria)."


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def create_mary_batch(db: Session, total: int, use_ai: bool) -> MaryBatch:
    batch = MaryBatch(status="running", total=total, use_ai=use_ai)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def create_mary_run(db: Session, batch_id: int, prompt_data: dict) -> MaryRun:
    run = MaryRun(
        batch_id    = batch_id,
        screen      = prompt_data["screen"],
        prompt      = prompt_data["prompt"],
        prompt_type = prompt_data.get("prompt_type", "general"),
        source      = prompt_data.get("source", "seed"),
        status      = "pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def update_mary_run(db: Session, run: MaryRun, scores: dict,
                    response_text: str, error_message: str,
                    response_time: float) -> None:
    run.response_text         = response_text
    run.responded_ok          = scores.get("responded_ok", False)
    run.speakable_ok          = scores.get("speakable_ok", False)
    run.context_ok            = scores.get("context_ok", False)
    run.persona_ok            = scores.get("persona_ok", False)
    run.length_ok             = scores.get("length_ok", False)
    run.helpful_ok            = scores.get("helpful_ok", False)
    run.tone_ok               = scores.get("tone_ok", False)
    run.score                 = scores.get("score", 0)
    run.overall_pass          = scores.get("overall_pass", False)
    run.error_message         = error_message
    run.response_time_seconds = response_time
    run.status                = "passed" if scores.get("overall_pass") else "failed"
    run.finished_at           = datetime.now(timezone.utc)
    db.commit()


def finalize_mary_batch(db: Session, batch: MaryBatch,
                        passed: int, failed: int) -> None:
    total           = passed + failed
    batch.passed    = passed
    batch.failed    = failed
    batch.completed = total
    batch.pass_rate = round((passed / total * 100) if total > 0 else 0, 1)
    batch.status    = "completed"
    batch.finished_at = datetime.now(timezone.utc)
    db.commit()


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_mary_batch(db: Session, batch_id: int,
                         prompts: list) -> None:
    """
    Run all Mary prompts for a batch. Stores each result in DB as it completes.
    Called as a background task by routes/mary.py.
    """
    batch  = db.query(MaryBatch).filter(MaryBatch.id == batch_id).first()
    passed = 0
    failed = 0

    for prompt_data in prompts:
        run        = create_mary_run(db, batch_id, prompt_data)
        case_start = time.time()

        response_text = ""
        error_message = None
        scores        = {
            "responded_ok": False, "speakable_ok": False,
            "context_ok":   False, "persona_ok":   False,
            "length_ok":    False, "helpful_ok":   False,
            "tone_ok":      False, "score":        0,
            "overall_pass": False,
        }
        response_time = 0.0

        try:
            async with httpx.AsyncClient(timeout=MARY_TIMEOUT) as client:
                response = await client.post(
                    f"{PHYSIS_BASE_URL}/mary",
                    json={
                        "question": prompt_data["prompt"],
                        "screen":   prompt_data["screen"],
                        "system":   MARY_SYSTEM_PROMPT,
                        "history":  [],
                    },
                    headers={"Content-Type": "application/json"},
                )

            response_time = round(time.time() - case_start, 2)

            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200]}"
                failed += 1
            else:
                data          = response.json()
                response_text = (data.get("answer") or "").strip()
                scores        = _score_response(response_text, prompt_data["screen"])
                if scores["overall_pass"]:
                    passed += 1
                else:
                    failed += 1
                    error_message = _build_failure_reason(scores, prompt_data["screen"])

        except httpx.TimeoutException:
            response_time = round(time.time() - case_start, 2)
            error_message = f"Mary did not respond within {MARY_TIMEOUT}s."
            failed += 1
        except Exception as e:
            response_time = round(time.time() - case_start, 2)
            error_message = f"Unexpected error: {str(e)}"
            failed += 1

        update_mary_run(db, run, scores, response_text, error_message, response_time)

        # Update batch progress live after each run
        batch.completed = passed + failed
        batch.passed    = passed
        batch.failed    = failed
        db.commit()

    finalize_mary_batch(db, batch, passed, failed)
