"""CSV exporter: writes the local-export columns table to a configured file."""

from __future__ import annotations

import csv
import logging

from ..config import CsvExportConfig
from ..models import Dataset
from .base import Exporter, ExporterResult
from .columns import row_for
from .paths import prepare_output_path, render_path

logger = logging.getLogger(__name__)


class CsvExporter(Exporter):
    needs_local_extras = True

    def __init__(self, config: CsvExportConfig) -> None:
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
        with path.open("w", newline="", encoding=config.encoding) as handle:
            writer = csv.writer(handle, delimiter=config.delimiter)
            writer.writerow(config.columns)
            writer.writerows(rows)

        logger.info("%s wrote %d rows to %s", self.name, len(rows), path)
        return ExporterResult(
            name=self.name,
            success=True,
            summary=f"wrote {len(rows)} rows to {path}",
            details={"rows": len(rows), "path": str(path)},
        )
