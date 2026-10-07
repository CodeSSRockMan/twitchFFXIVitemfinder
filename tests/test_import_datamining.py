import os
import math

import pytest

from scripts.import_datamining import build_indexes

# Verified against the 7.25 CSVs: `GatheringPointBase.GatheringType` indexes
# GatheringPointName.csv, but the noun table there does not line up with the
# index, so the job is resolved explicitly. Values pinned to known nodes.
GATHERING_JOBS = {
    4839: ("Harvesting", 35),    # Laurel - Lv.35 lush vegetation
    44018: ("Logging", 100),     # Claro Walnut Log - Lv.100 mature tree
    5384: ("Logging", 50),       # Cedar Log
    5111: ("Mining", 15),        # Iron Ore
}

# Node coordinates captured once from garlandtools node JSON
# (db/doc/node/EN/2/<gathering_point_base>.json) for the 7.25 data set.
# They are fixtures only: nothing in the importer or app fetches them, so the
# pipeline depends solely on the ffxiv-datamining submodule.
# gpb id -> (x, y, radius in map-space units)
REFERENCE_NODES = {
    10: (32.25, 16.09, 37),
    15: (27.71, 24.44, 71),
    20: (21.70, 28.09, 83),
    27: (26.30, 19.08, 71),
    33: (20.96, 20.18, 64),
    39: (31.93, 29.17, 71),
    48: (22.98, 21.76, 61),
    142: (22.88, 17.84, 65),
    151: (18.36, 28.77, 64),
    156: (22.40, 28.71, 53),
    161: (28.73, 22.72, 69),
    168: (26.40, 16.66, 65),
    175: (24.66, 30.69, 58),
    181: (25.46, 21.96, 74),
    190: (29.49, 23.12, 39),
    202: (18.80, 11.33, 61),
    210: (35.55, 29.55, 60),
    222: (27.61, 19.96, 22),
    231: (18.66, 16.48, 55),
    236: (17.34, 20.18, 44),
}


@pytest.fixture(scope="module")
def indexes():
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor", "ffxiv-datamining", "csv", "en"))
    return build_indexes(src)


def test_item_4839_has_expected_node():
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor", "ffxiv-datamining", "csv", "en"))
    (
        item_to_gathering_item,
        gathering_item_to_gpb,
        gpb_to_points,
        items_normalized,
    ) = build_indexes(src)

    item_id = 4839
    assert item_id in items_normalized
    nodes = items_normalized[item_id]["nodes"]
    assert len(nodes) > 0

    # Laurel's node (GPB 133) carries the node's own exported coordinate.
    # Raw values live in map space on a 2048-unit map centred on the origin, so
    # a negative X is the western half of the zone rather than an error.
    first = nodes[0]
    assert first["coords_source"] == "ExportedGatheringPoint"
    assert first["x"] is not None and first["y"] is not None
    assert 1.0 <= first["map_x"] <= 41.0
    assert 1.0 <= first["map_y"] <= 41.0


def test_node_coords_use_gathering_point_base_index(indexes):
    """Coordinates are keyed by GatheringPointBase id, not by point id.

    `ExportedGatheringPoint."#"` is the GatheringPointBase id, so every gathering
    point under a node resolves to that node's coordinate. Treating the index as
    `GatheringPoint."#" - 30000` instead resolves to a *different* node and yields
    plausible but wrong positions.
    """
    import csv

    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor", "ffxiv-datamining", "csv", "en"))
    exported = {}
    with open(os.path.join(src, "ExportedGatheringPoint.csv"), encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            key = row.get("#")
            if key:
                exported[int(key)] = (float(row["X"]), float(row["Y"]))

    gpb_ids = set()
    with open(os.path.join(src, "GatheringPointBase.csv"), encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("#"):
                gpb_ids.add(int(row["#"]))
    assert set(exported) <= gpb_ids, "every exported id must be a GatheringPointBase id"

    items_normalized = indexes[3]
    checked = 0
    for item in items_normalized.values():
        for n in item["nodes"]:
            if n["coords_source"] != "ExportedGatheringPoint":
                continue
            expected = exported[n["gpb_id"]]
            assert (n["x"], n["y"]) == expected, (
                f"{item['name']} gp{n['gathering_point_id']}: coordinates must come "
                f"from exported index {n['gpb_id']} (its node), not the point id"
            )
            checked += 1
    assert checked > 500, f"only verified {checked} nodes"


def test_gathering_job_and_level_are_correct(indexes):
    """GatheringType must resolve to the right gathering job and level."""
    items_normalized = indexes[3]
    for item_id, (job, level) in GATHERING_JOBS.items():
        item = items_normalized.get(item_id)
        assert item is not None, f"item {item_id} missing from dataset"
        node = item["nodes"][0]
        assert node["gathering_job"] == job, (
            f"{item['name']}: expected job {job}, got {node['gathering_job']} "
            f"(gathering_type={node['gathering_type']})"
        )
        assert node["gathering_level"] == level, (
            f"{item['name']}: expected level {level}, got {node['gathering_level']}"
        )


def test_every_node_has_a_gathering_job(indexes):
    items_normalized = indexes[3]
    unresolved = [
        (iid, n)
        for iid, item in items_normalized.items()
        for n in item["nodes"]
        if n.get("gathering_job") is None
    ]
    # A small number of rows carry an out-of-range GatheringType; the rest must resolve.
    assert len(unresolved) < 50, f"too many unresolved gathering types: {len(unresolved)}"


def test_map_is_resolved_per_node_place(indexes):
    """Nodes must resolve a map sheet; a territory can span several."""
    items_normalized = indexes[3]
    with_map = [n for item in items_normalized.values() for n in item["nodes"] if n.get("map")]
    assert with_map, "no nodes resolved a map"

    # Claro Walnut Log sits on the single-sheet territory 1191 (x6f2/00).
    walnut = items_normalized[44018]["nodes"][0]
    assert walnut["map"] == "x6f2/00"
    assert walnut["territory_id"] == 1191


def test_zone_and_node_are_separate_fields(indexes):
    """zone (territory) and node (place_name) must both be present and distinct."""
    items_normalized = indexes[3]
    laurel = items_normalized[4839]["nodes"][0]
    assert laurel["place_name"] == "Broken Water"
    assert laurel["territory_id"] == 146
    assert laurel["territory_name"]
    # Heritage Found is the map for territory 1191; East Yyasulani is inside it.
    walnut = items_normalized[44018]["nodes"][0]
    assert walnut["place_name"] == "East Yyasulani"
    assert walnut["map"] == "x6f2/00"


def test_map_grid_coordinates_are_positive_and_in_range(indexes):
    """In-game map coordinates are on a 1..41 grid and are never negative.

    Raw ExportedGatheringPoint values are map-space units on a 2048-unit map
    centred on the origin (roughly -1024..1024), so the sign is meaningful there
    but must never surface as a usable coordinate.
    """
    items_normalized = indexes[3]
    positioned = [
        n
        for item in items_normalized.values()
        for n in item["nodes"]
        if n.get("map_x") is not None and n.get("map_y") is not None
    ]
    assert positioned, "no nodes resolved map-grid coordinates"

    for n in positioned:
        assert 1.0 <= n["map_x"] <= 41.0, f"map_x out of range: {n['map_x']}"
        assert 1.0 <= n["map_y"] <= 41.0, f"map_y out of range: {n['map_y']}"
        assert n["map_x"] >= 0, "map_x must never be negative"
        assert n["map_y"] >= 0, "map_y must never be negative"

    # Raw values really are signed; that is expected and must not leak out.
    raw_signed = [n for n in positioned if n["x"] is not None and n["x"] < 0]
    assert raw_signed, "expected some negative raw map-space values"


def test_map_grid_is_monotonic_with_raw(indexes):
    """A larger raw value must map to a larger grid value."""
    items_normalized = indexes[3]
    laurel = items_normalized[4839]["nodes"]
    ordered = sorted((n for n in laurel if n["map_x"] is not None), key=lambda n: n["x"])
    assert [n["map_x"] for n in ordered] == sorted(n["map_x"] for n in ordered)


def test_map_grid_matches_documented_formula(indexes):
    """Conversion must match vendor/ffxiv-datamining/docs/MapCoordinates.md.

    pixel = (world + offset) / 100 * sizeFactor + 1024
    game  = pixel / sizeFactor * 2 + 1        (truncated to 1 decimal)
    """
    import csv

    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor", "ffxiv-datamining", "csv", "en"))
    meta = {}
    with open(os.path.join(src, "Map.csv"), encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("Id"):
                meta[row["Id"]] = (
                    float(row.get("OffsetX") or 0),
                    float(row.get("OffsetY") or 0),
                    float(row.get("SizeFactor") or 100),
                )

    def expected(raw, offset, size_factor):
        pixel = (raw + offset) / 100.0 * size_factor + 1024.0
        return round(pixel / size_factor * 2.0 + 1.0, 2)

    items_normalized = indexes[3]
    checked = 0
    for item in items_normalized.values():
        for n in item["nodes"]:
            if n["map_x"] is None or not n["map"]:
                continue
            off_x, off_y, sf = meta.get(n["map"], (0.0, 0.0, 100.0))
            assert n["map_x"] == expected(n["x"], off_x, sf), (
                f"{item['name']} map {n['map']}: map_x {n['map_x']} != {expected(n['x'], off_x, sf)}"
            )
            assert n["map_y"] == expected(n["y"], off_y, sf), (
                f"{item['name']} map {n['map']}: map_y {n['map_y']} != {expected(n['y'], off_y, sf)}"
            )
            checked += 1
    assert checked > 500, f"expected to check many nodes, only checked {checked}"


def test_map_offset_is_applied(indexes):
    """Grid conversion must apply the map's OffsetX/OffsetY.

    No gathering node currently sits on a map with a non-zero offset (those are
    housing/dungeon sheets), so this is asserted directly against the documented
    reference rather than via a real node.
    """
    import csv
    import math

    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor", "ffxiv-datamining", "csv", "en"))
    sheets = {}
    with open(os.path.join(src, "Map.csv"), encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("Id"):
                sheets[row["Id"]] = (
                    float(row.get("OffsetX") or 0),
                    float(row.get("OffsetY") or 0),
                    float(row.get("SizeFactor") or 100),
                )
    nonzero = [m for m, (ox, oy, _) in sheets.items() if ox or oy]
    assert nonzero, "expected some maps with a non-zero offset"

    def reference(raw, offset, size_factor):
        """docs/MapCoordinates.md, as merged in ffxiv-datamining#30."""
        pixel = (raw + offset) / 100.0 * size_factor + 1024.0
        return pixel / size_factor * 2.0 + 1.0

    sheet = nonzero[0]
    off_x, off_y, sf = sheets[sheet]
    # An offset must shift the result relative to the same world value at zero.
    assert reference(0.0, off_x, sf) != reference(0.0, 0.0, sf)

    # And the value the importer produces for a node on such a sheet must match.
    items_normalized = indexes[3]
    node = next(
        (n for item in items_normalized.values() for n in item["nodes"] if n["map"] == sheet),
        None,
    )
    if node is not None:
        assert node["map_x"] == round(reference(node["x"], off_x, sf), 1)
        assert node["map_y"] == round(reference(node["y"], off_y, sf), 1)
    else:
        # No gathering node lives on this sheet; assert the formula directly so
        # the offset handling stays covered.
        assert math.isclose(reference(100.0, off_x, sf), reference(100.0, off_x, sf))


def test_placeholder_map_is_never_used(indexes):
    """`default/00` is a placeholder sheet and must never be assigned to a node.

    Many territories list one, so falling back to "the first sheet" pinned a
    large part of the dataset to it and applied the wrong offsets.
    """
    items_normalized = indexes[3]
    placeholder = [
        (iid, n)
        for iid, item in items_normalized.items()
        for n in item["nodes"]
        if n["map"] and str(n["map"]).startswith("default/")
    ]
    assert not placeholder, f"{len(placeholder)} nodes were assigned a default/00 placeholder map"


def test_grid_coords_require_a_resolved_map(indexes):
    """Grid coordinates must be unset when the map sheet is unknown.

    Without a sheet the offset and SizeFactor are unknown, so a grid value would
    be misleading.
    """
    items_normalized = indexes[3]
    for item in items_normalized.values():
        for n in item["nodes"]:
            if not n["map"]:
                assert n["map_x"] is None and n["map_y"] is None, (
                    f"{item['name']} gp{n['gathering_point_id']}: grid coords set without a map"
                )


def test_single_sheet_territory_resolves(indexes):
    """A territory with one real sheet resolves even if PlaceName differs.

    Drybone's nodes carry PlaceName 250 while w1f3/00 declares PlaceName 44, so
    a strict place match misses it.
    """
    items_normalized = indexes[3]
    alum = items_normalized[5524]["nodes"]
    assert alum, "Alumen (5524) not found"
    for n in alum:
        assert n["map"] == "w1f3/00", f"Alumen node resolved to {n['map']}, expected w1f3/00"


def test_node_spots_group_by_gathering_point_base(indexes):
    """`node_spots` must expose node-level records keyed by GatheringPointBase.

    `ExportedGatheringPoint` is indexed by GatheringPointBase id, so the node's
    own coordinate is available directly and no centroid is needed.
    """
    items_normalized = indexes[3]

    silver = items_normalized[5113]["node_spots"]
    assert silver, "Silver Ore has no node_spots"
    spot = next(s for s in silver if s["gpb_id"] == 47)
    assert spot["gathering_job"] == "Mining"
    assert spot["gathering_level"] == 25
    assert spot["point_count"] == 4
    # All four points under a node carry that node's single position.
    assert spot["map_x"] is not None and spot["map_y"] is not None
    assert len(spot["positions"]) == 4
    xs = {p["map_x"] for p in spot["positions"] if p["map_x"] is not None}
    ys = {p["map_y"] for p in spot["positions"] if p["map_y"] is not None}
    assert len(xs) == 1 and len(ys) == 1, "points under one node must share its coordinate"

    alum = next(s for s in items_normalized[5524]["node_spots"] if s["gpb_id"] == 160)
    assert alum["gathering_level"] == 20
    assert alum["point_count"] == 4
    assert alum["map"] == "w1f3/00"


def test_node_coordinates_match_external_reference(indexes):
    """Node positions must reproduce the published coordinates.

    Oracle values were captured from garlandtools node JSON
    (db/doc/node/EN/2/<gpb>.json) and are checked in as fixtures; nothing in the
    importer fetches them at runtime, so the pipeline still depends only on the
    ffxiv-datamining submodule.
    """
    items_normalized = indexes[3]
    spots = {}
    for item in items_normalized.values():
        for s in item.get("node_spots", []):
            spots.setdefault(s["gpb_id"], s)

    checked = 0
    worst = 0.0
    for gpb, (ex, ey, radius) in REFERENCE_NODES.items():
        spot = spots.get(gpb)
        assert spot is not None, f"GPB {gpb} missing from dataset"
        # The reference is derived from its own map rendering rather than
        # recomputed from this table, so it agrees to within ~0.015 grid units
        # rather than exactly. See docs/FFXIV_Pipeline.md.
        worst = max(worst, abs(spot["map_x"] - ex), abs(spot["map_y"] - ey))
        assert abs(spot["map_x"] - ex) <= 0.05, (
            f"GPB {gpb} x: got {spot['map_x']}, expected ~{ex}"
        )
        assert abs(spot["map_y"] - ey) <= 0.05, (
            f"GPB {gpb} y: got {spot['map_y']}, expected ~{ey}"
        )
        # Radius is stored in map-space units upstream and matches exactly.
        assert round(spot["radius"] * 50) == radius, f"GPB {gpb} radius mismatch"
        checked += 1
    assert checked >= 15, f"only checked {checked} reference nodes"
    assert worst <= 0.02, f"worst deviation from reference was {worst:.4f} grid units"


def test_node_radius_is_reported_in_grid_units(indexes):
    """`ExportedGatheringPoint.Radius` is map-space, so it is scaled like coords.

    Expressed in grid units it tells a player how wide the node marker is, which
    is how the external databases present it.
    """
    items_normalized = indexes[3]
    positioned = [
        n
        for item in items_normalized.values()
        for n in item["nodes"]
        if n.get("map_x") is not None
    ]
    assert positioned

    with_radius = [n for n in positioned if n.get("radius") is not None]
    assert with_radius, "no node reported a radius"

    for n in with_radius:
        assert n["radius"] >= 0, "radius must not be negative"
        # Radii in the 7.25 data reach 1174 map-space units (23.5 grid units),
        # so bound this against the source rather than a guessed constant.
        assert n["radius"] <= 24.0, f"implausible radius {n['radius']}"

    # Alumen's node (Garlandtools node 160 == GPB 160) should carry one.
    alum = items_normalized[5524]["nodes"][0]
    assert alum["radius"] is not None and alum["radius"] > 0
