from __future__ import annotations

import json

import pytest

from exporter.errors import ConfigError
from exporter.ids import MangaUpdatesIdResolver, base36_decode


def test_base36_decode_matches_spec_example():
    assert base36_decode("5yoo9wh") == 12981205025


def test_current_slug_decoded_directly():
    resolver = MangaUpdatesIdResolver({})
    assert resolver.resolve("5yoo9wh") == 12981205025


def test_legacy_old_id_mapped_then_decoded():
    # "33" is a legacy numeric old id -> base36 slug -> integer.
    resolver = MangaUpdatesIdResolver({"33": "pb8uwds"})
    assert resolver.resolve("33") == base36_decode("pb8uwds")
    assert resolver.resolve("33") == 55099564912


def test_missing_mu_returns_none():
    resolver = MangaUpdatesIdResolver({})
    assert resolver.resolve(None) is None
    assert resolver.resolve("") is None


def test_invalid_slug_returns_none():
    resolver = MangaUpdatesIdResolver({})
    assert resolver.resolve("!!!not-base36!!!") is None


def test_from_file_roundtrip(tmp_path):
    path = tmp_path / "map.json"
    path.write_text(json.dumps({"1": "t8zu40m"}))
    resolver = MangaUpdatesIdResolver.from_file(path)
    assert resolver.resolve("1") == base36_decode("t8zu40m")


def test_from_file_missing(tmp_path):
    with pytest.raises(ConfigError):
        MangaUpdatesIdResolver.from_file(tmp_path / "nope.json")
