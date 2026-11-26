"""Parse a Noghtefone webhook envelope into provider-neutral fields.

PROVISIONAL payload fields
--------------------------
The integrations page documents the envelope ``{id, event, created_at, data}``
and the signature headers. It does **not** document the call object inside
``data``. The key names below are assumptions, isolated here so they can change
without touching customer association. They must be confirmed by the owner
(see ``docs/noghtefone-integration.md``).

Assumed keys inside ``data``:

- call id: ``uuid``, then ``call_uuid``, then ``id``
- callee phone: ``to``, ``destination``, ``number``, ``phone``
- caller phone: ``from``, ``caller``, ``source``
- direction: ``direction`` (``inbound`` / ``outbound``, which *are* documented
  as ``GET /calls`` query values)
- status: ``status``, then ``result``
- call time: ``started_at``, then ``created_at``, then the envelope ``created_at``
"""

import json
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from crm.integrations.noghtefone.outcomes import outcome_for_event
from crm.phones import phone_match_key

# Provisional. Not part of the documented webhook contract.
PROVISIONAL_CALL_ID_KEYS = ("uuid", "call_uuid", "id")
PROVISIONAL_CALLEE_KEYS = ("to", "destination", "number", "phone")
PROVISIONAL_CALLER_KEYS = ("from", "caller", "source")
PROVISIONAL_STATUS_KEYS = ("status", "result")
PROVISIONAL_TIME_KEYS = ("started_at", "created_at")


@dataclass(frozen=True)
class ParsedDelivery:
    external_event_id: str
    event_name: str
    call_external_id: str
    outcome: str
    normalized_phone: str
    dialed_number: str
    occurred_at: datetime | None
    is_call_event: bool
    parse_error: str


def parse_webhook_body(raw_body, *, event_header):
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _failed(event_header, "Payload is not valid JSON.")
    return parse_payload(payload, event_header=event_header)


def parse_payload(payload, *, event_header):
    if not isinstance(payload, dict):
        return _failed(event_header, "Payload is not a JSON object.")
    event_name = _string(payload.get("event")) or _string(event_header)
    header_name = _string(event_header)
    event_id = _bounded_id(payload.get("id"))
    if payload.get("id") not in (None, "") and not event_id:
        return _failed(event_name, "Event id is missing or longer than 128 characters.", event_id="")
    if header_name and _string(payload.get("event")) and header_name != _string(payload.get("event")):
        return _failed(
            event_name,
            "Event header does not match the payload event name.",
            event_id=event_id,
        )
    if not event_name:
        return _failed("", "Payload is missing an event name.", event_id=event_id)

    data = payload.get("data")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return ParsedDelivery(
            external_event_id=event_id,
            event_name=event_name,
            call_external_id="",
            outcome="",
            normalized_phone="",
            dialed_number="",
            occurred_at=None,
            is_call_event=False,
            parse_error="Payload data is not a JSON object.",
        )

    is_call_event, outcome = outcome_for_event(event_name, _first(data, PROVISIONAL_STATUS_KEYS))
    dialed_number = _phone_for_direction(data)
    occurred_at = _occurred_at(data, payload.get("created_at"))
    call_external_id = _bounded_id(_first(data, PROVISIONAL_CALL_ID_KEYS))
    raw_call_id = _first(data, PROVISIONAL_CALL_ID_KEYS)
    parse_error = ""
    if is_call_event and raw_call_id and not call_external_id:
        parse_error = "Call id is longer than 128 characters."
    return ParsedDelivery(
        external_event_id=event_id,
        event_name=event_name,
        call_external_id=call_external_id,
        outcome=outcome,
        normalized_phone=phone_match_key(dialed_number),
        dialed_number=dialed_number,
        occurred_at=occurred_at,
        is_call_event=is_call_event,
        parse_error=parse_error,
    )


def _failed(event_name, message, event_id=""):
    return ParsedDelivery(
        external_event_id=event_id,
        event_name=_string(event_name),
        call_external_id="",
        outcome="",
        normalized_phone="",
        dialed_number="",
        occurred_at=None,
        is_call_event=False,
        parse_error=message,
    )


def _phone_for_direction(data):
    direction = _string(data.get("direction")).lower()
    if direction == "inbound":
        return _first(data, PROVISIONAL_CALLER_KEYS) or _first(data, PROVISIONAL_CALLEE_KEYS)
    return _first(data, PROVISIONAL_CALLEE_KEYS) or _first(data, PROVISIONAL_CALLER_KEYS)


def _occurred_at(data, envelope_created_at):
    for key in PROVISIONAL_TIME_KEYS:
        parsed = _aware(data.get(key))
        if parsed is not None:
            return parsed
    return _aware(envelope_created_at)


def _aware(value):
    if not isinstance(value, str):
        return None
    parsed = parse_datetime(value)
    if parsed is None or timezone.is_naive(parsed):
        return None
    return parsed


def _first(data, keys):
    for key in keys:
        found = _string(data.get(key))
        if found:
            return found
    return ""


def _string(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return ""


def _bounded_id(value):
    text = _string(value)
    if not text or len(text) > 128:
        return ""
    return text
