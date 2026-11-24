from datetime import timedelta
from io import BytesIO, StringIO

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


class FakeHTTPResponse(BytesIO):
    status = 200


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


class CustomerCallHistoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="call-history-member", password="safe-test-password"
        )
        self.client.force_login(self.user)

    def test_call_record_stores_customer_number_and_supported_outcomes(self):
        from .models import CallRecord

        customer = Customer.objects.create(name="Call history customer")
        call = CallRecord.objects.create(
            customer=customer,
            dialed_number="test-dialed-number-answered",
            outcome=CallRecord.Outcome.ANSWERED,
        )

        self.assertEqual(call.customer, customer)
        self.assertEqual(call.dialed_number, "test-dialed-number-answered")
        self.assertEqual(
            [label for _, label in CallRecord.Outcome.choices],
            ["تماس پاسخ داده شده", "تماس مجدد"],
        )

    def test_customer_detail_displays_associated_calls(self):
        from .models import CallRecord

        customer = Customer.objects.create(name="History display")
        CallRecord.objects.create(
            customer=customer,
            dialed_number="test-dialed-number-displayed",
            outcome=CallRecord.Outcome.ANSWERED,
        )

        response = self.client.get(reverse("crm:customer_detail", args=[customer.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تاریخچهٔ تماس‌ها")
        self.assertContains(response, "test-dialed-number-displayed")
        self.assertContains(response, "تماس پاسخ داده شده")

    def test_customer_detail_does_not_show_another_customers_calls(self):
        from .models import CallRecord

        customer = Customer.objects.create(name="Own call history")
        other_customer = Customer.objects.create(name="Other call history")
        CallRecord.objects.create(
            customer=other_customer,
            dialed_number="test-dialed-number-other-customer",
            outcome=CallRecord.Outcome.CALL_AGAIN,
        )

        response = self.client.get(reverse("crm:customer_detail", args=[customer.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "test-dialed-number-other-customer")

    def test_call_outcome_update_cannot_change_another_customers_call(self):
        from .models import CallRecord

        customer = Customer.objects.create(name="Route customer")
        other_customer = Customer.objects.create(name="Other route customer")
        call = CallRecord.objects.create(
            customer=other_customer,
            dialed_number="test-dialed-number-route-scope",
            outcome=CallRecord.Outcome.ANSWERED,
        )

        response = self.client.post(
            f"/customers/{customer.pk}/calls/{call.pk}/outcome/",
            {"outcome": CallRecord.Outcome.CALL_AGAIN},
        )

        self.assertEqual(response.status_code, 404)
        call.refresh_from_db()
        self.assertEqual(call.outcome, CallRecord.Outcome.ANSWERED)

    def test_team_member_can_update_call_outcome_without_changing_customer_status(self):
        from .models import CallRecord

        customer = Customer.objects.create(
            name="Manual outcome update", status=Customer.Status.FOLLOW_UP
        )
        call = CallRecord.objects.create(
            customer=customer,
            dialed_number="test-dialed-number-update",
            outcome=CallRecord.Outcome.ANSWERED,
        )

        response = self.client.post(
            f"/customers/{customer.pk}/calls/{call.pk}/outcome/",
            {"outcome": CallRecord.Outcome.CALL_AGAIN},
        )

        self.assertEqual(response.status_code, 302)
        call.refresh_from_db()
        customer.refresh_from_db()
        self.assertEqual(call.outcome, CallRecord.Outcome.CALL_AGAIN)
        self.assertEqual(customer.status, Customer.Status.FOLLOW_UP)

    def test_unknown_call_outcome_is_rejected(self):
        from .models import CallRecord

        customer = Customer.objects.create(name="Invalid outcome")
        call = CallRecord.objects.create(
            customer=customer,
            dialed_number="test-dialed-number-invalid",
            outcome=CallRecord.Outcome.ANSWERED,
        )

        response = self.client.post(
            f"/customers/{customer.pk}/calls/{call.pk}/outcome/",
            {"outcome": "unsupported"},
        )

        self.assertEqual(response.status_code, 400)
        call.refresh_from_db()
        self.assertEqual(call.outcome, CallRecord.Outcome.ANSWERED)

    def test_call_outcome_update_requires_login(self):
        from .models import CallRecord

        customer = Customer.objects.create(name="Protected call")
        call = CallRecord.objects.create(
            customer=customer,
            dialed_number="test-dialed-number-auth",
            outcome=CallRecord.Outcome.ANSWERED,
        )
        self.client.logout()

        response = self.client.post(
            f"/customers/{customer.pk}/calls/{call.pk}/outcome/",
            {"outcome": CallRecord.Outcome.CALL_AGAIN},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        call.refresh_from_db()
        self.assertEqual(call.outcome, CallRecord.Outcome.ANSWERED)

    def test_call_outcome_update_rejects_get(self):
        from .models import CallRecord

        customer = Customer.objects.create(name="Read-only method")
        call = CallRecord.objects.create(
            customer=customer,
            dialed_number="test-dialed-number-get",
            outcome=CallRecord.Outcome.ANSWERED,
        )

        response = self.client.get(
            f"/customers/{customer.pk}/calls/{call.pk}/outcome/"
        )

        self.assertEqual(response.status_code, 405)


class NoghteStatusMappingTests(TestCase):
    def test_provider_statuses_map_to_only_the_approved_call_and_customer_states(self):
        from .integrations.noghte import map_call_status
        from .models import CallRecord

        self.assertEqual(
            map_call_status("answered"),
            (CallRecord.Outcome.ANSWERED, Customer.Status.REJECTED),
        )
        for provider_status in ("busy", "failed", "missed", "no_answer"):
            with self.subTest(provider_status=provider_status):
                self.assertEqual(
                    map_call_status(provider_status),
                    (CallRecord.Outcome.CALL_AGAIN, Customer.Status.CALL_AGAIN),
                )
        self.assertIsNone(map_call_status("unrecognized"))


class NoghteAPIClientTests(TestCase):
    def test_client_reads_bearer_key_uses_get_filters_and_follows_pages(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from urllib.parse import parse_qs, urlsplit

        from .integrations.noghte import NoghteAPIClient

        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = Path(temp_dir) / "api-key"
            key_file.write_text("synthetic-test-key", encoding="utf-8")
            key_file.chmod(0o600)
            page_payloads = (
                {"current_page": 1, "last_page": 2, "data": [{"id": "first"}]},
                {"current_page": 2, "last_page": 2, "data": [{"id": "second"}]},
            )
            responses = []
            for payload in page_payloads:
                response = FakeHTTPResponse(json.dumps(payload).encode())
                responses.append(response)

            with patch(
                "crm.integrations.noghte.urllib.request.urlopen", side_effect=responses
            ) as urlopen:
                client = NoghteAPIClient(api_key_file=key_file, retry_delay=0)
                calls = list(
                    client.iter_calls(number="test-customer-number", since="2026-11-22")
                )

        self.assertEqual([call["id"] for call in calls], ["first", "second"])
        self.assertEqual(urlopen.call_count, 2)
        first_request = urlopen.call_args_list[0].args[0]
        second_request = urlopen.call_args_list[1].args[0]
        self.assertEqual(first_request.get_method(), "GET")
        self.assertEqual(first_request.headers["Authorization"], "Bearer synthetic-test-key")
        self.assertEqual(first_request.headers["Accept"], "application/json")
        first_query = parse_qs(urlsplit(first_request.full_url).query)
        second_query = parse_qs(urlsplit(second_request.full_url).query)
        self.assertEqual(first_query["number"], ["test-customer-number"])
        self.assertEqual(first_query["since"], ["2026-11-22"])
        self.assertEqual(first_query["direction"], ["outbound"])
        self.assertNotIn("page", first_query)
        self.assertEqual(second_query["page"], ["2"])

    def test_client_rejects_out_of_sequence_page_without_requesting_a_later_page(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient, NoghteAPIError

        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = Path(temp_dir) / "api-key"
            key_file.write_text("synthetic-pagination-key", encoding="utf-8")
            key_file.chmod(0o600)
            client = NoghteAPIClient(api_key_file=key_file, retry_delay=0)
            responses = [
                FakeHTTPResponse(
                    json.dumps(
                        {"current_page": 2, "last_page": 3, "data": [{"id": "skipped-page"}]}
                    ).encode()
                ),
                FakeHTTPResponse(
                    json.dumps(
                        {"current_page": 3, "last_page": 3, "data": [{"id": "later-page"}]}
                    ).encode()
                ),
            ]
            with patch(
                "crm.integrations.noghte.urllib.request.urlopen", side_effect=responses
            ) as urlopen, self.assertRaises(NoghteAPIError):
                list(client.iter_calls(number="test-number", since="2026-11-22"))

        self.assertEqual(urlopen.call_count, 1)

    def test_client_rejects_group_or_world_readable_key_files(self):
        import tempfile
        from pathlib import Path

        from .integrations.noghte import NoghteAPIClient, NoghteAPIError

        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = Path(temp_dir) / "api-key"
            key_file.write_text("synthetic-insecure-secret", encoding="utf-8")
            key_file.chmod(0o644)

            with self.assertRaises(NoghteAPIError) as error:
                NoghteAPIClient(api_key_file=key_file)

        self.assertNotIn("synthetic-insecure-secret", str(error.exception))

    def test_incomplete_http_response_retries_without_exposing_partial_content(self):
        import tempfile
        from http.client import IncompleteRead
        from pathlib import Path
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient

        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = Path(temp_dir) / "api-key"
            key_file.write_text("synthetic-retry-secret", encoding="utf-8")
            key_file.chmod(0o600)
            client = NoghteAPIClient(api_key_file=key_file, retry_delay=0)
            partial = IncompleteRead(b'{"summary":"synthetic-partial-response"}')
            success = FakeHTTPResponse(
                b'{"current_page": 1, "last_page": 1, "data": []}'
            )
            with patch(
                "crm.integrations.noghte.urllib.request.urlopen",
                side_effect=[partial, success],
            ) as urlopen, patch("crm.integrations.noghte.time.sleep"):
                self.assertEqual(
                    list(client.iter_calls(number="test-number", since="2026-11-22")), []
                )

        self.assertEqual(urlopen.call_count, 2)

    def test_transient_http_failure_retries_and_auth_error_is_safe(self):
        import tempfile
        from email.message import Message
        from pathlib import Path
        from unittest.mock import patch
        from urllib.error import HTTPError

        from .integrations.noghte import NoghteAPIClient, NoghteAPIError

        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = Path(temp_dir) / "api-key"
            key_file.write_text("synthetic-secret-value", encoding="utf-8")
            key_file.chmod(0o600)
            client = NoghteAPIClient(api_key_file=key_file, retry_delay=0)
            transient_error = HTTPError(
                "https://api.phone.noghte.io/api/public/v1/calls", 503, "Unavailable", Message(), None
            )
            success = FakeHTTPResponse(
                b'{"current_page": 1, "last_page": 1, "data": []}'
            )
            with patch(
                "crm.integrations.noghte.urllib.request.urlopen",
                side_effect=[transient_error, success],
            ) as urlopen, patch("crm.integrations.noghte.time.sleep"):
                self.assertEqual(
                    list(client.iter_calls(number="test-number", since="2026-11-22")), []
                )
            self.assertEqual(urlopen.call_count, 2)

            forbidden = HTTPError(
                "https://api.phone.noghte.io/api/public/v1/calls", 403, "Forbidden", Message(), None
            )
            with patch(
                "crm.integrations.noghte.urllib.request.urlopen", side_effect=forbidden
            ) as urlopen, self.assertRaises(NoghteAPIError) as error:
                list(client.iter_calls(number="test-number", since="2026-11-22"))
            self.assertEqual(urlopen.call_count, 1)
            self.assertNotIn("synthetic-secret-value", str(error.exception))


class NoghteCallIdTests(TestCase):
    def test_provider_call_ids_are_unique_while_local_call_ids_remain_optional(self):
        from .models import CallRecord

        customer = Customer.objects.create(name="Provider call identity")
        CallRecord.objects.create(
            customer=customer,
            dialed_number="test-provider-number",
            outcome=CallRecord.Outcome.ANSWERED,
            external_id="provider-call-test-id",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CallRecord.objects.create(
                customer=customer,
                dialed_number="test-provider-number",
                outcome=CallRecord.Outcome.ANSWERED,
                external_id="provider-call-test-id",
            )
        CallRecord.objects.create(
            customer=customer,
            dialed_number="test-local-call-one",
            outcome=CallRecord.Outcome.CALL_AGAIN,
        )
        CallRecord.objects.create(
            customer=customer,
            dialed_number="test-local-call-two",
            outcome=CallRecord.Outcome.CALL_AGAIN,
        )
        self.assertEqual(CallRecord.objects.count(), 3)


class NoghteCallSyncCommandTests(TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        from django.test import override_settings

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.key_file = Path(self.temp_dir.name) / "api-key"
        self.key_file.write_text("synthetic-command-secret", encoding="utf-8")
        self.key_file.chmod(0o600)
        self.settings_override = override_settings(NOGHTE_API_KEY_FILE=str(self.key_file))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.call_time = (timezone.now() - timedelta(minutes=30)).replace(microsecond=0)
        self.since = self.call_time.date().isoformat()

    def make_customer(self, phone, *, status=Customer.Status.NO_CONTACT, changed_at=None):
        return Customer.objects.create(
            name="Synthetic phone customer",
            phone=phone,
            status=status,
            status_changed_at=changed_at or self.call_time - timedelta(days=1),
        )

    def provider_call(self, call_id, phone, *, status="answered", direction="outbound", when=None):
        when = when or self.call_time
        timestamp = when.isoformat().replace("+00:00", "Z")
        provider_call = {
            "id": call_id,
            "direction": direction,
            "status": status,
            "to": phone,
            "started_at": timestamp,
        }
        provider_call["answered_at" if status == "answered" else "ended_at"] = timestamp
        return provider_call

    def run_sync(self, stdout=None):
        call_command("sync_noghte_calls", "--since", self.since, stdout=stdout or StringIO())

    def test_answered_call_is_imported_and_sets_rejected_at_call_time(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient
        from .models import CallRecord

        customer = self.make_customer("test-known-number")
        provider_call = self.provider_call("provider-call-answered", customer.phone)
        output = StringIO()
        with patch.object(NoghteAPIClient, "iter_calls", return_value=iter([provider_call])):
            self.run_sync(output)

        call = CallRecord.objects.get(external_id="provider-call-answered")
        customer.refresh_from_db()
        self.assertEqual(call.customer, customer)
        self.assertEqual(call.dialed_number, customer.phone)
        self.assertEqual(call.outcome, CallRecord.Outcome.ANSWERED)
        self.assertEqual(call.called_at, self.call_time)
        self.assertEqual(customer.status, Customer.Status.REJECTED)
        self.assertEqual(customer.status_changed_at, self.call_time)
        self.assertNotIn(customer.phone, output.getvalue())
        self.assertNotIn("provider-call-answered", output.getvalue())

    def test_nonanswered_provider_statuses_set_call_again(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient
        from .models import CallRecord

        customers = {
            status: self.make_customer(f"test-number-{status}")
            for status in ("busy", "failed", "missed", "no_answer")
        }
        events = {
            customer.phone: [self.provider_call(f"provider-{status}", customer.phone, status=status)]
            for status, customer in customers.items()
        }
        with patch.object(
            NoghteAPIClient,
            "iter_calls",
            side_effect=lambda *, number, since: iter(events[number]),
        ):
            self.run_sync()

        for customer in customers.values():
            customer.refresh_from_db()
            self.assertEqual(customer.status, Customer.Status.CALL_AGAIN)
        self.assertEqual(
            set(CallRecord.objects.values_list("outcome", flat=True)),
            {CallRecord.Outcome.CALL_AGAIN},
        )

    def test_replay_preserves_manual_outcome_and_customer_status(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient
        from .models import CallRecord

        customer = self.make_customer("test-replay-number")
        provider_call = self.provider_call("provider-call-replay", customer.phone)
        with patch.object(
            NoghteAPIClient,
            "iter_calls",
            side_effect=[iter([provider_call]), iter([provider_call])],
        ):
            self.run_sync()
            call = CallRecord.objects.get(external_id="provider-call-replay")
            call.outcome = CallRecord.Outcome.CALL_AGAIN
            call.save(update_fields=("outcome",))
            customer.status = Customer.Status.FOLLOW_UP
            customer.status_changed_at = self.call_time + timedelta(minutes=1)
            customer.save(update_fields=("status", "status_changed_at", "updated_at"))
            self.run_sync()

        call.refresh_from_db()
        customer.refresh_from_db()
        self.assertEqual(CallRecord.objects.count(), 1)
        self.assertEqual(call.outcome, CallRecord.Outcome.CALL_AGAIN)
        self.assertEqual(customer.status, Customer.Status.FOLLOW_UP)
        self.assertEqual(customer.status_changed_at, self.call_time + timedelta(minutes=1))

    def test_manual_status_change_after_call_is_not_overwritten_by_later_sync(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient
        from .models import CallRecord

        manual_change_at = self.call_time + timedelta(minutes=1)
        customer = self.make_customer(
            "test-manual-status-number",
            status=Customer.Status.FOLLOW_UP,
            changed_at=manual_change_at,
        )
        provider_call = self.provider_call("provider-call-before-manual-change", customer.phone)
        with patch.object(NoghteAPIClient, "iter_calls", return_value=iter([provider_call])):
            self.run_sync()

        customer.refresh_from_db()
        self.assertEqual(customer.status, Customer.Status.FOLLOW_UP)
        self.assertEqual(customer.status_changed_at, manual_change_at)
        self.assertEqual(CallRecord.objects.count(), 1)

    def test_status_updated_during_provider_request_is_not_overwritten(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient
        from .models import CallRecord

        customer = self.make_customer("test-concurrent-status-number")
        manual_change_at = self.call_time + timedelta(minutes=1)
        provider_call = self.provider_call("provider-call-concurrent", customer.phone)

        def change_status_while_fetching(*, number, since):
            customer.status = Customer.Status.FOLLOW_UP
            customer.status_changed_at = manual_change_at
            customer.save(update_fields=("status", "status_changed_at", "updated_at"))
            return iter([provider_call])

        with patch.object(
            NoghteAPIClient, "iter_calls", side_effect=change_status_while_fetching
        ):
            self.run_sync()

        customer.refresh_from_db()
        self.assertEqual(customer.status, Customer.Status.FOLLOW_UP)
        self.assertEqual(customer.status_changed_at, manual_change_at)
        self.assertEqual(CallRecord.objects.count(), 1)

    def test_unmatched_and_unsupported_calls_are_not_associated(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient
        from .models import CallRecord

        customer = self.make_customer("test-expected-number")
        events = [
            self.provider_call("provider-mismatch", "test-other-number"),
            self.provider_call("provider-unsupported", customer.phone, status="queued"),
        ]
        with patch.object(NoghteAPIClient, "iter_calls", return_value=iter(events)):
            self.run_sync()

        customer.refresh_from_db()
        self.assertEqual(CallRecord.objects.count(), 0)
        self.assertEqual(customer.status, Customer.Status.NO_CONTACT)

    def test_duplicate_customer_numbers_are_skipped_without_provider_lookup(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient

        self.make_customer("test-duplicate-number")
        self.make_customer("test-duplicate-number")
        with patch.object(NoghteAPIClient, "iter_calls") as iter_calls:
            self.run_sync()

        iter_calls.assert_not_called()

    def test_number_shared_with_archived_customer_is_ambiguous_and_not_polled(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient

        self.make_customer("test-shared-number")
        archived = self.make_customer("test-shared-number")
        archived.archived_at = self.call_time
        archived.save(update_fields=("archived_at", "updated_at"))
        with patch.object(NoghteAPIClient, "iter_calls") as lookup:
            self.run_sync()

        lookup.assert_not_called()

    def test_archived_and_trashed_customers_are_not_polled_but_completed_customers_are(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient

        archived = self.make_customer("test-archived-number")
        archived.archived_at = self.call_time
        archived.save(update_fields=("archived_at", "updated_at"))
        trashed = self.make_customer("test-trashed-number")
        trashed.trashed_at = self.call_time
        trashed.save(update_fields=("trashed_at", "updated_at"))
        completed = self.make_customer(
            "test-completed-number", status=Customer.Status.COMPLETED
        )

        with patch.object(NoghteAPIClient, "iter_calls", return_value=iter([])) as lookup:
            self.run_sync()

        requested_numbers = [call.kwargs["number"] for call in lookup.call_args_list]
        self.assertEqual(requested_numbers, [completed.phone])

    def test_failed_partial_run_can_be_retried_without_duplicate_records_or_secret_leaks(self):
        from unittest.mock import patch

        from django.core.management.base import CommandError

        from .integrations.noghte import NoghteAPIClient, NoghteAPIError
        from .models import CallRecord

        first_customer = self.make_customer("test-failure-number-a")
        second_customer = self.make_customer("test-failure-number-b")
        first = self.provider_call("provider-call-before-failure", first_customer.phone)
        second = self.provider_call(
            "provider-call-after-failure",
            second_customer.phone,
            status="no_answer",
            when=self.call_time + timedelta(minutes=5),
        )

        output = StringIO()
        with patch.object(
            NoghteAPIClient,
            "iter_calls",
            side_effect=[iter([first]), NoghteAPIError("synthetic-command-secret"), iter([first]), iter([second])],
        ):
            with self.assertRaises(CommandError) as error:
                self.run_sync(output)
            self.assertNotIn("synthetic-command-secret", str(error.exception))
            self.assertEqual(CallRecord.objects.count(), 1)
            self.run_sync(output)

        self.assertEqual(CallRecord.objects.count(), 2)
        self.assertEqual(CallRecord.objects.filter(external_id="provider-call-before-failure").count(), 1)
        self.assertEqual(first_customer.call_records.count(), 1)
        self.assertEqual(second_customer.call_records.count(), 1)
        self.assertNotIn(first_customer.phone, output.getvalue())
        self.assertNotIn(second_customer.phone, output.getvalue())
        self.assertNotIn("provider-call-before-failure", output.getvalue())
