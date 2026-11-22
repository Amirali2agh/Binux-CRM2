"""Optional browser checks for the display-only CRM navigation.

Run a local Django server, install Playwright in your development environment,
then: python scripts/browser_smoke.py. Chrome/Chromium is required on the host.
"""

import os

from playwright.sync_api import sync_playwright  # pyright: ignore[reportMissingImports]

BASE_URL = os.environ.get("CRM_BASE_URL", "http://127.0.0.1:8000")
CHROME_PATH = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")


def check_no_horizontal_scroll(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
        f"horizontal overflow at {page.viewport_size}"
    )


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=CHROME_PATH,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            desktop = browser.new_page(viewport={"width": 1440, "height": 900})
            assert desktop.goto(f"{BASE_URL}/internal/office-inventory/").status == 200
            assert desktop.locator('a[aria-current="page"]').count() == 1
            assert desktop.locator(".topbar-search").is_visible()
            assert desktop.locator(".topbar-account").is_visible()
            check_no_horizontal_scroll(desktop)

            for width in (390, 320):
                mobile = browser.new_page(viewport={"width": width, "height": 820})
                assert mobile.goto(f"{BASE_URL}/internal/office-inventory/").status == 200
                check_no_horizontal_scroll(mobile)
                mobile.locator(".mobile-menu").click()
                assert mobile.locator(".sidebar-close").evaluate("el => el === document.activeElement")
                assert mobile.locator(".workspace").evaluate("el => el.inert")
                mobile.keyboard.press("Shift+Tab")
                assert mobile.locator(".sidebar a[href]").first.evaluate("el => el === document.activeElement")
                mobile.keyboard.press("Shift+Tab")
                assert mobile.locator(".sidebar button:visible").last.evaluate("el => el === document.activeElement"), mobile.evaluate("document.activeElement.outerHTML")
                mobile.keyboard.press("Tab")
                assert mobile.locator(".sidebar a[href]").first.evaluate("el => el === document.activeElement")
                mobile.keyboard.press("Escape")
                assert mobile.locator(".mobile-menu").evaluate("el => el === document.activeElement")
                assert mobile.locator(".workspace").evaluate("el => !el.inert")
                assert not mobile.locator(".sidebar").evaluate("el => el.classList.contains('is-mobile-open')")
                mobile.close()

            no_js = browser.new_page(
                viewport={"width": 390, "height": 820}, java_script_enabled=False
            )
            assert no_js.goto(f"{BASE_URL}/internal/office-inventory/").status == 200
            assert no_js.locator(".group-title-nojs").first.is_visible()
            assert not no_js.locator(".group-toggle").first.is_visible()
            assert no_js.locator(".submenu a").first.is_visible()
            check_no_horizontal_scroll(no_js)
            no_js.locator(".submenu a").nth(1).click()
            assert no_js.url.endswith("/internal/calendar/")
            assert no_js.locator("h1").inner_text() == "کلندر"
            no_js.close()
            desktop.close()
            print("Browser OK: desktop, mobile 390/320 keyboard focus, and no-JS navigation")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
