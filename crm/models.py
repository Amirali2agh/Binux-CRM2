from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Customer(models.Model):
    class Status(models.TextChoices):
        NO_CONTACT = "no_contact", "بدون تماس"
        REJECTED = "rejected", "رد شده"
        FOLLOW_UP = "follow_up", "پیگیری"
        SENT = "sent", "ارسالی"
        CALL_AGAIN = "call_again", "تماس مجدد"
        COMPLETED = "completed", "انجام شده"

    class Source(models.TextChoices):
        PHONE = "phone", "تماس تلفنی"
        DIVAR = "divar", "دیوار"
        IN_PERSON = "in_person", "حضوری"
        OTHER = "other", "سایر"

    class RestoreSource(models.TextChoices):
        ARCHIVE = "archive", "بایگانی"
        TRASH = "trash", "زباله‌دان"

    name = models.CharField("نام مشتری", max_length=255, blank=True)
    business_type = models.CharField("نوع کسب‌وکار", max_length=255, blank=True)
    business_name = models.CharField("نام کسب‌وکار", max_length=255, blank=True)
    phone = models.CharField("شماره تلفن", max_length=64, blank=True)
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

    def __str__(self):
        return self.name or f"مشتری #{self.pk}"


class CallRecord(models.Model):
    class Outcome(models.TextChoices):
        ANSWERED = "answered", "تماس پاسخ داده شده"
        CALL_AGAIN = "call_again", "تماس مجدد"

    customer = models.ForeignKey(
        Customer,
        verbose_name="مشتری",
        related_name="call_records",
        on_delete=models.CASCADE,
    )
    dialed_number = models.CharField("شمارهٔ گرفته‌شده", max_length=64)
    outcome = models.CharField("نتیجهٔ تماس", max_length=20, choices=Outcome.choices)
    called_at = models.DateTimeField("زمان تماس", default=timezone.now)

    class Meta:
        ordering = ("-called_at", "-pk")
        indexes = [models.Index(fields=("customer", "-called_at"))]
