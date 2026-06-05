"""MangaUpdates exporter: resolve -> classify -> batch-write.

For each manga we resolve the integer ``series.id`` (see :mod:`exporter.ids`),
classify it against the user's current membership of the 5 standard lists
(add / move / skip), then batch the adds and moves into as few write requests as
possible — respecting the documented five-second update delay (HTTP 412).
"""

from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Any

import httpx

from ..config import MangaUpdatesExportConfig, resolve_secret
from ..errors import ApiError, AuthError, ExportError
from ..ids import MangaUpdatesIdResolver
from ..models import Dataset
from .base import Exporter, ExporterResult

logger = logging.getLogger(__name__)

# Standard list_id -> expected list ``type`` (MangaUpdates convention). Used to
# validate the configured mapping once at startup against GET /lists.
EXPECTED_LIST_TYPES: dict[int, str] = {
    0: "read",
    1: "wish",
    2: "complete",
    3: "unfinished",
    4: "hold",
}

_SEARCH_PER_PAGE = 100


class MUClient:
    """Thin MangaUpdates API client: session login + retry/pacing for writes."""

    def __init__(
        self,
        config: MangaUpdatesExportConfig,
        *,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._username = resolve_secret(config.username_env)
        self._password = resolve_secret(config.password_env)
        self._http = http or httpx.Client(
            base_url=config.base_url, timeout=config.timeout
        )
        self._sleep = sleep
        self._clock = clock
        self._token: str | None = None
        self._last_write: float | None = None

    def login(self) -> None:
        response = self._http.put(
            "/account/login",
            json={"username": self._username, "password": self._password},
        )
        if response.status_code != 200:
            raise AuthError(
                f"MangaUpdates login failed (HTTP {response.status_code})"
            )
        context = response.json().get("context") or {}
        token = context.get("session_token")
        if not token:
            raise AuthError("MangaUpdates login response had no session_token")
        self._token = token

    def _headers(self) -> dict[str, str]:
        if self._token is None:
            self.login()
        return {"Authorization": f"Bearer {self._token}"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        is_write: bool = False,
    ) -> httpx.Response:
        attempt = 0
        relogged = False
        while True:
            if is_write:
                self._pace_write()
            try:
                response = self._http.request(
                    method, path, json=json, headers=self._headers()
                )
            except httpx.HTTPError as exc:
                if attempt >= self._config.max_retries:
                    raise ApiError(f"{path} failed: {exc}") from exc
                self._backoff(attempt)
                attempt += 1
                continue
            finally:
                if is_write:
                    self._last_write = self._clock()

            if response.status_code == 401 and not relogged:
                self._token = None
                relogged = True
                continue

            # 412 = five-second update delay; retry with backoff.
            if response.status_code == 412 or response.status_code >= 500:
                if attempt >= self._config.max_retries:
                    raise ApiError(
                        f"{path} still failing after {attempt} retries "
                        f"(HTTP {response.status_code})"
                    )
                self._backoff(attempt)
                attempt += 1
                continue

            if response.status_code >= 400:
                raise ApiError(f"{path} returned HTTP {response.status_code}")
            return response

    def _pace_write(self) -> None:
        if self._last_write is None:
            return
        elapsed = self._clock() - self._last_write
        remaining = self._config.update_delay - elapsed
        if remaining > 0:
            self._sleep(remaining)

    def _backoff(self, attempt: int) -> None:
        delay = self._config.backoff_factor * (2**attempt)
        if delay > 0:
            self._sleep(delay)

    def get_lists(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/lists")
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def list_membership(self, list_id: int) -> dict[int, int]:
        """Page ``/lists/{id}/search`` -> ``{series_id: list_id}`` for one list."""
        membership: dict[int, int] = {}
        page = 1
        while True:
            response = self._request(
                "POST",
                f"/lists/{list_id}/search",
                json={"page": page, "perpage": _SEARCH_PER_PAGE},
            )
            payload = response.json()
            results = payload.get("results") or []
            for item in results:
                record = item.get("record") or {}
                series = record.get("series") or {}
                series_id = series.get("id")
                if isinstance(series_id, int):
                    membership[series_id] = list_id
            total = payload.get("total_hits", 0)
            if page * _SEARCH_PER_PAGE >= total or not results:
                break
            page += 1
        return membership

    def add_series(self, items: list[dict[str, Any]]) -> None:
        self._request("POST", "/lists/series", json=items, is_write=True)

    def update_series(self, items: list[dict[str, Any]]) -> None:
        self._request("POST", "/lists/series/update", json=items, is_write=True)


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class MangaUpdatesExporter(Exporter):
    def __init__(
        self,
        config: MangaUpdatesExportConfig,
        *,
        resolver: MangaUpdatesIdResolver | None = None,
        client: MUClient | None = None,
    ) -> None:
        super().__init__(config.name)
        self._config = config
        self._resolver = resolver
        self._client = client

    def export(self, dataset: Dataset, *, dry_run: bool) -> ExporterResult:
        config = self._config
        resolver = self._resolver or MangaUpdatesIdResolver.from_file(
            config.old_ids_path
        )
        client = self._client or MUClient(config)
        client.login()

        self._validate_lists(client)
        membership = self._prefetch_membership(client)

        # Classify every record into add / move / skip buckets, keyed by target.
        status_map: dict[str, int] = {
            str(status): list_id
            for status, list_id in config.status_list_map.items()
        }
        to_add: dict[int, list[int]] = defaultdict(list)
        to_move: dict[int, list[int]] = defaultdict(list)
        skipped: Counter[int] = Counter()
        missing_mu = 0

        for record in dataset.records:
            target = status_map.get(record.status)
            if target is None:
                logger.warning(
                    "no list mapping for status %r (manga %s); skipping",
                    record.status,
                    record.uuid,
                )
                continue
            mu = record.attributes.get("links", {}).get("mu")
            series_id = resolver.resolve(mu)
            if series_id is None:
                missing_mu += 1
                logger.info("manga %s has no usable 'mu' id; skipping", record.uuid)
                continue
            current = membership.get(series_id)
            if current is None:
                to_add[target].append(series_id)
            elif current == target:
                skipped[target] += 1
            else:
                to_move[target].append(series_id)

        added, add_failed = self._write(
            client, to_add, dry_run, mode="add"
        )
        moved, move_failed = self._write(
            client, to_move, dry_run, mode="move"
        )

        details = {
            "added": dict(added),
            "moved": dict(moved),
            "skipped": dict(skipped),
            "failed": {**dict(add_failed), **dict(move_failed)},
            "missing_mu": missing_mu,
        }
        success = not add_failed and not move_failed
        summary = self._summarize(details, dry_run)
        logger.info("%s: %s", self.name, summary)
        return ExporterResult(
            name=self.name, success=success, summary=summary, details=details
        )

    def _validate_lists(self, client: MUClient) -> None:
        lists = {lst.get("list_id"): lst for lst in client.get_lists()}
        for list_id in set(self._config.status_list_map.values()):
            entry = lists.get(list_id)
            if entry is None:
                raise ExportError(
                    f"configured list_id {list_id} not found among the user's "
                    "MangaUpdates lists"
                )
            expected = EXPECTED_LIST_TYPES.get(list_id)
            actual = entry.get("type")
            if expected is not None and actual != expected:
                raise ExportError(
                    f"list_id {list_id} is type {actual!r} but expected "
                    f"{expected!r}; check the status->list_id mapping"
                )

    def _prefetch_membership(self, client: MUClient) -> dict[int, int]:
        membership: dict[int, int] = {}
        for list_id in sorted(set(self._config.status_list_map.values())):
            membership.update(client.list_membership(list_id))
        return membership

    def _write(
        self,
        client: MUClient,
        grouped: dict[int, list[int]],
        dry_run: bool,
        *,
        mode: str,
    ) -> tuple[Counter[int], Counter[int]]:
        done: Counter[int] = Counter()
        failed: Counter[int] = Counter()
        for list_id, series_ids in grouped.items():
            for chunk in _chunked(series_ids, self._config.batch_size):
                items = [
                    {"series": {"id": sid}, "list_id": list_id} for sid in chunk
                ]
                if dry_run:
                    done[list_id] += len(chunk)
                    continue
                try:
                    if mode == "add":
                        client.add_series(items)
                    else:
                        client.update_series(items)
                    done[list_id] += len(chunk)
                except ApiError as exc:
                    logger.error(
                        "%s batch for list %d failed: %s", mode, list_id, exc
                    )
                    failed[list_id] += len(chunk)
        return done, failed

    @staticmethod
    def _summarize(details: dict[str, Any], dry_run: bool) -> str:
        def total(group: dict[int, int]) -> int:
            return sum(group.values())

        prefix = "[dry-run] would " if dry_run else ""
        return (
            f"{prefix}add {total(details['added'])}, "
            f"move {total(details['moved'])}, "
            f"skip {total(details['skipped'])} (already present), "
            f"failed {total(details['failed'])}, "
            f"{details['missing_mu']} without a MangaUpdates id"
        )
