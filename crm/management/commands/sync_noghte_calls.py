from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from crm.integrations.noghte import NoghteAPIClient, NoghteAPIError, map_call_status
from crm.models import CallRecord, Customer


class Command(BaseCommand):
    help = "Import outbound customer call history from the configured Noghte account."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            required=True,
            help="Import provider calls starting from this ISO date (YYYY-MM-DD).",
        )

    def handle(self, *args, **options):
        since = options["since"]
        try:
            date.fromisoformat(since)
        except (TypeError, ValueError):
            raise CommandError("--since must be a valid ISO date in YYYY-MM-DD format.") from None

        try:
            client = NoghteAPIClient()
        except NoghteAPIError:
            raise CommandError(
                "Phone service credentials are unavailable; check the secure key-file setting."
            ) from None

        customers_by_phone = defaultdict(list)
        phone_record_counts = defaultdict(int)
        customers = Customer.objects.exclude(phone="").order_by("phone", "pk")
        for customer in customers.iterator():
            if not customer.phone.strip():
                continue
            phone_record_counts[customer.phone] += 1
            if customer.archived_at is None and customer.trashed_at is None:
                customers_by_phone[customer.phone].append(customer)

        stats = defaultdict(int)
        for phone in sorted(customers_by_phone):
            matches = customers_by_phone[phone]
            if len(matches) != 1 or phone_record_counts[phone] != 1:
                stats["ambiguous"] += 1
                continue
            customer = matches[0]
            try:
                provider_calls = list(client.iter_calls(number=phone, since=since))
            except NoghteAPIError:
                raise CommandError(
                    "Phone service sync failed; check the secure key configuration and retry "
                    "with the same --since date."
                ) from None

            valid_calls = []
            for provider_call in provider_calls:
                parsed, reason = self._parse_call(provider_call, phone)
                if reason:
                    stats[reason] += 1
                else:
                    valid_calls.append(parsed)

            for call in sorted(valid_calls, key=lambda item: (item["status_at"], item["external_id"])):
                with transaction.atomic():
                    try:
                        current_customer = Customer.objects.select_for_update().get(pk=customer.pk)
                    except Customer.DoesNotExist:
                        stats["lifecycle_preserved"] += 1
                        continue
                    if current_customer.archived_at or current_customer.trashed_at:
                        stats["lifecycle_preserved"] += 1
                        continue

                    record, created = CallRecord.objects.get_or_create(
                        external_id=call["external_id"],
                        defaults={
                            "customer": current_customer,
                            "dialed_number": phone,
                            "outcome": call["outcome"],
                            "called_at": call["called_at"],
                        },
                    )
                    if not created:
                        if record.customer_id != current_customer.pk:
                            stats["identity_conflicts"] += 1
                        else:
                            stats["duplicates"] += 1
                        continue

                    stats["imported"] += 1
                    status_updated = (
                        Customer.objects.filter(
                            pk=current_customer.pk,
                            archived_at__isnull=True,
                            trashed_at__isnull=True,
                            status_changed_at__lt=call["status_at"],
                        )
                        .exclude(status=call["customer_status"])
                        .update(
                            status=call["customer_status"],
                            status_changed_at=call["status_at"],
                            updated_at=timezone.now(),
                        )
                    )
                    stats["status_updated"] += status_updated

        self.stdout.write(
            "Imported {imported}; duplicates {duplicates}; ambiguous {ambiguous}; "
            "unmatched {unmatched}; unsupported {unsupported}; non-outbound {non_outbound}; "
            "invalid {invalid}; identity conflicts {identity_conflicts}; "
            "lifecycle-preserved {lifecycle_preserved}; status updates {status_updated}.".format(
                **{key: stats[key] for key in (
                    "imported",
                    "duplicates",
                    "ambiguous",
                    "unmatched",
                    "unsupported",
                    "non_outbound",
                    "invalid",
                    "identity_conflicts",
                    "lifecycle_preserved",
                    "status_updated",
                )}
            )
        )

    @staticmethod
    def _parse_call(provider_call, phone):
        if not isinstance(provider_call, dict):
            return None, "invalid"
        if provider_call.get("direction") != "outbound":
            return None, "non_outbound"
        if provider_call.get("to") != phone:
            return None, "unmatched"

        status_mapping = map_call_status(provider_call.get("status"))
        if status_mapping is None:
            return None, "unsupported"
        outcome, customer_status = status_mapping

        external_id = provider_call.get("id")
        if not isinstance(external_id, str) or not external_id or len(external_id) > 128:
            return None, "invalid"
        called_at = Command._parse_aware_datetime(provider_call.get("started_at"))
        if called_at is None:
            return None, "invalid"

        status_at_value = (
            provider_call.get("answered_at")
            if provider_call.get("status") == "answered"
            else None
        )
        status_at = Command._parse_aware_datetime(
            status_at_value or provider_call.get("ended_at") or provider_call.get("started_at")
        )
        if status_at is None or status_at < called_at:
            return None, "invalid"

        return {
            "external_id": external_id,
            "outcome": outcome,
            "customer_status": customer_status,
            "called_at": called_at,
            "status_at": status_at,
        }, None

    @staticmethod
    def _parse_aware_datetime(value):
        if not isinstance(value, str):
            return None
        parsed = parse_datetime(value)
        if parsed is None or timezone.is_naive(parsed):
            return None
        return parsed
