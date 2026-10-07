import os

import pytest

from scripts.import_recipes import build_recipes, summarise
from src import item_repository
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


class TestJobs:
    """CraftType maps to ClassJob + 8; verified against job-specific keywords."""

    def test_recipes_carry_a_job(self):
        recipe = source_factory.load_recipes()[2546][0]
        assert recipe["job"] is not None
        assert recipe["job"]["abbreviation"]
        assert recipe["job"]["job_id"] == recipe["craft_type"] + 8

    def test_single_job_item(self):
        rid = next(i for i, v in source_factory.load_recipes().items()
                   if any(r["item_name"] == "Hempen Yarn" for r in v))
        jobs = source_factory.jobs_for(rid)
        assert [j["abbreviation"] for j in jobs] == ["WVR"]

    def test_multi_job_item_lists_every_job(self):
        """Bronze Ingot is both blacksmith and armorer, so both must appear."""
        rid = next(i for i, v in source_factory.load_recipes().items()
                   if any(r["item_name"] == "Bronze Ingot" for r in v))
        jobs = source_factory.jobs_for(rid)
        abbrs = {j["abbreviation"] for j in jobs}
        assert "BSM" in abbrs and "ARM" in abbrs

    def test_jobs_reply_lists_all(self):
        rid = next(i for i, v in source_factory.load_recipes().items()
                   if any(r["item_name"] == "Bronze Ingot" for r in v))
        reply = item_repository.format_jobs_reply("Bronze Ingot", source_factory.jobs_for(rid))
        assert "BSM" in reply and "ARM" in reply

    def test_jobs_reply_without_recipe(self):
        reply = item_repository.format_jobs_reply("Laurel", [])
        assert "no recipe" in reply


    class TestNameLookup:
        """Names must resolve across both caches.

        Craftable items are absent from the gatherable cache entirely, so searching
        only that cache made `!icraft` and `!ijob` report every item as not found.
        """

        def test_finds_gatherable_by_name(self):
            hits = source_factory.find_by_name("Laurel")
            assert [h["id"] for h in hits] == [4839]

        def test_finds_craftable_by_name(self):
            hits = source_factory.find_by_name("Bronze Hatchet")
            assert len(hits) == 1
            assert source_factory.jobs_for(hits[0]["id"])

        def test_case_insensitive(self):
            assert source_factory.find_by_name("BRONZE INGOT") == source_factory.find_by_name("bronze ingot")

        def test_unknown_name(self):
            assert source_factory.find_by_name("Nonexistent Widget") == []


class TestCraftReply:
    def test_reply_is_ascii_safe(self):
        """Chat output must survive a cp1252 console."""
        rid = next(i for i, v in source_factory.load_recipes().items()
                   if any(r["item_name"] == "Bronze Hatchet" for r in v))
        recipe = source_factory.resolve(rid)["recipes"][0]
        reply = item_repository.format_craft_reply("Bronze Hatchet", recipe)
        reply.encode("ascii")  # raises if any non-ASCII marker slipped in

    def test_reply_groups_materials(self):
        rid = next(i for i, v in source_factory.load_recipes().items()
                   if any(r["item_name"] == "Bronze Hatchet" for r in v))
        recipe = source_factory.resolve(rid)["recipes"][0]
        reply = item_repository.format_craft_reply("Bronze Hatchet", recipe)
        assert "Gathered" in reply and "Crafted" in reply
        assert "Bronze Ingot" in reply

    def test_gathered_materials_are_marked(self):
        rid = next(i for i, v in source_factory.load_recipes().items()
                   if any(r["item_name"] == "Bronze Hatchet" for r in v))
        recipe = source_factory.resolve(rid)["recipes"][0]
        reply = item_repository.format_craft_reply("Bronze Hatchet", recipe)
        gathered = [m for m in recipe["materials"] if m["source"] == "gather"]
        for m in gathered:
            assert m["name"] in reply
