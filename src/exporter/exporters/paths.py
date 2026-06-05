"""Output-path helpers shared by the CSV and xlsx exporters."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..errors import ExportError


def render_path(pattern: str, *, now: datetime | None = None) -> Path:
    """Render ``{date}``/``{datetime}`` placeholders from the local-time run.

    ``{date}`` -> ``YYYY-MM-DD``; ``{datetime}`` -> ``YYYY-MM-DDTHHMMSS``
    (filename-safe, no colons).
    """
    moment = now or datetime.now()
    rendered = pattern.format(
        date=moment.strftime("%Y-%m-%d"),
        datetime=moment.strftime("%Y-%m-%dT%H%M%S"),
    )
    return Path(rendered)


def prepare_output_path(path: Path, on_existing: str) -> None:
    """Create parent dirs and enforce the ``on_existing`` policy.

    ``overwrite`` (default) lets the writer replace the file; ``error-if-exists``
    raises if the target already exists.
    """
    if on_existing == "error-if-exists" and path.exists():
        raise ExportError(
            f"output file already exists and on_existing=error-if-exists: {path}"
        )
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
