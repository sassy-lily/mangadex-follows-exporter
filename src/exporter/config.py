"""Configuration models, YAML loading, and env-var secret resolution.

Design rules enforced here (from the spec):

* The config file never holds secret *values* — only the *names* of the env
  vars to read them from. ``resolve_secret`` reads the real environment (after
  ``python-dotenv`` has loaded any ``.env``) and fails clearly if unset.
* MangaDex and MangaUpdates must use *distinct* credential env-var names.
* Everything is validated up front with pydantic so a bad config fails fast.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from .errors import ConfigError

# The MangaDex reading statuses, used both for the optional source filter and
# for the MangaUpdates status -> list_id mapping.
MANGADEX_STATUSES = (
    "reading",
    "on_hold",
    "plan_to_read",
    "dropped",
    "re_reading",
    "completed",
)
MangaDexStatus = Literal[
    "reading", "on_hold", "plan_to_read", "dropped", "re_reading", "completed"
]

DEFAULT_TOKEN_URL = (
    "https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token"
)

# Single source of truth for the local-export column order (CSV + xlsx default).
DEFAULT_COLUMNS: tuple[str, ...] = (
    "uuid",
    "primary_title",
    "secondary_title",
    "personal_rating",
    "global_rating",
    "highest_read_chapter",
    "highest_read_volume",
    "jp_publication_url",
    "en_publication_url",
    "mangadex_url",
)

# Default MangaDex status -> MangaUpdates standard list_id mapping.
DEFAULT_STATUS_LIST_MAP: dict[MangaDexStatus, int] = {
    "reading": 0,
    "re_reading": 0,
    "plan_to_read": 1,
    "completed": 2,
    "dropped": 3,
    "on_hold": 4,
}


def resolve_secret(env_var_name: str) -> str:
    """Read a secret value from the environment by variable name.

    Raises ``ConfigError`` (never logs the value) if the variable is unset or
    empty so misconfiguration surfaces as a clean message.
    """
    value = os.environ.get(env_var_name)
    if not value:
        raise ConfigError(
            f"Environment variable {env_var_name!r} is not set (or empty). "
            "Add it to your .env file or environment."
        )
    return value


class AuthConfig(BaseModel):
    """MangaDex OAuth2 (ROPC) settings — env-var names only, no secrets."""

    token_url: str = DEFAULT_TOKEN_URL
    flow: Literal["password"] = "password"
    username_env: str = "MANGADEX_USERNAME"
    password_env: str = "MANGADEX_PASSWORD"
    client_id_env: str = "MANGADEX_CLIENT_ID"
    client_secret_env: str = "MANGADEX_CLIENT_SECRET"

    def env_var_names(self) -> set[str]:
        return {
            self.username_env,
            self.password_env,
            self.client_id_env,
            self.client_secret_env,
        }


class ApiConfig(BaseModel):
    """MangaDex REST API connection + resilience settings."""

    base_url: str = "https://api.mangadex.org"
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: float = 30.0
    max_retries: int = 5
    backoff_factor: float = 1.0
    rate_limit: float = 5.0  # requests/second (global MangaDex cap is ~5)


class SourceConfig(BaseModel):
    """How to build the dataset from the user's reading list."""

    status: list[MangaDexStatus] | None = None  # None = all statuses
    batch_size: int = Field(default=100, ge=1, le=100)


class CsvExportConfig(BaseModel):
    type: Literal["csv"] = "csv"
    name: str = "csv"
    path: str = "./exports/mangadex-{datetime}.csv"
    on_existing: Literal["overwrite", "error-if-exists"] = "overwrite"
    delimiter: str = ","
    encoding: str = "utf-8"
    columns: list[str] = Field(default_factory=lambda: list(DEFAULT_COLUMNS))


class XlsxExportConfig(BaseModel):
    type: Literal["xlsx"] = "xlsx"
    name: str = "xlsx"
    path: str = "./exports/mangadex-{datetime}.xlsx"
    on_existing: Literal["overwrite", "error-if-exists"] = "overwrite"
    sheet_name: str = "manga"
    columns: list[str] = Field(default_factory=lambda: list(DEFAULT_COLUMNS))


class MangaUpdatesExportConfig(BaseModel):
    type: Literal["mangaupdates"] = "mangaupdates"
    name: str = "mangaupdates"
    base_url: str = "https://api.mangaupdates.com/v1"
    username_env: str = "MANGAUPDATES_USERNAME"
    password_env: str = "MANGAUPDATES_PASSWORD"
    status_list_map: dict[MangaDexStatus, int] = Field(
        default_factory=lambda: dict(DEFAULT_STATUS_LIST_MAP)
    )
    old_ids_path: str = "docs/mangaupdates.json"
    batch_size: int = Field(default=100, ge=1, le=100)
    timeout: float = 30.0
    max_retries: int = 5
    backoff_factor: float = 1.0
    update_delay: float = 5.0  # seconds between write requests (412 guard)

    def env_var_names(self) -> set[str]:
        return {self.username_env, self.password_env}


ExportConfig = Annotated[
    CsvExportConfig | XlsxExportConfig | MangaUpdatesExportConfig,
    Field(discriminator="type"),
]

LOCAL_EXPORT_TYPES = ("csv", "xlsx")


class Config(BaseModel):
    auth: AuthConfig = Field(default_factory=AuthConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    source: SourceConfig = Field(default_factory=SourceConfig)
    exports: list[ExportConfig]

    @model_validator(mode="after")
    def _validate(self) -> Config:
        if not self.exports:
            raise ValueError("'exports' must define at least one exporter")

        names = [e.name for e in self.exports]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(
                f"exporter names must be unique; duplicated: {sorted(dupes)}"
            )

        # MangaDex and MangaUpdates must not share credential env-var names.
        mangadex_envs = self.auth.env_var_names()
        for export in self.exports:
            if isinstance(export, MangaUpdatesExportConfig):
                shared = mangadex_envs & export.env_var_names()
                if shared:
                    raise ValueError(
                        "MangaUpdates and MangaDex must use distinct credential "
                        f"env-var names; shared: {sorted(shared)}"
                    )
        return self

    def exporter_names(self) -> list[str]:
        return [e.name for e in self.exports]

    def get_exporter(self, name: str) -> ExportConfig:
        for export in self.exports:
            if export.name == name:
                return export
        raise ConfigError(f"unknown exporter {name!r}")


def load_config(path: str | Path) -> Config:
    """Load and validate a YAML config file, raising ``ConfigError`` on failure."""
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"config file not found: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"could not parse YAML config: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration:\n{exc}") from exc
