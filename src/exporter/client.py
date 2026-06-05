"""HTTP client for the MangaDex REST API.

Responsibilities:

* Inject the bearer token and refresh-once on a 401.
* Retry 429/5xx with exponential backoff, honoring ``Retry-After``.
* Stay under the global ~5 req/s cap via a shared :class:`RateLimiter`.
* Offer two access patterns used by the source layer:
  - ``get_paginated`` for true offset/limit list endpoints (cap 100,
    ``offset + limit <= 10000``);
  - ``get_chunked`` for id-based endpoints, splitting the id list into
    <=100-per-request batches with the correct (per-endpoint) ``deepObject``
    query-param name.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Any

import httpx

from .auth import TokenManager
from .config import ApiConfig
from .errors import ApiError
from .ratelimit import RateLimiter

logger = logging.getLogger(__name__)

_MAX_LIMIT = 100
_MAX_OFFSET_PLUS_LIMIT = 10_000
_MAX_IDS_PER_REQUEST = 100

JsonDict = dict[str, Any]


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class MangaDexClient:
    def __init__(
        self,
        api: ApiConfig,
        tokens: TokenManager,
        *,
        http: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api = api
        self._tokens = tokens
        self._http = http or httpx.Client(
            base_url=api.base_url, timeout=api.timeout, headers=api.headers
        )
        self._limiter = limiter or RateLimiter(api.rate_limit)
        self._sleep = sleep

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> MangaDexClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- core request with retries + token refresh -------------------------

    def get_json(
        self, path: str, *, params: Sequence[tuple[str, Any]] | None = None
    ) -> JsonDict:
        response = self._request("GET", path, params=params)
        payload = response.json()
        if not isinstance(payload, dict):
            raise ApiError(f"unexpected non-object response from {path}")
        return payload

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Sequence[tuple[str, Any]] | None = None,
    ) -> httpx.Response:
        attempt = 0
        refreshed = False
        while True:
            self._limiter.acquire()
            token = self._tokens.token()
            headers = {"Authorization": f"Bearer {token}"}
            try:
                response = self._http.request(
                    method,
                    path,
                    params=list(params) if params is not None else None,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                if attempt >= self._api.max_retries:
                    raise ApiError(f"request to {path} failed: {exc}") from exc
                self._backoff(attempt)
                attempt += 1
                continue

            if response.status_code == 401 and not refreshed:
                logger.debug("got 401 for %s; refreshing token and retrying", path)
                self._tokens.invalidate()
                refreshed = True
                continue

            if self._is_retryable(response.status_code):
                if attempt >= self._api.max_retries:
                    raise ApiError(
                        f"{path} still failing after {attempt} retries "
                        f"(HTTP {response.status_code})"
                    )
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                self._backoff(attempt, retry_after)
                attempt += 1
                continue

            if response.status_code >= 400:
                raise ApiError(
                    f"{path} returned HTTP {response.status_code}"
                )
            return response

    @staticmethod
    def _is_retryable(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    def _backoff(self, attempt: int, retry_after: float | None = None) -> None:
        delay = (
            retry_after
            if retry_after is not None
            else self._api.backoff_factor * (2**attempt)
        )
        if delay > 0:
            self._sleep(delay)

    # -- access patterns ---------------------------------------------------

    def get_paginated(
        self,
        path: str,
        *,
        data_key: str = "data",
        params: Sequence[tuple[str, Any]] | None = None,
        limit: int = _MAX_LIMIT,
    ) -> list[Any]:
        """Walk an offset/limit list endpoint and return all items.

        Respects ``limit <= 100`` and ``offset + limit <= 10000``.
        """
        page_limit = min(limit, _MAX_LIMIT)
        base = list(params or [])
        offset = 0
        items: list[Any] = []
        while True:
            if offset + page_limit > _MAX_OFFSET_PLUS_LIMIT:
                page_limit = _MAX_OFFSET_PLUS_LIMIT - offset
                if page_limit <= 0:
                    break
            page_params = [
                *base,
                ("limit", page_limit),
                ("offset", offset),
            ]
            payload = self.get_json(path, params=page_params)
            page = payload.get(data_key, [])
            items.extend(page)
            total = payload.get("total")
            offset += page_limit
            if total is not None and offset >= total:
                break
            if not page:
                break
        return items

    def get_chunked(
        self,
        path: str,
        ids: Iterable[str],
        *,
        param_name: str,
        extra_params: Sequence[tuple[str, Any]] | None = None,
        chunk_size: int = _MAX_IDS_PER_REQUEST,
    ) -> Iterator[JsonDict]:
        """Yield one JSON payload per id batch.

        ``param_name`` is passed verbatim (e.g. ``ids[]``, ``manga``,
        ``manga[]``) so each endpoint's exact serialization is preserved.
        ``chunk_size`` is clamped to the 100-id-per-request API cap.
        """
        size = max(1, min(chunk_size, _MAX_IDS_PER_REQUEST))
        extras = list(extra_params or [])
        for chunk in _chunked(list(ids), size):
            params: list[tuple[str, Any]] = [
                *extras,
                *((param_name, value) for value in chunk),
            ]
            yield self.get_json(path, params=params)


def _chunked(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
