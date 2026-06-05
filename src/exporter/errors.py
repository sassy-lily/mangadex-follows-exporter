"""Typed exceptions used across the exporter.

Keeping these in one module lets the CLI catch them uniformly and translate
them into a clean error message + non-zero exit code, rather than leaking
tracebacks for expected failure modes (bad config, missing secret, auth, API).
"""

from __future__ import annotations


class ExporterError(Exception):
    """Base class for all expected, user-facing errors."""


class ConfigError(ExporterError):
    """Configuration file is missing, malformed, or references an unset env var."""


class AuthError(ExporterError):
    """Authentication against an upstream service failed."""


class ApiError(ExporterError):
    """An upstream API returned an unrecoverable error response."""


class ExportError(ExporterError):
    """An exporter failed while writing its output."""
