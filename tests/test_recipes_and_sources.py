import os

import pytest

from scripts.import_recipes import build_recipes, summarise
from src import source_factory


@pytest.fixture(scope="module")
def recipes():
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor", "ffxiv-datamining", "csv", "en"))
    return build_recipes(src)


def test_recipes_are_built(recipes):
    stats = summarise(recipes)
    assert stats["items_with_recipes"] > 10000
    assert stats["recipes_total"] > 10000


def test_materials_are_classified(recipes):
    """Each material must be marked gather, craft, or other."""
    seen = set()
    for item_recipes in recipes.values():
        for r in item_recipes:
            for m in r["materials"]:
                seen.add(m["source"])
                assert m["source"] in {"gather", "craft", "other"}
                assert m["name"] or m["item_id"]
    assert seen  # at least one material was classified


def test_recursive_flag_matches_materials(recipes):
    """`has_recursive_material` must be true exactly when a material is craftable."""
    checked = 0
    for item_recipes in recipes.values():
        for r in item_recipes:
            expected = any(m["source"] == "craft" for m in r["materials"])
            assert r["has_recursive_material"] is expected
            checked += 1
    assert checked > 10000


def test_a_known_recipe_is_flat(recipes):
    """Bronze Ingot is made from ores and shards, so it needs no further craft."""
    ingots = recipes.get(5056)
    assert ingots, "Bronze Ingot (5056) should have a recipe"
    assert ingots[0]["has_recursive_material"] is False


def test_a_known_recipe_is_recursive(recipes):
    """Bronze Hatchet needs Bronze Ingot and Maple Lumber, both crafted."""
    hatchets = recipes.get(2546)
    assert hatchets, "Bronze Hatchet (2546) should have a recipe"
    r = hatchets[0]
    assert r["has_recursive_material"] is True
    craft_mats = [m["name"] for m in r["materials"] if m["source"] == "craft"]
    assert "Bronze Ingot" in craft_mats


def test_negative_sentinels_are_dropped(recipes):
    """Ingredient -1 is an empty-slot sentinel, not a real material."""
    for item_recipes in recipes.values():
        for r in item_recipes:
            for m in r["materials"]:
                assert m["item_id"] > 0
                assert m["amount"] >= 1


class TestSourceFactory:
    def test_gatherable_wins(self):
        assert source_factory.classify(5114) == "gather"   # Mythril Ore
        assert source_factory.classify(4839) == "gather"   # Laurel

    def test_craftable_without_nodes(self):
        assert source_factory.classify(2546) == "craft"    # Bronze Hatchet

    def test_unknown_item(self):
        assert source_factory.classify(999999999) == "unknown"

    def test_resolve_exposes_every_source(self):
        record = source_factory.resolve(5114)
        assert record["source"] == "gather"
        assert record["sources"] == ["gather"]
        assert record["node_spots"]
        assert record["node_spots"][0]["map_x"] is not None

    def test_resolve_craft_only(self):
        record = source_factory.resolve(2546)
        assert record["source"] == "craft"
        assert record["sources"] == ["craft"]
        assert record["recipes"]
        assert record["has_recursive_material"] is True

    def test_resolve_unknown_raises(self):
        with pytest.raises(KeyError):
            source_factory.resolve(999999999)


def test_priority_order_is_documented():
    """Gatherable must outrank craft, since a node is a direct answer."""
    assert source_factory.SOURCE_PRIORITY["gather"] < source_factory.SOURCE_PRIORITY["craft"]


def test_craft_tree_terminates_at_gatherables():
    """Walking a recursive recipe must bottom out at gatherable materials."""
    def walk(item_id, depth=0, seen=frozenset()):
        assert item_id not in seen, "cycle in recipe tree"
        assert depth < 6, "recipe tree deeper than expected"
        seen = seen | {item_id}
        item = source_factory.load_items().get(item_id) or {}
        if any(s.get("map_x") is not None for s in item.get("node_spots", [])):
            return
        for r in source_factory.load_recipes().get(item_id, []):
            for m in r["materials"]:
                assert m["source"] in {"gather", "craft", "other"}
                if m["source"] == "craft":
                    walk(m["item_id"], depth + 1, seen)

    walk(2546)
