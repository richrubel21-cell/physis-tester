"""
routes/mary.py
--------------
FastAPI routes for Mary testing vertical in Physis Tester.
Fires canned prompts at POST /mary on physis.onrender.com,
scores each response, and returns structured results.
"""

from fastapi import APIRouter, HTTPException
from ..services.mary_runner import run_mary_batch

router = APIRouter(prefix="/mary", tags=["mary"])


@router.post("/batch")
async def start_mary_batch():
    """
    Run a Mary test batch — fires 5 canned prompts at the Mary endpoint,
    scores each response for accuracy, persona, and speakability.
    Returns results immediately (~20 seconds total — no polling needed).
    """
    try:
        result = await run_mary_batch()
        return {
            "batch_type":          "mary",
            "total":               result["total"],
            "passed":              result["passed"],
            "failed":              result["failed"],
            "pass_rate":           result["pass_rate"],
            "total_time_seconds":  result["total_time_seconds"],
            "results":             result["results"],
            "tested_at":           result["tested_at"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mary batch failed: {str(e)}")
