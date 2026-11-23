"""Removal of personal data from API payloads.

Listings are public, but some payloads carry data about private sellers (first name, internal
customer id, a free-text field that repeats the seller's name). yad2-client never returns them:
only an agency's business name and logo are kept.
"""

from __future__ import annotations

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
