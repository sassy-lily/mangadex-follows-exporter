"""In-memory representation of the assembled per-manga dataset."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReadProgress:
    """Highest read chapter/volume derived from read markers.

    ``highest_volume`` is the max over chapters that *have* a volume — the
    highest-numbered read chapter may have no volume yet, so it can differ from
    the volume of the chapter that set ``highest_chapter``.
    """

    highest_chapter: float | None = None
    highest_volume: float | None = None


@dataclass
class MangaRecord:
    uuid: str
    status: str
    attributes: dict[str, Any]
    personal_rating: int | None = None
    global_rating: float | None = None
    read_progress: ReadProgress | None = None


@dataclass
class Dataset:
    records: list[MangaRecord] = field(default_factory=list)
    # UUIDs present in /manga/status but omitted by /manga (deleted/restricted).
    skipped_uuids: list[str] = field(default_factory=list)
