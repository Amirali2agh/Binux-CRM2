import hashlib
import hmac
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from crm.integrations.noghtefone.signatures import signature_is_valid
from crm.models import CallEvent, CallRecord, Customer
from crm.phones import normalize_phone, phone_match_key

WEBHOOK_SECRET = "synthetic-webhook-secret"
PREVIOUS_SECRET = "synthetic-previous-webhook-secret"


def sign(body, secret, timestamp):
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.".encode("ascii") + body,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


@override_settings(
    NOGHTE_WEBHOOK_SECRET=WEBHOOK_SECRET,
    NOGHTE_WEBHOOK_SECRET_PREVIOUS=PREVIOUS_SECRET,
    NOGHTE_WEBHOOK_TOLERANCE_SECONDS=300,
)
class NoghtefoneWebhookTests(TestCase):
    def setUp(self):
        self.url = reverse("crm:noghtefone_webhook")
        self.when = (timezone.now() - timedelta(minutes=30)).replace(microsecond=0)
        self.customer = Customer.objects.create(
            name="Webhook customer",
            phone="09121234567",
            status_changed_at=self.when - timedelta(days=1),
        )

    def payload(self, *, event="call.answered", event_id="evt-1", call_id="call-1", phone="+989121234567", status=None, direction="outbound", data_extra=None):
        data = {
            "uuid": call_id,
            "direction": direction,
            "started_at": self.when.isoformat().replace("+00:00", "Z"),
        }
        if direction == "inbound":
            data["from"] = phone
        else:
            data["to"] = phone
        if status is not None:
            data["status"] = status
        if data_extra:
            data.update(data_extra)
        body = {
            "id": event_id,
            "event": event,
            "created_at": self.when.isoformat().replace("+00:00", "Z"),
            "data": data,
        }
        return json.dumps(body, separators=(",", ":")).encode("utf-8")

    def post(self, body, *, delivery="delivery-1", event="call.answered", secret=WEBHOOK_SECRET, timestamp=None, signature=None, client=None):
        timestamp = int(timezone.now().timestamp()) if timestamp is None else timestamp
        header = signature if signature is not None else sign(body, secret, timestamp)
        poster = client or self.client
        return poster.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_NOGHTE_SIGNATURE=header,
            HTTP_X_NOGHTE_DELIVERY=delivery,
            HTTP_X_NOGHTE_EVENT=event,
        )

    def test_answered_event_matches_normalized_number_and_records_the_call(self):
        body = self.payload()
        with self.assertLogs("crm.views", level="INFO") as logs:
            response = self.post(body)

        self.assertEqual(response.status_code, 200)
        call = CallRecord.objects.get(external_id="call-1")
        self.customer.refresh_from_db()
        self.assertEqual(call.customer, self.customer)
        self.assertEqual(call.outcome, CallRecord.Outcome.ANSWERED)
        self.assertEqual(call.dialed_number, "+989121234567")
        self.assertEqual(call.called_at, self.when)
        self.assertEqual(self.customer.status, Customer.Status.REJECTED)
        self.assertEqual(self.customer.status_changed_at, self.when)
        event = CallEvent.objects.get()
        self.assertEqual(event.disposition, CallEvent.Disposition.MATCHED)
        self.assertEqual(event.delivery_key, "delivery-1")
        self.assertEqual(event.call_record, call)
        logged = "\n".join(logs.output)
        self.assertNotIn(WEBHOOK_SECRET, logged)
        self.assertNotIn(self.customer.phone, logged)
        self.assertNotIn("+989121234567", logged)

        detail = self.client.get(reverse("crm:customer_detail", args=[self.customer.pk]))
        self.assertEqual(detail.status_code, 302)

    def test_signed_call_is_visible_on_the_customer_with_unknown_outcome_choice(self):
        user = get_user_model().objects.create_user(
            username="webhook-reader", password="safe-test-password"
        )
        self.client.force_login(user)
        body = self.payload(event="call_result.created", event_id="evt-unknown", call_id="call-unknown", status="queued")
        self.assertEqual(self.post(body, delivery="delivery-unknown", event="call_result.created").status_code, 200)

        response = self.client.get(reverse("crm:customer_detail", args=[self.customer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نامشخص / پشتیبانی‌نشده")
        self.assertContains(response, "+989121234567")
        call = CallRecord.objects.get(external_id="call-unknown")
        self.assertEqual(call.outcome, CallRecord.Outcome.UNKNOWN)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, Customer.Status.NO_CONTACT)

    def test_duplicate_delivery_and_duplicate_event_id_do_not_apply_twice(self):
        body = self.payload()
        self.assertEqual(self.post(body).status_code, 200)
        self.customer.status = Customer.Status.FOLLOW_UP
        self.customer.status_changed_at = self.when + timedelta(minutes=5)
        self.customer.save(update_fields=("status", "status_changed_at", "updated_at"))

        again = self.post(body)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(CallEvent.objects.count(), 1)
        self.assertEqual(CallRecord.objects.count(), 1)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, Customer.Status.FOLLOW_UP)

        other_delivery = self.post(body, delivery="delivery-2")
        self.assertEqual(other_delivery.status_code, 200)
        self.assertEqual(CallEvent.objects.count(), 1)
        self.assertEqual(CallRecord.objects.count(), 1)

    def test_unknown_number_is_stored_and_not_attached(self):
        body = self.payload(phone="09350000000", event_id="evt-unknown-number", call_id="call-unknown-number")
        response = self.post(body, delivery="delivery-unknown-number")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CallRecord.objects.count(), 0)
        event = CallEvent.objects.get()
        self.assertEqual(event.disposition, CallEvent.Disposition.UNMATCHED)
        self.assertIsNone(event.customer)
        self.assertEqual(event.normalized_phone, normalize_phone("09350000000"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, Customer.Status.NO_CONTACT)

    def test_ambiguous_and_archived_numbers_are_not_attached(self):
        Customer.objects.create(
            name="Same number",
            phone="+989121234567",
            status_changed_at=self.when - timedelta(days=1),
        )
        ambiguous = self.post(self.payload(event_id="evt-ambiguous", call_id="call-ambiguous"), delivery="delivery-ambiguous")
        self.assertEqual(ambiguous.status_code, 200)
        self.assertEqual(CallEvent.objects.get().disposition, CallEvent.Disposition.AMBIGUOUS)
        self.assertEqual(CallRecord.objects.count(), 0)

        Customer.objects.filter(name="Same number").delete()
        self.customer.archived_at = self.when
        self.customer.save(update_fields=("archived_at", "updated_at"))
        archived = self.post(
            self.payload(event_id="evt-archived", call_id="call-archived"),
            delivery="delivery-archived",
        )
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(
            CallEvent.objects.get(delivery_key="delivery-archived").disposition,
            CallEvent.Disposition.INACTIVE,
        )
        self.assertEqual(CallRecord.objects.count(), 0)

    def test_bad_signature_and_stale_timestamp_are_rejected_without_storage(self):
        body = self.payload()
        with self.assertLogs("crm.views", level="WARNING") as logs:
            bad = self.post(body, signature=sign(body, "other-secret", int(timezone.now().timestamp())))
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(CallEvent.objects.count(), 0)
        self.assertNotIn(WEBHOOK_SECRET, "\n".join(logs.output))
        self.assertNotIn("other-secret", "\n".join(logs.output))

        stale = self.post(body, timestamp=int(timezone.now().timestamp()) - 301, delivery="delivery-stale")
        self.assertEqual(stale.status_code, 401)
        self.assertEqual(CallEvent.objects.count(), 0)

    def test_previous_secret_is_accepted_during_rotation(self):
        body = self.payload(event_id="evt-rotated", call_id="call-rotated")
        response = self.post(body, delivery="delivery-rotated", secret=PREVIOUS_SECRET)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CallRecord.objects.get(external_id="call-rotated").customer, self.customer)

    def test_missing_secret_rejects_every_delivery(self):
        body = self.payload()
        with override_settings(NOGHTE_WEBHOOK_SECRET="", NOGHTE_WEBHOOK_SECRET_PREVIOUS=""):
            response = self.post(body)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(CallEvent.objects.count(), 0)

    def test_invalid_json_is_stored_as_failed_and_not_retried_by_us(self):
        response = self.post(b"not-json", delivery="delivery-bad-json", event="call.ended")
        self.assertEqual(response.status_code, 200)
        event = CallEvent.objects.get()
        self.assertEqual(event.disposition, CallEvent.Disposition.FAILED)
        self.assertEqual(CallRecord.objects.count(), 0)
        self.assertNotIn("not-json", event.detail)

    def test_storage_failure_returns_503_and_retry_stores_one_call(self):
        body = self.payload(event_id="evt-retry", call_id="call-retry")
        real_save = CallEvent.save
        state = {"calls": 0}

        def flaky_save(instance, *args, **kwargs):
            state["calls"] += 1
            if state["calls"] == 1:
                raise OperationalError("database is locked")
            return real_save(instance, *args, **kwargs)

        with self.assertLogs("crm.views", level="WARNING") as logs:
            with override_temporarily_save(flaky_save):
                first = self.post(body, delivery="delivery-retry")
        self.assertEqual(first.status_code, 503)
        self.assertEqual(CallEvent.objects.count(), 0)
        self.assertEqual(CallRecord.objects.count(), 0)
        self.assertNotIn(WEBHOOK_SECRET, "\n".join(logs.output))

        second = self.post(body, delivery="delivery-retry")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(CallEvent.objects.count(), 1)
        self.assertEqual(CallRecord.objects.filter(external_id="call-retry").count(), 1)

    def test_later_answered_event_refines_unknown_until_an_operator_locks_it(self):
        started = self.payload(event="call.started", event_id="evt-started", status=None)
        self.assertEqual(self.post(started, delivery="delivery-started", event="call.started").status_code, 200)
        call = CallRecord.objects.get(external_id="call-1")
        self.assertEqual(call.outcome, CallRecord.Outcome.UNKNOWN)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, Customer.Status.NO_CONTACT)

        answered = self.payload(event="call.answered", event_id="evt-answered")
        self.assertEqual(self.post(answered, delivery="delivery-answered", event="call.answered").status_code, 200)
        call.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertEqual(call.outcome, CallRecord.Outcome.ANSWERED)
        self.assertEqual(self.customer.status, Customer.Status.REJECTED)
        self.assertEqual(CallRecord.objects.count(), 1)

        user = get_user_model().objects.create_user(
            username="webhook-editor", password="safe-test-password"
        )
        self.client.force_login(user)
        edit = self.client.post(
            reverse("crm:call_outcome_update", args=[self.customer.pk, call.pk]),
            {"outcome": CallRecord.Outcome.CALL_AGAIN},
        )
        self.assertEqual(edit.status_code, 302)
        call.refresh_from_db()
        self.assertTrue(call.outcome_locked)
        self.assertEqual(call.outcome, CallRecord.Outcome.CALL_AGAIN)

        replay = self.payload(event="call.answered", event_id="evt-after-lock")
        self.assertEqual(self.post(replay, delivery="delivery-after-lock", event="call.answered").status_code, 200)
        call.refresh_from_db()
        self.assertEqual(call.outcome, CallRecord.Outcome.CALL_AGAIN)

    def test_inbound_caller_number_matches_and_non_call_events_are_ignored(self):
        inbound = self.payload(
            event="call.answered",
            event_id="evt-inbound",
            call_id="call-inbound",
            phone="9121234567",
            direction="inbound",
        )
        self.assertEqual(self.post(inbound, delivery="delivery-inbound", event="call.answered").status_code, 200)
        self.assertEqual(CallRecord.objects.get(external_id="call-inbound").customer, self.customer)

        recording = self.payload(event="recording.ready", event_id="evt-recording", call_id="call-recording")
        self.assertEqual(
            self.post(recording, delivery="delivery-recording", event="recording.ready").status_code,
            200,
        )
        recorded = CallEvent.objects.get(delivery_key="delivery-recording")
        self.assertEqual(recorded.disposition, CallEvent.Disposition.IGNORED)
        self.assertFalse(CallRecord.objects.filter(external_id="call-recording").exists())

    def test_webhook_accepts_a_signed_post_without_a_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        response = self.post(self.payload(event_id="evt-csrf", call_id="call-csrf"), delivery="delivery-csrf", client=client)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CallRecord.objects.filter(external_id="call-csrf").count(), 1)

    def test_event_name_answers_without_a_status_field(self):
        body = self.payload()
        parsed = json.loads(body)
        self.assertNotIn("status", parsed["data"])
        self.assertEqual(self.post(body, delivery="delivery-implied").status_code, 200)
        self.assertEqual(CallRecord.objects.get().outcome, CallRecord.Outcome.ANSWERED)


class PhoneNormalizationTests(TestCase):
    def test_iranian_mobile_formats_share_one_key(self):
        expected = "989121234567"
        for value in ("09121234567", "+989121234567", "989121234567", "9121234567", "۰۹۱۲۱۲۳۴۵۶۷", "+98 912-123-4567"):
            with self.subTest(value=value):
                self.assertEqual(normalize_phone(value), expected)
                self.assertEqual(phone_match_key(value), expected)

    def test_non_numeric_crm_values_keep_their_own_key(self):
        self.assertEqual(phone_match_key("test-known-number"), "test-known-number")
        self.assertEqual(normalize_phone("test-known-number"), "")


class SignatureUnitTests(TestCase):
    def test_rejects_rewritten_body_and_accepts_the_raw_body(self):
        raw = b'{"id":"1","event":"call.ended"}'
        now = 1_700_000_000
        header = sign(raw, WEBHOOK_SECRET, now)
        self.assertTrue(
            signature_is_valid(raw, header, [WEBHOOK_SECRET], now=now, tolerance_seconds=300)
        )
        rewritten = b'{"event":"call.ended","id":"1"}'
        self.assertFalse(
            signature_is_valid(rewritten, header, [WEBHOOK_SECRET], now=now, tolerance_seconds=300)
        )
        self.assertFalse(
            signature_is_valid(raw, header, [WEBHOOK_SECRET], now=now + 301, tolerance_seconds=300)
        )


class override_temporarily_save:
    def __init__(self, replacement):
        self.replacement = replacement

    def __enter__(self):
        self.original = CallEvent.save
        CallEvent.save = self.replacement
        return self

    def __exit__(self, exc_type, exc, traceback):
        CallEvent.save = self.original
        return False
