"""Command-line entry point and run orchestration.

Pipeline (see the spec): load+validate config -> select exporters -> authenticate
MangaDex + fetch the source (and, only if a local exporter is selected, the
extras) -> run each selected exporter -> print the summary and exit non-zero on
any failure. ``--dry-run`` performs every read/auth but suppresses all writes.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from dotenv import load_dotenv

from .auth import TokenManager
from .client import MangaDexClient
from .config import Config, load_config
from .errors import ExporterError
from .exporters.base import ExporterResult
from .exporters.registry import build_exporter
from .source import build_dataset

logger = logging.getLogger("exporter")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exporter",
        description="Export your MangaDex reading list to CSV/Excel or MangaUpdates.",
    )
    parser.add_argument("--config", default="./config.yaml", help="path to config.yaml")
    parser.add_argument(
        "--exporters",
        help="comma-separated exporter names to run (non-interactive)",
    )
    parser.add_argument(
        "--all", action="store_true", help="run every configured exporter"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="do all reads/auth but perform no writes",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logging verbosity",
    )
    parser.add_argument(
        "--verbose",
        action="store_const",
        const="DEBUG",
        dest="log_level",
        help="shorthand for --log-level DEBUG",
    )
    return parser


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def select_exporters(config: Config, args: argparse.Namespace) -> list[str]:
    """Resolve which exporter names to run from flags or the interactive prompt."""
    valid = config.exporter_names()

    if args.all:
        return valid

    if args.exporters is not None:
        chosen = [name.strip() for name in args.exporters.split(",") if name.strip()]
        if not chosen:
            raise ExporterError("no exporter selected (empty --exporters)")
        unknown = [name for name in chosen if name not in valid]
        if unknown:
            raise ExporterError(
                f"unknown exporter(s) {unknown}; valid names: {valid}"
            )
        return chosen

    if not sys.stdin.isatty():
        raise ExporterError(
            "no exporter selected: stdin is not a TTY and neither --exporters "
            "nor --all was given"
        )

    import questionary

    answer = questionary.checkbox(
        "Select exporter(s) to run:",
        choices=valid,
    ).ask()
    if not answer:
        raise ExporterError("no exporter selected")
    return [str(name) for name in answer]


def _print_summary(
    results: list[ExporterResult], skipped_uuids: int, dry_run: bool
) -> None:
    header = "Run summary (dry-run)" if dry_run else "Run summary"
    logger.info("=== %s ===", header)
    if skipped_uuids:
        logger.info(
            "%d manga skipped (deleted/restricted, omitted by /manga)", skipped_uuids
        )
    for result in results:
        marker = "OK " if result.success else "FAIL"
        logger.info("[%s] %s: %s", marker, result.name, result.summary)


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.log_level)
    load_dotenv()

    try:
        config = load_config(args.config)
        names = select_exporters(config, args)
        exporters = [build_exporter(config.get_exporter(name)) for name in names]
        logger.info(
            "running %d exporter(s): %s%s",
            len(exporters),
            ", ".join(names),
            " [dry-run]" if args.dry_run else "",
        )

        include_extras = any(e.needs_local_extras for e in exporters)
        tokens = TokenManager.from_config(config.auth)
        with MangaDexClient(config.api, tokens) as client:
            dataset = build_dataset(
                client, config.source, include_extras=include_extras
            )

        results: list[ExporterResult] = []
        for exporter in exporters:
            try:
                results.append(exporter.export(dataset, dry_run=args.dry_run))
            except ExporterError as exc:
                logger.error("exporter %s failed: %s", exporter.name, exc)
                results.append(
                    ExporterResult(
                        name=exporter.name, success=False, summary=f"failed: {exc}"
                    )
                )
    except ExporterError as exc:
        logger.error("%s", exc)
        return 1

    _print_summary(results, len(dataset.skipped_uuids), args.dry_run)
    return 0 if all(r.success for r in results) else 1


def main() -> None:
    sys.exit(run())
