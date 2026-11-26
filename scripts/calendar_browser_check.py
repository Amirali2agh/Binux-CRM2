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
        await page.emulate_media(reduced_motion="reduce")
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

        theme_toggle = page.locator(".sidebar-foot [data-theme-toggle]")
        assert await page.locator("html").get_attribute("data-theme") == "light"
        assert await theme_toggle.get_attribute("aria-checked") == "false"
        assert await theme_toggle.get_attribute("aria-label") == "تم شب"
        assert await theme_toggle.locator("[data-theme-state]").inner_text() == "خاموش"
        assert await page.get_by_text("محیط آموزشی · داده‌ها ساختگی‌اند").count() == 0
        off_switch = await theme_toggle.locator(".theme-switch-track").evaluate(
            "el => ({background: getComputedStyle(el).backgroundColor, "
            "thumb: getComputedStyle(el.querySelector('.theme-switch-thumb')).transform, "
            "transition: getComputedStyle(el.querySelector('.theme-switch-thumb')).transitionDuration})"
        )
        assert off_switch == {
            "background": "rgb(53, 70, 97)",
            "thumb": "none",
            "transition": "0s",
        }
        assert await page.evaluate("localStorage.getItem('binux-crm-theme')") is None

        await theme_toggle.focus()
        await page.keyboard.press("Enter")
        assert await page.locator("html").get_attribute("data-theme") == "dark"
        assert await theme_toggle.get_attribute("aria-checked") == "true"
        assert await theme_toggle.locator("[data-theme-state]").inner_text() == "روشن"
        on_switch = await theme_toggle.locator(".theme-switch-track").evaluate(
            "el => ({background: getComputedStyle(el).backgroundColor, "
            "thumb: getComputedStyle(el.querySelector('.theme-switch-thumb')).transform})"
        )
        assert on_switch["background"] == "rgb(53, 92, 152)"
        assert on_switch["thumb"] != "none"
        assert await page.evaluate("localStorage.getItem('binux-crm-theme')") == "dark"
        dark_surfaces = await page.evaluate(
            """() => ({
              workspace: getComputedStyle(document.querySelector('.workspace')).backgroundColor,
              topbar: getComputedStyle(document.querySelector('.topbar')).backgroundColor,
              calendar: getComputedStyle(document.querySelector('.calendar-panel')).backgroundColor,
              fridayHeader: getComputedStyle(document.querySelector('.jalali-calendar th:last-child')).color,
            })"""
        )
        assert dark_surfaces == {
            "workspace": "rgb(74, 74, 74)",
            "topbar": "rgb(74, 74, 74)",
            "calendar": "rgb(74, 74, 74)",
            "fridayHeader": "rgb(255, 204, 204)",
        }, f"Dark theme shell surfaces or Friday contrast color are incorrect: {dark_surfaces}"

        response = await page.goto(f"{BASE_URL}/customers/new/")
        assert response and response.status == 200
        theme_toggle = page.locator(".sidebar-foot [data-theme-toggle]")
        assert await page.locator("html").get_attribute("data-theme") == "dark"
        assert await theme_toggle.get_attribute("aria-checked") == "true"
        dark_form = await page.evaluate(
            """() => ({
              panel: getComputedStyle(document.querySelector('.customer-form-surface')).backgroundColor,
              label: getComputedStyle(document.querySelector('.field-row label')).color,
              input: getComputedStyle(document.querySelector('.form-control')).backgroundColor,
              inputText: getComputedStyle(document.querySelector('.form-control')).color,
            })"""
        )
        assert dark_form == {
            "panel": "rgb(92, 92, 92)",
            "label": "rgb(255, 255, 255)",
            "input": "rgb(74, 74, 74)",
            "inputText": "rgb(255, 255, 255)",
        }, f"Dark theme customer form is incorrect: {dark_form}"

        for width in (1440, 390, 320):
            await page.set_viewport_size({"width": width, "height": 1000})
            dimensions = await page.evaluate(
                "({viewport: document.documentElement.clientWidth, "
                "document: document.documentElement.scrollWidth})"
            )
            assert dimensions["document"] <= dimensions["viewport"], (
                f"Horizontal overflow at {width}px: {dimensions}"
            )
            if width <= 760:
                await page.locator(".mobile-menu").click()
            assert await page.get_by_role("switch", name="تم شب").is_visible(), (
                f"Theme switch hidden at {width}px"
            )
            sidebar_box = await page.locator(".sidebar").bounding_box()
            switch_box = await theme_toggle.bounding_box()
            bottom_gap = sidebar_box["y"] + sidebar_box["height"] - (
                switch_box["y"] + switch_box["height"]
            )
            assert 0 <= bottom_gap <= 40, (
                f"Theme switch is not at the bottom of the sidebar at {width}px: {bottom_gap}px"
            )
            if width <= 760:
                await page.keyboard.press("Escape")

        await page.locator(".mobile-menu").click()
        await theme_toggle.focus()
        await page.keyboard.press("Enter")
        assert await page.locator("html").get_attribute("data-theme") == "light"
        assert await theme_toggle.get_attribute("aria-checked") == "false"
        assert await theme_toggle.locator("[data-theme-state]").inner_text() == "خاموش"
        assert await page.evaluate("localStorage.getItem('binux-crm-theme')") == "light"
        await page.reload()
        assert await page.locator("html").get_attribute("data-theme") == "light"
        assert await page.locator(".sidebar-foot [data-theme-toggle]").get_attribute("aria-checked") == "false"

        await page.locator(".mobile-menu").click()
        theme_toggle = page.locator(".sidebar-foot [data-theme-toggle]")
        await theme_toggle.focus()
        await page.keyboard.press("Enter")
        assert await page.locator("html").get_attribute("data-theme") == "dark"
        response = await page.goto(f"{BASE_URL}/internal/calendar/?month=1403-01")
        assert response and response.status == 200
        assert await page.locator("html").get_attribute("data-theme") == "dark"
        assert await page.locator(".sidebar-foot [data-theme-toggle]").get_attribute("aria-checked") == "true"

        response = await page.goto(f"{BASE_URL}/internal/settings/users/")
        assert response and response.status == 200
        assert await page.get_by_role("heading", name="افزودن کاربر").count() == 1
        assert await page.get_by_role("heading", name="ایجاد حساب جدید").count() == 1
        assert await page.get_by_label("نام کاربری").is_visible()
        assert await page.get_by_label("گذرواژهٔ اولیه").is_visible()
        assert await page.get_by_label("نقش").is_visible()
        assert (
            await page.locator(".user-management-entry")
            .filter(has_text="calendar-ci")
            .count()
            == 1
        )
        checkbox_width = await page.get_by_label("حساب فعال باشد").evaluate(
            "el => getComputedStyle(el).width"
        )
        assert checkbox_width == "20px", f"User activation checkbox width is {checkbox_width}"
        for width in (1440, 390, 320):
            await page.set_viewport_size({"width": width, "height": 1000})
            dimensions = await page.evaluate(
                "({viewport: document.documentElement.clientWidth, "
                "document: document.documentElement.scrollWidth})"
            )
            assert dimensions["document"] <= dimensions["viewport"], (
                f"User-management page overflows at {width}px: {dimensions}"
            )

        response = await page.goto(f"{BASE_URL}/customers/assign/")
        assert response and response.status == 200
        assert await page.get_by_role("heading", name="ارجاع مشتریان").count() == 1
        assert await page.get_by_label("روش انتخاب مشتری").is_visible()
        assert await page.get_by_label("دسته مشتری").is_visible()
        assert await page.get_by_label("ارجاع به کاربر فعال").is_visible()
        assert await page.get_by_role("heading", name="مشتریانی که شما ارجاع داده‌اید").count() == 1
        assert await page.get_by_role("link", name="ارجاع مشتریان").count() == 1
        for width in (1440, 390, 320):
            await page.set_viewport_size({"width": width, "height": 1000})
            dimensions = await page.evaluate(
                "({viewport: document.documentElement.clientWidth, "
                "document: document.documentElement.scrollWidth})"
            )
            assert dimensions["document"] <= dimensions["viewport"], (
                f"Customer-assignment page overflows at {width}px: {dimensions}"
            )

        response = await page.goto(f"{BASE_URL}/management/dashboard/")
        assert response and response.status == 200
        assert await page.locator("html").get_attribute("dir") == "rtl"
        assert await page.get_by_role("heading", name="داشبورد تماس‌ها").count() == 1
        assert await page.get_by_role("link", name="داشبورد تماس‌ها").count() == 1
        assert await page.get_by_role("img", name="توزیع نتایج تماس‌ها").count() == 1
        assert await page.get_by_role(
            "img", name="تعداد تماس‌ها به تفکیک بازاریاب مسئول فعلی"
        ).count() == 1
        assert await page.locator(".dashboard-chart-table caption").count() == 2
        assert await page.locator(".dashboard-pie").count() == 2
        chart_background = await page.locator(".dashboard-pie").first.evaluate(
            "el => getComputedStyle(el).backgroundImage"
        )
        assert "conic-gradient" in chart_background, chart_background
        total_calls = page.locator(".dashboard-summary article").first.locator("strong")
        assert await total_calls.inner_text() == "2"

        await page.locator('select[name="staff"]').select_option(index=1)
        await page.get_by_role("button", name="اعمال فیلتر").click()
        assert await page.locator(".dashboard-summary article").first.locator("strong").inner_text() == "2"
        await page.locator('select[name="status"]').select_option("call_again")
        await page.get_by_role("button", name="اعمال فیلتر").click()
        assert await page.locator(".dashboard-summary article").first.locator("strong").inner_text() == "1"

        for width in (1440, 390, 320):
            await page.set_viewport_size({"width": width, "height": 1000})
            dimensions = await page.evaluate(
                "({viewport: document.documentElement.clientWidth, "
                "document: document.documentElement.scrollWidth})"
            )
            assert dimensions["document"] <= dimensions["viewport"], (
                f"Manager dashboard overflows at {width}px: {dimensions}"
            )
            chart_columns = await page.locator(".dashboard-charts").evaluate(
                "el => getComputedStyle(el).gridTemplateColumns.split(' ').length"
            )
            assert chart_columns == (1 if width <= 760 else 2), (
                f"Dashboard chart layout has {chart_columns} columns at {width}px"
            )

        assert not page_errors, f"Browser JavaScript errors: {page_errors}"
        print("Browser checks passed: calendar/theme, user management, customer "
              "assignment, and manager call dashboard at 1440/390/320px; no overflow/page errors.")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
