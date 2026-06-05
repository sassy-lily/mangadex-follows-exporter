from __future__ import annotations

import argparse

import pytest

from exporter.cli import build_parser, select_exporters
from exporter.config import Config
from exporter.errors import ExporterError


def _config() -> Config:
    return Config.model_validate(
        {
            "exports": [
                {"name": "csv", "type": "csv"},
                {"name": "mu", "type": "mangaupdates"},
            ]
        }
    )


def _args(**kwargs) -> argparse.Namespace:
    defaults = {"all": False, "exporters": None}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_all_selects_every_exporter():
    assert select_exporters(_config(), _args(all=True)) == ["csv", "mu"]


def test_explicit_names():
    assert select_exporters(_config(), _args(exporters="mu")) == ["mu"]


def test_unknown_name_errors_with_valid_list():
    with pytest.raises(ExporterError, match="unknown exporter"):
        select_exporters(_config(), _args(exporters="bogus"))


def test_empty_exporters_errors():
    with pytest.raises(ExporterError, match="no exporter selected"):
        select_exporters(_config(), _args(exporters=" , "))


def test_non_tty_without_flags_errors(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(ExporterError, match="not a TTY"):
        select_exporters(_config(), _args())


def test_parser_defaults():
    args = build_parser().parse_args([])
    assert args.config == "./config.yaml"
    assert args.dry_run is False
    assert args.log_level == "INFO"
