"""
Functional tester routes — Phase 1 surface.

Exposes /functional/smoke so the user can verify after a Render deploy
that:
  (a) the playwright python package imported successfully,
  (b) `playwright install --with-deps chromium` placed the browser on
      disk during the build, and
  (c) the worker has enough memory + sandbox permissions to actually
      drive a headless page.

Phase 2+ will add the per-batch test endpoints.
"""

from fastapi import APIRouter

from ..services.functional_tester import (
    is_available,
    import_error,
    smoke_test,
)

router = APIRouter(prefix="/functional", tags=["functional"])


@router.get("/smoke")
async def smoke():
    """Live browser smoke test. Curl this after a deploy:

      curl https://physis-tester.onrender.com/functional/smoke

    Returns ok=true with diagnostics on success, ok=false with a
    reason string on failure. Designed to be the single source of
    truth for "did Playwright land cleanly on this Render container"."""
    return await smoke_test()


@router.get("/health")
def health():
    """Cheap, no-browser health probe. Confirms the playwright import
    worked at module load time. Use this in uptime monitors instead of
    /functional/smoke to avoid spinning up chromium every minute."""
    return {
        "playwright_available": is_available(),
        "import_error":         import_error(),
    }
