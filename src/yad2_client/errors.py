"""Exceptions raised by yad2-client."""

from __future__ import annotations


class Yad2Error(Exception):
    """Base class for all yad2-client errors."""


class BlockedError(Yad2Error):
    """Yad2's bot protection (Radware) answered instead of the API.

    Blocks observed so far were temporary (well under an hour). Wait, slow down, and retry.
    """


class Yad2APIError(Yad2Error):
    """The API answered with an error (bad parameter, unknown listing, server error...)."""

    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message
