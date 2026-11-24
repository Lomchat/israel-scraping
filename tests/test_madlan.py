import json

import pytest

from israel_scraping import ApiError, BlockedError, Listing, Madlan, MadlanListing, drop_duplicates

from .conftest import FakeResponse, FakeSession


def fake_madlan(listings: list[dict], step: int = 34):
    """A fake /api2 applying Madlan's real paging rule: results start at (offset // limit) * step."""
    session = FakeSession(lambda url, params: None)

    def route(url, params):
        variables = session.bodies[-1]["variables"]
        start = (variables["offset"] // variables["limit"]) * step
        page = listings[start:start + variables["limit"]]
        return FakeResponse(body={"data": {"searchPoiV2": {"total": len(listings), "poi": page}}})

    session.route = route
    return Madlan(session_factory=lambda: session, delay=0, retries=0, block_retries=0), session


def test_iter_search_gets_every_listing_despite_the_odd_paging():
    """The API ignores offset and pages by 34: a naive client would only ever see ~1,000 listings."""
    listings = [{"id": f"L{i}", "type": "bulletin", "price": i} for i in range(2500)]
    madlan, session = fake_madlan(listings)

    ids = [x.id for x in madlan.iter_search("sale", location_id="תל-אביב-יפו-ישראל")]

    assert sorted(ids, key=lambda s: int(s[1:])) == [x["id"] for x in listings]  # all, once each
    assert len(session.calls) <= 4  # 2,500 listings in a handful of requests
    assert session.bodies[0]["variables"]["dealType"] == "unitBuy"


def test_refusals_are_blocks_and_api_errors_are_errors():
    challenge = FakeResponse(403, headers={"content-type": "text/html"}, text="<title>Just a moment...</title>")
    rate_limited = FakeResponse(429, headers={"content-type": "text/html"}, text="")
    perimeterx = FakeResponse(200, headers={"content-type": "text/html"}, text='<div id="px-captcha"></div>')
    for refused in (challenge, rate_limited, perimeterx):
        madlan = Madlan(session_factory=lambda r=refused: FakeSession(lambda url, params: r),
                        delay=0, block_retries=0)
        with pytest.raises(BlockedError):
            madlan.search("rent", location_id="רעננה-ישראל")

    missing_header = FakeResponse(400, headers={"content-type": "text/plain"}, text="sorry a1")
    graphql_error = FakeResponse(body={"errors": [{"message": "No matching clause: unitBuyNew"}]})
    for wrong in (missing_header, graphql_error):
        madlan = Madlan(session_factory=lambda r=wrong: FakeSession(lambda url, params: r), delay=0, retries=0)
        with pytest.raises(ApiError):
            madlan.search("rent", location_id="רעננה-ישראל")


def test_cross_site_duplicates_are_dropped_but_not_same_site_ones():
    def flat(source, id_, number="16", price=7000, rooms=3.5):
        return Listing(source=source, id=id_, url="", deal="rent", price=price, rooms=rooms,
                       street="ההסתדרות", house_number=number)

    listings = [
        flat("yad2", "y1"),
        flat("madlan", "m1", price=7100),  # same flat on Madlan, price within 3%: dropped
        flat("madlan", "m2", number="18"),  # another building: kept
        flat("madlan", "m3", price=9000),  # same address, other price: kept (another unit)
        flat("yad2", "y2"),  # same site, same data: kept (never merge a site with itself)
    ]
    assert [x.id for x in drop_duplicates(listings)] == ["y1", "m2", "m3", "y2"]


def test_phone_numbers_are_removed_from_descriptions():
    listing = MadlanListing.from_api({
        "id": "x", "dealType": "unitRent", "floor": "3",
        "description": "דירה מהממת, לפרטים 050-1234567 או 03 612 3456. מחיר 7,500 ש\"ח, 85 מ\"ר",
        "images": [{"imageUrl": "/bulletins/a.jpg"}, {"imageUrl": "/bulletins/plan.jpg", "isFloorplan": True}],
    })
    assert "1234567" not in listing.description and "612" not in json.dumps(listing.raw, ensure_ascii=False)
    assert "7,500" in listing.description and "85" in listing.description
    assert (listing.deal, listing.floor) == ("rent", 3)
    assert listing.images == ["https://images2.madlan.co.il/t:nonce:v=2/bulletins/a.jpg"]
    assert listing.floor_plans == ["https://images2.madlan.co.il/t:nonce:v=2/bulletins/plan.jpg"]
