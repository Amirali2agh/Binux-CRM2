from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import CustomerForm
from .jalali_calendar import build_month
from .models import Customer

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


class LoginGateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="login-gate-user", password="safe-test-password"
        )

    def test_anonymous_visitors_are_redirected_from_every_crm_page(self):
        for name, _, _ in PAGES:
            with self.subTest(name=name):
                response = self.client.get(reverse(f"crm:{name}"))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("login")))

    def test_root_lands_on_standalone_public_login_page(self):
        response = self.client.get("/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "crm/login.html")
        self.assertContains(response, "ورود اعضای تیم")
        self.assertNotContains(response, "sidebar-nav")
        self.assertNotContains(response, "موجودی دفتر")
        self.assertEqual(response.context["next"], reverse("crm:office_inventory"))

        response = self.client.post(
            reverse("login"),
            {
                "username": "login-gate-user",
                "password": "safe-test-password",
                "next": response.context["next"],
            },
        )
        self.assertRedirects(response, reverse("crm:office_inventory"))

    def test_login_returns_to_requested_page_and_authenticated_user_skips_login(self):
        destination = reverse("crm:office_inventory")
        response = self.client.get(destination)
        self.assertEqual(response.status_code, 302)
        self.assertIn(destination, response.url)

        response = self.client.post(
            reverse("login"),
            {
                "username": "login-gate-user",
                "password": "safe-test-password",
                "next": destination,
            },
        )
        self.assertRedirects(response, destination)
        self.assertEqual(self.client.get(destination).status_code, 200)
        self.assertRedirects(
            self.client.get(reverse("login")), reverse("crm:customer_list")
        )

    def test_login_rejects_untrusted_next_and_uses_default_destination(self):
        for next_url in ("https://example.invalid/", "//example.invalid/"):
            with self.subTest(next_url=next_url):
                response = self.client.post(
                    reverse("login"),
                    {
                        "username": "login-gate-user",
                        "password": "safe-test-password",
                        "next": next_url,
                    },
                )
                self.assertRedirects(response, reverse("crm:customer_list"))
                self.client.logout()

    def test_admin_retains_its_own_anonymous_login(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)
        admin_login = self.client.get(reverse("admin:login"))
        self.assertEqual(admin_login.status_code, 200)
        self.assertTemplateUsed(admin_login, "admin/login.html")

    def test_invalid_credentials_show_an_accessible_error(self):
        response = self.client.post(
            reverse("login"),
            {"username": "login-gate-user", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, "نام کاربری یا گذرواژه درست نیست.")


class DisplayOnlyPagesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="demo-reader", password="safe-test-password"
        )
        self.client.force_login(self.user)

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
                if name not in {"customer_list", "follow_ups", "calendar"}:
                    self.assertContains(response, 'data-demo="true"')
                self.assertContains(response, f'href="{url}" aria-current="page"')
                self.assertEqual(response.content.decode().count('aria-current="page"'), 1)
                self.assertContains(response, group)
                if name not in {"customer_list", "follow_ups", "calendar"}:
                    self.assertEqual(response.content.count(b"<form"), 1)
                    self.assertContains(response, 'class="logout-form"')
                self.assertEqual(self.client.post(url).status_code, 405)
        self.assertEqual(len(destinations), 17)

    def test_sidebar_has_five_groups_and_all_named_destinations(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("crm:office_inventory"))
        self.assertEqual(response.status_code, 200)
        for name, heading, _ in PAGES:
            with self.subTest(name=name):
                self.assertContains(response, f'href="{reverse(f"crm:{name}")}"')
                self.assertContains(response, heading)
        for name in (
            "tasks", "completed_customers", "customer_archive", "customer_trash"
        ):
            self.assertContains(response, f'href="{reverse(f"crm:{name}")}"')
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
            ("receipts_payments", "دریافت نمونه"),
            ("profit_sharing", "سهم نمونه"),
            ("follow_ups", "موردی برای نمایش وجود ندارد"),
            ("contract_draft", "پیش‌نمایش قرارداد"),
            ("contract_archive", "قرارداد نمونه"),
            ("active_agents", "ایجنت آزمایشی"),
            ("expirations", "انقضای نمونه"),
        ):
            with self.subTest(name=name):
                self.assertContains(self.client.get(reverse(f"crm:{name}")), marker)

    def test_finance_and_contract_previews_show_both_sides_and_distinct_content(self):
        self.assertContains(self.client.get(reverse("crm:creditors_debtors")), "دریافتنی")
        self.assertContains(self.client.get(reverse("crm:creditors_debtors")), "پرداختنی")
        draft = self.client.get(reverse("crm:contract_draft"))
        archive = self.client.get(reverse("crm:contract_archive"))
        self.assertContains(draft, "موضوع قرارداد نمونه")
        self.assertContains(archive, '<ul class="contract-archive">')
        self.assertContains(archive, "قرارداد نمونه")
        self.assertEqual(draft.content.count(b"<form"), 1)
        self.assertContains(draft, 'class="logout-form"')
        self.assertEqual(archive.content.count(b"<form"), 1)
        self.assertContains(archive, 'class="logout-form"')


class JalaliCalendarTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="calendar-reader", password="safe-test-password"
        )
        self.client.force_login(self.user)

    def test_calendar_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse("crm:calendar"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_calendar_renders_jalali_month_with_leap_day_and_empty_state(self):
        response = self.client.get(reverse("crm:calendar"), {"month": "1403-12"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اسفند ۱۴۰۳")
        self.assertContains(response, "۳۰")
        self.assertContains(response, "در این ماه رویدادی ثبت نشده است")
        self.assertContains(response, "رویدادی ثبت نشده")
        self.assertContains(response, 'dir="rtl"')
        self.assertNotContains(response, "رویداد نمونه")
        self.assertNotContains(response, "جلسهٔ آزمایشی تیم")

    def test_calendar_grid_starts_on_saturday_and_marks_fridays(self):
        response = self.client.get(reverse("crm:calendar"), {"month": "1403-01"})
        html = response.content.decode()
        self.assertLess(html.index(">شنبه</th>"), html.index(">یک‌شنبه</th>"))
        self.assertLess(html.index(">پنج‌شنبه</th>"), html.index(">جمعه</th>"))
        self.assertContains(response, 'class="calendar-day calendar-day--friday"')
        self.assertContains(response, 'aria-label="جمعه ۳ فروردین ۱۴۰۳"')

    def test_official_holiday_marker_has_distinct_calendar_presentation(self):
        from unittest.mock import patch

        month_data = build_month(
            1403, 1, holidays_by_jalali_date={"1403-01-01": ("تعطیلی آزمایشی",)}
        )
        with patch("crm.views.build_month", return_value=month_data):
            response = self.client.get(
                reverse("crm:calendar"), {"month": "1403-01"}
            )
        self.assertContains(
            response, 'class="calendar-day calendar-day--holiday"'
        )
        self.assertContains(response, "تعطیلی آزمایشی")
        self.assertContains(response, "calendar-holiday-swatch")

    def test_previous_next_and_today_navigation_preserve_jalali_months(self):
        response = self.client.get(reverse("crm:calendar"), {"month": "1403-01"})
        self.assertContains(response, 'href="?month=1402-12"')
        self.assertContains(response, 'href="?month=1403-02"')
        self.assertContains(response, 'href="/internal/calendar/"')

    def test_default_month_uses_tehran_local_date(self):
        from datetime import datetime, timezone as datetime_timezone
        from unittest.mock import patch

        instant = datetime(2024, 3, 19, 20, 30, tzinfo=datetime_timezone.utc)
        with patch("crm.views.timezone.now", return_value=instant):
            response = self.client.get(reverse("crm:calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "فروردین ۱۴۰۳")
        self.assertContains(response, 'href="?month=1403-02"')

    def test_common_year_esfand_has_no_thirtieth_day_and_crosses_year_boundary(self):
        response = self.client.get(reverse("crm:calendar"), {"month": "1402-12"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="سه‌شنبه ۲۹ اسفند ۱۴۰۲"')
        self.assertNotContains(response, 'aria-label="چهارشنبه ۳۰ اسفند ۱۴۰۲"')
        self.assertContains(response, 'href="?month=1403-01"')

    def test_invalid_month_query_returns_bad_request(self):
        response = self.client.get(reverse("crm:calendar"), {"month": "1403-13"})
        self.assertEqual(response.status_code, 400)


class CustomerWorkflowTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(
            username="team-member", password="safe-test-password"
        )
        self.client.force_login(self.user)

    def customer_data(self, **overrides):
        data = {
            "name": "",
            "business_type": "",
            "business_name": "",
            "phone": "",
            "status": Customer.Status.NO_CONTACT,
            "source": "",
            "address": "",
            "notes": "",
            "assignee": "",
        }
        data.update(overrides)
        return data

    def test_customer_list_filters_by_name_business_type_and_status(self):
        matching = Customer.objects.create(
            name="Northwind", business_type="Retail", status=Customer.Status.FOLLOW_UP
        )
        Customer.objects.create(name="Northwind Tools", business_type="Retail", status=Customer.Status.NO_CONTACT)
        Customer.objects.create(name="Southwind", business_type="Retail", status=Customer.Status.FOLLOW_UP)
        Customer.objects.create(name="Northwind", business_type="Services", status=Customer.Status.FOLLOW_UP)
        Customer.objects.create(name="Northwind", business_type="Retail", status=Customer.Status.FOLLOW_UP, archived_at=timezone.now())
        Customer.objects.create(name="Northwind", business_type="Retail", status=Customer.Status.FOLLOW_UP, trashed_at=timezone.now())

        response = self.client.get(reverse("crm:customer_list"), {
            "name": "Northwind", "business_type": "Retail", "status": Customer.Status.FOLLOW_UP,
        })
        self.assertEqual(list(response.context["customers"]), [matching])

    def test_customer_list_filters_combine_and_create_page_is_separate(self):
        Customer.objects.create(name="Combined", business_type="Retail", status=Customer.Status.FOLLOW_UP)
        response = self.client.get(reverse("crm:customer_list"), {"name": "Combined", "status": Customer.Status.NO_CONTACT})
        self.assertFalse(response.context["customers"])
        self.assertContains(response, reverse("crm:customer_create"))
        create_page = self.client.get(reverse("crm:customer_create"))
        self.assertContains(create_page, "ثبت مشتری")
        self.assertContains(create_page, reverse("crm:customer_list"))
        self.assertNotContains(create_page, "فیلتر مشتریان")

    def test_status_and_source_choices_match_the_persian_product_labels(self):
        form = CustomerForm()
        self.assertEqual(
            [label for value, label in form.fields["status"].choices if value],
            ["بدون تماس", "رد شده", "پیگیری", "ارسالی", "تماس مجدد", "انجام شده"],
        )
        self.assertEqual(
            [label for value, label in form.fields["source"].choices if value],
            ["تماس تلفنی", "دیوار", "حضوری", "سایر"],
        )

    def test_all_customer_fields_are_optional_and_record_persists(self):
        response = self.client.post(reverse("crm:customer_create"), {})
        self.assertEqual(response.status_code, 302)
        customer = Customer.objects.get()
        self.assertEqual(customer.name, "")
        self.assertEqual(customer.status, Customer.Status.NO_CONTACT)
        self.assertEqual(
            self.client.get(reverse("crm:customer_list")).status_code, 200
        )

    def test_sent_status_requires_assignee_on_server(self):
        response = self.client.post(
            reverse("crm:customer_create"),
            self.customer_data(status=Customer.Status.SENT),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Customer.objects.exists())
        self.assertContains(response, "برای وضعیت ارسالی انتخاب مسئول الزامی است")
        self.assertContains(response, "field-invalid")

    def test_status_change_rejects_assignee_deactivated_after_assignment(self):
        customer = Customer.objects.create(name="Existing assignment", assignee=self.user)
        self.user.is_active = False
        self.user.save(update_fields={"is_active"})
        customer.status = Customer.Status.SENT
        with self.assertRaises(ValidationError):
            customer.save(update_fields={"status"})
        customer.refresh_from_db()
        self.assertEqual(customer.status, Customer.Status.NO_CONTACT)

    def test_sent_status_rejects_inactive_assignee_from_model_write(self):
        inactive_user = get_user_model().objects.create_user(
            username="inactive-member", is_active=False
        )
        customer = Customer(name="Inactive assignment", assignee=inactive_user)
        with self.assertRaises(ValidationError):
            customer.status = Customer.Status.SENT
            customer.save()
        self.assertFalse(Customer.objects.exists())

    def test_sent_status_requires_assignee_in_database_too(self):
        customer = Customer.objects.create(name="Database constraint")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.filter(pk=customer.pk).update(
                status=Customer.Status.SENT
            )

    def test_status_changes_refresh_lifecycle_timestamp(self):
        customer = Customer.objects.create(name="Status change")
        previous_status_changed_at = customer.status_changed_at
        customer.status = Customer.Status.REJECTED
        customer.save(update_fields={"status"})
        customer.refresh_from_db()
        self.assertGreater(customer.status_changed_at, previous_status_changed_at)

    def test_assigned_customer_is_visible_in_tasks_and_sent_is_followup(self):
        self.client.post(
            reverse("crm:customer_create"),
            self.customer_data(
                name="Follow-up customer",
                status=Customer.Status.SENT,
                assignee=str(self.user.pk),
            ),
        )
        self.assertContains(
            self.client.get(reverse("crm:follow_ups")), "Follow-up customer"
        )
        self.assertContains(
            self.client.get(reverse("crm:tasks")), "Follow-up customer"
        )

    def test_completed_customers_have_a_separate_view(self):
        Customer.objects.create(name="Completed", status=Customer.Status.COMPLETED)
        response = self.client.get(reverse("crm:completed_customers"))
        self.assertContains(response, "Completed")
        self.assertNotContains(
            self.client.get(reverse("crm:customer_list")), "Completed"
        )

    def test_archive_and_trash_restore_to_followup_with_origin_marker(self):
        archived = Customer.objects.create(name="Archived")
        trashed = Customer.objects.create(name="Trashed")
        self.client.post(reverse("crm:customer_archive_action", args=[archived.pk]))
        self.client.post(reverse("crm:customer_delete", args=[trashed.pk]))

        archive_restore = self.client.post(
            reverse("crm:customer_restore", args=[archived.pk])
        )
        trash_restore = self.client.post(
            reverse("crm:customer_restore", args=[trashed.pk])
        )
        self.assertEqual(archive_restore.status_code, 302)
        self.assertEqual(trash_restore.status_code, 302)
        archived.refresh_from_db()
        trashed.refresh_from_db()
        self.assertEqual(archived.status, Customer.Status.FOLLOW_UP)
        self.assertEqual(archived.restored_from, Customer.RestoreSource.ARCHIVE)
        self.assertEqual(trashed.status, Customer.Status.FOLLOW_UP)
        self.assertEqual(trashed.restored_from, Customer.RestoreSource.TRASH)
        response = self.client.get(reverse("crm:follow_ups"))
        self.assertContains(response, "از بایگانی برگشته")
        self.assertContains(response, "از زباله‌دان برگشته")

    def test_due_rejected_customer_is_not_in_followups(self):
        Customer.objects.create(
            name="Rejected follow-up boundary",
            status=Customer.Status.REJECTED,
            status_changed_at=timezone.now() - timedelta(hours=2) - timedelta(seconds=1),
        )
        self.assertNotContains(
            self.client.get(reverse("crm:follow_ups")),
            "Rejected follow-up boundary",
        )
        self.assertContains(
            self.client.get(reverse("crm:customer_archive")),
            "Rejected follow-up boundary",
        )

    def test_rejected_customer_enters_archive_view_at_elapsed_two_hour_boundary(self):
        now = timezone.now()
        Customer.objects.create(
            name="Recently rejected", status=Customer.Status.REJECTED,
            status_changed_at=now - timedelta(hours=2) + timedelta(seconds=30),
        )
        due = Customer.objects.create(
            name="Archive due", status=Customer.Status.REJECTED,
            status_changed_at=now - timedelta(hours=2) - timedelta(seconds=30),
        )
        active = self.client.get(reverse("crm:customer_list"))
        archive = self.client.get(reverse("crm:customer_archive"))
        self.assertContains(active, "Recently rejected")
        self.assertNotContains(active, "Archive due")
        self.assertContains(archive, "Archive due")
        self.assertNotContains(archive, "Recently rejected")
        self.assertIsNone(due.archived_at)
        restored = self.client.post(
            reverse("crm:customer_restore", args=[due.pk])
        )
        self.assertEqual(restored.status_code, 302)
        due.refresh_from_db()
        self.assertEqual(due.status, Customer.Status.FOLLOW_UP)
        self.assertEqual(due.restored_from, Customer.RestoreSource.ARCHIVE)

    def test_create_edit_and_delete_keep_record_recoverable_in_trash(self):
        response = self.client.post(
            reverse("crm:customer_create"),
            self.customer_data(name="Before edit"),
        )
        customer = Customer.objects.get()
        self.client.post(
            reverse("crm:customer_update", args=[customer.pk]),
            self.customer_data(name="After edit"),
        )
        customer.refresh_from_db()
        self.assertEqual(customer.name, "After edit")
        response = self.client.post(
            reverse("crm:customer_delete", args=[customer.pk])
        )
        self.assertEqual(response.status_code, 302)
        customer.refresh_from_db()
        self.assertIsNotNone(customer.trashed_at)
        self.assertTrue(Customer.objects.filter(pk=customer.pk).exists())
        self.assertNotContains(
            self.client.get(reverse("crm:customer_list")), "After edit"
        )
        self.assertContains(
            self.client.get(reverse("crm:customer_trash")), "After edit"
        )

    def test_state_changing_routes_reject_get_requests(self):
        customer = Customer.objects.create(name="Method check")
        for route in ("customer_delete", "customer_archive_action"):
            with self.subTest(route=route):
                response = self.client.get(
                    reverse(f"crm:{route}", args=[customer.pk])
                )
                self.assertEqual(response.status_code, 405)

    def test_login_form_authenticates_team_user(self):
        self.client.logout()
        login_page = self.client.get(reverse("login"))
        self.assertEqual(login_page.status_code, 200)
        self.assertContains(login_page, "ورود اعضای تیم")
        self.assertNotContains(login_page, "sidebar-nav")
        response = self.client.post(
            reverse("login"),
            {"username": "team-member", "password": "safe-test-password"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("crm:customer_list"))
        self.assertContains(self.client.get(reverse("crm:customer_list")), "ثبت مشتری")

    def test_unauthenticated_users_cannot_view_or_change_customer_records(self):
        self.client.logout()
        active = Customer.objects.create(name="Protected active")
        archived = Customer.objects.create(name="Protected archive", archived_at=timezone.now())
        trashed = Customer.objects.create(name="Protected trash", trashed_at=timezone.now())
        get_routes = (
            reverse("crm:customer_list"), reverse("crm:customer_create"),
            reverse("crm:customer_update", args=[active.pk]),
            reverse("crm:follow_ups"), reverse("crm:tasks"), reverse("crm:completed_customers"),
            reverse("crm:customer_archive"), reverse("crm:customer_trash"),
            reverse("crm:customer_detail", args=[active.pk]),
        )
        for url in get_routes:
            with self.subTest(method="GET", url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)
        post_routes = (
            (reverse("crm:customer_create"), self.customer_data()),
            (reverse("crm:customer_update", args=[active.pk]), self.customer_data()),
            (reverse("crm:customer_delete", args=[active.pk]), {}),
            (reverse("crm:customer_archive_action", args=[active.pk]), {}),
            (reverse("crm:customer_restore", args=[archived.pk]), {}),
            (reverse("crm:customer_restore", args=[trashed.pk]), {}),
        )
        for url, data in post_routes:
            with self.subTest(method="POST", url=url):
                response = self.client.post(url, data)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)
        self.assertEqual(Customer.objects.count(), 3)

    def test_csrf_protection_is_enabled(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.user)
        active = Customer.objects.create(name="Active")
        archived = Customer.objects.create(name="Archived", archived_at=timezone.now())
        paths = (
            reverse("crm:customer_create"),
            reverse("crm:customer_update", args=[active.pk]),
            reverse("crm:customer_delete", args=[active.pk]),
            reverse("crm:customer_archive_action", args=[active.pk]),
            reverse("crm:customer_restore", args=[archived.pk]),
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(client.post(path, self.customer_data()).status_code, 403)


class CustomerLifecycleCommandTests(TestCase):
    def test_rejected_customer_archives_at_two_hour_boundary_and_retry_is_safe(self):
        now = timezone.now()
        not_due = Customer.objects.create(
            name="Not due", status=Customer.Status.REJECTED,
            status_changed_at=now - timedelta(hours=2) + timedelta(seconds=30),
        )
        due = Customer.objects.create(
            name="Due", status=Customer.Status.REJECTED,
            status_changed_at=now - timedelta(hours=2) - timedelta(seconds=1),
        )
        call_command("process_customer_lifecycle", stdout=StringIO())
        not_due.refresh_from_db()
        due.refresh_from_db()
        self.assertIsNone(not_due.archived_at)
        expected_archive_time = due.status_changed_at + timedelta(hours=2)
        self.assertEqual(due.archived_at, expected_archive_time)
        call_command("process_customer_lifecycle", stdout=StringIO())
        due.refresh_from_db()
        self.assertEqual(due.archived_at, expected_archive_time)

    def test_archive_and_trash_are_permanently_deleted_at_retention_boundaries(self):
        now = timezone.now()
        archived_due = Customer.objects.create(
            name="Archived due", archived_at=now - timedelta(days=30) - timedelta(seconds=1)
        )
        trash_due = Customer.objects.create(
            name="Trash due", trashed_at=now - timedelta(days=10) - timedelta(seconds=1)
        )
        archived_not_due = Customer.objects.create(
            name="Archived not due", archived_at=now - timedelta(days=30) + timedelta(seconds=30)
        )
        trash_not_due = Customer.objects.create(
            name="Trash not due", trashed_at=now - timedelta(days=10) + timedelta(seconds=30)
        )
        call_command("process_customer_lifecycle", stdout=StringIO())
        self.assertFalse(Customer.objects.filter(pk=archived_due.pk).exists())
        self.assertFalse(Customer.objects.filter(pk=trash_due.pk).exists())
        self.assertTrue(Customer.objects.filter(pk=archived_not_due.pk).exists())
        self.assertTrue(Customer.objects.filter(pk=trash_not_due.pk).exists())

    def test_restore_preserves_the_explicit_transition_timestamp(self):
        now = timezone.now() - timedelta(seconds=5)
        customer = Customer.objects.create(
            name="Restoration time", archived_at=now - timedelta(days=1)
        )
        self.assertTrue(customer.restore(now=now))
        customer.refresh_from_db()
        self.assertEqual(customer.status_changed_at, now)

    def test_auto_archived_rejected_customer_cannot_restore_after_archive_retention(self):
        now = timezone.now()
        expired_rejected = Customer.objects.create(
            name="Expired implicit archive",
            status=Customer.Status.REJECTED,
            status_changed_at=now - timedelta(days=31),
        )
        self.assertFalse(expired_rejected.restore(now=now))

    def test_restoration_is_refused_at_retention_expiry(self):
        now = timezone.now()
        archived = Customer.objects.create(
            name="Expired archive", archived_at=now - timedelta(days=30)
        )
        trashed = Customer.objects.create(
            name="Expired trash", trashed_at=now - timedelta(days=10)
        )
        self.assertFalse(archived.restore(now=now))
        self.assertFalse(trashed.restore(now=now))
        expired_rejected = Customer.objects.create(
            name="Expired implicit archive",
            status=Customer.Status.REJECTED,
            status_changed_at=now - timedelta(days=31),
        )
        self.assertFalse(expired_rejected.restore(now=now))
