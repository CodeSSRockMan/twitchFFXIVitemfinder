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

Coordinates come in two spaces, and only one of them is usable in game.

`ExportedGatheringPoint.X/Y` are **world coordinates** on the 2048x2048 map
texture the game renders, so they run roughly `-1024..1024` (measured across all
1077 exported rows: X `-872.9..970.3`, Y `-948.4..962.9`). The sign is meaningful
there — a negative X is simply the western half of the zone — but these values
must never be shown as a coordinate.

The in-game grid is **1..41**. The conversion is the official one from
`vendor/ffxiv-datamining/docs/MapCoordinates.md`, composed from its two
documented steps:

```
pixel = (world + offset) / 100 * sizeFactor + 1024
game  = pixel / sizeFactor * 2 + 1          # truncated to 1 decimal
```

This is the formula introduced by
[xivapi/ffxiv-datamining#30](https://github.com/xivapi/ffxiv-datamining/pull/30)
("Map Coordinate Fixes", merged 2022-11-02), which replaced the older
`41 / scale * ((val + 1024) / 2048) + 1` expression. That older form used `41` as
a magic number where `40.96` is correct; the two agree only for a zero map
offset, which is why offset-free variants drift on maps that have one.

`offset` is the map's `OffsetX`/`OffsetY` and is **not** always zero — 628 of 1268
maps carry a non-zero offset, so it must be applied per map. Each node therefore
carries `map_x` / `map_y` alongside the raw `x` / `y`. Across all 2340 positioned
nodes the result is `4.0..40.9` on both axes, with **zero negatives and zero
values outside 1..41**, which is what the game shows.

`tests/test_import_datamining.py` re-derives every node's coordinates from
`Map.csv` using the documented formula and asserts they match, so the conversion
cannot silently drift.

`coords_source` is `ExportedGatheringPoint` when coordinates exist, and is
`null` otherwise. Gathering points that were never exported have `x`/`y` and
`map_x`/`map_y` all `null`, and the summary reports `has_coords = false`. Only a
subset of gathering points is exported upstream (1077 of 5857 rows in 7.25), so
most items are located but not coordinate-pinned.

A separate table, `MapMarker.csv`, holds coordinates in a third space
(`0..2000`, origin at a corner, no negatives). It is not a node-coordinates
source: markers carry `PlaceNameSubtext` rather than a gathering-point id, so a
marker cannot be tied back to a specific node.

Zone, node and job

Each node carries four distinct location concepts, which are **not** the same thing:

| Field | Meaning | Example |
|-------|---------|---------|
| `territory_name` / `territory_id` | zone (e.g. `x6f2`) | East Yyasulani's territory |
| `place_name` | the node inside the zone | `Broken Water` |
| `map` | map sheet the node sits on | `x6f2/00` (Heritage Found) |
| `gathering_job` + `gathering_level` | which job, what level | Logging, level 100 |

A zone can sit inside a named area — East Yyasulani is inside Heritage Found, and
**the map used for coordinates comes from Heritage Found (`x6f2/00`)**, not from
the sub-zone name. A territory may also span several map sheets (204 of 614 do),
so `map` is resolved per node by matching the node's `PlaceName` against the
candidate sheets rather than picking one arbitrarily.

`GatheringPointBase.GatheringType` is an index, but it does **not** line up with
the nouns in `GatheringPointName.csv`. Verified against the 7.25 CSVs by sampling
the items on each type:

| `GatheringType` | Job | Confirmed by |
|---|---|---|
| 0 | Mining | Iron Ore, Adamantite Ore |
| 2 | Logging | Maple Log, Cedar Log, Claro Walnut Log (Lv.100 mature tree) |
| 3 | Harvesting | Laurel (Lv.35 lush vegetation) |

`gathering_type_name` retains the raw `GatheringPointName` noun for reference,
but `gathering_job` is the field to trust.

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
