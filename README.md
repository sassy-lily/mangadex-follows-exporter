# mangadex-follows-exporter

A config-driven Python CLI that exports the logged-in user's **MangaDex** reading
list to local files (**CSV**, **Excel**) and/or syncs it to **MangaUpdates** by
adding/moving each series onto the matching list.

Everything is driven by a YAML config file plus secrets supplied through
environment variables — no code edits are needed to add a new export job. The
only thing the tool asks at runtime is *which exporter(s) to run*.

## How it works

1. Load + validate the config (pydantic) and resolve all named env-var secrets.
2. Select exporters — interactive multi-select, or `--exporters` / `--all`.
3. Authenticate to MangaDex (OAuth2 ROPC) and fetch the reading list:
   `GET /manga/status` → batch `GET /manga?ids[]=` for details.
4. *Only if a local (csv/xlsx) exporter is selected*, fetch personal ratings,
   global stats, and read-progress.
5. Run each selected exporter:
   - **csv / xlsx** — write the columns table to the configured file(s).
   - **mangaupdates** — log in, validate the mapped list ids, pre-fetch
     membership, resolve each `series.id`, classify add/move/skip, batch-write.
6. Print a run summary and exit non-zero if anything failed.

`--dry-run` performs every read and authentication but writes nothing (no files,
no MangaUpdates `POST`s) and reports what *would* happen.

## Requirements

- **Python 3.14+**

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .            # add '.[dev]' for tests/lint/type-check

cp .env.example .env        # then fill in your credentials
# review config.yaml and adjust paths / mappings as needed
```

### Credentials

Secrets are **never** stored in `config.yaml`. The config only names the
environment variables to read them from; values live in `.env` (loaded
automatically) or the real environment. The two services use **distinct**
env-var names.

#### Getting MangaDex credentials

MangaDex authenticates via OAuth2 against its Keycloak server using a **personal
API client**:

1. Log in to MangaDex and open **Settings → API Clients**
   (<https://mangadex.org/settings> → API Clients).
2. **Create** a personal API client (give it a name/description). New clients
   start in a `requested`/pending state and must be **approved** before use —
   approval can take some time.
3. Once approved, open the client and use **"Get Secret"** to reveal the
   `client_secret`; the `client_id` is shown as `personal-client-<...>`.
4. Put the `client_id`, `client_secret`, and your MangaDex `username`/`password`
   into `.env`:

   ```
   MANGADEX_USERNAME=...
   MANGADEX_PASSWORD=...
   MANGADEX_CLIENT_ID=personal-client-xxxxxxxx-...
   MANGADEX_CLIENT_SECRET=...
   ```

   These are sent to the token endpoint
   `https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token`.

#### MangaUpdates credentials

The MangaUpdates exporter logs in via `PUT /account/login` with your
MangaUpdates account `username`/`password`. Use **distinct** env-var names from
the MangaDex ones:

```
MANGAUPDATES_USERNAME=...
MANGAUPDATES_PASSWORD=...
```

See `.env.example` for the full list.

## Configuration

A complete, commented example lives in [`config.yaml`](./config.yaml). Highlights:

- `auth` — MangaDex token URL (defaults to the Keycloak endpoint), flow
  (`password`), and the env-var names for the credentials.
- `api` — MangaDex base URL, headers, timeout, retry/backoff, and the
  client-side rate limit (~5 req/s).
- `source` — optional `status` filter and the id-batch size (≤100).
- `exports` — every available destination. Each entry has a unique `name` and a
  `type` (`csv` | `xlsx` | `mangaupdates`); **multiple instances of the same
  type are allowed**. The `name` is what appears in the interactive menu and in
  `--exporters`.

### Local-export columns (CSV & xlsx)

One row per manga, in this order:

`uuid`, `primary_title`, `secondary_title`, `personal_rating`, `global_rating`,
`highest_read_chapter`, `highest_read_volume`, `jp_publication_url`,
`en_publication_url`, `mangadex_url`. Missing values render as empty cells.

Output paths may contain `{date}` (`YYYY-MM-DD`) or `{datetime}`
(`YYYY-MM-DDTHHMMSS`, filename-safe) placeholders, rendered from the local-time
run timestamp. Existing files are overwritten by default
(`on_existing: error-if-exists` to refuse instead).

### Status → MangaUpdates list mapping

| MangaDex status | list_id | MangaUpdates list |
|---|---|---|
| `reading`, `re_reading` | 0 | Reading |
| `plan_to_read` | 1 | Wish |
| `completed` | 2 | Complete |
| `dropped` | 3 | Unfinished |
| `on_hold` | 4 | Hold |

These ids are validated once at startup against `GET /lists`. The exporter is
idempotent: a series already on its mapped list is skipped, one on a different
standard list is moved, and a new one is added.

## Usage

```bash
# Interactive: pick exporters from a menu
python -m exporter

# Non-interactive
python -m exporter --exporters csv,mangaupdates
python -m exporter --all

# Read everything and report, but write nothing
python -m exporter --all --dry-run

# Other flags
python -m exporter --config path/to/config.yaml --verbose
```

At least one exporter must be selected; an empty selection or an unknown name
exits with a clear error.

## Development

```bash
pip install -e '.[dev]'
ruff check .      # lint (PEP 8)
mypy src/exporter # type-check
pytest            # unit tests (network fully mocked; no live API calls)
```

## License

See [`LICENSE.md`](./LICENSE.md).
