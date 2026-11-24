"""Removal of personal data from API payloads.

Listings are public, but some payloads carry data about private sellers (first name, internal
customer id, a free-text field that repeats the seller's name). israel-scraping never returns them:
only an agency's business name and logo are kept, contact fields are never requested, and phone
numbers typed into descriptions are removed.
"""

from __future__ import annotations

import re
from typing import Any

_KEEP_IN_CUSTOMER = {"agencyName", "agencyLogo"}
_DROP_KEYS = {
    "searchText",  # free text that includes the seller's name
    "phone",
    "phones",
    "phoneNumber",
    "phoneNumbers",
    "virtualPhoneNumber",
    "email",
    "contactName",
    "contactPhone",
}


# Israeli phone numbers as people type them in descriptions: 050-1234567, 03 123 4567, +972 52...
_PHONE = re.compile(r"(?<!\d)(?:\+?972[-\s.]?|0)(?:[23489]|5\d|7\d)[-\s.]?\d{3}[-\s.]?\d{4}(?!\d)")


def redact_phones(text: str | None) -> str | None:
    """Replace phone numbers found in free text (descriptions) by ``[phone removed]``."""
    return _PHONE.sub("[phone removed]", text) if text else text


def scrub(obj: Any) -> Any:
    """Return a copy of ``obj`` without personal data."""
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key in _DROP_KEYS:
                continue
            if key == "customer" and isinstance(value, dict):
                value = {k: v for k, v in value.items() if k in _KEEP_IN_CUSTOMER}
                if not value:
                    continue
            out[key] = scrub(value)
        return out
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj
