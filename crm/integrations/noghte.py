import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from django.conf import settings

API_BASE_URL = "https://api.phone.noghte.io/api/public/v1"
MAX_API_PAGES = 10000
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}


class NoghteAPIError(Exception):
    pass


def map_call_status(provider_status):
    """Return ``(call_outcome, customer_status_or_none)`` for a provider status.

    Empty values are unusable (``None``). Any other unrecognized status is the
    explicit unknown outcome and does not change the customer.
    """
    from crm.call_ingestion import customer_status_for_outcome
    from crm.integrations.noghtefone.outcomes import outcome_from_provider_status

    outcome = outcome_from_provider_status(provider_status)
    if outcome is None:
        return None
    return outcome, customer_status_for_outcome(outcome)


class NoghteAPIClient:
    """Read-only ``GET /calls`` client.

    Pagination keys ``data``, ``current_page``, and ``last_page`` are provisional.
    The integrations page documents the URL and query parameters, not the JSON shape.
    """
    def __init__(self, api_key_file=None, *, timeout=20, max_attempts=3, retry_delay=1):
        if api_key_file is None:
            api_key_file = getattr(settings, "NOGHTE_API_KEY_FILE", "")
        if not api_key_file:
            raise NoghteAPIError("NOGHTE_API_KEY_FILE is not configured.")
        try:
            with Path(api_key_file).open(encoding="utf-8") as key_file:
                if os.name != "nt" and os.fstat(key_file.fileno()).st_mode & 0o077:
                    raise NoghteAPIError(
                        "The configured phone API key file must not be group- or world-accessible."
                    )
                token = key_file.read().strip()
        except NoghteAPIError:
            raise
        except OSError:
            raise NoghteAPIError("The configured phone API key file is not readable.") from None
        if not token or "\n" in token or "\r" in token:
            raise NoghteAPIError("The configured phone API key file is empty or invalid.")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self._token = token
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay

    def iter_calls(self, *, number, since):
        if not isinstance(number, str) or not number:
            raise NoghteAPIError("A customer phone number is required for call lookup.")
        base_params = {"number": number, "since": str(since), "direction": "outbound"}
        page = 1
        while page <= MAX_API_PAGES:
            params = dict(base_params)
            if page > 1:
                params["page"] = str(page)
            payload = self._request_json(params)
            rows = payload.get("data")
            current_page = payload.get("current_page", page)
            last_page = payload.get("last_page", current_page)
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise NoghteAPIError("Phone service returned an invalid call-history page.")
            if (
                not isinstance(current_page, int)
                or isinstance(current_page, bool)
                or not isinstance(last_page, int)
                or isinstance(last_page, bool)
                or current_page != page
                or last_page < current_page
            ):
                if not rows and last_page == 0:
                    return
                raise NoghteAPIError("Phone service returned invalid pagination metadata.")
            yield from rows
            if current_page >= last_page:
                return
            page = current_page + 1
        raise NoghteAPIError("Phone service pagination exceeded the safe page limit.")

    def _request_json(self, params):
        url = f"{API_BASE_URL}/calls?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
            method="GET",
        )
        for attempt in range(self.max_attempts):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    try:
                        payload = json.loads(response.read())
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        raise NoghteAPIError("Phone service returned invalid JSON.") from None
                    if not isinstance(payload, dict):
                        raise NoghteAPIError("Phone service returned an invalid response.")
                    return payload
            except urllib.error.HTTPError as error:
                if error.code in RETRYABLE_HTTP_STATUSES and attempt + 1 < self.max_attempts:
                    time.sleep(self.retry_delay * (2**attempt))
                    continue
                if error.code in RETRYABLE_HTTP_STATUSES:
                    raise NoghteAPIError("Phone service request failed after retries.") from None
                raise NoghteAPIError(
                    f"Phone service rejected the request (HTTP {error.code})."
                ) from None
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
                if attempt + 1 < self.max_attempts:
                    time.sleep(self.retry_delay * (2**attempt))
                    continue
                raise NoghteAPIError("Phone service request failed after retries.") from None
        raise NoghteAPIError("Phone service request failed after retries.")
