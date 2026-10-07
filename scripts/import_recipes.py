"""Build the crafting dataset from Recipe.csv.

This is the second source type behind the factory in `build_sources.py`. It is
kept separate from `import_datamining.py`, which stays scoped to gatherables,
so each importer owns one family of CSVs and produces one cache.

Recipes are recursive: 68% of them use at least one material that is itself
craftable, to a maximum depth of 3 in the 7.25 data. Each recipe therefore
records how its materials are obtained, and `has_recursive_material` marks the
recipes that need a tree walk rather than a flat list. The tree itself is
resolved on demand later, so it is not stored here.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from collections import defaultdict
from typing import Dict, Iterable, List, Optional

LOG = logging.getLogger("import_recipes")

MATERIAL_SLOTS = 8


def _safe_int(s: str) -> int:
    try:
        return int(s)
    except Exception:
        return 0


def _read_csv(path: str) -> Iterable[Dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh)


def build_recipes(src_dir: str) -> Dict[int, List[Dict]]:
    """Return item_id -> list of recipes, with each material classified.

    A material is classified as `gather` when it is a gathering item, `craft`
    when it has a recipe of its own, and `other` otherwise. Nothing is expanded
    into a tree here: `craft` simply tells the caller it must recurse.
    """
    recipe_path = os.path.join(src_dir, "Recipe.csv")
    item_path = os.path.join(src_dir, "Item.csv")
    gathering_item_path = os.path.join(src_dir, "GatheringItem.csv")

    names: Dict[int, str] = {}
    for row in _read_csv(item_path):
        iid = _safe_int(row.get("#", "0"))
        if iid:
            names[iid] = row.get("Name", "") or ""

    gathering_items = set()
    for row in _read_csv(gathering_item_path):
        iid = _safe_int(row.get("Item", "0"))
        if iid:
            gathering_items.add(iid)

    recipes_by_result: Dict[int, List[Dict]] = defaultdict(list)
    for row in _read_csv(recipe_path):
        result = _safe_int(row.get("ItemResult", "0"))
        if not result:
            continue
        materials = []
        for i in range(MATERIAL_SLOTS):
            mat = _safe_int(row.get("Ingredient[%d]" % i))
            if mat <= 0:  # 0 = empty slot, -1 = sentinel
                continue
            amount = _safe_int(row.get("AmountIngredient[%d]" % i)) or 1
            materials.append({
                "item_id": mat,
                "name": names.get(mat, ""),
                "amount": amount,
                "source": "other",  # resolved below, once all recipes are known
            })
        recipes_by_result[result].append({
            "recipe_id": _safe_int(row.get("#", "0")),
            "item_id": result,
            "item_name": names.get(result, ""),
            "craft_type": _safe_int(row.get("CraftType", "0")) or None,
            "required_quality": _safe_int(row.get("RequiredQuality", "0")) or None,
            "amount_result": _safe_int(row.get("AmountResult", "0")) or 1,
            "is_expert": (row.get("IsExpert") or "").strip().lower() in ("1", "true"),
            "from_recipe_notebook": bool(_safe_int(row.get("RecipeNotebookList", "0"))),
            "from_master_book": bool(_safe_int(row.get("SecretRecipeBook", "0"))),
            "quest_required": _safe_int(row.get("Quest", "0")) or None,
            "materials": materials,
            # Set below: a material that must itself be crafted.
            "has_recursive_material": False,
        })

    craftable = set(recipes_by_result)

    def classify(item_id: int) -> str:
        if item_id in gathering_items:
            return "gather"
        if item_id in craftable:
            return "craft"
        return "other"

    for result, recipes in recipes_by_result.items():
        for recipe in recipes:
            for mat in recipe["materials"]:
                mat["source"] = classify(mat["item_id"])
            recipe["has_recursive_material"] = any(
                m["source"] == "craft" for m in recipe["materials"]
            )

    return dict(recipes_by_result)


def summarise(recipes: Dict[int, List[Dict]]) -> Dict[str, int]:
    total = sum(len(v) for v in recipes.values())
    recursive = sum(
        1 for rs in recipes.values() for r in rs if r["has_recursive_material"]
    )
    return {
        "items_with_recipes": len(recipes),
        "recipes_total": total,
        "recipes_with_recursive_material": recursive,
        "recipes_flat": total - recursive,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Import Recipe.csv into a crafting cache")
    p.add_argument("--src", default=os.path.join("vendor", "ffxiv-datamining", "csv", "en"))
    p.add_argument("--out", default=os.path.join("data", "recipes"))
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    LOG.info("Building recipes from %s", args.src)
    recipes = build_recipes(args.src)

    os.makedirs(args.out, exist_ok=True)
    target = os.path.join(args.out, "recipes.json")
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(recipes, fh)

    stats = summarise(recipes)
    LOG.info("Wrote %s", target)
    for key, value in stats.items():
        LOG.info("  %-34s %d", key, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
