"""Simple CLI to look up normalized item nodes produced by the importer.

Usage examples:
  python scripts/lookup_normalized.py --id 4839
  python scripts/lookup_normalized.py --name laurel
  python scripts/lookup_normalized.py --list 50
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Dict, Optional


DEFAULT_PATH = os.path.join("data", "normalized", "items_normalized.json")
DEFAULT_DATADIR = os.path.join("vendor", "ffxiv-datamining", "csv", "en")


def load_items(path: str) -> Dict[int, dict]:
    if not os.path.exists(path):
        print(f"Normalized file not found: {path}\nRun: python scripts/import_datamining.py --src vendor/ffxiv-datamining/csv/en --out data/normalized")
        sys.exit(2)
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    items: Dict[int, dict] = {}
    for k, v in data.items():
        try:
            items[int(k)] = v
        except Exception:
            # skip non-int keys
            continue
    return items


def print_item(item_id: int, item: dict) -> None:
    print(f"Item {item_id}: {item.get('name','<unknown>')}")
    nodes = item.get("nodes", [])
    if not nodes:
        print("  (no gathering nodes found)")
        return
    for i, n in enumerate(nodes, start=1):
        gpb = n.get("gpb_id")
        gp = n.get("gathering_point_id")
        exported = n.get("exported_index")
        territory = n.get("territory_id")
        territory_name = n.get("territory_name") or ""
        place_id = n.get("place_name_id")
        place = n.get("place_name") or ""
        map_id = n.get("map") or ""
        x = n.get("x")
        y = n.get("y")
        coord = f"{x:.3f},{y:.3f}" if (isinstance(x, (int, float)) and isinstance(y, (int, float))) else "N/A"
        source = n.get("coords_source") or ""
        extra = f"gpb={gpb} gp={gp} exported={exported}"
        print(f"  {i}. {extra} territory={territory} ({territory_name}) place={place_id} ({place}) map={map_id} coords={coord} source={source}")


def _read_csv_indexed(path: str, key_col: str = "#") -> Dict[int, dict]:
    out: Dict[int, dict] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                k = int(row.get(key_col, "0") or 0)
            except Exception:
                continue
            out[k] = row
    return out


def _read_csv_rows(path: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def _find_map_row_advanced(path: str, map_id: str | None = None, territory_id: int | None = None) -> Optional[dict]:
    """Try several strategies to find the best Map.csv row for `map_id` or `territory_id`.

    Strategies (in order):
    - exact `Id` match
    - match by Id prefix (e.g. w1f4 from w1f4/02)
    - match by TerritoryType column
    Returns the first matching row or None.
    """
    rows = _read_csv_rows(path)
    if map_id:
        # exact match
        for row in rows:
            if (row.get("Id") or "") == map_id:
                return row
        # prefix match
        prefix = map_id.split("/")[0]
        for row in rows:
            rid = (row.get("Id") or "")
            if rid and rid.split("/")[0] == prefix:
                return row
    # territory match
    if territory_id:
        for row in rows:
            try:
                if int(row.get("TerritoryType") or 0) == territory_id:
                    return row
            except Exception:
                continue
    return None


def to_map_coord(raw: float, offset: float, size_factor: float) -> float:
    """Convert exported raw coordinate to map-local coordinate using provided formula.

    Formula provided by user:
        c = size_factor / 100
        return round(((41 / c) * ((raw + offset) / 2048)) + 1, 1)
    """
    try:
        c = float(size_factor) / 100.0
        return round(((41.0 / c) * ((float(raw) + float(offset)) / 2048.0)) + 1.0, 1)
    except Exception:
        return 0.0


def to_map_coord_with_wrap(raw: float, offset: float, size_factor: float) -> float:
    """Try converting with possible wrap offsets if the direct conversion is out-of-range.

    Some exported raw X/Y values can be negative; attempt adding multiples of 2048
    to bring them into the positive map range. Return the first value in [1,41].
    """
    candidates = [0, 2048, -2048, 4096, -4096]
    for add in candidates:
        try:
            val = to_map_coord(raw + add, offset, size_factor)
        except Exception:
            continue
        if 1.0 <= val <= 41.0:
            return val
    # fallback to direct conversion
    try:
        return to_map_coord(raw, offset, size_factor)
    except Exception:
        return 0.0


def _find_map_row_by_id(path: str, map_id: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if (row.get("Id") or "") == map_id:
                return row
    return None


def describe_item(item_id: int, item: dict, datadir: str | None = None) -> None:
    """Build and print a short natural-language sentence describing the item and a best node."""
    datadir = datadir or DEFAULT_DATADIR
    item_csv = os.path.join(datadir, "Item.csv")
    search_cat_csv = os.path.join(datadir, "ItemSearchCategory.csv")
    map_csv = os.path.join(datadir, "Map.csv")
    place_csv = os.path.join(datadir, "PlaceName.csv")

    # Load lookups
    item_rows = _read_csv_indexed(item_csv)
    search_cats = _read_csv_indexed(search_cat_csv)

    item_row = item_rows.get(item_id, {})
    level = item_row.get("LevelItem") if item_row else None
    try:
        level_val = int(level) if level not in (None, "") else None
    except Exception:
        level_val = None

    cat_label = None
    if item_row:
        try:
            cat_id = int(item_row.get("ItemSearchCategory") or 0)
        except Exception:
            cat_id = 0
        cat_label = (search_cats.get(cat_id) or {}).get("Name")

    # Choose best node (prefer exported coords)
    nodes = item.get("nodes") or []
    # Show raw nodes to the user for verification before we pick one
    print("Nodes:")
    if not nodes:
        print("  (no gathering nodes found)")
    else:
        for i, n in enumerate(nodes, start=1):
            gpb = n.get("gpb_id")
            gp = n.get("gathering_point_id")
            exported = n.get("exported_index")
            territory = n.get("territory_id")
            territory_name = n.get("territory_name") or ""
            place_id = n.get("place_name_id")
            place = n.get("place_name") or ""
            map_id = n.get("map") or ""
            x = n.get("x")
            y = n.get("y")
            source = n.get("coords_source") or ""
            # compute raw coord text
            if (isinstance(x, (int, float)) and isinstance(y, (int, float))):
                coord_raw = f"{x:.3f},{y:.3f}"
                # attempt to compute normalized map coords using Map.csv info
                map_row_n = _find_map_row_advanced(map_csv, map_id=map_id, territory_id=n.get("territory_id"))
                if map_row_n:
                    try:
                        size = float(map_row_n.get("SizeFactor") or 100)
                        offx = float(map_row_n.get("OffsetX") or 0)
                        offy = float(map_row_n.get("OffsetY") or 0)
                        xmap = to_map_coord_with_wrap(x, offx, size)
                        ymap = to_map_coord_with_wrap(y, offy, size)
                        coord = f"{coord_raw} (map {xmap},{ymap})"
                    except Exception:
                        coord = coord_raw
                else:
                    coord = coord_raw
            else:
                coord = "N/A"
            print(f"  {i}. gpb={gpb} gp={gp} exported={exported} territory={territory} ({territory_name}) place={place_id} ({place}) map={map_id} coords={coord} source={source}")
    chosen = None
    for n in nodes:
        if n.get("coords_source") == "ExportedGatheringPoint" and isinstance(n.get("x"), (int, float)) and isinstance(n.get("y"), (int, float)):
            chosen = n
            break
    if chosen is None:
        for n in nodes:
            if isinstance(n.get("x"), (int, float)) and isinstance(n.get("y"), (int, float)):
                chosen = n
                break

    region_name = None
    coords_text = "N/A"
    # Determine a candidate node for map/territory resolution: prefer chosen (with coords), otherwise first node
    candidate = chosen or (nodes[0] if nodes else None)
    if chosen:
        x = chosen.get("x")
        y = chosen.get("y")
        coords_text = f"{x:.3f}, {y:.3f}" if (isinstance(x, (int, float)) and isinstance(y, (int, float))) else "N/A"

    if candidate:
        map_id = candidate.get("map") or ""
        # Prefer Map.csv -> PlaceName lookup for human-readable region using
        # several strategies (exact id, id-prefix, territory match)
        map_row = _find_map_row_advanced(map_csv, map_id=map_id, territory_id=candidate.get("territory_id"))
        place_rows = _read_csv_indexed(place_csv)
        territory_rows = _read_csv_indexed(os.path.join(datadir, "TerritoryType.csv"))
        if map_row:
            # Prefer the specific PlaceName first, then PlaceNameRegion, then PlaceNameSub
            pname_id = 0
            for fld in ("PlaceName", "PlaceNameRegion", "PlaceNameSub"):
                try:
                    v = map_row.get(fld)
                    if v and v.strip() != "":
                        pname_id = int(v)
                        break
                except Exception:
                    continue
            region_name = (place_rows.get(pname_id) or {}).get("Name")
        # If still no region name, try to find an enclosing area by scanning Map.csv
        if not region_name:
            try:
                tid = int(candidate.get("territory_id") or 0)
            except Exception:
                tid = 0
            if tid:
                for row in _read_csv_rows(map_csv):
                    try:
                        if int(row.get("TerritoryType") or 0) != tid:
                            continue
                    except Exception:
                        continue
                    # prefer PlaceName (specific) from other maps in same territory, then region
                    for fld in ("PlaceName", "PlaceNameRegion", "PlaceNameSub"):
                        try:
                            v = row.get(fld)
                            if v and v.strip() != "":
                                pn = (place_rows.get(int(v)) or {}).get("Name")
                                if pn:
                                    region_name = pn
                                    break
                        except Exception:
                            continue
                    if region_name:
                        break
        # final fallback: territory name
        if not region_name:
            try:
                tid = int(candidate.get("territory_id") or 0)
                region_name = (territory_rows.get(tid) or {}).get("Name")
            except Exception:
                region_name = region_name
    # Fallbacks
    if not region_name and nodes:
        # use node's place_name (gathering point place)
        region_name = nodes[0].get("place_name") or nodes[0].get("territory_name") or "<unknown>"

    # Build sentence
    item_name = item.get("name") or f"{item_id}"
    level_part = f"level {level_val}" if level_val is not None else ""
    cat_part = (cat_label or "item").lower()
    region_part = region_name or "an unknown location"
    # compute normalized map coords for the chosen node (if present)
    norm_coords_text = "N/A"
    if chosen:
        cx = chosen.get("x")
        cy = chosen.get("y")
        if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
            # reuse map_row if available, otherwise try to look it up
            map_row_used = map_row if 'map_row' in locals() and map_row else _find_map_row_advanced(map_csv, map_id=(chosen.get('map') or ''), territory_id=chosen.get('territory_id'))
            if map_row_used:
                try:
                    size = float(map_row_used.get("SizeFactor") or 100)
                    offx = float(map_row_used.get("OffsetX") or 0)
                    offy = float(map_row_used.get("OffsetY") or 0)
                    nx = to_map_coord_with_wrap(cx, offx, size)
                    ny = to_map_coord_with_wrap(cy, offy, size)
                    norm_coords_text = f"{nx}, {ny}"
                except Exception:
                    norm_coords_text = "N/A"
    # Prefer showing normalized (map) coordinates if available, otherwise raw coords_text
    coords_display = norm_coords_text if norm_coords_text != "N/A" else coords_text
    print(f"{item_name} is an Item {level_part} {cat_part} that can be found in {region_part}, at the coordinates x={coords_display}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Lookup normalized item nodes")
    p.add_argument("--path", default=DEFAULT_PATH, help="Path to items_normalized.json")
    p.add_argument("--id", type=int, help="Item id to lookup")
    p.add_argument("--name", help="Case-insensitive substring search on item name")
    p.add_argument("--sentence", action="store_true", help="Print a short natural-language sentence describing the item")
    p.add_argument("--list", type=int, nargs="?", const=50, help="List first N items (default 50)")
    p.add_argument("query", nargs="?", help="Exact name lookup (case-insensitive) or id if numeric when no prefix provided")
    args = p.parse_args(argv)

    items = load_items(args.path)

    if args.list is not None:
        n = args.list or 50
        print(f"Listing first {n} items (id : name)")
        for i, (iid, val) in enumerate(sorted(items.items())[:n], start=1):
            print(f"{i}. {iid} : {val.get('name','')}")
        return 0

    if args.id is not None:
        item = items.get(args.id)
        if not item:
            print(f"Item id {args.id} not found")
            return 1
        if args.sentence:
            describe_item(args.id, item)
        else:
            print_item(args.id, item)
        return 0

    # If a bare positional query was provided and no search flags, treat it as
    # an exact-name lookup (case-insensitive) as the user's primary intent.
    if getattr(args, "query", None) and not args.name and args.id is None and args.list is None:
        q = args.query.strip()
        # exact-case-insensitive match on item name
        matches = [(iid, v) for iid, v in items.items() if (v.get("name") or "").casefold() == q.casefold()]
        if matches:
            if len(matches) == 1:
                iid, item = matches[0]
                if args.sentence:
                    describe_item(iid, item)
                else:
                    print_item(iid, item)
                return 0
            print(f"Multiple exact matches for '{q}':")
            for iid, item in matches:
                print(f"- {iid} : {item.get('name','')}")
            return 0
        # if numeric, try id fallback
        if q.isdigit():
            iid = int(q)
            item = items.get(iid)
            if item:
                if args.sentence:
                    describe_item(iid, item)
                else:
                    print_item(iid, item)
                return 0
        print(f"No exact match for '{q}'. Use '--name {q}' for substring search.")
        return 1

    if args.name:
        q = args.name.casefold()
        matches = [(iid, v) for iid, v in items.items() if q in (v.get("name") or "").casefold()]
        if not matches:
            print(f"No items match '{args.name}'")
            return 1
        if len(matches) == 1:
            iid, item = matches[0]
            if args.sentence:
                describe_item(iid, item)
            else:
                print_item(iid, item)
            return 0
        print(f"Found {len(matches)} matches for '{args.name}':")
        for iid, item in matches:
            print(f"- {iid} : {item.get('name','')}")
        return 0

    p.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
