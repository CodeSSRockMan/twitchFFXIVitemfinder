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

    # 2) Gather GPB -> items/gathering items
    gathering_item_to_gpb: Dict[int, List[int]] = defaultdict(list)
    for row in _read_csv(gpb_path):
        gpb_id = _safe_int(row.get("#", "0"))
        if not gpb_id:
            continue
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

    # 4) ExportedGatheringPoint -> coords
    exported_coords: Dict[int, Tuple[float, float]] = {}
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

    # 7) Map by territory (Map.csv has TerritoryType column)
    map_by_territory: Dict[int, Dict[str, str]] = {}
    for row in _read_csv(map_path):
        try:
            tid = _safe_int(row.get("TerritoryType", "0"))
        except Exception:
            tid = 0
        if tid:
            map_by_territory.setdefault(tid, {})["map_id"] = row.get("Id", "")
            # PlaceName column can be useful too
            map_by_territory[tid]["place_name_id"] = _safe_int(row.get("PlaceName", "0"))

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
                    map_info = map_by_territory.get(territory_id, {})
                    exported_index = exported_idx
                    coords_source = "ExportedGatheringPoint" if coord else None
                    nodes.append({
                        "gpb_id": gpb,
                        "gathering_point_id": gp_id,
                        "exported_index": exported_index,
                        "territory_id": territory_id,
                        "territory_name": territory_names.get(territory_id, ""),
                        "place_name_id": place_id,
                        "place_name": place_names.get(place_id, ""),
                        "map": map_info.get("map_id", ""),
                        "x": x,
                        "y": y,
                        "coords_source": coords_source,
                    })
        items_normalized[item_id] = {"name": item_names.get(item_id, ""), "nodes": nodes}

    # Convert defaultdicts to regular dicts for return
    return (
        dict(item_to_gathering_item),
        {k: v for k, v in gathering_item_to_gpb.items()},
        {k: v for k, v in gpb_to_points.items()},
        items_normalized,
    )


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
