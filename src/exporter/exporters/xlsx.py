"""Excel exporter: writes the local-export columns to a single sheet via openpyxl."""

from __future__ import annotations

import logging

from openpyxl import Workbook

from ..config import XlsxExportConfig
from ..models import Dataset
from .base import Exporter, ExporterResult
from .columns import row_for
from .paths import prepare_output_path, render_path

logger = logging.getLogger(__name__)


class XlsxExporter(Exporter):
    needs_local_extras = True

    def __init__(self, config: XlsxExportConfig) -> None:
        super().__init__(config.name)
        self._config = config

    def export(self, dataset: Dataset, *, dry_run: bool) -> ExporterResult:
        config = self._config
        path = render_path(config.path)
        rows = [row_for(record, config.columns) for record in dataset.records]

        if dry_run:
            logger.info(
                "[dry-run] %s would write %d rows to %s", self.name, len(rows), path
            )
            return ExporterResult(
                name=self.name,
                success=True,
                summary=f"[dry-run] would write {len(rows)} rows to {path}",
                details={"rows": len(rows), "path": str(path), "dry_run": True},
            )

        prepare_output_path(path, config.on_existing)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = config.sheet_name
        sheet.append(config.columns)
        for row in rows:
            sheet.append(row)
        workbook.save(path)

        logger.info("%s wrote %d rows to %s", self.name, len(rows), path)
        return ExporterResult(
            name=self.name,
            success=True,
            summary=f"wrote {len(rows)} rows to {path}",
            details={"rows": len(rows), "path": str(path)},
        )
