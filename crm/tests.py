from datetime import timedelta
from io import BytesIO, StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .forms import CustomerForm
from .jalali_calendar import build_month
from .models import CallRecord, Customer


def create_manager_user(username, **kwargs):
    user = get_user_model().objects.create_user(
        username=username, password="safe-test-password", **kwargs
    )
    group, _ = Group.objects.get_or_create(name="CRM Manager")
    user.groups.add(group)
    return user


class ExistingUserManagerRoleMigrationTests(TransactionTestCase):
    migrate_from = [
        ("crm", "0009_crm_role_groups"),
        ("crm", "0009_category_customer_numbers"),
    ]
    migrate_to = ("crm", "0010_elevate_existing_users_to_manager")

    def test_existing_users_become_managers_without_changing_other_groups(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        User = old_apps.get_model("auth", "User")
        Group = old_apps.get_model("auth", "Group")
        manager, _ = Group.objects.get_or_create(name="CRM Manager")
        marketer, _ = Group.objects.get_or_create(name="CRM Marketer")
        unrelated, _ = Group.objects.get_or_create(name="Unrelated test group")

        User.objects.create(username="existing-unassigned")
        marketer_user = User.objects.create(username="existing-marketer")
        dual_role_user = User.objects.create(username="existing-dual-role")
        marketer_user.groups.add(marketer)
        dual_role_user.groups.add(manager, marketer, unrelated)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        migrated_apps = executor.loader.project_state([self.migrate_to]).apps
        MigratedUser = migrated_apps.get_model("auth", "User")
        existing_usernames = (
            "existing-unassigned",
            "existing-marketer",
            "existing-dual-role",
        )
        for username in existing_usernames:
            with self.subTest(username=username):
                user = MigratedUser.objects.get(username=username)
                names = set(user.groups.values_list("name", flat=True))
                self.assertIn("CRM Manager", names)
                self.assertNotIn("CRM Marketer", names)
        self.assertIn(
            "Unrelated test group",
            set(
                MigratedUser.objects.get(username="existing-dual-role")
                .groups.values_list("name", flat=True)
            ),
        )
        future_user = MigratedUser.objects.create(username="future-unassigned")
        self.assertEqual(future_user.groups.count(), 0)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()


class CustomerNumberMigrationTests(TransactionTestCase):
    def test_existing_customers_are_numbered_by_creation_order(self):
        from datetime import datetime, timezone as datetime_timezone

        migrate_from = ("crm", "0007_customer_phone_secondary_customer_phone_tertiary")
        migrate_to = ("crm", "0008_customernumbersequence_customer_customer_number_and_more")
        executor = MigrationExecutor(connection)
        executor.migrate([migrate_from])
        old_customer = executor.loader.project_state([migrate_from]).apps.get_model(
            "crm", "Customer"
        )
        later = old_customer.objects.create(name="Later created")
        earlier = old_customer.objects.create(name="Earlier created")
        old_customer.objects.filter(pk=later.pk).update(
            created_at=datetime(2025, 1, 2, tzinfo=datetime_timezone.utc)
        )
        old_customer.objects.filter(pk=earlier.pk).update(
            created_at=datetime(2025, 1, 1, tzinfo=datetime_timezone.utc)
        )

        executor = MigrationExecutor(connection)
        executor.migrate([migrate_to])
        apps = executor.loader.project_state([migrate_to]).apps
        Customer = apps.get_model("crm", "Customer")
        Sequence = apps.get_model("crm", "CustomerNumberSequence")
        self.assertEqual(
            list(Customer.objects.order_by("customer_number").values_list("name", "customer_number")),
            [("Earlier created", 1), ("Later created", 2)],
        )
        self.assertEqual(Sequence.objects.get(pk=1).next_number, 3)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()


class CategoryCustomerNumberMigrationTests(TransactionTestCase):
    migrate_from = ("crm", "0008_customernumbersequence_customer_customer_number_and_more")
    migrate_to = ("crm", "0009_category_customer_numbers")

    def test_categories_receive_prefixes_and_uncategorized_numbers_stay_unchanged(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        Customer = old_apps.get_model("crm", "Customer")
        Customer.objects.create(name="Old company", category="company", customer_number=42)
        Customer.objects.create(name="Old retail", category="micro_business", customer_number=7)
        Customer.objects.create(name="Legacy unknown", category="uncategorized", customer_number=12)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        apps = executor.loader.project_state([self.migrate_to]).apps
        Customer = apps.get_model("crm", "Customer")
        Sequence = apps.get_model("crm", "CustomerNumberSequence")
        self.assertEqual(Customer.objects.get(name="Old company").customer_number, "C01")
        self.assertEqual(Customer.objects.get(name="Old retail").customer_number, "A01")
        self.assertEqual(Customer.objects.get(name="Legacy unknown").customer_number, "12")
        self.assertEqual(Sequence.objects.get(category="uncategorized").next_number, 13)
        self.assertEqual(Sequence.objects.get(category="company").next_number, 2)
        self.assertEqual(Sequence.objects.get(category="micro_business").next_number, 2)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()


class CustomerPhoneMigrationTests(TransactionTestCase):
    migrate_from = ("crm", "0006_customer_category")
    migrate_to = ("crm", "0007_customer_phone_secondary_customer_phone_tertiary")

    def migrate_to_target(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        return executor.loader.project_state([target]).apps

    def test_existing_primary_phone_survives_adding_optional_phone_columns(self):
        old_apps = self.migrate_to_target(self.migrate_from)
        old_customer = old_apps.get_model("crm", "Customer")
        old_customer.objects.create(name="Existing phone", phone="5550901")

        new_apps = self.migrate_to_target(self.migrate_to)
        migrated_customer = new_apps.get_model("crm", "Customer").objects.get(
            name="Existing phone"
        )
        self.assertEqual(migrated_customer.phone, "5550901")
        self.assertEqual(migrated_customer.phone_secondary, "")
        self.assertEqual(migrated_customer.phone_tertiary, "")

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()


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
        self.user = create_manager_user("login-gate-user")

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


class CrmRoleAccessTests(TestCase):
    def create_user_with_role(self, username, role, **kwargs):
        user = get_user_model().objects.create_user(
            username=username, password="safe-test-password", **kwargs
        )
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
        return user

    def setUp(self):
        self.manager = self.create_user_with_role("role-manager", "CRM Manager")
        self.marketer = self.create_user_with_role("role-marketer", "CRM Marketer")
        self.other_marketer = self.create_user_with_role(
            "other-marketer", "CRM Marketer"
        )
        self.manager_customer = Customer.objects.create(name="Manager-only record")
        self.assigned_customer = Customer.objects.create(
            name="Assigned record", assignee=self.marketer,
            status=Customer.Status.FOLLOW_UP,
        )
        self.other_customer = Customer.objects.create(
            name="Other marketer record", assignee=self.other_marketer,
            status=Customer.Status.FOLLOW_UP,
        )
        self.unassigned_customer = Customer.objects.create(name="Unassigned record")

    def test_marketer_sees_only_assigned_customers_and_their_followups(self):
        self.client.force_login(self.marketer)
        customers = self.client.get(reverse("crm:customer_list"))
        followups = self.client.get(reverse("crm:follow_ups"))

        self.assertEqual(customers.status_code, 200)
        self.assertContains(customers, "Assigned record")
        self.assertNotContains(customers, "Other marketer record")
        self.assertNotContains(customers, "Unassigned record")
        self.assertNotContains(customers, "Manager-only record")
        self.assertNotContains(customers, 'href="/customers/new/"')
        self.assertNotContains(customers, 'href="/finance/')
        self.assertNotContains(customers, 'href="/customers/completed/"')
        self.assertContains(followups, "Assigned record")
        self.assertNotContains(followups, "Other marketer record")

    def test_marketer_root_redirects_to_customer_workflow(self):
        self.client.force_login(self.marketer)
        response = self.client.get(reverse("crm:home"))
        self.assertRedirects(response, reverse("crm:customer_list"))

    def test_marketer_can_read_assigned_detail_without_mutation_controls(self):
        self.client.force_login(self.marketer)
        response = self.client.get(
            reverse("crm:customer_detail", args=[self.assigned_customer.pk])
        )
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "ویرایش")
        self.assertNotContains(response, 'action="/customers/')

    def test_marketer_sees_assigned_call_history_and_manager_can_edit_it(self):
        from .models import CallRecord

        CallRecord.objects.create(
            customer=self.assigned_customer,
            dialed_number="safe-role-call",
            outcome=CallRecord.Outcome.ANSWERED,
        )
        self.client.force_login(self.marketer)
        response = self.client.get(
            reverse("crm:customer_detail", args=[self.assigned_customer.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تاریخچهٔ تماس‌ها")
        self.assertContains(response, "safe-role-call")
        self.assertContains(response, "تماس پاسخ داده شده")
        self.assertNotContains(response, 'name="outcome"')

        self.client.force_login(self.manager)
        manager_response = self.client.get(
            reverse("crm:customer_detail", args=[self.assigned_customer.pk])
        )
        self.assertEqual(manager_response.status_code, 200)
        self.assertContains(manager_response, "safe-role-call")
        self.assertContains(manager_response, 'name="outcome"')

    def test_marketer_cannot_open_unassigned_or_another_marketers_customer(self):
        self.client.force_login(self.marketer)
        for customer in (self.other_customer, self.unassigned_customer):
            with self.subTest(customer=customer.name):
                response = self.client.get(
                    reverse("crm:customer_detail", args=[customer.pk])
                )
                self.assertEqual(response.status_code, 404)

    def test_marketer_cannot_use_write_actions_or_other_crm_areas(self):
        self.client.force_login(self.marketer)
        call = CallRecord.objects.create(
            customer=self.assigned_customer,
            dialed_number="safe-test-number",
            outcome=CallRecord.Outcome.ANSWERED,
        )
        denied = (
            self.client.post(reverse("crm:customer_create"), {"name": "Injected"}),
            self.client.post(
                reverse("crm:customer_update", args=[self.assigned_customer.pk]),
                {"name": "Changed"},
            ),
            self.client.post(
                reverse("crm:customer_delete", args=[self.assigned_customer.pk])
            ),
            self.client.post(
                reverse("crm:customer_archive_action", args=[self.assigned_customer.pk])
            ),
            self.client.post(
                reverse("crm:customer_restore", args=[self.assigned_customer.pk])
            ),
            self.client.post(
                reverse(
                    "crm:call_outcome_update",
                    args=[self.assigned_customer.pk, call.pk],
                ),
                {"outcome": CallRecord.Outcome.CALL_AGAIN},
            ),
            self.client.get(reverse("crm:tasks")),
            self.client.get(reverse("crm:completed_customers")),
            self.client.get(reverse("crm:customer_archive")),
            self.client.get(reverse("crm:customer_trash")),
            self.client.get(reverse("crm:calendar")),
            self.client.get(reverse("crm:office_inventory")),
        )
        self.assertTrue(all(response.status_code == 403 for response in denied))
        self.assigned_customer.refresh_from_db()
        self.assertEqual(self.assigned_customer.name, "Assigned record")
        self.assertFalse(Customer.objects.filter(name="Injected").exists())

    def test_marketer_cannot_enter_django_admin_even_if_staff(self):
        self.marketer.is_staff = True
        self.marketer.save(update_fields={"is_staff"})
        self.client.force_login(self.marketer)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 403)

    def test_unassigned_user_has_no_crm_access(self):
        user = get_user_model().objects.create_user(
            username="role-unassigned", password="safe-test-password"
        )
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("crm:customer_list")).status_code, 403)

    def test_user_with_conflicting_roles_has_no_crm_access(self):
        user = self.create_user_with_role("conflicting-role-user", "CRM Manager")
        marketer_group, _ = Group.objects.get_or_create(name="CRM Marketer")
        user.groups.add(marketer_group)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("crm:customer_list")).status_code, 403)

    def test_unassigned_superuser_can_explicitly_bootstrap_roles_in_admin(self):
        user = get_user_model().objects.create_superuser(
            username="role-bootstrap-admin", password="safe-test-password",
            email="bootstrap@example.invalid",
        )
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_manager_retains_full_customer_access_and_can_create(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("crm:customer_list"))
        self.assertContains(response, "Manager-only record")
        self.assertContains(response, "Assigned record")
        created = self.client.post(
            reverse("crm:customer_create"),
            {
                "name": "Manager-created record",
"category": Customer.Category.CRM,
                "status": Customer.Status.NO_CONTACT,
            },
        )
        self.assertEqual(created.status_code, 302)
        self.assertTrue(Customer.objects.filter(name="Manager-created record").exists())


class DisplayOnlyPagesTests(TestCase):
    def setUp(self):
        self.user = create_manager_user("demo-reader")
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
                expected_current_pages = 3 if name == "customer_list" else 1
                self.assertEqual(
                    response.content.decode().count('aria-current="page"'),
                    expected_current_pages,
                )
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

    def test_customer_navigation_is_first_and_brand_logo_is_accessible(self):
        response = self.client.get(reverse("crm:customer_list"))
        html = response.content.decode()
        self.assertLess(html.index("بازاریابی و مشتریان"), html.index("داخلی"))
        self.assertContains(response, '<img class="brand-logo" src="/static/crm/binux-logo.png" alt="Binux CRM">', html=True)

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
        self.user = create_manager_user("calendar-reader")
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

        self.user = create_manager_user("team-member")
        self.client.force_login(self.user)

    def customer_data(self, **overrides):
        data = {
            "name": "",
            "business_type": "",
            "business_name": "",
            "category": Customer.Category.CRM,
            "phone": "",
            "phone_secondary": "",
            "phone_tertiary": "",
            "status": Customer.Status.NO_CONTACT,
            "source": "",
            "address": "",
            "notes": "",
            "assignee": "",
        }
        data.update(overrides)
        return data

    def test_customer_numbers_are_sequential_unique_and_displayed_with_minimum_two_digits(self):
        first = Customer.objects.create(name="First numbered", category=Customer.Category.COMPANY)
        second = Customer.objects.create(name="Second numbered", category=Customer.Category.COMPANY)
        retail = Customer.objects.create(name="Retail numbered", category=Customer.Category.MICRO_BUSINESS)
        crm_customer = Customer.objects.create(name="CRM numbered", category=Customer.Category.CRM)
        erp_customer = Customer.objects.create(name="ERP numbered", category=Customer.Category.ERP)
        self.assertEqual((first.customer_number, second.customer_number), ("C01", "C02"))
        self.assertEqual(retail.customer_number, "A01")
        self.assertEqual(crm_customer.customer_number, "M01")
        self.assertEqual(erp_customer.customer_number, "E01")
        first.delete()
        third = Customer.objects.create(name="Third numbered", category=Customer.Category.COMPANY)
        self.assertEqual(third.customer_number, "C03")

        response = self.client.get(reverse("crm:customer_list"))
        self.assertContains(response, "C02")
        self.assertContains(response, "C03")
        self.assertContains(response, "A01")

    def test_customer_number_database_constraint_rejects_duplicate_values(self):
        Customer.objects.create(name="First company", category=Customer.Category.COMPANY)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.bulk_create(
                [Customer(name="Duplicate", category=Customer.Category.COMPANY, customer_number="C01")]
            )

    def test_customer_number_supports_three_digits(self):
        from .models import CustomerNumberSequence

        CustomerNumberSequence.objects.filter(category=Customer.Category.ERP).update(next_number=100)
        customer = Customer.objects.create(name="Hundredth ERP", category=Customer.Category.ERP)
        self.assertEqual(customer.customer_number, "E100")

    def test_customer_creation_reports_number_capacity_exhaustion(self):
        from .models import CustomerNumberSequence

        CustomerNumberSequence.objects.filter(category=Customer.Category.COMPANY).update(next_number=10000)
        response = self.client.post(
            reverse("crm:customer_create"), self.customer_data(name="At capacity", category=Customer.Category.COMPANY)
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ظرفیت شماره مشتری‌های این دسته تکمیل شده است.")
        self.assertFalse(Customer.objects.filter(name="At capacity").exists())

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

    def test_customer_category_is_required_and_can_be_selected_on_customer_form(self):
        default_response = self.client.post(reverse("crm:customer_create"), {})
        self.assertEqual(default_response.status_code, 200)
        self.assertFalse(Customer.objects.exists())
        selected_response = self.client.post(
            reverse("crm:customer_create"),
            self.customer_data(name="ERP customer", category=Customer.Category.ERP),
        )
        self.assertEqual(selected_response.status_code, 302)
        selected_customer = Customer.objects.get(name="ERP customer")
        self.assertEqual(selected_customer.category, Customer.Category.ERP)
        response = self.client.get(reverse("crm:customer_create"))
        self.assertContains(response, "دسته مشتری")
        self.assertContains(response, "مشتری ERP")

    def test_customer_list_category_and_status_tabs_filter_and_preserve_name(self):
        match = Customer.objects.create(
            name="Filtered ERP", category=Customer.Category.ERP,
            status=Customer.Status.FOLLOW_UP,
        )
        Customer.objects.create(
            name="Filtered CRM", category=Customer.Category.CRM,
            status=Customer.Status.FOLLOW_UP,
        )
        Customer.objects.create(
            name="Filtered ERP, no contact", category=Customer.Category.ERP,
            status=Customer.Status.NO_CONTACT,
        )
        Customer.objects.create(
            name="Archived ERP", category=Customer.Category.ERP,
            status=Customer.Status.FOLLOW_UP, archived_at=timezone.now(),
        )
        Customer.objects.create(
            name="Trashed ERP", category=Customer.Category.ERP,
            status=Customer.Status.FOLLOW_UP, trashed_at=timezone.now(),
        )
        Customer.objects.create(
            name="Filtered ERP, completed", category=Customer.Category.ERP,
            status=Customer.Status.COMPLETED,
        )
        response = self.client.get(reverse("crm:customer_list"), {
            "name": "Filtered", "category": Customer.Category.ERP,
            "status": Customer.Status.FOLLOW_UP,
        })
        self.assertEqual(list(response.context["customers"]), [match])
        self.assertContains(response, 'aria-label="دسته‌بندی مشتریان"')
        self.assertContains(response, 'aria-label="وضعیت مشتریان"')
        self.assertContains(response, "name=Filtered&amp;category=erp&amp;status=follow_up")
        self.assertEqual(
            [tab["label"] for tab in response.context["status_tabs"]],
            ["همهٔ وضعیت‌ها", "بدون تماس", "رد شده", "پیگیری", "ارسالی", "تماس مجدد", "انجام شده"],
        )
        completed_tab_url = response.context["status_tabs"][-1]["url"]
        self.assertEqual(
            completed_tab_url,
            reverse("crm:completed_customers")
            + "?name=Filtered&category=erp",
        )
        completed_response = self.client.get(completed_tab_url)
        self.assertContains(completed_response, "Filtered ERP, completed")
        self.assertNotContains(completed_response, "Filtered ERP</a>")

    def test_customer_form_persists_three_optional_phone_numbers(self):
        response = self.client.post(
            reverse("crm:customer_create"),
            self.customer_data(
                name="Three phone test",
                phone="5550101",
                phone_secondary="5550102",
                phone_tertiary="5550103",
            ),
        )
        self.assertEqual(response.status_code, 302)
        customer = Customer.objects.get(name="Three phone test")
        self.assertEqual(customer.phone, "5550101")
        self.assertEqual(customer.phone_secondary, "5550102")
        self.assertEqual(customer.phone_tertiary, "5550103")

        edit_response = self.client.get(
            reverse("crm:customer_update", args=[customer.pk])
        )
        self.assertContains(edit_response, "شماره تلفن دوم")
        self.assertContains(edit_response, "شماره تلفن سوم")
        self.assertContains(edit_response, 'value="5550102"')
        self.assertContains(edit_response, 'value="5550103"')

        update_response = self.client.post(
            reverse("crm:customer_update", args=[customer.pk]),
            self.customer_data(
                name="Three phone test",
                phone="5550104",
                phone_secondary="5550105",
                phone_tertiary="",
            ),
        )
        self.assertEqual(update_response.status_code, 302)
        customer.refresh_from_db()
        self.assertEqual(customer.phone, "5550104")
        self.assertEqual(customer.phone_secondary, "5550105")
        self.assertEqual(customer.phone_tertiary, "")

        detail_response = self.client.get(
            reverse("crm:customer_detail", args=[customer.pk])
        )
        self.assertContains(detail_response, "5550104")
        self.assertContains(detail_response, "5550105")
        self.assertNotContains(detail_response, "5550103")

    def test_customer_list_add_phone_action_only_shows_below_three_numbers(self):
        addable = Customer.objects.create(name="Add a phone", phone="5550201")
        second_slot = Customer.objects.create(
            name="Add the third phone", phone="5550202", phone_secondary="5550203"
        )
        missing_primary = Customer.objects.create(
            name="Fill missing primary", phone_secondary="5550252",
            phone_tertiary="5550253",
        )
        full = Customer.objects.create(
            name="All phones", phone="5550301", phone_secondary="5550302",
            phone_tertiary="5550303",
        )
        response = self.client.get(reverse("crm:customer_list"))
        self.assertContains(response, "5550201")
        self.assertContains(response, "5550301")
        self.assertContains(response, "5550302")
        self.assertContains(response, "5550303")
        self.assertContains(response, "افزودن شماره")
        self.assertContains(
            response,
            f'href="{reverse("crm:customer_update", args=[addable.pk])}#id_phone_secondary"',
        )
        self.assertContains(
            response,
            f'href="{reverse("crm:customer_update", args=[second_slot.pk])}#id_phone_tertiary"',
        )
        self.assertContains(
            response,
            f'href="{reverse("crm:customer_update", args=[missing_primary.pk])}#id_phone"',
        )
        self.assertFalse(full.can_add_phone)
        self.assertNotContains(
            response,
            f'href="{reverse("crm:customer_update", args=[full.pk])}#id_phone_secondary"',
        )

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

    def test_non_category_customer_fields_are_optional_and_record_persists(self):
        response = self.client.post(
            reverse("crm:customer_create"),
            self.customer_data(category=Customer.Category.ERP),
        )
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
        self.user = create_manager_user("call-history-member")
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
            ["تماس پاسخ داده شده", "تماس مجدد", "نامشخص / پشتیبانی‌نشده"],
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
        self.assertEqual(
            map_call_status("unrecognized"),
            (CallRecord.Outcome.UNKNOWN, None),
        )
        self.assertIsNone(map_call_status(""))
        self.assertIsNone(map_call_status(None))


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
            call.outcome_locked = True
            call.save(update_fields=("outcome", "outcome_locked"))
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

    def test_unmatched_calls_are_not_associated_and_unknown_status_is_recorded(self):
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
        call = CallRecord.objects.get(external_id="provider-unsupported")
        self.assertEqual(call.customer, customer)
        self.assertEqual(call.outcome, CallRecord.Outcome.UNKNOWN)
        self.assertFalse(CallRecord.objects.filter(external_id="provider-mismatch").exists())
        self.assertEqual(customer.status, Customer.Status.NO_CONTACT)

    def test_later_poll_refines_an_unlocked_unknown_outcome(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient
        from .models import CallRecord

        customer = self.make_customer("09120001122")
        unknown = self.provider_call("provider-refine", "+989120001122", status="queued")
        answered = self.provider_call("provider-refine", "+989120001122", status="answered")
        with patch.object(
            NoghteAPIClient,
            "iter_calls",
            side_effect=[iter([unknown]), iter([answered])],
        ):
            self.run_sync()
            call = CallRecord.objects.get(external_id="provider-refine")
            self.assertEqual(call.outcome, CallRecord.Outcome.UNKNOWN)
            self.run_sync()

        call.refresh_from_db()
        customer.refresh_from_db()
        self.assertEqual(CallRecord.objects.count(), 1)
        self.assertEqual(call.outcome, CallRecord.Outcome.ANSWERED)
        self.assertFalse(call.outcome_locked)
        self.assertEqual(customer.status, Customer.Status.REJECTED)

    def test_iranian_number_formats_match_and_equivalent_duplicates_are_ambiguous(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient
        from .models import CallRecord

        customer = self.make_customer("09121234567")
        provider_call = self.provider_call("provider-normalized", "+989121234567")
        with patch.object(NoghteAPIClient, "iter_calls", return_value=iter([provider_call])) as lookup:
            self.run_sync()

        call = CallRecord.objects.get(external_id="provider-normalized")
        customer.refresh_from_db()
        self.assertEqual(call.customer, customer)
        self.assertEqual(call.dialed_number, "+989121234567")
        self.assertEqual(customer.status, Customer.Status.REJECTED)
        self.assertEqual(lookup.call_args.kwargs["number"], "09121234567")

        self.make_customer("9125556677")
        self.make_customer("+989125556677")
        with patch.object(
            NoghteAPIClient, "iter_calls", side_effect=lambda **kwargs: iter([])
        ) as lookup:
            self.run_sync()
        requested = [call.kwargs["number"] for call in lookup.call_args_list]
        self.assertNotIn("9125556677", requested)
        self.assertNotIn("+989125556677", requested)

    def test_secondary_and_tertiary_numbers_are_polled_and_associated(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient
        from .models import CallRecord

        secondary = self.make_customer("")
        secondary.phone_secondary = "09123330000"
        secondary.save(update_fields=("phone", "phone_secondary", "updated_at"))
        tertiary = self.make_customer("")
        tertiary.phone_tertiary = "9144400000"
        tertiary.save(update_fields=("phone", "phone_tertiary", "updated_at"))
        calls = {
            "09123330000": [self.provider_call("provider-secondary", "+989123330000")],
            "9144400000": [
                self.provider_call("provider-tertiary", "09144400000", status="no_answer")
            ],
        }
        with patch.object(
            NoghteAPIClient,
            "iter_calls",
            side_effect=lambda *, number, since: iter(calls[number]),
        ) as lookup:
            self.run_sync()

        self.assertEqual(
            CallRecord.objects.get(external_id="provider-secondary").customer, secondary
        )
        tertiary_call = CallRecord.objects.get(external_id="provider-tertiary")
        self.assertEqual(tertiary_call.customer, tertiary)
        self.assertEqual(tertiary_call.outcome, CallRecord.Outcome.CALL_AGAIN)
        self.assertCountEqual(
            [call.kwargs["number"] for call in lookup.call_args_list],
            ["09123330000", "9144400000"],
        )

    def test_number_shared_across_customer_slots_is_not_polled(self):
        from unittest.mock import patch

        from .integrations.noghte import NoghteAPIClient

        left = self.make_customer("")
        left.phone_secondary = "09126667777"
        left.save(update_fields=("phone", "phone_secondary", "updated_at"))
        self.make_customer("+989126667777")
        with patch.object(
            NoghteAPIClient, "iter_calls", side_effect=lambda **kwargs: iter([])
        ) as lookup:
            self.run_sync()

        requested = [call.kwargs["number"] for call in lookup.call_args_list]
        self.assertNotIn("09126667777", requested)
        self.assertNotIn("+989126667777", requested)

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


class ManagerUserManagementTests(TestCase):
    def setUp(self):
        self.manager = create_manager_user("user-management-manager")
        self.client.force_login(self.manager)

    def test_manager_can_open_user_management_page(self):
        response = self.client.get(reverse("crm:user_management"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "افزودن کاربر")
        self.assertContains(response, "user-management-manager")

    def test_manager_can_create_account_with_explicit_role_and_hashed_password(self):
        response = self.client.post(
            reverse("crm:user_management"),
            {
                "action": "create",
                "username": "new-marketer",
                "password1": "Good-Example-Password-42!",
                "password2": "Good-Example-Password-42!",
                "role": "CRM Marketer",
            },
        )

        self.assertEqual(response.status_code, 302)
        created = get_user_model().objects.get(username="new-marketer")
        self.assertTrue(created.check_password("Good-Example-Password-42!"))
        self.assertEqual(
            set(created.groups.values_list("name", flat=True)), {"CRM Marketer"}
        )
        self.assertNotIn("Good-Example-Password-42!", response.content.decode())

    def test_manager_can_create_a_manager_account(self):
        response = self.client.post(
            reverse("crm:user_management"),
            {
                "action": "create",
                "username": "new-manager",
                "password1": "Another-Safe-Password-52!",
                "password2": "Another-Safe-Password-52!",
                "role": "CRM Manager",
            },
        )

        self.assertEqual(response.status_code, 302)
        created = get_user_model().objects.get(username="new-manager")
        self.assertEqual(
            set(created.groups.values_list("name", flat=True)), {"CRM Manager"}
        )

    def test_invalid_creation_does_not_create_account(self):
        response = self.client.post(
            reverse("crm:user_management"),
            {
                "action": "create",
                "username": "new-marketer",
                "password1": "weak",
                "password2": "different",
                "role": "CRM Marketer",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="new-marketer").exists())

    def test_manager_can_change_role_and_deactivate_user(self):
        user = get_user_model().objects.create_user(username="role-change-user")
        response = self.client.post(
            reverse("crm:user_management"),
            {
                "action": "update",
                "user_id": user.pk,
                "role": "CRM Marketer",
                "is_active": "",
                "confirm": "yes",
            },
        )

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(set(user.groups.values_list("name", flat=True)), {"CRM Marketer"})

        response = self.client.post(
            reverse("crm:user_management"),
            {
                "action": "update",
                "user_id": user.pk,
                "role": "CRM Marketer",
                "is_active": "on",
                "confirm": "yes",
            },
            follow=True,
        )
        self.assertContains(response, "تغییرات حساب با موفقیت ذخیره شد.")
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_user_changes_require_confirmation(self):
        user = get_user_model().objects.create_user(username="unconfirmed-user")
        response = self.client.post(
            reverse("crm:user_management"),
            {
                "action": "update",
                "user_id": user.pk,
                "role": "CRM Marketer",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(user.groups.filter(name="CRM Marketer").exists())

    def test_marketer_cannot_open_or_submit_user_management(self):
        marketer = get_user_model().objects.create_user(
            username="user-management-marketer", password="safe-test-password"
        )
        marketer.groups.add(Group.objects.get_or_create(name="CRM Marketer")[0])
        self.client.force_login(marketer)

        get_response = self.client.get(reverse("crm:user_management"))
        post_response = self.client.post(
            reverse("crm:user_management"),
            {
                "action": "create",
                "username": "forbidden-user",
                "password1": "Good-Example-Password-42!",
                "password2": "Good-Example-Password-42!",
                "role": "CRM Manager",
            },
        )

        self.assertEqual(get_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username="forbidden-user").exists())

    def test_inactive_user_cannot_authenticate(self):
        user = get_user_model().objects.create_user(
            username="deactivated-user", password="safe-test-password", is_active=False
        )

        self.assertFalse(
            self.client.login(username=user.username, password="safe-test-password")
        )

    def test_inactive_users_cannot_receive_new_customer_assignments(self):
        inactive_user = get_user_model().objects.create_user(
            username="inactive-assignee", is_active=False
        )
        form = CustomerForm(
            data={
                "name": "New customer",
                "category": Customer.Category.CRM,
                "assignee": inactive_user.pk,
            }
        )

        self.assertFalse(form.is_valid())
        with self.assertRaises(ValidationError):
            Customer.objects.create(
                name="New customer", category=Customer.Category.CRM,
                assignee=inactive_user,
            )

    def test_customer_forms_preserve_an_existing_inactive_assignee(self):
        user = get_user_model().objects.create_user(username="historical-assignee")
        customer = Customer.objects.create(
            name="Previously assigned", category=Customer.Category.CRM, assignee=user
        )
        user.is_active = False
        user.save(update_fields={"is_active"})
        form = CustomerForm(
            data={
                "name": "Previously assigned",
                "category": Customer.Category.CRM,
                "status": Customer.Status.NO_CONTACT,
                "assignee": user.pk,
            },
            instance=customer,
        )

        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.assignee_id, user.pk)

    def test_existing_assignment_is_preserved_after_user_deactivation(self):
        user = get_user_model().objects.create_user(username="historical-assignee")
        customer = Customer.objects.create(
            name="Previously assigned", category=Customer.Category.CRM, assignee=user
        )
        user.is_active = False
        user.save(update_fields={"is_active"})

        customer.notes = "Retained attribution"
        customer.save()
        customer.refresh_from_db()

        self.assertEqual(customer.assignee_id, user.pk)
        self.assertEqual(customer.notes, "Retained attribution")

    def test_manager_cannot_deactivate_self_or_the_last_active_manager(self):
        response = self.client.post(
            reverse("crm:user_management"),
            {
                "action": "update",
                "user_id": self.manager.pk,
                "role": "CRM Manager",
                "is_active": "",
                "confirm": "yes",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)


class CustomerAssignmentTests(TestCase):
    def setUp(self):
        self.manager = create_manager_user("assignment-manager")
        self.recipient = get_user_model().objects.create_user(username="assignment-recipient")
        self.client.force_login(self.manager)
        self.url = reverse("crm:customer_assignment")

    def post_selection(self, *, mode="range", category=Customer.Category.COMPANY,
                       start=1, end=1, numbers="", assignee=None):
        return self.client.post(self.url, {
            "mode": mode,
            "category": category,
            "start_number": start,
            "end_number": end,
            "customer_numbers": numbers,
            "assignee": (assignee or self.recipient).pk,
        })

    def test_manager_can_assign_category_scoped_inclusive_number_range(self):
        first = Customer.objects.create(name="Range first", category=Customer.Category.COMPANY)
        second = Customer.objects.create(name="Range second", category=Customer.Category.COMPANY)
        same_suffix_other_category = Customer.objects.create(
            name="Other category", category=Customer.Category.CRM
        )

        response = self.post_selection(start=1, end=2)

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        same_suffix_other_category.refresh_from_db()
        self.assertEqual(first.assignee_id, self.recipient.pk)
        self.assertEqual(second.assignee_id, self.recipient.pk)
        self.assertIsNone(same_suffix_other_category.assignee_id)
        self.assertEqual(first.assignment_history.get().assigned_by, self.manager)
        self.assertContains(response, "C01")
        self.assertContains(response, "C02")

    def test_repeated_submission_does_not_create_duplicate_assignment(self):
        customer = Customer.objects.create(name="Duplicate submission", category=Customer.Category.COMPANY)

        self.post_selection()
        response = self.post_selection()

        customer.refresh_from_db()
        self.assertEqual(customer.assignee_id, self.recipient.pk)
        self.assertEqual(customer.assignment_history.count(), 1)
        self.assertContains(response, "این مشتری قبلاً ارجاع شده")

    def test_explicit_number_selection_and_missing_number_are_reported(self):
        customer = Customer.objects.create(name="Explicit choice", category=Customer.Category.CRM)

        response = self.post_selection(
            mode="explicit", category=Customer.Category.CRM,
            numbers="M01, M03", start="", end="",
        )

        customer.refresh_from_db()
        self.assertEqual(customer.assignee_id, self.recipient.pk)
        self.assertContains(response, "M01")
        self.assertContains(response, "این شماره مشتری پیدا نشد")
        self.assertContains(response, "M03")

    def test_previously_assigned_customer_is_not_overwritten_and_current_assignee_is_shown(self):
        current = get_user_model().objects.create_user(username="current-customer-owner")
        customer = Customer.objects.create(
            name="Already assigned", category=Customer.Category.COMPANY, assignee=current
        )

        response = self.post_selection()

        customer.refresh_from_db()
        self.assertEqual(customer.assignee_id, current.pk)
        self.assertContains(response, "این مشتری قبلاً ارجاع شده")
        self.assertContains(response, "current-customer-owner")
        self.assertFalse(customer.assignment_history.exists())

    def test_inactive_recipient_is_rejected_without_assignment(self):
        inactive = get_user_model().objects.create_user(
            username="inactive-recipient", is_active=False
        )
        customer = Customer.objects.create(name="Inactive recipient", category=Customer.Category.COMPANY)

        response = self.post_selection(assignee=inactive)

        self.assertEqual(response.status_code, 200)
        customer.refresh_from_db()
        self.assertIsNone(customer.assignee_id)
        self.assertContains(response, "Select a valid choice", status_code=200)

    def test_active_django_admin_account_can_be_a_recipient(self):
        administrator = get_user_model().objects.create_superuser(
            username="assignment-admin", password="safe-test-password"
        )
        customer = Customer.objects.create(name="Admin recipient", category=Customer.Category.COMPANY)

        response = self.post_selection(assignee=administrator)

        self.assertEqual(response.status_code, 200)
        customer.refresh_from_db()
        self.assertEqual(customer.assignee_id, administrator.pk)

    def test_invalid_category_prefix_does_not_mutate_any_customer(self):
        customer = Customer.objects.create(name="Mismatched number", category=Customer.Category.CRM)

        response = self.post_selection(
            mode="explicit", category=Customer.Category.COMPANY,
            numbers="M01", start="", end="",
        )

        self.assertEqual(response.status_code, 200)
        customer.refresh_from_db()
        self.assertIsNone(customer.assignee_id)
        self.assertContains(response, "با دستهٔ انتخاب‌شده هم‌خوان نیست")

    def test_reclaim_keeps_history_and_releases_assignment(self):
        customer = Customer.objects.create(name="Reclaim target", category=Customer.Category.COMPANY)
        self.post_selection()
        assignment = customer.assignment_history.get()

        response = self.client.post(
            reverse("crm:customer_assignment_reclaim", args=(assignment.pk,))
        )

        self.assertEqual(response.status_code, 302)
        customer.refresh_from_db()
        assignment.refresh_from_db()
        self.assertIsNone(customer.assignee_id)
        self.assertEqual(assignment.assigned_by, self.manager)
        self.assertEqual(assignment.reclaimed_by, self.manager)
        self.assertIsNotNone(assignment.reclaimed_at)
        self.assertContains(self.client.get(self.url), "پس‌گرفته‌شده")

    def test_reclaiming_sent_customer_moves_it_to_follow_up(self):
        customer = Customer.objects.create(name="Sent target", category=Customer.Category.COMPANY)
        self.post_selection()
        customer.refresh_from_db()
        customer.status = Customer.Status.SENT
        customer.save(update_fields=("status", "updated_at"))
        assignment = customer.assignment_history.get()

        self.client.post(reverse("crm:customer_assignment_reclaim", args=(assignment.pk,)))

        customer.refresh_from_db()
        self.assertIsNone(customer.assignee_id)
        self.assertEqual(customer.status, Customer.Status.FOLLOW_UP)

    def test_only_manager_can_view_or_submit_assignment_workflow(self):
        marketer = get_user_model().objects.create_user(username="assignment-marketer")
        marketer.groups.add(Group.objects.get_or_create(name="CRM Marketer")[0])
        customer = Customer.objects.create(name="Permission target", category=Customer.Category.COMPANY)
        self.client.force_login(marketer)

        get_response = self.client.get(self.url)
        post_response = self.post_selection()

        self.assertEqual(get_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)
        customer.refresh_from_db()
        self.assertIsNone(customer.assignee_id)

    def test_reclaim_is_limited_to_assigning_manager(self):
        customer = Customer.objects.create(name="Manager isolation", category=Customer.Category.COMPANY)
        self.post_selection()
        assignment = customer.assignment_history.get()
        other_manager = create_manager_user("other-assignment-manager")
        self.client.force_login(other_manager)

        response = self.client.post(
            reverse("crm:customer_assignment_reclaim", args=(assignment.pk,))
        )

        self.assertEqual(response.status_code, 404)
        customer.refresh_from_db()
        self.assertEqual(customer.assignee_id, self.recipient.pk)
