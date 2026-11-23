"""Exceptions raised by israel-listings."""

from __future__ import annotations


class ListingsError(Exception):
    """Base class for all israel-listings errors."""


class BlockedError(ListingsError):
    """The site's bot protection kept refusing the request.

    Refusals observed so far were temporary (seconds to minutes). Wait, slow down, and retry,
    or give the client a fallback route.
    """


class ApiError(ListingsError):
    """The site's API answered with an error (bad parameter, unknown listing, server error...)."""

    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


# Names from yad2-client 0.2, kept so existing code keeps working.
Yad2Error = ListingsError
Yad2APIError = ApiError
