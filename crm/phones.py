"""Phone match keys for CRM customer numbers.

Iranian mobile numbers are written several ways in the wild. These forms are the
same subscriber and must match each other:

- ``09121234567``
- ``+989121234567``
- ``989121234567``
- ``9121234567``

Values that are not Iranian numbers keep their exact text aside from surrounding
whitespace, so an existing CRM value still matches itself.
"""

import re

_DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_phone(value):
    """Return canonical ``98`` + national digits, or ``""`` when ``value`` is not an Iranian number."""
    if not isinstance(value, str):
        return ""
    digits = re.sub(r"\D", "", value.translate(_DIGIT_TRANSLATION))
    if digits.startswith("0098"):
        digits = digits[2:]
    if digits.startswith("98"):
        return _from_national(digits[2:])
    if digits.startswith("0"):
        return _from_national(digits[1:])
    if len(digits) == 10 and digits.startswith("9"):
        return "98" + digits
    return ""


def phone_match_key(value):
    """Key used to compare a CRM phone with a provider phone."""
    if not isinstance(value, str):
        return ""
    normalized = normalize_phone(value)
    if normalized:
        return normalized
    # Not an Iranian number: ignore surrounding whitespace only, so an existing
    # CRM value such as "test-known-number" still matches itself exactly.
    return "".join(value.strip().translate(_DIGIT_TRANSLATION).split())


def _from_national(national):
    if len(national) == 10 and national.startswith("9"):
        return "98" + national
    # Trunk-prefix landlines (for example 021… / +9821…) use the same country
    # code. Lengths outside this band are left unmatched rather than guessed.
    if not national.startswith("9") and 8 <= len(national) <= 10:
        return "98" + national
    return ""
