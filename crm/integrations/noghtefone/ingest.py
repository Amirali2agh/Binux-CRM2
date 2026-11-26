"""Turn one authenticated Noghtefone webhook body into a domain delivery."""

from crm.call_ingestion import record_delivery
from crm.integrations.noghtefone.parser import parse_webhook_body

PROVIDER = "noghtefone"


def ingest_signed_body(*, raw_body, delivery_id, event_header):
    parsed = parse_webhook_body(raw_body, event_header=event_header)
    return record_delivery(
        provider=PROVIDER,
        delivery_key=delivery_id,
        external_event_id=parsed.external_event_id,
        event_name=parsed.event_name,
        call_external_id=parsed.call_external_id,
        outcome=parsed.outcome,
        normalized_phone=parsed.normalized_phone,
        dialed_number=parsed.dialed_number,
        occurred_at=parsed.occurred_at,
        is_call_event=parsed.is_call_event,
        parse_error=parsed.parse_error,
    )
