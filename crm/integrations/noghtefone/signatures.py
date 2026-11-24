"""Verify Noghtefone webhook signatures.

``v1`` is ``HMAC_SHA256(secret, "{timestamp}.{raw_body}")`` as documented on the
integrations page. The raw request body is used; re-serializing JSON would
break the signature. Comparison uses :func:`hmac.compare_digest`.
"""

import hmac
import hashlib


def signature_is_valid(raw_body, header, secrets, *, now, tolerance_seconds):
    """Return whether ``header`` signs ``raw_body`` with any configured secret.

    ``now`` is a Unix timestamp. Signatures older or newer than
    ``tolerance_seconds`` are rejected. Every configured secret is compared so
    a rotation window (current + previous) does not stop after the first match.
    """
    parsed = _parse_header(header)
    if parsed is None or not secrets:
        return False
    timestamp, provided = parsed
    if abs(now - timestamp) > tolerance_seconds:
        return False
    signed = f"{timestamp}.".encode("ascii") + raw_body
    provided_bytes = provided.encode("ascii")
    matched = False
    for secret in secrets:
        if not secret:
            continue
        expected = hmac.new(
            secret.encode("utf-8"), signed, hashlib.sha256
        ).hexdigest().encode("ascii")
        if hmac.compare_digest(expected, provided_bytes):
            matched = True
    return matched


def _parse_header(header):
    if not isinstance(header, str) or not header or len(header) > 512:
        return None
    parts = {}
    for piece in header.split(","):
        if "=" not in piece:
            return None
        key, value = piece.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in parts:
            return None
        parts[key] = value
    timestamp_text = parts.get("t", "")
    signature = parts.get("v1", "")
    if not timestamp_text.isdigit() or len(signature) != 64:
        return None
    if any(character not in "0123456789abcdefABCDEF" for character in signature):
        return None
    return int(timestamp_text), signature.lower()
