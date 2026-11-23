"""HTTP layer: browser-like TLS fingerprint, polite pacing, retries, block detection."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from curl_cffi import requests as cffi_requests

from .errors import BlockedError, Yad2APIError, Yad2Error

API_BASE = "https://gw.yad2.co.il"
SITE = "https://www.yad2.co.il"

# The API rejects some clients that do not look like the site itself calling it
# (e.g. a Chrome TLS fingerprint without a Referer), so always send what the site sends.
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": SITE,
    "Referer": SITE + "/",
}


def _encode(value: Any) -> Any:
    if isinstance(value, bool):
        return 1 if value else None
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(v) for v in value)
    return value


def clean_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop empty values and encode booleans (``True`` -> 1) and lists (comma-separated)."""
    out = {}
    for key, value in (params or {}).items():
        value = _encode(value)
        if value is not None and value != "":
            out[key] = value
    return out


def _is_blocked(resp: Any) -> bool:
    # The API never redirects: Radware redirects blocked clients to validate.perfdrive.com.
    if 300 <= resp.status_code < 400:
        return True
    if "json" in (resp.headers.get("content-type") or ""):
        return False
    head = (resp.text or "")[:5000]
    return "perfdrive" in head or "Radware" in head


class Yad2:
    """Client for Yad2's public JSON API.

    >>> yad2 = Yad2()
    >>> page = yad2.realestate.search("rent", city="raanana", max_price=8000)

    :param impersonate: browser whose TLS/HTTP2 fingerprint is presented (see curl_cffi).
    :param delay: minimum seconds between two requests. Be gentle: the default is one per second.
    :param timeout: request timeout in seconds.
    :param retries: retries on network errors, HTTP 429 and 5xx (with exponential backoff).
    :param block_retries: when the bot protection refuses a request, wait ``block_wait`` seconds
        and retry, at most this many times, before raising ``BlockedError``.
    :param block_wait: seconds to wait after a refusal.
    :param proxy: optional proxy URL, e.g. ``socks5h://127.0.0.1:1080``.
    :param session: custom session object (mainly for tests).
    """

    def __init__(
        self,
        *,
        impersonate: str = "chrome",
        delay: float = 1.0,
        timeout: float = 30.0,
        retries: int = 2,
        block_retries: int = 2,
        block_wait: float = 60.0,
        proxy: str | None = None,
        session: Any = None,
    ):
        from .realestate import RealEstate
        from .vehicles import Vehicles

        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.block_retries = block_retries
        self.block_wait = block_wait
        self._proxies = {"http": proxy, "https": proxy} if proxy else None
        self._session = session or cffi_requests.Session(impersonate=impersonate)
        self._last_request = 0.0
        self.realestate = RealEstate(self)
        self.vehicles = Vehicles(self)

    def _throttle(self) -> None:
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """GET ``API_BASE + path`` and return the decoded JSON body.

        :raises BlockedError: the bot protection answered instead of the API.
        :raises Yad2APIError: the API answered with an error.
        """
        url = API_BASE + path
        query = clean_params(params)
        failures = blocks = 0
        while True:
            self._throttle()
            try:
                resp = self._session.get(
                    url,
                    params=query,
                    headers=HEADERS,
                    proxies=self._proxies,
                    timeout=self.timeout,
                    allow_redirects=False,
                )
            except Exception as exc:  # curl_cffi raises its own error types
                if failures >= self.retries:
                    raise Yad2Error(f"network error on {url}: {exc}") from exc
                failures += 1
                time.sleep(2**failures)
                continue

            if _is_blocked(resp):
                # Isolated refusals happen under load, and blocks last minutes: back off, then retry.
                if blocks >= self.block_retries:
                    raise BlockedError(
                        f"blocked by Yad2's bot protection on {path} (HTTP {resp.status_code}). "
                        "Blocks are usually temporary: wait, lower the request rate, and retry."
                    )
                blocks += 1
                time.sleep(self.block_wait)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if failures >= self.retries:
                    raise Yad2APIError(resp.status_code, _error_message(resp))
                failures += 1
                time.sleep(2**failures)
                continue
            if resp.status_code >= 400:
                raise Yad2APIError(resp.status_code, _error_message(resp))
            return resp.json()


def _error_message(resp: Any) -> str:
    try:
        return str(resp.json().get("message") or resp.text[:200])
    except Exception:
        return (resp.text or "")[:200]
