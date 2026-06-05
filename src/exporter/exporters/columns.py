"""Derive the local-export columns from a manga record.

This module is the single source of truth for the CSV/xlsx column values, so
the documented gotchas live here in one place:

* ``primary_title`` is the *first value* of the ``title`` map (don't assume the
  language key).
* ``secondary_title`` is the first ``en``-keyed entry in ``altTitles`` (a list
  of single-key maps); blank if none.
* ``highest_read_volume`` is the max *non-null* volume — the top read chapter
  may have no volume yet (computed upstream in ``source``).
* Missing/optional values render as empty strings, never ``"None"``.
"""

from __future__ import annotations

from typing import Any

from ..errors import ExportError
from ..models import MangaRecord

MANGADEX_TITLE_URL = "https://mangadex.org/title/{uuid}"


def _first_value(mapping: Any) -> str:
    if isinstance(mapping, dict):
        for value in mapping.values():
            if value:
                return str(value)
    return ""


def _english_alt_title(alt_titles: Any) -> str:
    if isinstance(alt_titles, list):
        for entry in alt_titles:
            if isinstance(entry, dict) and "en" in entry:
                return str(entry["en"])
    return ""


def _fmt_number(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def derive_fields(record: MangaRecord) -> dict[str, str]:
    """Return all known local-export fields for ``record`` as strings."""
    attrs = record.attributes
    raw_links = attrs.get("links")
    links: dict[str, Any] = raw_links if isinstance(raw_links, dict) else {}
    progress = record.read_progress

    return {
        "uuid": record.uuid,
        "primary_title": _first_value(attrs.get("title")),
        "secondary_title": _english_alt_title(attrs.get("altTitles")),
        "personal_rating": _fmt_number(record.personal_rating),
        "global_rating": _fmt_number(record.global_rating),
        "highest_read_chapter": _fmt_number(
            progress.highest_chapter if progress else None
        ),
        "highest_read_volume": _fmt_number(
            progress.highest_volume if progress else None
        ),
        "jp_publication_url": str(links.get("raw", "") or ""),
        "en_publication_url": str(links.get("engtl", "") or ""),
        "mangadex_url": MANGADEX_TITLE_URL.format(uuid=record.uuid),
    }


def row_for(record: MangaRecord, columns: list[str]) -> list[str]:
    fields = derive_fields(record)
    unknown = [c for c in columns if c not in fields]
    if unknown:
        raise ExportError(f"unknown export column(s): {unknown}")
    return [fields[column] for column in columns]
