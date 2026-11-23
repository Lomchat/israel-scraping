import pytest

from israel_listings import BlockedError, Yad2, Yad2APIError, find_city
from israel_listings.yad2.realestate import build_params
from israel_listings.yad2.vehicles import build_params as vehicle_params

from .conftest import FakeResponse, FakeSession


def test_block_and_api_errors_are_told_apart(client_with):
    """A Radware block must never be mistaken for data or for a plain API error."""
    redirect = FakeResponse(302, headers={"location": "https://validate.perfdrive.com/x"}, text="")
    captcha = FakeResponse(200, headers={"content-type": "text/html"}, text="<title>Radware Page</title>")
    # firewall stub served as valid JSON: must not be read as an empty page of results
    stub = FakeResponse(200, text='{\n\t"_event_transid" : 2937976752,\n\t"_event_clientip" : "1.2.3.4"\n}')
    firewall = FakeResponse(403, headers={"content-type": "text/html"}, text="<h2>403 Forbidden</h2>")
    rejected = FakeResponse(400, body={"data": {}, "message": "foo is not allowed"})

    for blocked in (redirect, captcha, stub, firewall):
        client, _ = client_with(lambda url, params, r=blocked: r)
        with pytest.raises(BlockedError):
            client.get_json("/realestate-feed/rent/feed", {"region": 1})

    client, _ = client_with(lambda url, params: rejected)
    with pytest.raises(Yad2APIError) as err:
        client.get_json("/realestate-feed/rent/feed", {"foo": 1})
    assert err.value.status == 400 and "foo is not allowed" in err.value.message

    # an isolated refusal (common under load) is waited out instead of aborting a long sweep
    answers = iter([redirect, FakeResponse(body={"data": {"ok": True}})])
    client, session = client_with(lambda url, params: next(answers), block_retries=1)
    assert client.get_json("/realestate-feed/rent/feed", {"region": 1}) == {"data": {"ok": True}}
    assert len(session.calls) == 2


def test_sessions_are_renewed_before_and_after_the_per_session_limit():
    """Yad2 refuses a session (cookies) after ~450 requests: renew it before, and right after a refusal."""
    redirect = FakeResponse(302, headers={"location": "https://validate.perfdrive.com/x"}, text="")
    ok = FakeResponse(body={"data": {}})
    made: list[FakeSession] = []

    def factory(limit: int) -> FakeSession:
        session = FakeSession(lambda url, params: ok)
        session.route = lambda url, params: redirect if len(session.calls) > limit else ok
        made.append(session)
        return session

    # renewed every 3 requests: 7 requests -> 3 sessions, never refused
    client = Yad2(session_factory=lambda: factory(5), delay=0, block_retries=0, session_max_requests=3)
    for _ in range(7):
        client.get_json("/x")
    assert [len(s.calls) for s in made] == [3, 3, 1]

    # a used session refused at its 3rd request is replaced at once, without waiting or failing
    made.clear()
    client = Yad2(session_factory=lambda: factory(2), delay=0, block_retries=0, session_max_requests=100)
    for _ in range(4):
        client.get_json("/x")
    assert [len(s.calls) for s in made] == [3, 2]


def test_refused_route_falls_back_to_proxy_then_comes_back(client_with, monkeypatch):
    """Blocked direct route -> switch to the fallback proxy at once, back to direct after the rest."""
    clock = [1000.0]
    monkeypatch.setattr("israel_listings.http.time.monotonic", lambda: clock[0])
    redirect = FakeResponse(302, headers={"location": "https://validate.perfdrive.com/x"}, text="")
    ok = FakeResponse(body={"data": {}})
    answers = iter([redirect, ok, ok, ok])
    client, session = client_with(lambda url, params: next(answers),
                                  fallback_proxies=["socks5h://u:p@127.0.0.1:40000"], route_cooldown=600)

    client.get_json("/x")  # refused directly, served by the proxy without waiting
    assert session.proxies == [None, "socks5h://u:p@127.0.0.1:40000"]
    assert client.route == "socks5h://127.0.0.1:40000"  # credentials never shown

    client.get_json("/x")  # direct route still resting
    clock[0] += 601
    client.get_json("/x")  # rest over: back to direct
    assert session.proxies[2:] == ["socks5h://u:p@127.0.0.1:40000", None]


def test_city_and_manufacturer_names_resolve_to_ids():
    assert build_params("raanana", None, {}) == {"city": "8700", "region": 1}
    assert build_params("tel aviv", None, {"max_price": 8000})["city"] == "5000"
    assert find_city("רעננה").id == "8700"
    with pytest.raises(LookupError):
        find_city("atlantis")
    with pytest.raises(TypeError):  # the API rejects unknown parameters: fail early and clearly
        build_params("raanana", None, {"max_prise": 8000})
    cars = vehicle_params({"manufacturer": "toyota", "year": (2018, None)})
    assert cars == {"manufacturer": 19, "year": "2018--1"}
    assert vehicle_params({"manufacturer": "טויוטה"})["manufacturer"] == 19
