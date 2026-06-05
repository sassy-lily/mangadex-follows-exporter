from __future__ import annotations

from exporter.config import DEFAULT_COLUMNS
from exporter.exporters.columns import derive_fields, row_for
from exporter.models import MangaRecord, ReadProgress


def _record(**overrides) -> MangaRecord:
    attrs = {
        "title": {"ja": "原題"},
        "altTitles": [{"fr": "Titre"}, {"en": "English Title"}],
        "links": {"raw": "https://jp.example", "engtl": "https://en.example"},
    }
    base = {
        "uuid": "uuid-1",
        "status": "reading",
        "attributes": attrs,
        "personal_rating": 8,
        "global_rating": 7.5,
        "read_progress": ReadProgress(highest_chapter=11.0, highest_volume=2.0),
    }
    base.update(overrides)
    return MangaRecord(**base)


def test_primary_title_is_first_value_regardless_of_key():
    fields = derive_fields(_record())
    assert fields["primary_title"] == "原題"


def test_secondary_title_picks_english_alt():
    fields = derive_fields(_record())
    assert fields["secondary_title"] == "English Title"


def test_secondary_title_blank_when_no_english():
    rec = _record(attributes={"title": {"en": "T"}, "altTitles": [{"fr": "x"}]})
    assert derive_fields(rec)["secondary_title"] == ""


def test_highest_read_volume_is_max_non_null():
    # Top chapter (11) has no volume; the max *non-null* volume is 2.
    rec = _record(read_progress=ReadProgress(highest_chapter=11.0, highest_volume=2.0))
    fields = derive_fields(rec)
    assert fields["highest_read_chapter"] == "11"
    assert fields["highest_read_volume"] == "2"


def test_missing_values_render_empty_not_none():
    rec = _record(
        personal_rating=None,
        global_rating=None,
        read_progress=None,
        attributes={"title": {}, "altTitles": [], "links": {}},
    )
    fields = derive_fields(rec)
    for key in (
        "personal_rating",
        "global_rating",
        "highest_read_chapter",
        "highest_read_volume",
        "primary_title",
        "secondary_title",
        "jp_publication_url",
    ):
        assert fields[key] == ""
    assert "None" not in fields.values()


def test_mangadex_url_built_from_uuid():
    assert derive_fields(_record())["mangadex_url"] == (
        "https://mangadex.org/title/uuid-1"
    )


def test_row_for_respects_column_order():
    row = row_for(_record(), list(DEFAULT_COLUMNS))
    assert row[0] == "uuid-1"
    assert len(row) == len(DEFAULT_COLUMNS)


def test_fractional_chapter_preserved():
    rec = _record(read_progress=ReadProgress(highest_chapter=10.5, highest_volume=None))
    assert derive_fields(rec)["highest_read_chapter"] == "10.5"
