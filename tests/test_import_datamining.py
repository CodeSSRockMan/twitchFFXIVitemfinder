import os
import math

from scripts.import_datamining import build_indexes


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
