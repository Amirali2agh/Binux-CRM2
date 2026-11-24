from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class CustomerNumberSequence(models.Model):
    category = models.CharField(max_length=20, unique=True)
    next_number = models.PositiveSmallIntegerField(default=1)


class Customer(models.Model):
    class Status(models.TextChoices):
        NO_CONTACT = "no_contact", "بدون تماس"
        REJECTED = "rejected", "رد شده"
        FOLLOW_UP = "follow_up", "پیگیری"
        SENT = "sent", "ارسالی"
        CALL_AGAIN = "call_again", "تماس مجدد"
        COMPLETED = "completed", "انجام شده"

    class Category(models.TextChoices):
        MICRO_BUSINESS = "micro_business", "کسب‌وکار خرد"
        COMPANY = "company", "شرکت"
        CRM = "crm", "مشتری CRM"
        ERP = "erp", "مشتری ERP"
        UNCATEGORIZED = "uncategorized", "نامشخص"

    class Source(models.TextChoices):
        PHONE = "phone", "تماس تلفنی"
        DIVAR = "divar", "دیوار"
        IN_PERSON = "in_person", "حضوری"
        OTHER = "other", "سایر"

    class RestoreSource(models.TextChoices):
        ARCHIVE = "archive", "بایگانی"
        TRASH = "trash", "زباله‌دان"

    customer_number = models.CharField(
        "شماره مشتری", max_length=24, unique=True, editable=False
    )
    name = models.CharField("نام مشتری", max_length=255, blank=True)
    business_type = models.CharField("نوع کسب‌وکار", max_length=255, blank=True)
    business_name = models.CharField("نام کسب‌وکار", max_length=255, blank=True)
    category = models.CharField(
        "دسته مشتری",
        max_length=20,
        choices=Category.choices,
        default=Category.UNCATEGORIZED,
    )
    phone = models.CharField("شماره تلفن", max_length=64, blank=True)
    phone_secondary = models.CharField("شماره تلفن دوم", max_length=64, blank=True)
    phone_tertiary = models.CharField("شماره تلفن سوم", max_length=64, blank=True)
    status = models.CharField(
        "وضعیت", max_length=20, choices=Status.choices, default=Status.NO_CONTACT,
        blank=True,
    )
    source = models.CharField("نوع/منبع مشتری", max_length=20, choices=Source.choices, blank=True)
    address = models.TextField("نشانی", blank=True)
    notes = models.TextField("یادداشت", blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="مسئول",
        related_name="assigned_customers",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    status_changed_at = models.DateTimeField(default=timezone.now)
    archived_at = models.DateTimeField(blank=True, null=True)
    trashed_at = models.DateTimeField(blank=True, null=True)
    restored_from = models.CharField(
        max_length=10, choices=RestoreSource.choices, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-pk")
        indexes = [
            models.Index(fields=("status", "status_changed_at")),
            models.Index(fields=("archived_at",)),
            models.Index(fields=("trashed_at",)),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status="sent") | models.Q(assignee__isnull=False),
                name="customer_sent_requires_assignee",
            )
        ]

    def clean(self):
        if self.status == self.Status.SENT:
            if not self.assignee_id:
                raise ValidationError(
                    {"assignee": "برای وضعیت ارسالی انتخاب مسئول الزامی است"}
                )
            assignee_model = self._meta.get_field("assignee").remote_field.model
            if not assignee_model.objects.filter(
                pk=self.assignee_id, is_active=True
            ).exists():
                raise ValidationError(
                    {"assignee": "مسئول وضعیت ارسالی باید کاربر فعال باشد"}
                )

    def save(self, *args, **kwargs):
        if self._state.adding and not self.customer_number:
            prefix_by_category = {
                self.Category.COMPANY: "C",
                self.Category.MICRO_BUSINESS: "A",
                self.Category.CRM: "M",
                self.Category.ERP: "E",
            }
            prefix = prefix_by_category.get(self.category)
            if prefix is None and self.category != self.Category.UNCATEGORIZED:
                raise ValidationError({"category": "برای مشتری جدید انتخاب دسته الزامی است."})
            with transaction.atomic():
                sequence = CustomerNumberSequence.objects.filter(
                    category=self.category, next_number__lte=9999
                )
                if sequence.update(next_number=models.F("next_number") + 1) != 1:
                    raise ValidationError("ظرفیت شماره مشتری‌های این دسته تکمیل شده است.")
                number = sequence.get().next_number - 1
                self.customer_number = f"{prefix}{number:02d}" if prefix else str(number)
                return self._save_customer(*args, **kwargs)
        return self._save_customer(*args, **kwargs)

    def _save_customer(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if (
            self._state.adding
            or update_fields is None
            or {"status", "assignee"} & set(update_fields)
        ):
            self.full_clean()
        if self.pk and (update_fields is None or "status" in update_fields):
            previous = type(self).objects.filter(pk=self.pk).values(
                "status", "status_changed_at"
            ).first()
            if (
                previous is not None
                and previous["status"] != self.status
                and previous["status_changed_at"] == self.status_changed_at
                and (update_fields is None or "status_changed_at" not in update_fields)
            ):
                self.status_changed_at = timezone.now()
                if update_fields is not None:
                    kwargs["update_fields"] = set(update_fields) | {
                        "status_changed_at", "updated_at"
                    }
        super().save(*args, **kwargs)

    def move_to_archive(self, *, now=None):
        self.archived_at = now or timezone.now()
        self.trashed_at = None
        self.restored_from = ""
        self.save(update_fields=("archived_at", "trashed_at", "restored_from", "updated_at"))

    def move_to_trash(self, *, now=None):
        self.trashed_at = now or timezone.now()
        self.archived_at = None
        self.restored_from = ""
        self.save(update_fields=("trashed_at", "archived_at", "restored_from", "updated_at"))

    def restore(self, *, now=None):
        now = now or timezone.now()
        if self.trashed_at:
            if now >= self.trashed_at + timedelta(days=10):
                return False
            self.restored_from = self.RestoreSource.TRASH
            self.trashed_at = None
        elif self.archived_at:
            if now >= self.archived_at + timedelta(days=30):
                return False
            self.restored_from = self.RestoreSource.ARCHIVE
            self.archived_at = None
        elif self.status == self.Status.REJECTED:
            archive_deadline = self.status_changed_at + timedelta(hours=2)
            if now < archive_deadline or now >= archive_deadline + timedelta(days=30):
                return False
            self.restored_from = self.RestoreSource.ARCHIVE
        else:
            return False
        self.status = self.Status.FOLLOW_UP
        self.status_changed_at = now
        self.save(
            update_fields=(
                "status", "status_changed_at", "archived_at", "trashed_at",
                "restored_from", "updated_at",
            )
        )
        return True

    @property
    def phone_numbers(self):
        return tuple(
            (label, number)
            for label, number in (
                ("شماره اول", self.phone),
                ("شماره دوم", self.phone_secondary),
                ("شماره سوم", self.phone_tertiary),
            )
            if number
        )

    @property
    def next_phone_field(self):
        for field_name in ("phone", "phone_secondary", "phone_tertiary"):
            if not getattr(self, field_name):
                return f"id_{field_name}"
        return ""

    @property
    def can_add_phone(self):
        return bool(self.next_phone_field)

    def __str__(self):
        return self.name or f"مشتری #{self.pk}"


class CallRecord(models.Model):
    class Outcome(models.TextChoices):
        ANSWERED = "answered", "تماس پاسخ داده شده"
        CALL_AGAIN = "call_again", "تماس مجدد"
        UNKNOWN = "unknown", "نامشخص / پشتیبانی‌نشده"

    customer = models.ForeignKey(
        Customer,
        verbose_name="مشتری",
        related_name="call_records",
        on_delete=models.CASCADE,
    )
    dialed_number = models.CharField("شمارهٔ گرفته‌شده", max_length=64)
    outcome = models.CharField("نتیجهٔ تماس", max_length=20, choices=Outcome.choices)
    called_at = models.DateTimeField("زمان تماس", default=timezone.now)
    external_id = models.CharField(
        "شناسهٔ تماس خارجی",
        max_length=128,
        unique=True,
        blank=True,
        null=True,
    )
    outcome_locked = models.BooleanField(
        "نتیجهٔ دستی",
        default=False,
        help_text="Set when an operator saves the outcome. Provider replays do not overwrite it.",
    )

    class Meta:
        ordering = ("-called_at", "-pk")
        indexes = [models.Index(fields=("customer", "-called_at"))]


class CallEvent(models.Model):
    """One authenticated provider delivery, stored before customer association."""

    class Disposition(models.TextChoices):
        MATCHED = "matched", "Matched to a customer"
        UNMATCHED = "unmatched", "Unknown number"
        AMBIGUOUS = "ambiguous", "Ambiguous number"
        INACTIVE = "inactive", "Inactive customer"
        IGNORED = "ignored", "Not a call outcome"
        FAILED = "failed", "Failed"
        CONFLICT = "conflict", "Call already linked elsewhere"

    provider = models.CharField(max_length=32, default="noghtefone")
    delivery_key = models.CharField(max_length=128)
    external_event_id = models.CharField(max_length=128, blank=True)
    event_name = models.CharField(max_length=64, blank=True)
    call_external_id = models.CharField(max_length=128, blank=True)
    outcome = models.CharField(max_length=20, blank=True)
    normalized_phone = models.CharField(max_length=32, blank=True)
    disposition = models.CharField(max_length=20, choices=Disposition.choices)
    detail = models.CharField(max_length=255, blank=True)
    customer = models.ForeignKey(
        Customer,
        related_name="call_events",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    call_record = models.ForeignKey(
        CallRecord,
        related_name="call_events",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    occurred_at = models.DateTimeField(blank=True, null=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "delivery_key"),
                name="call_event_provider_delivery_uniq",
            ),
            models.UniqueConstraint(
                fields=("provider", "external_event_id"),
                condition=~models.Q(external_event_id=""),
                name="call_event_provider_event_id_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("disposition", "received_at")),
            models.Index(fields=("call_external_id",)),
        ]

    def __str__(self):
        return f"{self.provider}:{self.delivery_key}"
