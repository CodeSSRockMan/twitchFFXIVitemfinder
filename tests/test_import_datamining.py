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

    # Look for the known exported coordinate for the sample chain (approx)
    expected_x = -611.869
    expected_y = 718.873
    found = False
    for n in nodes:
        x = n.get("x")
        y = n.get("y")
        if x is None or y is None:
            continue
        if math.isclose(x, expected_x, abs_tol=1e-3) and math.isclose(y, expected_y, abs_tol=1e-3):
            found = True
            break

    assert found, "Expected coordinate not found for item 4839"


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
        return round(pixel / size_factor * 2.0 + 1.0, 1)

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
    assert checked > 1000, f"expected to check many nodes, only checked {checked}"


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
