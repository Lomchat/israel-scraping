import json

from israel_listings import cli

from .conftest import FakeResponse, feed, make_item


def test_search_parses_listings_and_strips_personal_data(client_with):
    agency = make_item("b", "agency", customer={"agencyName": "TGR", "agencyLogo": "l.png", "id": 42})
    page = feed([make_item("a", customer={"id": 7, "name": "Ofer"})], [agency], 1,
                platinum=[make_item("p")])  # promoted lists are ignored
    client, session = client_with(lambda url, params: page)

    result = client.realestate.search("rent", city="raanana", max_price=8000, parking=True)

    url, params = session.calls[0]
    assert url.endswith("/realestate-feed/rent/feed")
    assert params == {"city": "8700", "region": 1, "maxPrice": 8000, "parking": 1, "page": 1}
    assert [x.token for x in result.items] == ["a", "b"]
    first = result.items[0]
    assert (first.price, first.rooms, first.city, first.floor, first.lat) == (5000, 3, "רעננה", 2, 32.17)
    assert first.url == "https://www.yad2.co.il/realestate/item/a"
    assert "customer" not in first.raw  # private seller: nothing kept
    assert result.items[1].raw["customer"] == {"agencyName": "TGR", "agencyLogo": "l.png"}
    assert result.items[1].agency_name == "TGR"

    detail_payload = make_item("a", searchText="שם מוכר עפר", customer={"name": "Ofer"},
                               metaData={"description": "nice"}, inProperty={"includeBalcony": True})
    client, _ = client_with(lambda url, params: FakeResponse(body={"data": detail_payload}))
    detail = client.realestate.get("a")
    assert detail.description == "nice" and detail.features == {"includeBalcony": True}
    dumped = json.dumps(detail.to_dict(include_raw=True), ensure_ascii=False)
    assert "Ofer" not in dumped and "עפר" not in dumped


def test_iter_search_reads_every_page_once_without_duplicates(client_with):
    pages = {
        1: feed([make_item("a"), make_item("b")], [make_item("c", "agency")], 3),
        2: feed([make_item("b"), make_item("d")], [], 3),  # "b" moved to page 2 meanwhile
        3: feed([], [make_item("e", "agency")], 3),
    }
    client, session = client_with(lambda url, params: pages[params["page"]])

    tokens = [x.token for x in client.realestate.iter_search("forsale", city=8700)]
    assert tokens == ["a", "b", "c", "d", "e"]
    assert [p["page"] for _, p in session.calls] == [1, 2, 3]

    session.calls.clear()
    list(client.realestate.iter_search("forsale", city=8700, max_pages=2))
    assert len(session.calls) == 2


def test_cli_watch_outputs_only_new_listings(client_with, monkeypatch, tmp_path, capsys):
    listings = [make_item("a"), make_item("b")]
    client, _ = client_with(lambda url, params: feed(list(listings), [], 1))
    monkeypatch.setattr(cli, "Yad2", lambda **_: client)
    state = str(tmp_path / "seen.json")
    argv = ["realestate", "rent", "--city", "raanana", "--watch", state]

    assert cli.main(argv) == 0
    assert [json.loads(line)["id"] for line in capsys.readouterr().out.splitlines()] == ["a", "b"]

    listings.append(make_item("c"))
    assert cli.main(argv) == 0
    assert [json.loads(line)["id"] for line in capsys.readouterr().out.splitlines()] == ["c"]
    assert set(json.load(open(state))["seen"]) == {"a", "b", "c"}
