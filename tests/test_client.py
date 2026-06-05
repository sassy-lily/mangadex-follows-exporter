from __future__ import annotations

import httpx

from conftest import FakeTokens, fast_limiter, mock_client, noop_sleep
from exporter.client import MangaDexClient


def make_client(handler, api_config) -> tuple[MangaDexClient, FakeTokens]:
    tokens = FakeTokens()
    client = MangaDexClient(
        api_config,
        tokens,  # type: ignore[arg-type]
        http=mock_client(handler),
        limiter=fast_limiter(),
        sleep=noop_sleep,
    )
    return client, tokens


def test_get_paginated_walks_all_pages(api_config):
    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        offset = int(params["offset"])
        limit = int(params["limit"])
        total = 250
        page = [{"id": i} for i in range(offset, min(offset + limit, total))]
        return httpx.Response(200, json={"data": page, "total": total})

    client, _ = make_client(handler, api_config)
    items = client.get_paginated("/manga")
    assert len(items) == 250


def test_get_chunked_splits_ids_and_uses_param_name(api_config):
    seen: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        ids = request.url.params.get_list("ids[]")
        seen.append(ids)
        return httpx.Response(200, json={"data": [{"id": i} for i in ids]})

    client, _ = make_client(handler, api_config)
    ids = [f"id-{n}" for n in range(150)]
    payloads = list(client.get_chunked("/manga", ids, param_name="ids[]"))

    assert [len(c) for c in seen] == [100, 50]
    assert len(payloads) == 2


def test_retries_on_429_then_succeeds(api_config):
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        return httpx.Response(200, json={"ok": True})

    client, _ = make_client(handler, api_config)
    assert client.get_json("/manga/status") == {"ok": True}
    assert calls["n"] == 2


def test_401_triggers_single_refresh_and_retry(api_config):
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(401, json={})
        return httpx.Response(200, json={"ok": True})

    client, tokens = make_client(handler, api_config)
    assert client.get_json("/manga/status") == {"ok": True}
    assert tokens.invalidated == 1
    assert calls["n"] == 2
