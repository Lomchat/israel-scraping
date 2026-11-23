import pytest

from yad2_client import BlockedError, Yad2APIError, find_city
from yad2_client.realestate import build_params

from .conftest import FakeResponse


def test_block_and_api_errors_are_told_apart(client_with):
    """A Radware block must never be mistaken for data or for a plain API error."""
    redirect = FakeResponse(302, headers={"location": "https://validate.perfdrive.com/x"}, text="")
    captcha = FakeResponse(200, headers={"content-type": "text/html"}, text="<title>Radware Page</title>")
    rejected = FakeResponse(400, body={"data": {}, "message": "foo is not allowed"})

    for blocked in (redirect, captcha):
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


def test_city_names_resolve_to_ids_and_region():
    assert build_params("raanana", None, {}) == {"city": "8700", "region": 1}
    assert build_params("tel aviv", None, {"max_price": 8000})["city"] == "5000"
    assert find_city("רעננה").id == "8700"
    with pytest.raises(LookupError):
        find_city("atlantis")
    with pytest.raises(TypeError):  # the API rejects unknown parameters: fail early and clearly
        build_params("raanana", None, {"max_prise": 8000})
