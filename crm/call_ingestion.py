"""Associate provider-neutral call deliveries with CRM customers.

Provider payloads are parsed before they reach this module. A delivery is
stored once, then linked to a customer only when its normalized phone number
belongs to exactly one CRM customer that is neither archived nor in Trash.
"""

from dataclasses import dataclass

from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from crm.models import CallEvent, CallRecord, Customer
from crm.phones import phone_match_key


class IngestTemporarilyUnavailable(Exception):
    """The delivery was not stored. The provider should retry."""


@dataclass(frozen=True)
class DeliveryResult:
    created: bool
    disposition: str
    detail: str = ""


def customer_status_for_outcome(outcome):
    """CRM status implied by a call outcome.

    ``answered`` -> ``rejected`` and unanswered outcomes -> ``call_again`` are
    the mapping already recorded for the Noghte importer. ``unknown`` does not
    change the customer.
    """
    if outcome == CallRecord.Outcome.ANSWERED:
        return Customer.Status.REJECTED
    if outcome == CallRecord.Outcome.CALL_AGAIN:
        return Customer.Status.CALL_AGAIN
    return None


def apply_customer_status(customer, outcome, occurred_at):
    """Move ``customer`` when this call is newer than the last status change."""
    status = customer_status_for_outcome(outcome)
    if status is None or occurred_at is None:
        return 0
    return Customer.objects.filter(
        pk=customer.pk,
        archived_at__isnull=True,
        trashed_at__isnull=True,
        status_changed_at__lt=occurred_at,
    ).exclude(status=status).update(
        status=status,
        status_changed_at=occurred_at,
        updated_at=timezone.now(),
    )


def record_delivery(
    *,
    provider,
    delivery_key,
    external_event_id,
    event_name,
    call_external_id,
    outcome,
    normalized_phone,
    dialed_number,
    occurred_at,
    is_call_event,
    parse_error,
):
    """Durably store one delivery and apply it when it is a customer call.

    The same ``delivery_key`` or non-empty ``external_event_id`` is a duplicate
    and is not applied again. Database errors before commit raise
    :class:`IngestTemporarilyUnavailable` so the caller can return a retryable
    HTTP status.
    """
    try:
        with transaction.atomic():
            return _record_delivery(
                provider=provider,
                delivery_key=delivery_key,
                external_event_id=external_event_id,
                event_name=event_name,
                call_external_id=call_external_id,
                outcome=outcome,
                normalized_phone=normalized_phone,
                dialed_number=dialed_number,
                occurred_at=occurred_at,
                is_call_event=is_call_event,
                parse_error=parse_error,
            )
    except IntegrityError:
        return DeliveryResult(created=False, disposition="duplicate")
    except OperationalError as exc:
        raise IngestTemporarilyUnavailable from exc


def _record_delivery(
    *,
    provider,
    delivery_key,
    external_event_id,
    event_name,
    call_external_id,
    outcome,
    normalized_phone,
    dialed_number,
    occurred_at,
    is_call_event,
    parse_error,
):
    if _delivery_exists(provider, delivery_key, external_event_id):
        return DeliveryResult(created=False, disposition="duplicate")

    event = CallEvent(
        provider=provider,
        delivery_key=delivery_key,
        external_event_id=external_event_id,
        event_name=(event_name or "")[:64],
        call_external_id=(call_external_id or "")[:128],
        outcome=outcome or "",
        normalized_phone=(normalized_phone or "")[:32],
        occurred_at=occurred_at,
        disposition=CallEvent.Disposition.FAILED,
    )
    if parse_error:
        event.detail = parse_error[:255]
        event.save()
        return DeliveryResult(True, event.disposition, event.detail)
    if not is_call_event:
        event.disposition = CallEvent.Disposition.IGNORED
        event.detail = "Event does not carry a call outcome."
        event.save()
        return DeliveryResult(True, event.disposition, event.detail)

    association = _associate_call(
        call_external_id=call_external_id,
        dialed_number=dialed_number,
        normalized_phone=normalized_phone,
        outcome=outcome,
        occurred_at=occurred_at,
    )
    event.disposition = association.disposition
    event.detail = association.detail
    event.customer = association.customer
    event.call_record = association.call_record
    event.save()
    return DeliveryResult(True, event.disposition, event.detail)


def _delivery_exists(provider, delivery_key, external_event_id):
    if CallEvent.objects.filter(provider=provider, delivery_key=delivery_key).exists():
        return True
    if external_event_id and CallEvent.objects.filter(
        provider=provider, external_event_id=external_event_id
    ).exists():
        return True
    return False


@dataclass
class _Association:
    disposition: str
    detail: str = ""
    customer: Customer | None = None
    call_record: CallRecord | None = None


def _associate_call(*, call_external_id, dialed_number, normalized_phone, outcome, occurred_at):
    if not call_external_id:
        return _Association(CallEvent.Disposition.FAILED, "Call id is missing or too long.")
    if not normalized_phone:
        return _Association(
            CallEvent.Disposition.FAILED, "Call payload has no usable phone number."
        )
    allowed = {value for value, _label in CallRecord.Outcome.choices}
    if outcome not in allowed:
        return _Association(CallEvent.Disposition.FAILED, "Call outcome is not recognized.")

    matches = [
        customer
        for customer in Customer.objects.exclude(phone="").only(
            "id", "phone", "archived_at", "trashed_at"
        )
        if phone_match_key(customer.phone) == normalized_phone
    ]
    if not matches:
        return _Association(CallEvent.Disposition.UNMATCHED, "No customer has this number.")
    if len(matches) != 1:
        return _Association(
            CallEvent.Disposition.AMBIGUOUS, "More than one customer has this number."
        )

    customer = Customer.objects.select_for_update().get(pk=matches[0].pk)
    if customer.archived_at or customer.trashed_at:
        return _Association(
            CallEvent.Disposition.INACTIVE, "Customer is archived or in trash."
        )

    record = (
        CallRecord.objects.select_for_update().filter(external_id=call_external_id).first()
    )
    if record is not None and record.customer_id != customer.pk:
        return _Association(
            CallEvent.Disposition.CONFLICT,
            "Call id is already linked to another customer.",
        )
    if record is None:
        record = CallRecord.objects.create(
            customer=customer,
            dialed_number=(dialed_number or normalized_phone)[:64],
            outcome=outcome,
            called_at=occurred_at or timezone.now(),
            external_id=call_external_id,
        )
        apply_customer_status(customer, outcome, occurred_at)
        return _Association(CallEvent.Disposition.MATCHED, "", customer, record)

    if not record.outcome_locked and should_replace_outcome(record.outcome, outcome):
        record.outcome = outcome
        record.save(update_fields=("outcome",))
    if not record.outcome_locked and record.outcome == outcome:
        apply_customer_status(customer, outcome, occurred_at)
    return _Association(CallEvent.Disposition.MATCHED, "", customer, record)


def should_replace_outcome(current, new):
    """Whether a new provider outcome may replace one that is not operator-locked.

    ``unknown`` never overwrites a more specific outcome. A later specific
    outcome replaces ``unknown`` or a different specific outcome.
    """
    if new == CallRecord.Outcome.UNKNOWN and current != CallRecord.Outcome.UNKNOWN:
        return False
    return current != new
