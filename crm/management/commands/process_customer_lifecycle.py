from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from crm.models import Customer


class Command(BaseCommand):
    help = "Apply due customer archive and retention transitions."

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        rejected = list(
            Customer.objects.filter(
                status=Customer.Status.REJECTED,
                status_changed_at__lte=now - timedelta(hours=2),
                archived_at__isnull=True,
                trashed_at__isnull=True,
            )
        )
        for customer in rejected:
            customer.archived_at = customer.status_changed_at + timedelta(hours=2)
        if rejected:
            Customer.objects.bulk_update(rejected, ("archived_at",))

        archived_count, _ = Customer.objects.filter(
            archived_at__lte=now - timedelta(days=30)
        ).delete()
        trashed_count, _ = Customer.objects.filter(
            trashed_at__lte=now - timedelta(days=10)
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Archived {len(rejected)} rejected customer(s); "
                f"permanently deleted {archived_count} archived and "
                f"{trashed_count} trashed object(s)."
            )
        )
