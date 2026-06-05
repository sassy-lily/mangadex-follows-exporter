from __future__ import annotations

import pytest

from exporter.config import (
    CsvExportConfig,
    MangaUpdatesExportConfig,
    load_config,
    resolve_secret,
)
from exporter.errors import ConfigError

VALID_CONFIG = """
exports:
  - name: csv
    type: csv
    path: ./out.csv
  - name: mangaupdates
    type: mangaupdates
"""


def _write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def test_load_valid_config(tmp_path):
    config = load_config(_write(tmp_path, VALID_CONFIG))
    assert config.exporter_names() == ["csv", "mangaupdates"]
    assert isinstance(config.get_exporter("csv"), CsvExportConfig)
    assert isinstance(config.get_exporter("mangaupdates"), MangaUpdatesExportConfig)
    # defaults applied
    assert config.auth.token_url.endswith("/openid-connect/token")
    assert config.source.batch_size == 100


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_empty_exports_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "exports: []\n"))


def test_duplicate_names_rejected(tmp_path):
    text = """
exports:
  - {name: dup, type: csv}
  - {name: dup, type: xlsx}
"""
    with pytest.raises(ConfigError, match="unique"):
        load_config(_write(tmp_path, text))


def test_shared_credential_env_names_rejected(tmp_path):
    text = """
auth:
  username_env: SHARED
exports:
  - type: mangaupdates
    username_env: SHARED
"""
    with pytest.raises(ConfigError, match="distinct"):
        load_config(_write(tmp_path, text))


def test_batch_size_bounds(tmp_path):
    text = "source:\n  batch_size: 999\nexports:\n  - {type: csv}\n"
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, text))


def test_resolve_secret_missing(monkeypatch):
    monkeypatch.delenv("DEFINITELY_UNSET", raising=False)
    with pytest.raises(ConfigError, match="DEFINITELY_UNSET"):
        resolve_secret("DEFINITELY_UNSET")


def test_resolve_secret_present(monkeypatch):
    monkeypatch.setenv("PRESENT", "value")
    assert resolve_secret("PRESENT") == "value"
