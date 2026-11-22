from django.test import SimpleTestCase
from django.urls import reverse

PAGES = (
    ("office_inventory", "موجودی دفتر", "داخلی"),
    ("calendar", "کلندر", "داخلی"),
    ("agent_management", "مدیریت ایجنت", "داخلی"),
    ("settings", "تنظیمات", "داخلی"),
    ("receipts_payments", "دریافتی و پرداختی", "مالی"),
    ("office_expenses", "هزینه های دفتر", "مالی"),
    ("profit_sharing", "تقسیم سود", "مالی"),
    ("creditors_debtors", "طلبکار و بستانکار", "مالی"),
    ("project_expenses", "هزینه های پروژه", "مالی"),
    ("customer_list", "لیست مشتریان", "بازاریابی و مشتریان"),
    ("contacted_customers", "مشتریان بازرایابی شده", "بازاریابی و مشتریان"),
    ("follow_ups", "پیگیری", "بازاریابی و مشتریان"),
    ("contract_draft", "نوشتن قرارداد", "قرارداد"),
    ("contract_archive", "بایگانی قرارداد", "قرارداد"),
    ("active_agents", "لیست ایجنت های فعال", "مدیریت سرور و ایجنت"),
    ("active_servers", "لیست سرور های فعال", "مدیریت سرور و ایجنت"),
    ("expirations", "انقضا", "مدیریت سرور و ایجنت"),
)


class DisplayOnlyPagesTests(SimpleTestCase):
    def test_all_17_named_routes_render_distinct_demo_pages(self):
        destinations = set()
        for name, heading, group in PAGES:
            with self.subTest(name=name):
                url = reverse(f"crm:{name}")
                self.assertNotIn(url, destinations)
                destinations.add(url)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response, f'<h1 id="page-title">{heading}</h1>', html=True
                )
                self.assertContains(response, 'data-demo="true"')
                self.assertContains(response, 'aria-current="page"')
                self.assertContains(response, group)
                self.assertNotContains(response, "<form")
                self.assertEqual(self.client.post(url).status_code, 405)
        self.assertEqual(len(destinations), 17)

    def test_sidebar_has_five_groups_and_all_named_destinations(self):
        response = self.client.get(reverse("crm:office_inventory"))
        self.assertEqual(response.status_code, 200)
        for name, heading, _ in PAGES:
            with self.subTest(name=name):
                self.assertContains(response, f'href="{reverse(f"crm:{name}")}"')
                self.assertContains(response, heading)
        for group in (
            "داخلی",
            "مالی",
            "بازاریابی و مشتریان",
            "قرارداد",
            "مدیریت سرور و ایجنت",
        ):
            self.assertContains(response, group)
        self.assertContains(response, 'dir="rtl"')
        self.assertContains(response, 'aria-expanded="true"')

    def test_demo_is_safe_for_read_only_navigation(self):
        response = self.client.get(reverse("crm:active_servers"))
        self.assertContains(response, "سرور آزمایشی")
        self.assertContains(response, "اطلاعات این صفحه نمونه است")
        self.assertNotContains(response, "192.168.")
        self.assertEqual(self.client.get("/does-not-exist/").status_code, 404)
        self.assertEqual(
            self.client.head(reverse("crm:active_servers")).status_code, 200
        )

    def test_section_examples_and_empty_states(self):
        for name, marker in (
            ("office_inventory", "صندلی اداری"),
            ("calendar", "رویداد نمونه"),
            ("receipts_payments", "دریافت نمونه"),
            ("profit_sharing", "سهم نمونه"),
            ("customer_list", "مشتری نمونه"),
            ("follow_ups", "پیگیری ثبت نشده است"),
            ("contract_draft", "پیش‌نمایش قرارداد"),
            ("contract_archive", "قرارداد نمونه"),
            ("active_agents", "ایجنت آزمایشی"),
            ("expirations", "انقضای نمونه"),
        ):
            with self.subTest(name=name):
                self.assertContains(self.client.get(reverse(f"crm:{name}")), marker)
