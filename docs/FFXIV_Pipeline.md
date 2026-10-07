# FFXIV Sheets Pipeline (CSV / EXD)

This document describes the new data ingestion pipeline for converting FFXIV sheets (CSV / EXD) into a normalized, indexed dataset suitable for fast application queries.

Goals
- Convert raw CSV and EXD exports into a normalized game schema
- Build relationship indexes and search-friendly caches
- Store data in an optimized cache / database for application queries
- Automate updates from the official datamining sources using the `ffxiv-datamining` submodule

Pipeline overview

1) Importer
- Purpose: read CSV and EXD files produced by datamining tools and export raw JSON/CSV dumps.
- Input: CSV / EXD files (raw datamined tables).
- Output: raw parsed files under `data/raw/` (or a configurable `--out` directory).
- Notes: Use the `ffxiv-datamining` project (see "Submodule integration") as the canonical source for extracting EXD/CSV.

2) Normalization
- Purpose: canonicalize fields (IDs, names, enums), deduplicate entries, and map raw columns to the project schema described in [docs/README.md](docs/README.md).
- Output: normalized JSON/NDJSON and staging tables ready for relationship indexing.

3) Relationship indexing
- Purpose: create explicit relationship tables and indexes (e.g. `items -> item_sources`, `recipes -> recipe_ingredients`, `npcs -> locations`).
- Output: relational JSON/SQL dumps and precomputed adjacency indexes to speed joins and graph traversals.

4) Optimized cache / database
- Purpose: store the normalized data in a query-optimized form. Recommended options:
  - SQLite with appropriate indices and FTS5 for text search (good for single-host deployments)
  - PostgreSQL for multi-process or larger-scale deployments
- Tips:
  - Precompute and persist search indices (name variants, fuzzy tokens).
  - Build lookup maps (item_id -> recipe_id[], item_id -> locations[]) to avoid expensive runtime joins.

5) Application queries
- Expose concise APIs and queries for the Twitch bot and any web UI.
- Examples:
  - Find item locations by name (fuzzy search, then exact match by id)
  - Expand a recipe tree to list all gatherable ingredients
  - Resolve NPC vendor stocks and coordinates

The read layer shared by the API and the bot is `src/item_repository.py`, which
loads `data/normalized/items_normalized.json` once per process and exposes
`get_item`, `search_items`, and `find_items_by_name`.

HTTP API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/items/{item_id}` | Full item record including every gathering node. Returns `404` for unknown ids. |
| `GET`  | `/items?q=<name>&limit=<n>` | Case-insensitive name search. Exact matches rank first, then prefix matches, then substring matches. `limit` defaults to 20 (max 200). |

Interactive OpenAPI docs are served at `/docs` while the app is running.

```bash
curl "http://localhost:8000/items/4839"
curl "http://localhost:8000/items?q=laurel"
```

Coordinate resolution

`ExportedGatheringPoint."#"` is the id of the gathering point it was exported
from, so the exported index is always `GatheringPoint."#" - 30000`. Verified
against the 7.25 CSVs: this single rule accounts for every exported index.

Gathering points that were never exported have no entry in
`ExportedGatheringPoint.csv`; their `x`/`y` are `null` and the summary reports
`has_coords = false`. Only a subset of gathering points is exported upstream
(1077 of 5857 rows in 7.25), so most items are located but not coordinate-pinned.

Submodule integration: ffxiv-datamining

This pipeline uses the upstream project `https://github.com/xivapi/ffxiv-datamining` as a submodule to keep datamined tables and extraction tools in sync.

Recommended submodule path: `vendor/ffxiv-datamining`

Commands

- Add the submodule (first time):

```
git submodule add https://github.com/xivapi/ffxiv-datamining vendor/ffxiv-datamining
git submodule update --init --recursive
```

- Update / check for remote changes (manual):

```
cd vendor/ffxiv-datamining
git fetch origin
git rev-parse HEAD        # local
git ls-remote origin HEAD # remote HEAD commit
```

Automated helper scripts

To make it easy to check whether the installed submodule is behind the remote and optionally pull updates, this repo includes small helper scripts:

- [scripts/check_datamining_submodule.sh](../scripts/check_datamining_submodule.sh) — Bash script, usage:

```
./scripts/check_datamining_submodule.sh         # shows if update available
./scripts/check_datamining_submodule.sh --update    # attempts a fast-forward pull
```

- [scripts/check_datamining_submodule.ps1](../scripts/check_datamining_submodule.ps1) — PowerShell equivalent, usage:

```
powershell -File .\scripts\check_datamining_submodule.ps1        # shows status
powershell -File .\scripts\check_datamining_submodule.ps1 -Update  # pulls updates
```

- [scripts/check_datamining_submodule.py](../scripts/check_datamining_submodule.py) — Python helper for environments where Python is preferred.

Developer workflow

- Regular update flow (recommended as a periodic job):
  1. Run the submodule check script and update if changes exist.
  2. Run the importer to regenerate `data/raw/` from the updated datamining repo.
  3. Run normalization + relationship indexing to produce staging data.
  4. Load staging data into the optimized DB and rebuild caches/search indices.

- Example (bash):

```
./scripts/check_datamining_submodule.sh --update
# then run your importer/normalizer tools, e.g.
# python scripts/import_datamining.py --source vendor/ffxiv-datamining --out data/raw
# python scripts/normalize.py --in data/raw --out data/normalized
# python scripts/build_indexes.py --in data/normalized --out data/db
```

Notes and recommendations

- Keep `vendor/ffxiv-datamining` as a submodule (not a copy) so updates are tracked and easy to audit.
- Use shallow updates if you want smaller fetches (`git fetch --depth=1`) but be aware of implications for history.
- Test normalization and index building in a disposable environment before replacing production caches.
- Consider running the submodule check + import pipeline nightly and storing versioned snapshots (timestamped DB dumps).

Troubleshooting

- If the submodule reports 'detached HEAD' after initialization, change to the desired branch in the submodule directory:

```
cd vendor/ffxiv-datamining
git checkout main
```

Acknowledgements

- The pipeline relies on `ffxiv-datamining` for extraction and canonical data. Respect that project's license and contribution guidelines when using or redistributing their extracts.
