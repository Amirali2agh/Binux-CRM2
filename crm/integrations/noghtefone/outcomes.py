"""Map Noghtefone event names and status strings onto CRM call outcomes.

Status strings other than the ones already approved for the read-only importer
are not given new CRM meanings. They become the explicit ``unknown`` outcome
and are still recorded.
"""

from crm.models import CallRecord

# Approved provider statuses from the existing call-history importer.
_ANSWERED_STATUSES = {"answered"}
_UNANSWERED_STATUSES = {"busy", "failed", "missed", "no_answer"}

# The event name itself is the outcome. ``call.answered`` is the documented example.
_EVENT_IMPLIED_OUTCOMES = {
    "call.answered": CallRecord.Outcome.ANSWERED,
}

# Events that describe a phone call even when no final result is known yet.
CALL_EVENT_NAMES = frozenset(
    {
        "call.started",
        "call.answered",
        "call.ended",
        "call_result.created",
        "voicemail.created",
    }
)


def outcome_from_provider_status(provider_status):
    """Return a call outcome, or ``None`` when ``provider_status`` is empty.

    Any other non-empty status is ``unknown`` (unsupported), not a dropped event.
    """
    if not isinstance(provider_status, str):
        return None
    key = provider_status.strip().lower()
    if not key:
        return None
    if key in _ANSWERED_STATUSES:
        return CallRecord.Outcome.ANSWERED
    if key in _UNANSWERED_STATUSES:
        return CallRecord.Outcome.CALL_AGAIN
    return CallRecord.Outcome.UNKNOWN


def outcome_for_event(event_name, provider_status):
    """Return ``(is_call_event, outcome)``.

    An implied event outcome wins over a contradictory provisional status field.
    Call events without an implied outcome or a known status use ``unknown``.
    """
    if event_name in _EVENT_IMPLIED_OUTCOMES:
        return True, _EVENT_IMPLIED_OUTCOMES[event_name]
    if event_name not in CALL_EVENT_NAMES:
        return False, ""
    mapped = outcome_from_provider_status(provider_status)
    if mapped is None:
        return True, CallRecord.Outcome.UNKNOWN
    return True, mapped
