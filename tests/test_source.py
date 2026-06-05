from __future__ import annotations

import httpx

from conftest import FakeTokens, fast_limiter, mock_client, noop_sleep
from exporter.client import MangaDexClient
from exporter.config import SourceConfig
from exporter.source import build_dataset, fetch_status_map

# Two manga in the reading list; "deleted-uuid" is intentionally omitted by
# /manga to exercise the skip path.
STATUSES = {
    "m1": "reading",
    "m2": "completed",
    "deleted-uuid": "dropped",
}

MANGA = {
    "m1": {
        "title": {"ja": "M1"},
        "altTitles": [{"en": "M1 EN"}],
        "links": {"mu": "5yoo9wh"},
    },
    "m2": {"title": {"en": "M2"}, "altTitles": [], "links": {}},
}

# m1 read two chapters: ch=10 vol=1 and ch=11 vol=null -> highest vol must be 1.
READ_GROUPED = {"m1": ["c1", "c2"]}
CHAPTERS = {
    "c1": {"chapter": "10", "volume": "1"},
    "c2": {"chapter": "11", "volume": None},
}


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    params = request.url.params
    if path == "/manga/status":
        return httpx.Response(200, json={"result": "ok", "statuses": STATUSES})
    if path == "/manga":
        ids = params.get_list("ids[]")
        data = [{"id": i, "attributes": MANGA[i]} for i in ids if i in MANGA]
        return httpx.Response(200, json={"result": "ok", "data": data})
    if path == "/rating":
        ids = params.get_list("manga")
        ratings = {i: {"rating": 9} for i in ids if i == "m1"}
        return httpx.Response(200, json={"result": "ok", "ratings": ratings})
    if path == "/statistics/manga":
        ids = params.get_list("manga[]")
        stats = {i: {"rating": {"average": 8.25}} for i in ids}
        return httpx.Response(200, json={"result": "ok", "statistics": stats})
    if path == "/manga/read":
        ids = params.get_list("ids[]")
        data = {i: READ_GROUPED[i] for i in ids if i in READ_GROUPED}
        return httpx.Response(200, json={"result": "ok", "data": data})
    if path == "/chapter":
        ids = params.get_list("ids[]")
        data = [{"id": i, "attributes": CHAPTERS[i]} for i in ids if i in CHAPTERS]
        return httpx.Response(200, json={"result": "ok", "data": data})
    return httpx.Response(404, json={})


def make_client() -> MangaDexClient:
    from exporter.config import ApiConfig

    return MangaDexClient(
        ApiConfig(base_url="http://testserver", backoff_factor=0.0),
        FakeTokens(),  # type: ignore[arg-type]
        http=mock_client(_handler),
        limiter=fast_limiter(),
        sleep=noop_sleep,
    )


def test_status_filter_applied():
    client = make_client()
    filtered = fetch_status_map(client, SourceConfig(status=["reading"]))
    assert filtered == {"m1": "reading"}


def test_build_dataset_joins_status_and_skips_missing():
    client = make_client()
    dataset = build_dataset(client, SourceConfig(), include_extras=True)

    by_uuid = {r.uuid: r for r in dataset.records}
    assert set(by_uuid) == {"m1", "m2"}
    assert dataset.skipped_uuids == ["deleted-uuid"]
    assert by_uuid["m1"].status == "reading"
    assert by_uuid["m2"].status == "completed"


def test_extras_populated_and_highest_volume_is_non_null_max():
    client = make_client()
    dataset = build_dataset(client, SourceConfig(), include_extras=True)
    m1 = next(r for r in dataset.records if r.uuid == "m1")

    assert m1.personal_rating == 9
    assert m1.global_rating == 8.25
    assert m1.read_progress is not None
    assert m1.read_progress.highest_chapter == 11.0
    assert m1.read_progress.highest_volume == 1.0  # top chapter had no volume


def test_extras_skipped_when_not_requested():
    client = make_client()
    dataset = build_dataset(client, SourceConfig(), include_extras=False)
    m1 = next(r for r in dataset.records if r.uuid == "m1")
    assert m1.personal_rating is None
    assert m1.read_progress is None
