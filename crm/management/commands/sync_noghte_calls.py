from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from crm.call_ingestion import apply_customer_status, should_replace_outcome
from crm.integrations.noghte import NoghteAPIClient, NoghteAPIError, map_call_status
from crm.models import CallRecord, Customer
from crm.phones import phone_match_key, unique_phone_keys


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
        query_values = {}
        customers = Customer.objects.exclude(
            phone="", phone_secondary="", phone_tertiary=""
        ).order_by("pk")
        for customer in customers.iterator():
            pairs = unique_phone_keys(
                (customer.phone, customer.phone_secondary, customer.phone_tertiary)
            )
            if not pairs:
                continue
            active = customer.archived_at is None and customer.trashed_at is None
            for match_key, raw in pairs:
                phone_record_counts[match_key] += 1
                if active:
                    customers_by_phone[match_key].append(customer)
                    query_values.setdefault(match_key, raw)

        stats = defaultdict(int)
        for match_key in sorted(customers_by_phone):
            matches = customers_by_phone[match_key]
            if len(matches) != 1 or phone_record_counts[match_key] != 1:
                stats["ambiguous"] += 1
                continue
            customer = matches[0]
            phone = query_values[match_key]
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
                            "dialed_number": call["dialed_number"],
                            "outcome": call["outcome"],
                            "called_at": call["called_at"],
                        },
                    )
                    if not created:
                        if record.customer_id != current_customer.pk:
                            stats["identity_conflicts"] += 1
                        elif (
                            not record.outcome_locked
                            and should_replace_outcome(record.outcome, call["outcome"])
                        ):
                            stats["duplicates"] += 1
                            record.outcome = call["outcome"]
                            record.save(update_fields=("outcome",))
                            if call["customer_status"] is not None:
                                stats["status_updated"] += apply_customer_status(
                                    current_customer, call["outcome"], call["status_at"]
                                )
                        else:
                            stats["duplicates"] += 1
                        continue

                    stats["imported"] += 1
                    if call["outcome"] == CallRecord.Outcome.UNKNOWN:
                        stats["unknown"] += 1
                    if call["customer_status"] is not None:
                        stats["status_updated"] += apply_customer_status(
                            current_customer, call["outcome"], call["status_at"]
                        )

        self.stdout.write(
            "Imported {imported}; duplicates {duplicates}; ambiguous {ambiguous}; "
            "unmatched {unmatched}; unknown {unknown}; unsupported {unsupported}; "
            "non-outbound {non_outbound}; invalid {invalid}; "
            "identity conflicts {identity_conflicts}; "
            "lifecycle-preserved {lifecycle_preserved}; status updates {status_updated}.".format(
                **{key: stats[key] for key in (
                    "imported",
                    "duplicates",
                    "ambiguous",
                    "unmatched",
                    "unknown",
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
        # Provisional call-object fields (id, direction, to, status, started_at,
        # answered_at, ended_at). The public API page does not document them.
        # See docs/noghtefone-integration.md.
        if not isinstance(provider_call, dict):
            return None, "invalid"
        if provider_call.get("direction") != "outbound":
            return None, "non_outbound"
        provider_number = provider_call.get("to")
        if not isinstance(provider_number, str) or phone_match_key(provider_number) != phone_match_key(phone):
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
            "dialed_number": provider_number[:64],
        }, None

    @staticmethod
    def _parse_aware_datetime(value):
        if not isinstance(value, str):
            return None
        parsed = parse_datetime(value)
        if parsed is None or timezone.is_naive(parsed):
            return None
        return parsed
