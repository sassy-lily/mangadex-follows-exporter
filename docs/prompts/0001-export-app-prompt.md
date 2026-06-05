# Prompt: Build a config-driven Python data export tool

> Ready to paste into Claude Code (or any capable coding assistant) as the task description. Assumes these files exist: `docs/apis/mangadex-api.yaml` (source OpenAPI spec), `docs/apis/mangaupdates-api.yaml` (destination OpenAPI spec), and `docs/mangaupdates.json` (static old-id → new-id mapping).

---

## Task

Build a **config-driven Python script** that extracts data from an authenticated REST API and exports it to multiple formats/destinations. All settings come from a config file plus secrets from the environment — no code edits required to add a new export job. The only thing the script asks the user at runtime is **which of the configured exporters to run**.

### Execution flow (overview)

Order matters — later steps depend on earlier ones, and some fetches are conditional on which exporters are selected:

1. **Load & validate** config (pydantic) and resolve all named env-var secrets; fail fast if anything is missing/malformed.
2. **Select exporters** — interactive multi-select (or `--exporters`/`--all`). This is decided *before* fetching, because it determines which data is needed.
3. **Authenticate to MangaDex** (ROPC) and fetch the source: `GET /manga/status` → manga-uuid→status map; then batch `GET /manga?ids[]` for details.
4. **Conditionally fetch extras** *only if a local exporter (csv/xlsx) is selected*: personal ratings, global stats, and read-progress (read markers → chapter details).
5. **Run each selected exporter** against the assembled per-manga records:
   - **Local (csv/xlsx):** write the columns table to the configured file(s).
   - **MangaUpdates:** authenticate → `GET /lists` to validate the mapped list ids → pre-fetch the membership map → resolve each `series.id` → classify add/move/skip → batch-write.
6. **Print the run summary** and exit non-zero if anything failed.

Each section below details a step. `--dry-run` performs steps 1–5 **including all reads and authentication**, but suppresses every write (no files, no MangaUpdates `POST`s) and instead reports what *would* happen.

## Source: authenticated REST API (OAuth2)

- The source REST API is **documented in the OpenAPI spec at <https://api.mangadex.org/docs/static/api.yaml>**; a local copy is provided at `docs/apis/mangadex-api.yaml`. Treat that spec as the source of truth for base URL, endpoint paths, query/path parameters, request/response schemas, and pagination behavior. Consider generating or deriving the endpoint models from it where practical.
- Authenticate using **OAuth2 — Resource Owner Password Credentials (ROPC) grant**. MangaDex uses a Keycloak auth server **separate from the API host** (this endpoint is *not* in the OpenAPI spec):
  - **Token endpoint:** `https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token` (make this configurable; default to this value).
  - **Password grant:** POST as `application/x-www-form-urlencoded` with `grant_type=password`, `username`, `password`, `client_id`, `client_secret`. The `client_id` is a MangaDex **personal API client** (`personal-client-...`) and `client_secret` is revealed via the "Get Secret" action once the client is approved. No scopes are required.
  - **Refresh grant:** POST `grant_type=refresh_token` with `refresh_token`, `client_id`, `client_secret`.
  - Leave a clean extension point for other flows (e.g. client-credentials, authorization-code).
- Read the token endpoint from config; read `username`, `password`, `client_id`, and `client_secret` from environment variables (never from the config file or source).
- The token response is JSON with `access_token` (≈15-minute lifetime) and `refresh_token`. Cache the access token in memory and **refresh automatically** before/at expiry and on a `401` (retry the request once after refreshing). Use the `refresh_token` grant to renew; fall back to a fresh password grant if the refresh token is missing or rejected.
- Send the access token as `Authorization: Bearer <access_token>` on API requests.
- Base API URL (default `https://api.mangadex.org`), default headers, and per-endpoint paths come from config.
- **Pagination:** MangaDex uses **offset/limit** only (no cursors); `limit` is capped at 100 and `offset + limit` must stay ≤ 10,000. Page where a list endpoint returns more than one page; for the id-based endpoints used here (`/manga`, `/chapter`) "paging" means **chunking the id list** into ≤100-id requests rather than offset paging.
- Be resilient: timeouts, retries with exponential backoff on `429`/`5xx`, and respect `Retry-After`. MangaDex also enforces a **global rate limit (~5 requests/second)** — throttle client-side (e.g. a shared rate limiter) so the batched calls below stay under it.

### Source dataset: the logged-in user's manga reading statuses

- The series to export come from **`GET /manga/status`** ("Get all Manga reading status for logged User") — an authenticated endpoint. It returns an object `{ "result": "ok", "statuses": { "<manga-uuid>": "<status>", ... } }`, i.e. a **map of manga UUID → reading status** (`reading`, `on_hold`, `plan_to_read`, `dropped`, `re_reading`, `completed`). It is **not** paginated and returns *only* UUIDs and statuses — no manga details.
- Optionally filter by status via the `status` query param (expose this in config, default = all statuses).
- **Second step — fetch manga details.** `GET /manga/status` does not include `attributes`, so to obtain each manga's title, links, etc., fetch the manga objects by id: batch them through **`GET /manga?ids[]=<uuid>&ids[]=...`** (max **100 ids per request** — page through the full set), rather than one `GET /manga/{id}` per manga. Carry the per-manga reading status from step 1 alongside the fetched details.
  - A uuid present in the status map may be **deleted or restricted**, so the batch response can silently omit it. Treat any uuid that has no returned manga object as **skipped** (log it in the run summary); do not abort the run.
- **Extra per-manga data for the local exports** (see the column list under CSV/Excel). These come from separate endpoints and are needed only when a local exporter is selected — fetch them lazily/conditionally to avoid unnecessary calls. Batch all of these in **≤100 ids per request** (same cap as `/manga`). **Use the exact query-param name and serialization from the spec — they differ per endpoint:** `/rating` takes `manga` (no `[]`), `/statistics/manga` takes `manga[]`, `/manga/read` takes `ids[]` (all `deepObject` style):
  - **Personal rating:** `GET /rating?manga=<uuid>...` → `ratings[uuid].rating` (integer 1–10; absent if the user never rated it).
  - **Global rating:** `GET /statistics/manga?manga[]=<uuid>...` → `statistics[uuid].rating.average` (nullable number; `bayesian` is the population-weighted variant).
  - **Highest read chapter/volume:** `GET /manga/read?ids[]=<uuid>...&grouped=true` returns the **read chapter ids** grouped by manga uuid. Resolve those ids to chapter numbers via `GET /chapter?ids[]=<chapter-uuid>...` (≤100/request) and read each chapter's `attributes.chapter` and `attributes.volume` (both nullable strings; parse numerically). Because a series can have hundreds of read chapters, **collect the full set of read chapter ids across all manga, de-duplicate, and fetch them in shared ≤100-id batches** (build a `chapter-id → (chapter, volume)` lookup once), rather than per-manga. *(Alternative if call volume is still too high: derive the numbers from `GET /manga/{id}/aggregate` intersected with the read-marker ids.)*
- The combined per-manga record handed to the exporters includes: `uuid`, the manga `attributes` (`title`, `altTitles`, `links`), reading status, and (when needed) personal rating, global rating, and read-progress.

## Exporters / destinations

The script fetches the source dataset once (per the section above), then writes it to one or more user-selected destinations:

1. **CSV** — configurable delimiter, encoding (default UTF-8), header row; emits the **local-export columns** below.
2. **Excel (.xlsx)** — a header row plus the same **local-export columns** below, written to a single configurable sheet (default `manga`); use `openpyxl` or `pandas`.

   **Local-export columns** (CSV and Excel share this schema; one row per manga, in this order):

   | Column | Source | Notes |
   |---|---|---|
   | `uuid` | manga `data.id` | the series UUID |
   | `primary_title` | the single value of `attributes.title` | `title` is a `LocalizedString` map that normally has one entry — take its **first** value (don't assume the language key) |
   | `secondary_title` | the `en`-keyed entry within `attributes.altTitles` | `altTitles` is an array of single-key maps; pick the first whose key is `en`; blank if none |
   | `personal_rating` | `ratings[uuid].rating` from `GET /rating` | integer 1–10; blank if the user hasn't rated it |
   | `global_rating` | `statistics[uuid].rating.average` from `GET /statistics/manga` | number; blank/null if unrated globally |
   | `highest_read_chapter` | max `attributes.chapter` over the manga's read chapters | parse chapter strings numerically (may be e.g. `10.5`); blank if no read chapters |
   | `highest_read_volume` | max **non-null** `attributes.volume` over the manga's read chapters | volume is nullable — the highest-numbered read chapter may have no volume yet, so take the max over chapters that **do** have a volume |
   | `jp_publication_url` | `attributes.links.raw` | official Japanese/raw publication; blank if absent |
   | `en_publication_url` | `attributes.links.engtl` | official English publication; blank if absent |
   | `mangadex_url` | `https://mangadex.org/title/{uuid}` | the series page on MangaDex, built from the series UUID |

   Missing/optional values render as empty cells (not the string `"None"`). This column set/order is the **single source of truth** for what the local exporters write; keep it configurable in each local exporter's options but default to exactly the above. (The `source` config does not separately define columns.)

   **Output files:** each local exporter writes to a configured path. The path may contain a `{date}` / `{datetime}` placeholder — render it from the **local-time** run timestamp, `{date}` as `YYYY-MM-DD` and `{datetime}` as `YYYY-MM-DDTHHMMSS` (filename-safe, no colons). Default behavior is **overwrite** the target file; make this configurable (`overwrite` | `error-if-exists`). Append is not supported (a run always reflects the full current dataset).
3. **Third-party online service — MangaUpdates.** Export the data into the user's MangaUpdates account by **adding each series to a MangaUpdates list** via its REST API.
   - The MangaUpdates API is documented at <https://api.mangaupdates.com/openapi.yaml>; a local copy is provided at `docs/apis/mangaupdates-api.yaml` — treat it as the source of truth for endpoints, request/response schemas, and which endpoints require auth. Base URL: `https://api.mangaupdates.com/v1`.
   - **Authentication**: `PUT /account/login` with a JSON body `{ "username": ..., "password": ... }` returns a **session token**; send it as `Authorization: Bearer <token>` on all protected endpoints. Read the MangaUpdates `username`/`password` from environment variables (never config or source). Cache the session token and re-login when it is missing or rejected with `401`.
   - **Target endpoint**: `POST /lists/series` ("add a series to a list"). The body is a JSON **array** of objects shaped like `{ "series": { "id": <int> }, "list_id": <int> }` (see schema `ListsSeriesModelUpdateV1`). The `series.id` field is **`type: integer`** — so the value sent must be an integer, never a string/slug. Each array item carries **its own `list_id`**, so a single request may target multiple lists at once. The documented **five-second update delay** (`412` response) applies to **write requests** (add/update/delete), not per series — so prefer **fewer, larger batched requests** spaced ≥5s apart, and retry a `412` with backoff.
   - **Preserve the user's status/list by mapping it.** MangaDex returns a per-manga reading status (from `GET /manga/status`); place each series on the corresponding MangaUpdates standard list via this **status → `list_id`** mapping (keep it in config so it can be adjusted):

     | MangaDex status | MangaUpdates `list_id` | MangaUpdates list |
     |---|---|---|
     | `reading` | `0` | Reading |
     | `re_reading` | `0` | Reading |
     | `plan_to_read` | `1` | Wish |
     | `completed` | `2` | Complete |
     | `dropped` | `3` | Unfinished |
     | `on_hold` | `4` | Hold |

     These integer ids are the standard MangaUpdates lists by **convention** (the spec names them `read`/`wish`/`complete`/`unfinished`/`hold` but does not enumerate the integers). **Validate them once at startup** by calling `GET /lists` (returns the user's lists as `ListsModelV1` with `list_id`/`title`/`type`); confirm each mapped `list_id` exists and matches the expected standard list, and fail with a clear error if the assumption doesn't hold.

   The per-series runtime sequence is **resolve → classify → batch-write**:

   - **(1) Resolve the integer `series.id`.** MangaDex exposes the MangaUpdates id inside each manga's `attributes.links` **object** (a map keyed by source code), under the key `mu` — e.g. `"links": { "mu": "5yoo9wh", "al": "149893", ... }`. (It is *not* a list; access it by key.)
     - If there is **no `mu` key**, the MangaUpdates id is unavailable and that manga **cannot be sent** to MangaUpdates — skip it (and log it in the run summary).
     - Otherwise compute the integer id as: **`series.id = base36_decode( mu_is_old_id ? old_ids[mu] : mu )`**. In words:
       - `docs/mangaupdates.json` is a static, definitive mapping of **legacy numeric old ids → base36 slug** (keys are numeric strings, e.g. `{"1": "t8zu40m", "33": "pb8uwds", ...}`).
       - If the `mu` value **is a key in this list** (a legacy numeric old id), first replace it with the mapped base36 slug.
       - If the `mu` value is **not** in the list, use it **directly** (skip the lookup) — it is already the current base36 slug.
       - **In both cases**, base36-decode the resulting slug to the integer `series.id`. Examples: old id `"33"` → `"pb8uwds"` → `55099564912`; current `"5yoo9wh"` → `12981205025`.
     - Load `docs/mangaupdates.json` once (it is large, ~3 MB) and look ids up from an in-memory dict.
   - **(2) Classify against current membership (idempotency).** A series is on **at most one** list (`GET /lists/series/{series_id}` returns a single `ListsSeriesModelV1`, not an array), so classification is unambiguous. The **managed universe is only the 5 standard lists** in the mapping (ids `0`–`4`); custom user lists are out of scope. Build the membership view efficiently: page `POST /lists/{id}/search` (body `ListsSearchRequestV1`) **once per mapped standard list** at startup into an in-memory map of `series_id → list_id`, and classify against that — rather than one `GET /lists/series/{series_id}` request per series. (Per-series `GET /lists/series/{series_id}` is the fallback if the bulk search is unavailable; note it can report a *custom* list too, which for our purposes counts as "not on a managed list.") Classify each resolved series:
     - **Not on any of the 5 standard lists** → **add** it to its mapped list via `POST /lists/series`. (This includes a series that currently sits only on a *custom* list — it gets added to the mapped standard list; we do not read or modify custom lists.)
     - **On a *different* standard list** than its mapped target (e.g. the user's status changed) → **move** it to the mapped `list_id` via `POST /lists/series/update` ("update a series list item", same `ListsSeriesModelUpdateV1` body).
     - **Already on the mapped target `list_id`** → **skip** it and record it as "already present" in the run summary.
   - **(3) Batch the additions and moves.** Send the **add** group to `POST /lists/series` and the **move** group to `POST /lists/series/update`; in both cases build one array with each item set to `{ "series": { "id": <int> }, "list_id": <mapped id> }` and send in batches rather than one request per series. Make the batch size configurable (default e.g. 100) and chunk larger sets across multiple requests; pace requests to respect the five-second update delay and retry a `412` with backoff. Report per-batch results (added / moved / skipped / failed, grouped by target list) in the run summary.
   - Design this as one implementation of a generic `Exporter` interface so more destinations can be added later without touching core logic. (MangaUpdates is the **first** such destination; expect more.)

Exporters must share a common interface (e.g. `Exporter.export(dataset, options)`). All exporter **settings** (file paths, sheet names, remote targets, credentials env-var names, etc.) live in the config file, but **which exporters actually run is chosen by the user interactively at runtime** — see CLI & UX.

## Configuration

- Use a single **YAML** config file (e.g. `config.yaml`), path passed via CLI arg `--config` (default `./config.yaml`).
- **Secret-wiring (one mechanism):** the config file **never contains secret values** and does **not** interpolate them. Instead, wherever a credential is needed the config holds the **name of the environment variable** to read it from (e.g. `username_env: MANGADEX_USERNAME`). Secrets are loaded from a `.env` file and/or the real environment (`python-dotenv`). The script must error clearly if a named env var is unset.
- Config schema should cover:
  - `auth` (MangaDex source): token URL (default `https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token`), flow type (default `password`/ROPC), and the **env-var names** for `username`, `password`, `client_id`, `client_secret`.
  - `api` (MangaDex): base URL (default `https://api.mangadex.org`), default headers, timeout, retry/rate-limit settings.
  - `source`: options for building the dataset from the user's reading list — an optional `status` filter for `GET /manga/status` and the batch size for the id-based fetches (default 100). (Output columns are defined per local exporter, not here — see CSV/Excel.)
  - `exports`: the full set of available destinations and their options. This defines what *can* be used; the user selects which to run at launch. Each entry has a **unique name** (defaulting to its type) and a **type** (`csv` | `xlsx` | `mangaupdates`); the name is what appears in the interactive menu and in `--exporters`. **Multiple instances of the same type are allowed** (e.g. a `csv_full` and a `csv_minimal`, each with its own options). Per type:
    - **csv / xlsx**: output path (timestamp pattern allowed), existing-file behavior (`overwrite` default | `error-if-exists`), CSV delimiter/encoding, and the xlsx **sheet name** (default e.g. `manga`).
    - **mangaupdates**: base URL (default `https://api.mangaupdates.com/v1`), the **env-var names** for its account `username`/`password` (used against `PUT /account/login`), the **status → `list_id` mapping** (defaulting to the table above), and the add-batch size. **These username/password env vars must be different from the MangaDex ones** — the script should not assume the two services share credentials.
- **Validate** the config on startup (use `pydantic`) and fail fast with a readable error if it's malformed.

## CLI & UX

- Single entry point runnable as `python -m exporter` or `python export.py`.
- **All settings come from the config file** — the script never asks the user for connection details, paths, or credentials.
- **The one interactive step is exporter selection**: on launch, list the exporters defined in the config's `exports` section and prompt the user to pick one or more to run (a multi-select menu; e.g. `questionary` or a simple numbered prompt). Run only the selected exporters.
  - Provide a non-interactive override for automation: a `--exporters a,b,c` flag (and/or `--all`) that skips the prompt. If stdin is not a TTY and no flag is given, error with a clear message rather than hanging.
  - **At least one exporter is required:** selecting none (empty interactive selection or empty `--exporters`) exits with a clear "no exporter selected" message. An **unknown name** in `--exporters` errors and lists the valid exporter names from config.
- Flags: `--config PATH`, `--exporters LIST` / `--all`, `--dry-run`, `--verbose/--log-level`.
- **`--dry-run`** still **authenticates and performs all reads** (MangaDex fetches; MangaUpdates `GET /lists` + membership pre-fetch) and resolves everything, but performs **no writes**: local exporters write no files; the MangaUpdates exporter computes the add/move/skip plan but sends **no `POST`** — and reports what it *would* do. (It therefore still requires valid credentials.)
- Structured **logging** to stdout (not `print`), with a summary at the end, per selected exporter: for local exporters, rows written and the output path; for MangaUpdates, counts of **added / moved / skipped / failed** (grouped by target list) plus how many manga were skipped for a missing `mu` id.
- Exit non-zero on any failure.

## Quality requirements

- **Python 3.14.** Use `requests` (or `httpx`) for HTTP, `pydantic` for config, `python-dotenv` for env loading, and `questionary` (or similar) for the interactive exporter prompt.
- **Adhere to PEP 8** for all code style (naming, layout, imports, line length); enforce it with `ruff` (configured to the PEP 8 conventions).
- Type hints throughout; pass `mypy`/`ruff` cleanly.
- **Check up-to-date documentation before implementing.** Do not rely on memory for third-party details — consult the **current** docs for Python 3.14, each library used, and both services. Authoritative sources: the bundled specs (`docs/apis/mangadex-api.yaml`, `docs/apis/mangaupdates-api.yaml`) and the live API docs (<https://api.mangadex.org/docs/> and <https://api.mangaupdates.com/>); verify endpoints, auth flows, field names, and library APIs against these rather than assumptions, and prefer the latest stable releases of dependencies.
- Clear module layout, e.g.:
  - `auth.py` (OAuth2 token management)
  - `client.py` (REST client: pagination, retries)
  - `config.py` (pydantic models + loading)
  - `exporters/` (`base.py`, `csv.py`, `xlsx.py`, `mangaupdates.py`)
  - `cli.py` / `__main__.py`
- **Never log or print secrets or tokens.**
- Include `pyproject.toml` (with `requires-python = ">=3.14"` and `ruff` configured for PEP 8) plus dependencies, a `.env.example`, and a sample `config.yaml` with the `source` options and all three exporters configured.
- Provide a `README.md` covering setup, configuration, and a usage example. It **must** include a "Getting MangaDex credentials" section explaining how to obtain the `client_id`/`client_secret`:
  1. Log in to MangaDex and open **Settings → API Clients** (`https://mangadex.org/settings` → API Clients).
  2. **Create** a personal API client (give it a name/description). New clients start in a `requested`/pending state and must be **approved** before use (approval can take time).
  3. Once approved, open the client and use **"Get Secret"** to reveal the `client_secret`; the `client_id` is shown as `personal-client-<...>`.
  4. Put `client_id`, `client_secret`, and your MangaDex `username`/`password` into `.env` (per `.env.example`); they are sent to the token endpoint `https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token`.
  - Also document the MangaUpdates credentials (account `username`/`password` used against `PUT /account/login`) in the same setup section. Use **distinct env-var names** for each service (e.g. `MANGADEX_USERNAME`/`MANGADEX_PASSWORD` vs `MANGAUPDATES_USERNAME`/`MANGAUPDATES_PASSWORD`) and list all of them in `.env.example`.
- Write **unit tests** (`pytest`) for: token refresh, pagination, config validation, the source flow (parsing the `/manga/status` map + batching ids ≤100 into `GET /manga` and joining status with details), the MangaUpdates id resolution (legacy old-id → slug lookup then base36 decode, current-id direct base36 decode, and the missing-`mu` skip case — all yielding an integer), the status → `list_id` mapping, the startup list-id validation against `GET /lists`, the add/move/skip decision (not-on-any-list → add, on a different list → move, on the mapped list → skip), the local-export column derivation (single-value `title`, `en` `altTitles` lookup, and especially `highest_read_volume` as the max **non-null** volume when the top chapter has none), and each exporter (mock the network and the third-party service — no live calls in tests).

## Deliverables

1. The full project source laid out as above.
2. `config.yaml` example + `.env.example`.
3. `README.md`.
4. Passing tests.

## Out of scope (for now)

- Scheduling/orchestration (assume cron or an external scheduler runs the script).
- A GUI or web interface.

## References

- **MangaUpdates old-id → new-id mapping** — <https://github.com/henrik9999/mangaupdates-old-id-mapping> (origin/format of the static `docs/mangaupdates.json` legacy-id list).
- **MangaUpdates API Python client** — <https://github.com/FourierMeow/manga-updates-api-client> (reference implementation for authenticating to and calling the MangaUpdates API).
