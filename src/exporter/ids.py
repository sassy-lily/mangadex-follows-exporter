"""Resolve a MangaDex ``mu`` link to the integer MangaUpdates ``series.id``.

``series.id`` is ``base36_decode( mu_is_legacy_old_id ? old_ids[mu] : mu )``:

* ``docs/mangaupdates.json`` maps legacy *numeric* old ids -> current base36
  slug. If ``mu`` is a key there, swap it for the slug first.
* Otherwise ``mu`` is already the current slug — use it directly.
* In both cases, base36-decode the slug to the integer id.

A manga with no ``mu`` link cannot be synced (resolver returns ``None``; the
caller skips and logs it).
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import ConfigError


def base36_decode(slug: str) -> int:
    return int(slug, 36)


class MangaUpdatesIdResolver:
    def __init__(self, old_ids: dict[str, str]) -> None:
        self._old_ids = old_ids

    @classmethod
    def from_file(cls, path: str | Path) -> MangaUpdatesIdResolver:
        mapping_path = Path(path)
        if not mapping_path.is_file():
            raise ConfigError(f"old-id mapping file not found: {mapping_path}")
        try:
            data = json.loads(mapping_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"could not parse {mapping_path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{mapping_path} must be a JSON object")
        return cls(data)

    def resolve(self, mu: str | None) -> int | None:
        """Return the integer series id, or ``None`` if ``mu`` is missing/invalid."""
        if not mu:
            return None
        slug = self._old_ids.get(mu, mu)
        try:
            return base36_decode(slug)
        except (ValueError, TypeError):
            return None
