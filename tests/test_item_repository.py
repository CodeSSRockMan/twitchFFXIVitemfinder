import json

import pytest

from src import item_repository

LAUREL_ID = 4839


@pytest.fixture(scope="module")
def items():
    return item_repository.load_items()


def test_dataset_loads_with_integer_keys(items):
    assert len(items) > 1000
    assert all(isinstance(k, int) for k in items)


def test_get_item_returns_record():
    item = item_repository.get_item(LAUREL_ID)
    assert item is not None
    assert item["name"] == "Laurel"


def test_get_item_unknown_returns_none():
    assert item_repository.get_item(999999999) is None


def test_known_coordinate_is_preserved():
    item = item_repository.get_item(LAUREL_ID)
    nodes = item["nodes"]
    # Coordinates come from the node (GatheringPointBase 133) and are reported on
    # the 1..41 in-game map grid, never as raw map-space values.
    assert any(
        n["map_x"] is not None and 1.0 <= n["map_x"] <= 41.0
        and n["map_y"] is not None and 1.0 <= n["map_y"] <= 41.0
        for n in nodes
    )


def test_node_spots_expose_node_coordinates():
    """Items expose the node-level position, the shape external databases use."""
    item = item_repository.get_item(LAUREL_ID)
    spots = item["node_spots"]
    spot = next(s for s in spots if s["gpb_id"] == 133)
    assert spot["place_name"] == "Broken Water"
    assert spot["gathering_level"] == 35
    assert spot["map_x"] is not None and 1.0 <= spot["map_x"] <= 41.0
    assert spot["radius"] is not None and spot["radius"] > 0


def test_search_ranks_exact_match_first():
    results = item_repository.search_items("laurel")
    assert results
    assert results[0]["name"] == "Laurel"
    assert results[0]["id"] == LAUREL_ID


def test_search_limit_is_respected():
    assert len(item_repository.search_items("e", limit=2)) <= 2


def test_search_blank_query_returns_empty():
    assert item_repository.search_items("   ") == []


def test_find_items_by_name_is_exact():
    # "Laurel" must not match "Lover's Laurel"
    assert [m["name"] for m in item_repository.find_items_by_name("Laurel")] == ["Laurel"]


def test_format_chat_reply_lists_places_and_coords():
    item = item_repository.get_item(LAUREL_ID)
    reply = item_repository.format_chat_reply("Laurel", item)
    assert "Laurel" in reply
    assert "Broken Water" in reply
    assert "X:" in reply


def test_format_chat_reply_when_no_nodes():
    reply = item_repository.format_chat_reply("Ghost", {"name": "Ghost", "nodes": []})
    assert "no gathering data" in reply


def test_summarize_reports_has_coords():
    summary = item_repository.summarize_item(LAUREL_ID, item_repository.get_item(LAUREL_ID))
    assert summary == {
        "id": LAUREL_ID,
        "name": "Laurel",
        "node_count": 4,
        "has_coords": True,
    }


def test_missing_dataset_raises(tmp_path):
    with pytest.raises(item_repository.DatasetNotFoundError):
        item_repository.load_items(str(tmp_path / "missing.json"))


def test_loads_from_explicit_path(tmp_path, items):
    target = tmp_path / "subset.json"
    target.write_text(json.dumps({"4839": items[LAUREL_ID]}), encoding="utf-8")
    loaded = item_repository.load_items(str(target))
    assert list(loaded) == [LAUREL_ID]
