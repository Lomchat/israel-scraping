"""Shared HTTP layer: browser TLS fingerprint, polite pacing, session renewal, fallback routes,
retries and refusal detection. Each site client gives its base URL, headers and a function that
recognizes its bot protection's refusals."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from curl_cffi import requests as cffi_requests

from .errors import ApiError, BlockedError, ListingsError

log = logging.getLogger("israel_listings")


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


class HttpClient:
    """HTTP client shared by the site clients.

    :param base_url: e.g. ``https://gw.yad2.co.il``.
    :param headers: headers sent with every request (what the site itself sends).
    :param is_blocked: tells whether a response is a refusal from the bot protection.
    :param site: name used in messages.
    :param impersonate: browser whose TLS/HTTP2 fingerprint is presented (see curl_cffi).
    :param delay: minimum seconds between two requests.
    :param timeout: request timeout in seconds.
    :param retries: retries on network errors, HTTP 429 and 5xx (with exponential backoff).
    :param block_retries: when every route is refused, wait ``block_wait`` seconds and retry, at
        most this many times, before raising ``BlockedError``.
    :param block_wait: seconds to wait after a refusal.
    :param proxy: optional proxy URL for the main route, e.g. ``socks5h://127.0.0.1:1080``.
    :param fallback_proxies: proxies to switch to when the main route is refused (e.g. a local
        Cloudflare WARP proxy). A refused route rests ``route_cooldown`` seconds, then the client
        goes back to it: the main route is always preferred.
    :param route_cooldown: seconds a refused route is left aside.
    :param session_max_requests: start a fresh session (new cookies) after this many requests;
        a used session that gets refused is also replaced at once.
    :param session_factory: callable returning a new HTTP session (mainly for tests).
    """

    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        is_blocked: Callable[[Any], bool],
        site: str,
        impersonate: str = "chrome",
        delay: float = 1.0,
        timeout: float = 30.0,
        retries: int = 2,
        block_retries: int = 2,
        block_wait: float = 60.0,
        proxy: str | None = None,
        fallback_proxies: Sequence[str] = (),
        route_cooldown: float = 600.0,
        session_max_requests: int = 300,
        session_factory: Callable[[], Any] | None = None,
    ):
        self.base_url = base_url
        self.headers = dict(headers)
        self.is_blocked = is_blocked
        self.site = site
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.block_retries = block_retries
        self.block_wait = block_wait
        self.route_cooldown = route_cooldown
        self.session_max_requests = session_max_requests
        self._new_session = session_factory or (lambda: cffi_requests.Session(impersonate=impersonate))
        self._routes: list[str | None] = [proxy, *fallback_proxies]
        self._resting_until = [0.0] * len(self._routes)
        self._route = 0
        self._sessions: dict[int, Any] = {}  # one session (cookies) per route
        self._session_uses: dict[int, int] = {}
        self._last_request = 0.0

    @property
    def route(self) -> str:
        """The route in use: ``"direct"`` or the proxy URL (without credentials)."""
        return _label(self._routes[self._route])

    def _throttle(self) -> None:
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _choose_route(self) -> bool:
        """Use the first route that is not resting. False if they all are."""
        now = time.monotonic()
        for index, until in enumerate(self._resting_until):
            if until <= now:
                if index != self._route:
                    log.warning("%s: now using route %s", self.site, _label(self._routes[index]))
                self._route = index
                return True
        return False

    def _session_for(self, route: int) -> Any:
        """The route's session, renewed every ``session_max_requests`` requests."""
        if route not in self._sessions or self._session_uses[route] >= self.session_max_requests:
            self._sessions[route] = self._new_session()
            self._session_uses[route] = 0
        self._session_uses[route] += 1
        return self._sessions[route]

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: str | bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Send a request and return the response, once it is neither refused nor an error.

        :raises BlockedError: the bot protection kept refusing on every route.
        :raises ApiError: the site answered with an error.
        """
        url = self.base_url + path
        query = clean_params(params)
        all_headers = {**self.headers, **(headers or {})}
        failures = blocks = 0
        while True:
            self._choose_route()  # if every route rests, keep the current one
            route = self._route
            proxy = self._routes[route]
            self._throttle()
            try:
                resp = self._session_for(route).request(
                    method,
                    url,
                    params=query or None,
                    data=data,
                    headers=all_headers,
                    proxies={"http": proxy, "https": proxy} if proxy else None,
                    timeout=self.timeout,
                    allow_redirects=False,
                )
            except Exception as exc:  # curl_cffi raises its own error types
                if failures >= self.retries:
                    raise ListingsError(f"{self.site}: network error on {url} via {_label(proxy)}: {exc}") from exc
                failures += 1
                time.sleep(2**failures)
                continue

            if self.is_blocked(resp):
                used = self._session_uses.get(route, 0)
                if used > 1:
                    # Refusals are often tied to the session (cookies), not the IP: retry at once
                    # with a fresh one. A fresh session refused too means the route itself is.
                    log.info("%s: session refused after %d requests, starting a fresh one", self.site, used)
                    del self._sessions[route]
                    continue
                self._resting_until[route] = time.monotonic() + self.route_cooldown
                if len(self._routes) > 1:
                    log.warning("%s: route %s refused, resting %.0fs", self.site, _label(proxy),
                                self.route_cooldown)
                    if any(until <= time.monotonic() for until in self._resting_until):
                        continue  # another route is available: switch right away
                if blocks >= self.block_retries:
                    raise BlockedError(
                        f"{self.site}: refused by the bot protection on {path} (HTTP {resp.status_code}). "
                        "Blocks are usually temporary: wait, lower the request rate, and retry."
                    )
                blocks += 1
                time.sleep(self.block_wait)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if failures >= self.retries:
                    raise ApiError(resp.status_code, _error_message(resp))
                failures += 1
                time.sleep(2**failures)
                continue
            if resp.status_code >= 400:
                raise ApiError(resp.status_code, _error_message(resp))
            return resp

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """GET ``base_url + path`` and return the decoded JSON body."""
        return self.request("GET", path, params=params).json()

    def post_json(self, path: str, body: str, headers: Mapping[str, str] | None = None) -> Any:
        """POST a JSON body to ``base_url + path`` and return the decoded JSON answer."""
        return self.request("POST", path, data=body.encode(), headers=headers).json()


def _label(proxy: str | None) -> str:
    if not proxy:
        return "direct"
    scheme, _, rest = proxy.partition("://")
    return f"{scheme}://{rest.rpartition('@')[2]}"


def _error_message(resp: Any) -> str:
    try:
        return str(resp.json().get("message") or resp.text[:200])
    except Exception:
        return (resp.text or "")[:200]
