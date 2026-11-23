"""Headless CI checks for the authenticated calendar at desktop and mobile widths."""

import asyncio
import os
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.async_api import async_playwright

BASE_URL = os.environ.get("CRM_BASE_URL", "http://127.0.0.1:8000")
USERNAME = "calendar-ci"
PASSWORD = os.environ["CALENDAR_TEST_PASSWORD"]


def wait_for_app():
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{BASE_URL}/accounts/login/", timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.25)
    raise RuntimeError("The CI Django application did not become ready in 30 seconds.")


async def main():
    wait_for_app()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        response = await page.goto(f"{BASE_URL}/internal/calendar/?month=1403-01")
        assert response and response.status == 200
        await page.get_by_label("نام کاربری").fill(USERNAME)
        await page.get_by_label("گذرواژه").fill(PASSWORD)
        await page.get_by_role("button", name="ورود").click()
        await page.wait_for_url("**/internal/calendar/?month=1403-01")
        assert await page.get_by_role("heading", name="فروردین ۱۴۰۳").count() == 1
        assert await page.locator("time[aria-label]").count() >= 28

        next_month = page.get_by_role("link", name="رفتن به ماه بعد")
        await next_month.focus()
        await page.keyboard.press("Enter")
        await page.wait_for_url("**month=1403-02")
        assert await page.get_by_role("heading", name="اردیبهشت ۱۴۰۳").count() == 1

        for width in (1440, 390, 320):
            await page.set_viewport_size({"width": width, "height": 1000})
            dimensions = await page.evaluate(
                "({viewport: document.documentElement.clientWidth, "
                "document: document.documentElement.scrollWidth})"
            )
            assert dimensions["document"] <= dimensions["viewport"], (
                f"Horizontal overflow at {width}px: {dimensions}"
            )

        assert not page_errors, f"Browser JavaScript errors: {page_errors}"
        print("Browser calendar check passed: login, keyboard month navigation, "
              "accessible dates, 1440/390/320px widths, no page errors.")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
