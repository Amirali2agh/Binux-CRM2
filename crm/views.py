from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
    require_safe,
)

from .catalog import PAGES, SECTIONS
from .forms import CustomerForm
from .models import Customer


class TeamLoginView(LoginView):
    template_name = "crm/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        section, page = PAGES["customer_list"]
        context.update(
            sections=SECTIONS,
            section=section,
            page=page,
            current_page="customer_list",
        )
        return context


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
    }


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
@require_safe
def customer_list(request):
    customers = _active_customers().exclude(
        status=Customer.Status.COMPLETED
    ).select_related("assignee")
    return render(
        request, "crm/customer_list.html",
        _customer_context("لیست مشتریان", customers),
    )


@login_required
@require_safe
def customer_follow_ups(request):
    customers = Customer.objects.filter(
        status__in=(Customer.Status.FOLLOW_UP, Customer.Status.SENT),
        archived_at__isnull=True, trashed_at__isnull=True,
    ).select_related("assignee")
    return render(
        request, "crm/customer_list.html",
        _customer_context("پیگیری", customers, page_key="follow_ups"),
    )


@login_required
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
@require_safe
def completed_customers(request):
    customers = Customer.objects.filter(
        status=Customer.Status.COMPLETED,
        archived_at__isnull=True, trashed_at__isnull=True,
    ).select_related("assignee")
    return render(
        request, "crm/customer_list.html",
        _customer_context(
            "مشتریان تکمیل‌شده", customers, page_key="completed_customers"
        ),
    )


@login_required
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
@require_http_methods(["GET", "POST"])
def customer_create(request):
    form = CustomerForm(
        request.POST if request.method == "POST" else None
    )
    if request.method == "POST" and form.is_valid():
        customer = form.save()
        return redirect("crm:customer_detail", pk=customer.pk)
    return render(
        request, "crm/customer_form.html",
        _customer_context("ثبت مشتری", ()) | {"form": form},
    )


@login_required
@require_safe
def customer_detail(request, pk):
    customer = get_object_or_404(
        Customer.objects.select_related("assignee"), pk=pk
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
        },
    )


@login_required
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
@require_POST
def customer_delete(request, pk):
    customer = _active_customer(pk)
    customer.move_to_trash()
    return redirect("crm:customer_trash")


@login_required
@require_POST
def customer_archive_action(request, pk):
    customer = _active_customer(pk)
    customer.move_to_archive()
    return redirect("crm:customer_archive")


@login_required
@require_POST
def customer_restore(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if customer.restore():
        return redirect("crm:follow_ups")
    if customer.trashed_at:
        return redirect("crm:customer_trash")
    return redirect("crm:customer_archive")
