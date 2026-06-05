"""Build concrete exporters from their config entries."""

from __future__ import annotations

from ..config import (
    CsvExportConfig,
    ExportConfig,
    MangaUpdatesExportConfig,
    XlsxExportConfig,
)
from .base import Exporter
from .csv import CsvExporter
from .mangaupdates import MangaUpdatesExporter
from .xlsx import XlsxExporter


def build_exporter(config: ExportConfig) -> Exporter:
    if isinstance(config, CsvExportConfig):
        return CsvExporter(config)
    if isinstance(config, XlsxExportConfig):
        return XlsxExporter(config)
    if isinstance(config, MangaUpdatesExportConfig):
        return MangaUpdatesExporter(config)
    raise TypeError(f"unsupported export config: {type(config).__name__}")
