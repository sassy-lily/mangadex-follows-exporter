"""Build the per-manga dataset from the MangaDex API.

Flow:

1. ``GET /manga/status`` -> ``{uuid: status}`` (not paginated; optionally
   filtered to the configured statuses, client-side).
2. ``GET /manga?ids[]=`` in <=100-id batches -> details; UUIDs missing from the
   response are deleted/restricted and recorded as skipped (never abort).
3. Only when a local exporter is selected (``include_extras``): personal
   ratings, global stats, and read-progress. Read markers are collected across
   all manga, de-duplicated, and resolved to chapter numbers in shared batches.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import MangaDexClient
from .config import SourceConfig
from .models import Dataset, MangaRecord, ReadProgress

logger = logging.getLogger(__name__)


def _to_float(value: Any) -> float | None:
    """Parse a nullable numeric string (e.g. ``"10.5"``); ``None`` if unparsable."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_status_map(client: MangaDexClient, source: SourceConfig) -> dict[str, str]:
    payload = client.get_json("/manga/status")
    statuses = payload.get("statuses") or {}
    if not isinstance(statuses, dict):
        return {}
    if source.status:
        wanted = set(source.status)
        return {uuid: st for uuid, st in statuses.items() if st in wanted}
    return dict(statuses)


def fetch_manga_details(
    client: MangaDexClient, uuids: list[str], batch_size: int
) -> dict[str, dict[str, Any]]:
    """Return ``{uuid: attributes}``. The ``limit`` extra is essential: the
    ``/manga`` default page size is small, so without it a 100-id request would
    return only the first few manga."""
    details: dict[str, dict[str, Any]] = {}
    for payload in client.get_chunked(
        "/manga",
        uuids,
        param_name="ids[]",
        extra_params=[("limit", batch_size)],
    ):
        for manga in payload.get("data", []):
            uuid = manga.get("id")
            attributes = manga.get("attributes")
            if uuid and isinstance(attributes, dict):
                details[uuid] = attributes
    return details


def fetch_personal_ratings(
    client: MangaDexClient, uuids: list[str]
) -> dict[str, int]:
    ratings: dict[str, int] = {}
    for payload in client.get_chunked("/rating", uuids, param_name="manga"):
        for uuid, entry in (payload.get("ratings") or {}).items():
            rating = entry.get("rating") if isinstance(entry, dict) else None
            if isinstance(rating, int):
                ratings[uuid] = rating
    return ratings


def fetch_global_ratings(
    client: MangaDexClient, uuids: list[str]
) -> dict[str, float | None]:
    averages: dict[str, float | None] = {}
    for payload in client.get_chunked(
        "/statistics/manga", uuids, param_name="manga[]"
    ):
        for uuid, entry in (payload.get("statistics") or {}).items():
            rating = entry.get("rating") if isinstance(entry, dict) else None
            average = rating.get("average") if isinstance(rating, dict) else None
            averages[uuid] = _to_float(average)
    return averages


def _fetch_read_markers(
    client: MangaDexClient, uuids: list[str]
) -> dict[str, list[str]]:
    """``{manga_uuid: [chapter_uuid, ...]}`` from grouped read markers."""
    grouped: dict[str, list[str]] = {}
    for payload in client.get_chunked(
        "/manga/read",
        uuids,
        param_name="ids[]",
        extra_params=[("grouped", "true")],
    ):
        data = payload.get("data")
        if isinstance(data, dict):
            for uuid, chapter_ids in data.items():
                grouped.setdefault(uuid, []).extend(chapter_ids)
    return grouped


def _fetch_chapter_numbers(
    client: MangaDexClient, chapter_ids: list[str], batch_size: int
) -> dict[str, tuple[float | None, float | None]]:
    """``{chapter_uuid: (chapter_number, volume_number)}`` for read chapters."""
    lookup: dict[str, tuple[float | None, float | None]] = {}
    for payload in client.get_chunked(
        "/chapter",
        chapter_ids,
        param_name="ids[]",
        extra_params=[("limit", batch_size)],
    ):
        for chapter in payload.get("data", []):
            cid = chapter.get("id")
            attrs = chapter.get("attributes") or {}
            if cid:
                lookup[cid] = (
                    _to_float(attrs.get("chapter")),
                    _to_float(attrs.get("volume")),
                )
    return lookup


def fetch_read_progress(
    client: MangaDexClient, uuids: list[str], batch_size: int
) -> dict[str, ReadProgress]:
    grouped = _fetch_read_markers(client, uuids)
    all_chapter_ids = sorted({cid for ids in grouped.values() for cid in ids})
    if not all_chapter_ids:
        return {}
    chapter_numbers = _fetch_chapter_numbers(client, all_chapter_ids, batch_size)

    progress: dict[str, ReadProgress] = {}
    for uuid, chapter_ids in grouped.items():
        chapters = [chapter_numbers.get(cid, (None, None)) for cid in chapter_ids]
        chapter_values = [c for c, _ in chapters if c is not None]
        volume_values = [v for _, v in chapters if v is not None]
        progress[uuid] = ReadProgress(
            highest_chapter=max(chapter_values) if chapter_values else None,
            highest_volume=max(volume_values) if volume_values else None,
        )
    return progress


def build_dataset(
    client: MangaDexClient,
    source: SourceConfig,
    *,
    include_extras: bool,
) -> Dataset:
    """Assemble the dataset; ``include_extras`` gates the local-export fetches."""
    status_map = fetch_status_map(client, source)
    uuids = list(status_map)
    logger.info("found %d manga in reading list", len(uuids))
    if not uuids:
        return Dataset()

    details = fetch_manga_details(client, uuids, source.batch_size)

    ratings: dict[str, int] = {}
    global_ratings: dict[str, float | None] = {}
    read_progress: dict[str, ReadProgress] = {}
    if include_extras:
        present = [u for u in uuids if u in details]
        ratings = fetch_personal_ratings(client, present)
        global_ratings = fetch_global_ratings(client, present)
        read_progress = fetch_read_progress(client, present, source.batch_size)

    dataset = Dataset()
    for uuid in uuids:
        attributes = details.get(uuid)
        if attributes is None:
            dataset.skipped_uuids.append(uuid)
            logger.warning("manga %s omitted by /manga (deleted/restricted)", uuid)
            continue
        dataset.records.append(
            MangaRecord(
                uuid=uuid,
                status=status_map[uuid],
                attributes=attributes,
                personal_rating=ratings.get(uuid),
                global_rating=global_ratings.get(uuid),
                read_progress=read_progress.get(uuid),
            )
        )
    return dataset
