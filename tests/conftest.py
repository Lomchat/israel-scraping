from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from yad2_client import Yad2


class FakeResponse:
    def __init__(
        self, status: int = 200, body: Any = None, headers: dict | None = None, text: str | None = None
    ):
        self.status_code = status
        self.headers = headers or {"content-type": "application/json; charset=utf-8"}
        self.text = text if text is not None else json.dumps(body)
        self._body = body

    def json(self) -> Any:
        return self._body if self._body is not None else json.loads(self.text)


class FakeSession:
    """Answers GET requests with ``route(url, params)``; records the calls."""

    def __init__(self, route: Callable[[str, dict], FakeResponse]):
        self.route = route
        self.calls: list[tuple[str, dict]] = []
        self.proxies: list[str | None] = []

    def get(self, url: str, params: dict | None = None, proxies: dict | None = None, **_: Any) -> Any:
        self.calls.append((url, dict(params or {})))
        self.proxies.append((proxies or {}).get("https"))
        return self.route(url, dict(params or {}))


def make_item(token: str, ad_type: str = "private", **extra: Any) -> dict:
    item = {
        "token": token,
        "adType": ad_type,
        "price": 5000,
        "address": {
            "city": {"id": 8700, "text": "רעננה"},
            "neighborhood": {"id": 798, "text": "קרית הפרחים"},
            "street": {"text": "החרצית"},
            "house": {"number": 10, "floor": 2},
            "coords": {"lat": 32.17, "lon": 34.85},
        },
        "additionalDetails": {"property": {"text": "דירה"}, "roomsCount": 3, "squareMeter": 80},
        "metaData": {"coverImage": "https://img/1.jpg", "images": ["https://img/1.jpg"]},
        "tags": [{"name": "ממ\"ד", "id": 1}],
    }
    item.update(extra)
    return item


def feed(private: list, agency: list, total_pages: int, **promoted: list) -> FakeResponse:
    data = {"private": private, "agency": agency, "pagination": {"total": 0, "totalPages": total_pages}}
    data.update(promoted)
    return FakeResponse(body={"data": data, "message": "OK"})


@pytest.fixture
def client_with() -> Callable[[Callable[[str, dict], FakeResponse]], tuple[Yad2, FakeSession]]:
    def make(route: Callable[[str, dict], FakeResponse], **options: Any) -> tuple[Yad2, FakeSession]:
        session = FakeSession(route)
        settings = {"delay": 0, "retries": 0, "block_retries": 0, "block_wait": 0, **options}
        return Yad2(session_factory=lambda: session, **settings), session

    return make
