# CLAUDE.md

Guidance for working in this repository. The full task specification lives in
[`docs/prompts/0001-export-app-prompt.md`](./docs/prompts/0001-export-app-prompt.md) —
treat it as the authoritative requirements; this file is the quick-reference for
conventions and the non-obvious domain gotchas.

## What this app is

A **config-driven Python CLI** that exports the logged-in user's MangaDex
reading list to local files (**CSV**, **Excel**) and/or syncs it to
**MangaUpdates** (adds/moves each series to a list). All settings come from a
YAML config + secrets from environment variables; the only runtime prompt is
**which exporter(s) to run**.

Pipeline: read MangaDex reading statuses → fetch manga details → (conditionally)
fetch ratings/stats/read-progress → write local files and/or sync to
MangaUpdates.

## Tech stack & conventions

- **Python 3.14**. `pyproject.toml` with `requires-python = ">=3.14"`.
- **PEP 8** for all code; enforce with **`ruff`**. Full **type hints**; must pass
  **`mypy`** and `ruff` cleanly.
- Libraries: `requests`/`httpx` (HTTP), `pydantic` (config models + validation),
  `python-dotenv` (env loading), `questionary` (interactive exporter prompt),
  `openpyxl`/`pandas` (xlsx), `pytest` (tests).
- **Never log or print secrets or tokens.**
- **Check up-to-date docs before implementing** — don't rely on memory for
  Python 3.14, library APIs, or either service. Verify against the bundled specs
  and the live API docs (see References).

## Workflow

- Use Conventional Commits for the commit messages.
- End every commit message with a trailer attributing the commit to you using `Co-Authored-By`.

## Module layout

```
auth.py              # MangaDex OAuth2 (ROPC) token management
client.py            # REST client: pagination/chunking, retries, rate limiting
config.py            # pydantic config models + loading
exporters/
  base.py            # Exporter interface: export(dataset, options)
  csv.py
  xlsx.py
  mangaupdates.py
cli.py / __main__.py # entry point, exporter selection, run summary
```

## Critical domain gotchas (don't re-derive these)

These were verified against the live APIs and specs — get them wrong and the app
silently misbehaves:

- **MangaDex auth is ROPC against Keycloak, NOT the API host.** Token endpoint:
  `https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token`
  (not in the OpenAPI spec). `grant_type=password` as
  `application/x-www-form-urlencoded` with `username`, `password`, `client_id`
  (a personal client, `personal-client-…`), `client_secret`. `access_token`
  lasts ~15 min; refresh via `grant_type=refresh_token`.
- **Source is two-step.** `GET /manga/status` returns only `uuid → status`; you
  must batch `GET /manga?ids[]=` (≤100 ids/request) for details (`title`,
  `altTitles`, `links`). Manga deleted/restricted are silently omitted — skip + log.
- **Per-endpoint query param names differ:** `/rating` → `manga` (no `[]`),
  `/statistics/manga` → `manga[]`, `/manga/read` → `ids[]` (all `deepObject`).
- **MangaDex pagination is offset/limit only** (`limit` ≤100, `offset+limit`
  ≤10,000) and there's a **global ~5 req/s rate limit** — use a shared throttle.
- **MangaUpdates `series_id` is an integer; the MangaDex `mu` link is a base36
  slug.** Resolve via:
  `series.id = base36_decode( mu in old_ids ? old_ids[mu] : mu )`.
  `docs/mangaupdates.json` maps legacy numeric old ids → base36 slug; if `mu`
  isn't a key there, it's already current — use it directly, but **still
  base36-decode** to the integer. No `mu` key → can't sync, skip + log.
  (e.g. `"5yoo9wh"` → `12981205025`.)
- **Status → MangaUpdates list_id mapping** (standard lists, validate once via
  `GET /lists`): `reading`/`re_reading`→0, `plan_to_read`→1, `completed`→2,
  `dropped`→3, `on_hold`→4.
- **MangaUpdates sync = resolve → classify → batch-write.** A series is on at
  most one list. Not on a managed list → **add** (`POST /lists/series`); on a
  different standard list → **move** (`POST /lists/series/update`); already on the
  mapped list → **skip**. Batch the array bodies; respect the **5-second update
  delay** (`412`) — favor fewer, larger requests.
- **Secret-wiring:** config holds **env-var names only**, never secret values and
  no `${VAR}` interpolation. MangaDex and MangaUpdates credentials use **distinct**
  env-var names.

## Local-export columns (CSV & xlsx, in order)

`uuid`, `primary_title` (first value of `attributes.title`), `secondary_title`
(`en` entry in `altTitles`), `personal_rating` (`GET /rating`), `global_rating`
(`statistics.rating.average`), `highest_read_chapter`, `highest_read_volume`
(max **non-null** volume — the top chapter may have none), `jp_publication_url`
(`links.raw`), `en_publication_url` (`links.engtl`),
`mangadex_url` (`https://mangadex.org/title/{uuid}`). Missing values → empty cells.

## Running & testing

- Run: `python -m exporter` (interactive) or `--exporters csv,mangaupdates` /
  `--all` for non-interactive. `--dry-run` does all reads/auth but no writes.
- Test: `pytest` — mock all network; no live API calls. Cover token refresh,
  pagination/chunking, config validation, the source flow, id resolution
  (old-id decode, current-id decode, missing-`mu` skip), status→list mapping,
  list-id validation, add/move/skip classification, and column derivation
  (esp. `highest_read_volume`).
- Lint/type: `ruff check .` and `mypy .` must pass.

## Reference files

- `docs/prompts/0001-export-app-prompt.md` — authoritative spec.
- `docs/apis/mangadex-api.yaml` — MangaDex OpenAPI spec (source of truth for endpoints;
  note the auth token endpoint is *not* in it).
- `docs/apis/mangaupdates-api.yaml` — MangaUpdates OpenAPI spec.
- `docs/mangaupdates.json` — static legacy old-id → base36-slug mapping (~3 MB;
  load once into a dict).
- Live docs: <https://api.mangadex.org/docs/> · <https://api.mangaupdates.com/>
