import logging
import re
import time
from datetime import timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import jdatetime
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
    require_safe,
)

from .call_ingestion import IngestTemporarilyUnavailable
from .catalog import PAGES, SECTIONS
from .forms import CallOutcomeForm, CustomerForm
from .integrations.noghtefone.ingest import ingest_signed_body
from .integrations.noghtefone.signatures import signature_is_valid
from .forms import (
    CallOutcomeForm,
    CustomerForm,
    TeamUserCreationForm,
    TeamUserUpdateForm,
)
from .jalali_calendar import build_month
from .models import CallRecord, Customer
from .roles import (
    customer_queryset_for_user,
    is_marketer,
    manager_required,
    role_required,
)

logger = logging.getLogger(__name__)
MAX_WEBHOOK_BODY_BYTES = 1_000_000


class TeamLoginView(LoginView):
    template_name = "crm/login.html"
    redirect_authenticated_user = True

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["username"].widget.attrs.update(
            {
                "class": "login-input",
                "autocomplete": "username",
                "autofocus": "autofocus",
                "dir": "auto",
            }
        )
        form.fields["password"].widget.attrs.update(
            {
                "class": "login-input",
                "autocomplete": "current-password",
                "dir": "ltr",
            }
        )
        return form


def _active_customers():
    rejection_cutoff = timezone.now() - timedelta(hours=2)
    return Customer.objects.filter(
        archived_at__isnull=True, trashed_at__isnull=True
    ).exclude(
        status=Customer.Status.REJECTED,
        status_changed_at__lte=rejection_cutoff,
    )


def _customer_context(title, customers, *, page_key="customer_list"):
    section, _ = PAGES["customer_list"]
    return {
        "sections": SECTIONS,
        "section": section,
        "page": {"title": title, "description": "مدیریت اطلاعات و وضعیت مشتریان"},
        "current_page": page_key,
        "customers": customers,
        "status_choices": Customer.Status.choices,
    }


def _user_management_context(request, creation_form=None, selected_form=None):
    user_model = get_user_model()
    users = user_model.objects.prefetch_related("groups").order_by("username")
    entries = []
    for user in users:
        form = (
            selected_form
            if selected_form is not None and selected_form.user == user
            else TeamUserUpdateForm(user=user, actor=request.user)
        )
        role_names = set(
            user.groups.filter(name__in=("CRM Manager", "CRM Marketer"))
            .values_list("name", flat=True)
        )
        entries.append(
            {
                "user": user,
                "form": form,
                "role_label": {
                    "CRM Manager": "مدیر",
                    "CRM Marketer": "بازاریاب",
                }.get(next(iter(role_names)) if len(role_names) == 1 else "", "بدون نقش"),
            }
        )
    section, _ = PAGES["settings"]
    return {
        "sections": SECTIONS,
        "section": section,
        "page": {"title": "افزودن کاربر", "description": "ایجاد و مدیریت حساب‌های تیم"},
        "current_page": "user_management",
        "creation_form": creation_form or TeamUserCreationForm(),
        "user_entries": entries,
    }


@login_required
@manager_required
@require_http_methods(["GET", "POST"])
def user_management(request):
    if request.method == "GET":
        return render(
            request, "crm/user_management.html", _user_management_context(request)
        )

    action = request.POST.get("action")
    if action == "create":
        form = TeamUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "حساب کاربری با موفقیت ایجاد شد.")
            return redirect("crm:user_management")
        return render(
            request,
            "crm/user_management.html",
            _user_management_context(request, creation_form=form),
        )

    if action == "update":
        user_model = get_user_model()
        try:
            managed_user = user_model.objects.get(pk=request.POST.get("user_id"))
        except (user_model.DoesNotExist, ValueError, TypeError):
            return HttpResponseNotFound("کاربر پیدا نشد.")
        form = TeamUserUpdateForm(
            request.POST, user=managed_user, actor=request.user
        )
        if form.is_valid():
            with transaction.atomic():
                managed_user.is_active = form.cleaned_data["is_active"]
                managed_user.save(update_fields={"is_active"})
                role_groups = Group.objects.filter(
                    name__in=("CRM Manager", "CRM Marketer")
                )
                managed_user.groups.remove(*role_groups)
                role, _ = Group.objects.get_or_create(name=form.cleaned_data["role"])
                managed_user.groups.add(role)
            messages.success(request, "تغییرات حساب با موفقیت ذخیره شد.")
            return redirect("crm:user_management")
        return render(
            request,
            "crm/user_management.html",
            _user_management_context(request, selected_form=form),
        )

    return HttpResponseBadRequest("درخواست مدیریت کاربر معتبر نیست.")


@require_safe
def home(request):
    destination = (
        "crm:customer_list" if is_marketer(request.user) else "crm:office_inventory"
    )
    return redirect(destination)


@login_required
@manager_required
@require_safe
def display_page(request, page_key):
    section, page = PAGES[page_key]
    return render(
        request,
        "crm/page.html",
        {
            "sections": SECTIONS,
            "page": page,
            "section": section,
            "current_page": page_key,
            "contract_reference": "DEMO-01",
            "display_rows": tuple(
                tuple(zip(page["columns"], row)) for row in page.get("rows", ())
            )
            if page["kind"] == "table"
            else (),
        },
    )


@login_required
@manager_required
@require_safe
def calendar_view(request):
    month_value = request.GET.get("month")
    if month_value is None:
        local_now = timezone.localtime(
            timezone.now(), timezone=ZoneInfo("Asia/Tehran")
        )
        current_date = jdatetime.date.fromgregorian(
            date=local_now.date(), locale=jdatetime.FA_LOCALE
        )
        year, month = current_date.year, current_date.month
    else:
        match = re.fullmatch(r"([0-9]{4})-(0[1-9]|1[0-2])", month_value)
        if match is None:
            return HttpResponseBadRequest("ماه انتخاب‌شده معتبر نیست.")
        year, month = (int(part) for part in match.groups())
        try:
            jdatetime.date(year, month, 1)
        except ValueError:
            return HttpResponseBadRequest("ماه انتخاب‌شده معتبر نیست.")

    section, page = PAGES["calendar"]
    return render(
        request,
        "crm/calendar.html",
        {
            "sections": SECTIONS,
            "section": section,
            "page": page,
            "current_page": "calendar",
            **build_month(year, month),
        },
    )


@login_required
@role_required
@require_safe
def customer_list(request):
    customers = customer_queryset_for_user(_active_customers(), request.user).exclude(
        status=Customer.Status.COMPLETED
    ).select_related("assignee")
    name = request.GET.get("name", "").strip()
    business_type = request.GET.get("business_type", "").strip()
    category = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()
    if name:
        customers = customers.filter(name__icontains=name)
    if business_type:
        customers = customers.filter(business_type__icontains=business_type)
    if category in Customer.Category.values:
        customers = customers.filter(category=category)
    else:
        category = ""
    if status in Customer.Status.values:
        customers = customers.filter(status=status)
    else:
        status = ""

    def tab_url(**changes):
        params = {
            "name": name,
            "business_type": business_type,
            "category": category,
            "status": status,
        }
        params.update(changes)
        return "?" + urlencode({key: value for key, value in params.items() if value})

    category_tabs = [
        {"value": "", "label": "همه", "url": tab_url(category="")}
    ] + [
        {"value": value, "label": label, "url": tab_url(category=value)}
        for value, label in Customer.Category.choices
    ]
    completed_params = {
        key: value
        for key, value in {
            "name": name,
            "business_type": business_type,
            "category": category,
        }.items()
        if value
    }
    completed_tab_url = reverse("crm:completed_customers")
    if completed_params:
        completed_tab_url += "?" + urlencode(completed_params)
    status_tabs = [
        {"value": "", "label": "همهٔ وضعیت‌ها", "url": tab_url(status="")}
    ] + [
        {
            "value": value,
            "label": label,
            "url": (
                completed_tab_url
                if value == Customer.Status.COMPLETED
                else tab_url(status=value)
            ),
        }
        for value, label in Customer.Status.choices
    ]
    filters = {
        "name": name,
        "business_type": business_type,
        "category": category,
        "status": status,
    }
    return render(
        request, "crm/customer_list.html",
        _customer_context("لیست مشتریان", customers)
        | {
            "filters": filters,
            "category_tabs": category_tabs,
            "status_tabs": status_tabs,
        },
    )


@login_required
@role_required
@require_safe
def customer_follow_ups(request):
    customers = customer_queryset_for_user(Customer.objects.all(), request.user).filter(
        status__in=(Customer.Status.FOLLOW_UP, Customer.Status.SENT),
        archived_at__isnull=True, trashed_at__isnull=True,
    ).select_related("assignee")
    return render(
        request, "crm/customer_list.html",
        _customer_context("پیگیری", customers, page_key="follow_ups"),
    )


@login_required
@manager_required
@require_safe
def customer_tasks(request):
    customers = _active_customers().filter(
        assignee__isnull=False
    ).select_related("assignee")
    return render(
        request, "crm/customer_list.html",
        _customer_context("کارهای ارجاع‌شده", customers, page_key="tasks"),
    )


@login_required
@manager_required
@require_safe
def completed_customers(request):
    customers = Customer.objects.filter(
        status=Customer.Status.COMPLETED,
        archived_at__isnull=True, trashed_at__isnull=True,
    ).select_related("assignee")
    name = request.GET.get("name", "").strip()
    business_type = request.GET.get("business_type", "").strip()
    category = request.GET.get("category", "").strip()
    if name:
        customers = customers.filter(name__icontains=name)
    if business_type:
        customers = customers.filter(business_type__icontains=business_type)
    if category in Customer.Category.values:
        customers = customers.filter(category=category)
    else:
        category = ""
    return render(
        request, "crm/customer_list.html",
        _customer_context(
            "مشتریان تکمیل‌شده", customers, page_key="completed_customers"
        ) | {"filters": {"name": name, "business_type": business_type, "category": category}},
    )


@login_required
@manager_required
@require_safe
def customer_archive(request):
    rejection_cutoff = timezone.now() - timedelta(hours=2)
    customers = Customer.objects.filter(
        Q(archived_at__isnull=False)
        | Q(
            status=Customer.Status.REJECTED,
            status_changed_at__lte=rejection_cutoff,
            trashed_at__isnull=True,
        )
    ).filter(trashed_at__isnull=True).select_related("assignee")
    return render(
        request, "crm/customer_list.html",
        _customer_context("بایگانی مشتریان", customers, page_key="customer_archive"),
    )


@login_required
@manager_required
@require_safe
def customer_trash(request):
    customers = Customer.objects.filter(trashed_at__isnull=False).select_related(
        "assignee"
    )
    return render(
        request, "crm/customer_list.html",
        _customer_context("زباله‌دان مشتریان", customers, page_key="customer_trash"),
    )


def _active_customer(pk):
    return get_object_or_404(_active_customers(), pk=pk)


@login_required
@manager_required
@require_http_methods(["GET", "POST"])
def customer_create(request):
    form = CustomerForm(
        request.POST if request.method == "POST" else None
    )
    if request.method == "POST" and form.is_valid():
        try:
            customer = form.save()
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect("crm:customer_detail", pk=customer.pk)
    return render(
        request, "crm/customer_form.html",
        _customer_context("ثبت مشتری", (), page_key="customer_create") | {"form": form},
    )


@login_required
@role_required
@require_safe
def customer_detail(request, pk):
    customer = get_object_or_404(
        customer_queryset_for_user(
            Customer.objects.select_related("assignee").prefetch_related("call_records"),
            request.user,
        ),
        pk=pk,
    )
    auto_archive_due = (
        customer.status == Customer.Status.REJECTED
        and customer.status_changed_at + timedelta(hours=2) <= timezone.now()
    )
    return render(
        request, "crm/customer_detail.html",
        _customer_context("جزئیات مشتری", (), page_key="customer_list")
        | {
            "customer": customer,
            "is_customer_archived": bool(customer.archived_at or auto_archive_due),
            "is_customer_trashed": bool(customer.trashed_at),
            "call_outcome_choices": CallRecord.Outcome.choices,
        },
    )


@csrf_exempt
@require_POST
def noghtefone_webhook(request):
    """Accept a signed Noghtefone webhook. Authentication is the HMAC signature.

    A durable store is acknowledged with 200. Signature or timestamp failures
    are 401 and are not stored. A database error before commit is 503 so the
    provider retries. Secrets and payload bodies are not logged.
    """
    raw_body = request.body
    if len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
        logger.warning("Noghtefone webhook rejected because the body is too large.")
        return HttpResponse(status=413)

    secrets = [
        secret
        for secret in (
            settings.NOGHTE_WEBHOOK_SECRET,
            settings.NOGHTE_WEBHOOK_SECRET_PREVIOUS,
        )
        if secret
    ]
    if not signature_is_valid(
        raw_body,
        request.META.get("HTTP_X_NOGHTE_SIGNATURE", ""),
        secrets,
        now=time.time(),
        tolerance_seconds=settings.NOGHTE_WEBHOOK_TOLERANCE_SECONDS,
    ):
        logger.warning("Noghtefone webhook rejected (signature, timestamp, or missing secret).")
        return HttpResponse(status=401)

    delivery_id = request.META.get("HTTP_X_NOGHTE_DELIVERY", "").strip()
    if not delivery_id or len(delivery_id) > 128:
        logger.warning("Noghtefone webhook rejected because the delivery id is missing.")
        return HttpResponse(status=400)

    try:
        result = ingest_signed_body(
            raw_body=raw_body,
            delivery_id=delivery_id,
            event_header=request.META.get("HTTP_X_NOGHTE_EVENT", ""),
        )
    except IngestTemporarilyUnavailable:
        logger.warning(
            "Noghtefone webhook was not stored (delivery_id=%s).", delivery_id
        )
        return HttpResponse(status=503)

    logger.info(
        "Noghtefone webhook stored (delivery_id=%s, disposition=%s).",
        delivery_id,
        result.disposition,
    )
    return HttpResponse(status=200)


@login_required
@manager_required
@require_POST
def call_outcome_update(request, pk, call_pk):
    customer = get_object_or_404(Customer, pk=pk)
    call = get_object_or_404(CallRecord, pk=call_pk, customer=customer)
    form = CallOutcomeForm(request.POST, instance=call)
    if not form.is_valid():
        return HttpResponseBadRequest("نتیجهٔ تماس معتبر نیست.".encode())
    form.save()
    return redirect("crm:customer_detail", pk=customer.pk)


@login_required
@manager_required
@require_http_methods(["GET", "POST"])
def customer_update(request, pk):
    customer = _active_customer(pk)
    form = CustomerForm(
        request.POST if request.method == "POST" else None, instance=customer
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("crm:customer_detail", pk=customer.pk)
    return render(
        request, "crm/customer_form.html",
        _customer_context("ویرایش مشتری", (), page_key="customer_list")
        | {"form": form, "customer": customer},
    )


@login_required
@manager_required
@require_POST
def customer_delete(request, pk):
    customer = _active_customer(pk)
    customer.move_to_trash()
    return redirect("crm:customer_trash")


@login_required
@manager_required
@require_POST
def customer_archive_action(request, pk):
    customer = _active_customer(pk)
    customer.move_to_archive()
    return redirect("crm:customer_archive")


@login_required
@manager_required
@require_POST
def customer_restore(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if customer.restore():
        return redirect("crm:follow_ups")
    if customer.trashed_at:
        return redirect("crm:customer_trash")
    return redirect("crm:customer_archive")
