"""
Functional Tester — Phase 1 scaffolding for Tests 37–46.

This module owns the headless-browser lifecycle for the entire process:
one chromium instance launched lazily on first use, kept warm across
batches, torn down on shutdown. Each test gets its OWN BrowserContext
so cookies / localStorage / etc. don't leak between apps in a batch.

Phase 1 deliverables (this commit):
  * launch_browser / close_browser / get_browser singleton
  * new_context() helper for per-app isolation
  * capture_screenshot_b64 with a 200 KB cap
  * smoke_test() — launch, navigate to example.com, close, return diagnostics

Phase 2+ will add the actual test functions (Tests 37, 38, 39, 40, 44,
41, 42, 45, 43, 46) and call this module's helpers.

Concurrency note: per the platform rule, tests run sequentially. We
guard browser access with an asyncio.Lock so a misuse from somewhere
else in the codebase can't race two tests through the same context.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Any, Dict, Optional

# Playwright is imported lazily so the rest of the tester still imports
# cleanly on a dev machine that hasn't run `playwright install` yet.
# Production startup verifies the import via the smoke-test endpoint.
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page  # noqa: F401
    _PLAYWRIGHT_AVAILABLE = True
    _PLAYWRIGHT_IMPORT_ERROR: Optional[str] = None
except Exception as _pw_exc:  # pragma: no cover — only on dev without playwright
    async_playwright = None  # type: ignore
    Browser = Any  # type: ignore
    BrowserContext = Any  # type: ignore
    Page = Any  # type: ignore
    _PLAYWRIGHT_AVAILABLE = False
    _PLAYWRIGHT_IMPORT_ERROR = str(_pw_exc)


# ── Tunables ─────────────────────────────────────────────────────────────────
DEFAULT_VIEWPORT       = {"width": 1280, "height": 800}
DEFAULT_NAV_TIMEOUT_MS = 20_000
SCREENSHOT_MAX_BYTES   = 200 * 1024   # 200 KB cap per Phase 1 spec


# ── Singleton state ──────────────────────────────────────────────────────────
# One Playwright + Browser instance per process. Lazy-launched so the
# import cost doesn't hit every uvicorn worker on cold start; the
# browser lights up the first time a test or smoke call needs it.
_pw_singleton: Any = None       # holds the playwright async context manager handle
_browser_singleton: Optional[Any] = None
_lock = asyncio.Lock()


def is_available() -> bool:
    """True when playwright was importable. Call sites should branch on this
    before invoking any of the helpers below — when False every helper
    raises a clear RuntimeError with the original ImportError reason."""
    return _PLAYWRIGHT_AVAILABLE


def import_error() -> Optional[str]:
    return _PLAYWRIGHT_IMPORT_ERROR


async def get_browser() -> Any:
    """Return the process-wide chromium Browser, launching it if needed.
    Safe to call from anywhere; lock-guarded so two callers can't race
    the launch path."""
    global _pw_singleton, _browser_singleton
    if not _PLAYWRIGHT_AVAILABLE:
        raise RuntimeError(
            f"Playwright not available: {_PLAYWRIGHT_IMPORT_ERROR}. "
            "Did `playwright install --with-deps chromium` run on the build host?"
        )
    async with _lock:
        if _browser_singleton is not None:
            return _browser_singleton
        _pw_singleton = await async_playwright().start()
        # --no-sandbox is required when running as root inside a Render
        # container; chromium otherwise refuses to start.
        _browser_singleton = await _pw_singleton.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        return _browser_singleton


async def close_browser() -> None:
    """Tear the browser down cleanly. Called from main.py's shutdown
    hook so a uvicorn restart doesn't leak the chromium process."""
    global _pw_singleton, _browser_singleton
    async with _lock:
        try:
            if _browser_singleton is not None:
                await _browser_singleton.close()
        except Exception:
            pass
        try:
            if _pw_singleton is not None:
                await _pw_singleton.stop()
        except Exception:
            pass
        _browser_singleton = None
        _pw_singleton = None


async def new_context(
    viewport: Optional[Dict[str, int]] = None,
    user_agent: Optional[str] = None,
) -> Any:
    """Per-test BrowserContext. Cheap (~50 ms). Caller MUST close it via
    `await context.close()` to release memory; recommended pattern is
    `async with new_context() as ctx:`-style by wrapping in try/finally."""
    browser = await get_browser()
    return await browser.new_context(
        viewport=viewport or DEFAULT_VIEWPORT,
        user_agent=user_agent or (
            # Identifiable so Physis can tag tester traffic in its own logs.
            "PhysisTester/1.0 (+https://physis-tester.pages.dev) "
            "PlaywrightHeadlessChromium"
        ),
        ignore_https_errors=True,
    )


# ── Screenshot helper ────────────────────────────────────────────────────────
async def capture_screenshot_b64(page: Any) -> Optional[str]:
    """Viewport-only PNG screenshot, base64 encoded. Returns None when the
    raw bytes exceed SCREENSHOT_MAX_BYTES (200 KB) so we don't bloat the
    DB row — a missing screenshot is preferable to a 5 MB fullscreen one
    that crowds out other rows in the same query.

    Failures (page closed, navigation in flight, etc.) silently return
    None — capture is debug-only and must never crash a test."""
    try:
        png_bytes = await page.screenshot(full_page=False, type="png")
    except Exception:
        return None
    if not png_bytes:
        return None
    if len(png_bytes) > SCREENSHOT_MAX_BYTES:
        # Soft cap — try a cheaper jpeg-style fallback at lower quality.
        # (PNG has no quality knob, so we just bail on oversized images.)
        return None
    try:
        return base64.b64encode(png_bytes).decode("ascii")
    except Exception:
        return None


def screenshot_failure_record(test_id: int, png_b64: Optional[str]) -> Optional[Dict[str, Any]]:
    """Pack a captured screenshot into the shape used by
    Run.functional_failure_screenshots. Returns None when there's
    nothing to store, so callers can `[f for f in [...] if f]`."""
    if not png_b64:
        return None
    return {
        "test_id":     test_id,
        "png_b64":     png_b64,
        "captured_at": _now_iso(),
    }


# ── Smoke test ───────────────────────────────────────────────────────────────
async def smoke_test(target_url: str = "https://example.com") -> Dict[str, Any]:
    """End-to-end browser sanity check: launch (or reuse) chromium,
    navigate to target_url, read the page title, close the per-call
    context (NOT the singleton browser), return a diagnostics dict.

    Used by the /functional/smoke endpoint after a Render deploy to
    verify the full toolchain — Standard plan has memory headroom,
    apt deps are installed, the chromium binary downloaded, and the
    process can actually drive a page."""
    if not _PLAYWRIGHT_AVAILABLE:
        return {
            "ok":            False,
            "reason":        "playwright_import_failed",
            "import_error":  _PLAYWRIGHT_IMPORT_ERROR,
        }

    started = time.time()
    context = None
    page    = None
    try:
        context = await new_context()
        page    = await context.new_page()
        await page.goto(target_url, timeout=DEFAULT_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        title = await page.title()
        url   = page.url
        return {
            "ok":            True,
            "browser":       "chromium",
            "target_url":    target_url,
            "resolved_url":  url,
            "page_title":    title,
            "duration_ms":   int((time.time() - started) * 1000),
            "memory_mb_estimate": _process_rss_mb(),
        }
    except Exception as exc:
        return {
            "ok":           False,
            "reason":       "smoke_failed",
            "error":        str(exc),
            "duration_ms":  int((time.time() - started) * 1000),
        }
    finally:
        # Close the per-call context but leave the singleton browser warm
        # — subsequent tests reuse it for fast turnaround.
        try:
            if page is not None:
                await page.close()
        except Exception:
            pass
        try:
            if context is not None:
                await context.close()
        except Exception:
            pass


# ── Internals ────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _process_rss_mb() -> Optional[int]:
    """Best-effort current process RSS in MB. None if /proc isn't
    readable (non-Linux dev machines). Useful for spotting OOM
    pressure in the smoke-test response."""
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    # "VmRSS:    123456 kB"
                    parts = line.split()
                    return int(parts[1]) // 1024
    except Exception:
        pass
    try:
        # Fallback for non-Linux: psutil may or may not be installed.
        import resource  # type: ignore
        kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS returns bytes, Linux returns kilobytes — normalise to MB.
        return int(kb / (1024 if os.uname().sysname == "Linux" else 1024 * 1024))
    except Exception:
        return None
