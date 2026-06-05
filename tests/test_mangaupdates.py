from __future__ import annotations

import json

import httpx
import pytest

from conftest import mock_client, noop_sleep
from exporter.config import MangaUpdatesExportConfig
from exporter.errors import ExportError
from exporter.exporters.mangaupdates import MangaUpdatesExporter, MUClient
from exporter.ids import MangaUpdatesIdResolver, base36_decode
from exporter.models import Dataset, MangaRecord

SERIES_A = base36_decode("5yoo9wh")  # add (not on any list)
SERIES_B = base36_decode("t8zu40m")  # already on list 0 -> skip
SERIES_C = base36_decode("pb8uwds")  # on list 2 -> move to 0

STANDARD_LISTS = [
    {"list_id": 0, "type": "read"},
    {"list_id": 1, "type": "wish"},
    {"list_id": 2, "type": "complete"},
    {"list_id": 3, "type": "unfinished"},
    {"list_id": 4, "type": "hold"},
]

MEMBERSHIP = {0: [SERIES_B], 2: [SERIES_C]}


def _dataset() -> Dataset:
    def rec(uuid: str, mu: str | None) -> MangaRecord:
        links = {"mu": mu} if mu is not None else {}
        return MangaRecord(uuid=uuid, status="reading", attributes={"links": links})

    return Dataset(
        records=[
            rec("A", "5yoo9wh"),
            rec("B", "t8zu40m"),
            rec("C", "pb8uwds"),
            rec("D", None),  # no mu -> missing
        ]
    )


def make_handler(lists=STANDARD_LISTS):
    captured: dict[str, list] = {"add": [], "move": []}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/account/login":
            return httpx.Response(200, json={"context": {"session_token": "tok"}})
        if path == "/lists":
            return httpx.Response(200, json=lists)
        if path.startswith("/lists/") and path.endswith("/search"):
            list_id = int(path.split("/")[2])
            ids = MEMBERSHIP.get(list_id, [])
            results = [{"record": {"series": {"id": sid}}} for sid in ids]
            return httpx.Response(
                200, json={"total_hits": len(results), "results": results}
            )
        if path == "/lists/series":
            captured["add"].append(json.loads(request.content))
            return httpx.Response(200, json={"status": "success"})
        if path == "/lists/series/update":
            captured["move"].append(json.loads(request.content))
            return httpx.Response(200, json={"status": "success"})
        return httpx.Response(404, json={})

    return handler, captured


@pytest.fixture
def mu_config() -> MangaUpdatesExportConfig:
    return MangaUpdatesExportConfig(update_delay=0.0, backoff_factor=0.0)


def _exporter(config, handler) -> MangaUpdatesExporter:
    client = MUClient(config, http=mock_client(handler), sleep=noop_sleep)
    return MangaUpdatesExporter(
        config, resolver=MangaUpdatesIdResolver({}), client=client
    )


@pytest.mark.usefixtures("mangaupdates_env")
def test_classify_add_move_skip_and_missing(mu_config):
    handler, captured = make_handler()
    result = _exporter(mu_config, handler).export(_dataset(), dry_run=False)

    assert result.success
    assert result.details["added"] == {0: 1}
    assert result.details["moved"] == {0: 1}
    assert result.details["skipped"] == {0: 1}
    assert result.details["missing_mu"] == 1

    # Batch bodies carry integer series ids and the mapped list_id.
    add_body = captured["add"][0]
    assert add_body == [{"series": {"id": SERIES_A}, "list_id": 0}]
    move_body = captured["move"][0]
    assert move_body == [{"series": {"id": SERIES_C}, "list_id": 0}]


@pytest.mark.usefixtures("mangaupdates_env")
def test_dry_run_sends_no_writes(mu_config):
    handler, captured = make_handler()
    result = _exporter(mu_config, handler).export(_dataset(), dry_run=True)

    assert captured["add"] == []
    assert captured["move"] == []
    # Plan still computed.
    assert result.details["added"] == {0: 1}
    assert result.details["moved"] == {0: 1}


@pytest.mark.usefixtures("mangaupdates_env")
def test_list_validation_rejects_wrong_type(mu_config):
    bad_lists = [{"list_id": 0, "type": "wish"}, *STANDARD_LISTS[1:]]
    handler, _ = make_handler(lists=bad_lists)
    with pytest.raises(ExportError, match="expected 'read'"):
        _exporter(mu_config, handler).export(_dataset(), dry_run=False)


@pytest.mark.usefixtures("mangaupdates_env")
def test_list_validation_rejects_missing_list(mu_config):
    handler, _ = make_handler(lists=[{"list_id": 0, "type": "read"}])
    with pytest.raises(ExportError, match="not found"):
        _exporter(mu_config, handler).export(_dataset(), dry_run=False)


@pytest.mark.usefixtures("mangaupdates_env")
def test_login_extracts_session_token(mu_config):
    handler, _ = make_handler()
    client = MUClient(mu_config, http=mock_client(handler), sleep=noop_sleep)
    client.login()
    assert client.get_lists()  # uses the bearer token without error
