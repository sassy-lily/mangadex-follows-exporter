"""The common exporter interface.

Every destination (CSV, xlsx, MangaUpdates, future ones) implements ``Exporter``
and returns an ``ExporterResult`` so the CLI can render a uniform run summary
and decide the process exit code. Exporter *options* come from config and are
passed at construction; ``export`` only takes the assembled dataset and the
dry-run flag.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..models import Dataset


@dataclass
class ExporterResult:
    name: str
    success: bool
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


class Exporter(ABC):
    """Base class for all export destinations."""

    #: Whether this exporter needs the conditional local-export extras
    #: (ratings/stats/read-progress) fetched before it runs.
    needs_local_extras: bool = False

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def export(self, dataset: Dataset, *, dry_run: bool) -> ExporterResult:
        """Write/sync ``dataset`` to this destination (or plan it, if dry_run)."""
