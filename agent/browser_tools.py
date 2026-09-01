from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from core.project import APP_ROOT

DEFAULT_BROWSER_PROFILE = APP_ROOT / "work" / "auto_pilot" / "browser_profile"
_SESSION: dict[str, Any] | None = None


def browser_open(
    url: str,
    *,
    headless: bool = False,
    wait_ms: int = 1000,
    persistent: bool = True,
) -> dict[str, Any]:
    global _SESSION
    _validate_url(url)
    if _SESSION is None:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        context = None
        browser = None
        errors: list[str] = []

        # Browser channel priority: chrome -> msedge -> chromium
        channels = ("chrome", "msedge", "chromium") if sys.platform == "darwin" else ("chrome", "msedge", "chromium")

        if persistent:
            DEFAULT_BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
            for channel in channels:
                try:
                    context = playwright.chromium.launch_persistent_context(
                        user_data_dir=str(DEFAULT_BROWSER_PROFILE),
                        channel=channel if channel != "chromium" else None,
                        headless=headless,
                        viewport={"width": 1440, "height": 900},
                    )
                    break
                except Exception as error:
                    errors.append(f"persistent-{channel}: {error}")

        if context is None:
            for channel in channels:
                try:
                    browser = playwright.chromium.launch(
                        channel=channel if channel != "chromium" else None,
                        headless=headless,
                    )
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 900}
                    )
                    break
                except Exception as error:
                    errors.append(f"standard-{channel}: {error}")

        if context is None:
            playwright.stop()
            raise RuntimeError(
                "Unable to launch Chrome/Edge via Playwright. "
                "Please install Google Chrome / Microsoft Edge or run 'playwright install chromium'. "
                + " | ".join(errors)[-1000:]
            )
        page = context.pages[0] if context.pages else context.new_page()
        _SESSION = {
            "playwright": playwright,
            "browser": browser,
            "context": context,
            "page": page,
        }
    page = _SESSION["page"]
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    if wait_ms:
        page.wait_for_timeout(max(0, min(wait_ms, 10000)))
    return _page_summary(page)


def browser_snapshot(max_chars: int = 12000) -> dict[str, Any]:
    page = _page()
    body_text = page.locator("body").inner_text(timeout=10000)
    return {
        **_page_summary(page),
        "text": body_text[:max_chars],
        "truncated": len(body_text) > max_chars,
    }


def browser_click(
    *,
    selector: str = "",
    text: str = "",
    wait_ms: int = 500,
) -> dict[str, Any]:
    page = _page()
    locator = _locator(page, selector=selector, text=text)
    locator.first.click(timeout=15000)
    if wait_ms:
        page.wait_for_timeout(max(0, min(wait_ms, 10000)))
    return _page_summary(page)


def browser_type(
    value: str,
    *,
    selector: str = "",
    text: str = "",
    press_enter: bool = False,
) -> dict[str, Any]:
    page = _page()
    locator = _locator(page, selector=selector, text=text)
    locator.first.fill(value, timeout=15000)
    if press_enter:
        locator.first.press("Enter")
    return _page_summary(page)


def browser_extract(
    *,
    selector: str = "",
    max_chars: int = 12000,
) -> dict[str, Any]:
    page = _page()
    locator = page.locator(selector) if selector else page.locator("body")
    content = locator.first.inner_text(timeout=10000)
    return {
        "selector": selector or "body",
        "text": content[:max_chars],
        "truncated": len(content) > max_chars,
    }


def browser_screenshot() -> dict[str, Any]:
    page = _page()
    directory = APP_ROOT / "work" / "auto_pilot" / "browser"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (
        datetime.now().strftime("%Y%m%d-%H%M%S") + ".png"
    )
    page.screenshot(path=str(path), full_page=False)
    return {"path": str(path), **_page_summary(page)}


def browser_close() -> dict[str, Any]:
    global _SESSION
    if _SESSION is None:
        return {"closed": False, "reason": "Browser not open"}
    try:
        if _SESSION.get("context"):
            try:
                _SESSION["context"].close()
            except Exception:
                pass
        if _SESSION.get("browser"):
            try:
                _SESSION["browser"].close()
            except Exception:
                pass
        if _SESSION.get("playwright"):
            try:
                _SESSION["playwright"].stop()
            except Exception:
                pass
    finally:
        _SESSION = None
    return {"closed": True}


def _page() -> Any:
    if _SESSION is None:
        raise RuntimeError("Browser is not open. Call browser_open first.")
    return _SESSION["page"]


def _locator(page: Any, *, selector: str, text: str) -> Any:
    if selector.strip():
        return page.locator(selector.strip())
    if text.strip():
        return page.get_by_text(text.strip(), exact=False)
    raise ValueError("Either CSS selector or text is required to locate element.")


def _page_summary(page: Any) -> dict[str, Any]:
    return {
        "url": page.url,
        "title": page.title(),
    }


def _validate_url(url: str) -> None:
    value = str(url or "").strip().lower()
    if not value.startswith(("http://", "https://")):
        raise ValueError("Browser only supports http:// or https:// URLs.")
