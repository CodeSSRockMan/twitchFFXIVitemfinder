"""Import and normalize FFXIV datamining CSVs into index structures and per-item JSON.

Creates these mappings:
- item_to_gathering_item: item_id -> [gathering_item_id, ...]
- gathering_item_to_gpb: gathering_item_id -> [gpb_id, ...]
- gpb_to_points: gpb_id -> [ {gathering_point_id, territory_id, place_name_id}, ...]

And produces a per-item normalized structure with node coordinates resolved
from ExportedGatheringPoint.csv using `exported_index = gathering_point_id - 30000`.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

LOG = logging.getLogger("import_datamining")


def _safe_int(s: str) -> int:
    try:
        return int(s)
    except Exception:
        return 0


def _read_csv(path: str) -> Iterable[Dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield row


def build_indexes(src_dir: str):
    """Read CSV files from `src_dir` and build index structures.

    Returns (item_to_gathering_item, gathering_item_to_gpb, gpb_to_points, items_normalized)
    where keys and numeric ids are ints.
    """
    # Paths
    gi_path = os.path.join(src_dir, "GatheringItem.csv")
    gpb_path = os.path.join(src_dir, "GatheringPointBase.csv")
    gp_path = os.path.join(src_dir, "GatheringPoint.csv")
    exp_gp_path = os.path.join(src_dir, "ExportedGatheringPoint.csv")
    item_path = os.path.join(src_dir, "Item.csv")
    place_path = os.path.join(src_dir, "PlaceName.csv")
    map_path = os.path.join(src_dir, "Map.csv")
    territory_path = os.path.join(src_dir, "TerritoryType.csv")

    # 1) GatheringItem -> item mapping and item -> gathering_item index
    gathering_item_to_item: Dict[int, int] = {}
    item_to_gathering_item: Dict[int, List[int]] = defaultdict(list)
    for row in _read_csv(gi_path):
        gid = _safe_int(row.get("#", "0"))
        item_id = _safe_int(row.get("Item", "0"))
        if gid:
            gathering_item_to_item[gid] = item_id
        if item_id:
            item_to_gathering_item[item_id].append(gid)

    # 2) Gather GPB -> items/gathering items, and GPB -> node type/level
    #
    # `GatheringPointBase.GatheringType` indexes `GatheringPointName.csv`, but the
    # noun table there does NOT line up with the index: `GatheringType 2` is what
    # Maple Log, Cedar Log and Claro Walnut Log live on (trees), while `GatheringType
    # 3` is what Laurel lives on (vegetation). Verified against the 7.25 CSVs by
    # sampling the items on each type, and cross-checked against known nodes.
    #
    # So the index is resolved to a job here, not read off GatheringPointName.
    # GatheringTypeName is kept only as the raw index for reference.
    GATHERING_TYPE_JOBS = {
        0: "Mining",
        1: "Mining",
        2: "Logging",
        3: "Harvesting",
    }
    node_nouns: Dict[int, str] = {}
    gpn_path = os.path.join(src_dir, "GatheringPointName.csv")
    if os.path.exists(gpn_path):
        for row in _read_csv(gpn_path):
            noun = (row.get("Singular") or "").strip()
            if noun:
                node_nouns[_safe_int(row.get("#", "0"))] = noun

    gathering_item_to_gpb: Dict[int, List[int]] = defaultdict(list)
    gpb_meta: Dict[int, Dict[str, object]] = {}
    for row in _read_csv(gpb_path):
        gpb_id = _safe_int(row.get("#", "0"))
        if not gpb_id:
            continue
        gtype = _safe_int(row.get("GatheringType", "0"))
        gpb_meta[gpb_id] = {
            "gathering_type": gtype,
            "gathering_job": GATHERING_TYPE_JOBS.get(gtype),
            "gathering_type_name": node_nouns.get(gtype),
            "gathering_level": _safe_int(row.get("GatheringLevel", "0")) or None,
        }
        # Item[0]..Item[7]
        for i in range(8):
            col = f"Item[{i}]"
            v = _safe_int(row.get(col, "0"))
            if not v:
                continue
            if v in gathering_item_to_item:
                # value is a gathering_item id
                gathering_item_to_gpb[v].append(gpb_id)
            elif v in item_to_gathering_item:
                # value is an item id -> map to all gathering_item ids
                for gid in item_to_gathering_item[v]:
                    gathering_item_to_gpb[gid].append(gpb_id)
            else:
                # unknown value; attempt to treat as item id mapping
                for gid in item_to_gathering_item.get(v, []):
                    gathering_item_to_gpb[gid].append(gpb_id)

    # 3) GatheringPoint -> group by GPB
    gpb_to_points: Dict[int, List[Dict[str, int]]] = defaultdict(list)
    for row in _read_csv(gp_path):
        gp_id = _safe_int(row.get("#", "0"))
        gpb_id = _safe_int(row.get("GatheringPointBase", "0"))
        if not gp_id or not gpb_id:
            continue
        territory = _safe_int(row.get("TerritoryType", "0"))
        place = _safe_int(row.get("PlaceName", "0"))
        gpb_to_points[gpb_id].append({
            "gathering_point_id": gp_id,
            "territory": territory,
            "place_name": place,
        })

    # 4) ExportedGatheringPoint -> coords and node radius
    exported_coords: Dict[int, Tuple[float, float]] = {}
    exported_radius: Dict[int, float] = {}
    for row in _read_csv(exp_gp_path):
        idx = _safe_int(row.get("#", "0"))
        if not idx:
            continue
        try:
            x = float(row.get("X", "0") or 0)
            y = float(row.get("Y", "0") or 0)
        except Exception:
            x = 0.0
            y = 0.0
        exported_coords[idx] = (x, y)
        try:
            exported_radius[idx] = float(row.get("Radius", "0") or 0)
        except Exception:
            exported_radius[idx] = 0.0

    # 5) Item names
    item_names: Dict[int, str] = {}
    for row in _read_csv(item_path):
        iid = _safe_int(row.get("#", "0"))
        if iid:
            item_names[iid] = row.get("Name", "")

    # 6) Place names
    place_names: Dict[int, str] = {}
    for row in _read_csv(place_path):
        pid = _safe_int(row.get("#", "0"))
        if pid:
            place_names[pid] = row.get("Name", "")

    # 6.1) Territory names
    territory_names: Dict[int, str] = {}
    for row in _read_csv(territory_path):
        tid = _safe_int(row.get("#", "0"))
        if tid:
            territory_names[tid] = row.get("Name", "")

    # 7) Maps by territory.
    #
    # A territory can span several map sheets (204 of 614 do), so keep every
    # candidate instead of overwriting and keeping an arbitrary one. The map
    # a node belongs to is resolved per node from its own PlaceName, falling
    # back to a single-map territory, then to the first candidate.
    map_place_names: Dict[str, int] = {}
    maps_by_territory: Dict[int, List[Dict[str, object]]] = defaultdict(list)
    for row in _read_csv(map_path):
        tid = _safe_int(row.get("TerritoryType", "0"))
        if not tid:
            continue
        map_id = row.get("Id", "") or ""
        place_id = _safe_int(row.get("PlaceName", "0"))
        if map_id:
            map_place_names[map_id] = place_id
        maps_by_territory[tid].append({"map_id": map_id, "place_name_id": place_id})

    # 8) ExportedGatheringPoint."#" is the canonical id of the gathering point it
        # was exported from, which is exactly `GatheringPoint."#" - EXPORTED_INDEX_OFFSET`.
        # Verified against the 7.25 CSVs: this single rule accounts for every exported
        # index, so it is used directly instead of guessing a per-territory offset.
        #
        # A previous heuristic inferred the offset per territory by maximising how many
        # gathering points landed on existing exported indices. That is unsound: for
        # some territories several offsets tie on coverage (so the result depends on
        # iteration order), and for territories with no exported points at all it
        # picked an arbitrary offset that resolved to a different territory's
        # coordinates. Points absent from ExportedGatheringPoint simply have no coords.
        EXPORTED_INDEX_OFFSET = 30000

    # 8.1) Map-space (grid) coordinates.
    #
    # `ExportedGatheringPoint.X/Y` are *world* coordinates on the same 2048-unit
    # map texture the game renders, so they run roughly -1024..1024 and the sign is
    # meaningful: a negative X is simply the western half of the zone. Measured
    # across all 1077 exported rows (X: -872.9..970.3, Y: -948.4..962.9).
    #
    # These must never be surfaced as a coordinate. The conversion below is the
    # official one from `vendor/ffxiv-datamining/docs/MapCoordinates.md`, composed
    # from its two documented steps:
    #
    #   GetPixelCoordinates:  pixel = (world + mapOffset) / 100 * sizeFactor + 1024
    #   GetGameMapCoordinates: game  = pixel / sizeFactor * 2 + 1
    #
    # `mapOffset` is the map's OffsetX/OffsetY and is NOT always zero: 628 of 1268
    # maps carry a non-zero offset. The in-game grid is 1..41.
    def to_map_grid(raw: float, map_offset: float, size_factor: float) -> float:
        pixel = (raw + map_offset) / 100.0 * size_factor + 1024.0
        # The game truncates to one decimal place.
        return round(pixel / size_factor * 2.0 + 1.0, 1)

    # 8.2) Per-map offsets and size factors.
    map_offsets: Dict[str, Tuple[float, float]] = {}
    map_size_factors: Dict[str, float] = {}
    for row in _read_csv(map_path):
        mid = row.get("Id", "") or ""
        if not mid:
            continue
        try:
            map_offsets[mid] = (float(row.get("OffsetX", 0) or 0), float(row.get("OffsetY", 0) or 0))
        except Exception:
            map_offsets[mid] = (0.0, 0.0)
        try:
            map_size_factors[mid] = float(row.get("SizeFactor", 100) or 100)
        except Exception:
            map_size_factors[mid] = 100.0

    # 9) Build per-item normalized JSON
    items_normalized: Dict[int, Dict] = {}
    for item_id, gathering_ids in item_to_gathering_item.items():
        nodes: List[Dict] = []
        for gid in gathering_ids:
            for gpb in gathering_item_to_gpb.get(gid, []):
                for point in gpb_to_points.get(gpb, []):
                    gp_id = point["gathering_point_id"]
                    exported_idx = gp_id - EXPORTED_INDEX_OFFSET
                    coord = exported_coords.get(exported_idx)
                    if coord:
                        x, y = coord
                    else:
                        x = y = None
                    territory_id = point.get("territory")
                    place_id = point.get("place_name")
                    # Prefer the map sheet whose PlaceName matches this node's place; a territory
                    # may span several sheets. Falling back to "first candidate"
                    # is wrong: many territories list a `default/00` placeholder
                    # sheet, so an unmatched place used to pin large parts of the
                    # dataset to `default/00` and its offsets. Only accept a
                    # fallback when the territory really has one usable sheet,
                    # and never pick `default/00`.
                    candidates = maps_by_territory.get(territory_id, [])
                    usable = [
                        c for c in candidates
                        if c["map_id"] and not str(c["map_id"]).startswith("default/")
                    ]
                    map_id = ""
                    for cand in usable:
                        if cand["place_name_id"] and cand["place_name_id"] == place_id:
                            map_id = str(cand["map_id"])
                            break
                    if not map_id and usable:
                        # No place matched. If every real sheet agrees on the
                        # offset and SizeFactor the choice does not matter, so any
                        # of them yields the same grid coordinate (e.g. the two
                        # w1f4 sheets, both offset 0 / SizeFactor 100).
                        sigs = {
                            (map_offsets.get(str(c["map_id"]), (0.0, 0.0)),
                             map_size_factors.get(str(c["map_id"]), 100.0))
                            for c in usable
                        }
                        if len(sigs) == 1:
                            map_id = str(usable[0]["map_id"])
                    meta = gpb_meta.get(gpb, {})
                    exported_index = exported_idx
                    coords_source = "ExportedGatheringPoint" if coord else None
                    size_factor = map_size_factors.get(map_id, 100.0)
                    off_x, off_y = map_offsets.get(map_id, (0.0, 0.0))
                    # Without a resolved map sheet the offset and SizeFactor are
                    # unknown, and different sheets use different ones, so the raw
                    # value cannot be placed on the 1..41 grid. Keep the raw
                    # coordinates but leave the grid values unset.
                    if map_id:
                        map_x = to_map_grid(x, off_x, size_factor) if x is not None else None
                        map_y = to_map_grid(y, off_y, size_factor) if y is not None else None
                    else:
                        map_x = map_y = None
                    nodes.append({
                        "gpb_id": gpb,
                        "gathering_point_id": gp_id,
                        "exported_index": exported_index,
                        "gathering_type": meta.get("gathering_type"),
                        "gathering_job": meta.get("gathering_job"),
                        "gathering_type_name": meta.get("gathering_type_name"),
                        "gathering_level": meta.get("gathering_level"),
                        "territory_id": territory_id,
                        "territory_name": territory_names.get(territory_id, ""),
                        "place_name_id": place_id,
                        "place_name": place_names.get(place_id, ""),
                        "map": map_id,
                        "x": x,
                        "y": y,
                        "map_x": map_x,
                        "map_y": map_y,
                        "radius": (
                            exported_radius.get(exported_idx, 0.0) / 50.0
                            if map_id and exported_idx in exported_radius
                            else None
                        ),
                        "coords_source": coords_source,
                    })
        items_normalized[item_id] = {
            "name": item_names.get(item_id, ""),
            "nodes": nodes,
            # Node-level view: one representative position per GatheringPointBase.
            # External databases publish a single coords/radius per node rather
            # than per gathering point, so expose the same shape here.
            "node_spots": _node_spots(nodes),
        }

    # Convert defaultdicts to regular dicts for return
    return (
        dict(item_to_gathering_item),
        {k: v for k, v in gathering_item_to_gpb.items()},
        {k: v for k, v in gpb_to_points.items()},
        items_normalized,
    )


def _node_spots(nodes: List[Dict]) -> List[Dict]:
    """Group gathering points by GatheringPointBase (node).

    External databases publish one coords/radius per node, but the gathering
    points under one node can sit many grid units apart, so averaging them would
    invent a position that is not on the map. Each spot therefore lists the real
    positions, and `map_x`/`map_y` are only filled in when the node's points
    coincide within half a grid unit, which is when a single point is meaningful.
    """
    grouped: Dict[int, List[Dict]] = defaultdict(list)
    for n in nodes:
        grouped[n.get("gpb_id")].append(n)

    spots: List[Dict] = []
    for gpb_id, group in sorted(grouped.items()):
        positioned = [n for n in group if n.get("map_x") is not None]
        radii = [n["radius"] for n in group if n.get("radius") is not None]

        single_x = single_y = None
        if positioned:
            xs = {round(n["map_x"], 1) for n in positioned}
            ys = {round(n["map_y"], 1) for n in positioned}
            if len(xs) == 1 and len(ys) == 1:
                single_x = positioned[0]["map_x"]
                single_y = positioned[0]["map_y"]

        spots.append({
            "gpb_id": gpb_id,
            "place_name": group[0].get("place_name", ""),
            "map": group[0].get("map", ""),
            "gathering_job": group[0].get("gathering_job"),
            "gathering_level": group[0].get("gathering_level"),
            "map_x": single_x,
            "map_y": single_y,
            "radius": round(max(radii), 2) if radii else None,
            "point_count": len(group),
            "positions": [
                {
                    "gathering_point_id": n["gathering_point_id"],
                    "map_x": n["map_x"],
                    "map_y": n["map_y"],
                    "radius": n.get("radius"),
                }
                for n in group
            ],
        })
    return spots


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Import FFXIV datamining CSVs and build indexes")
    p.add_argument("--src", default=os.path.join("vendor", "ffxiv-datamining", "csv", "en"))
    p.add_argument("--out", default=os.path.join("data", "normalized"))
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    LOG.info("Building indexes from %s", args.src)
    (
        item_to_gathering_item,
        gathering_item_to_gpb,
        gpb_to_points,
        items_normalized,
    ) = build_indexes(args.src)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "item_to_gathering_item.json"), "w", encoding="utf-8") as fh:
        json.dump(item_to_gathering_item, fh, indent=2)
    with open(os.path.join(args.out, "gathering_item_to_gpb.json"), "w", encoding="utf-8") as fh:
        json.dump(gathering_item_to_gpb, fh, indent=2)
    with open(os.path.join(args.out, "gpb_to_points.json"), "w", encoding="utf-8") as fh:
        json.dump(gpb_to_points, fh, indent=2)
    with open(os.path.join(args.out, "items_normalized.json"), "w", encoding="utf-8") as fh:
        json.dump(items_normalized, fh, indent=2)

    LOG.info("Wrote outputs to %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
