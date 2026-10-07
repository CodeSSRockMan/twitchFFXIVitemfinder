"""Resolve each item to its acquisition source, in priority order.

Items reach the app through more than one route: gathered from the world,
crafted from materials, bought from a vendor. The importers produce one cache
per source and this module joins them into a single view, applying a fixed
priority so an item always reports the same way.

Current priority:

    1. gather  a node with map coordinates is the most precise answer
    2. craft   a recipe, whose materials are themselves resolved on demand
    3. unknown no source is available in the data

Gatherable sits above craft because a located node is a direct answer, while a
recipe only says what to make and still leaves the materials to be found.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS_PATH = os.path.join(REPO_ROOT, "data", "normalized", "items_normalized.json")
RECIPES_PATH = os.path.join(REPO_ROOT, "data", "recipes", "recipes.json")

# Lower number wins when an item has more than one source.
SOURCE_PRIORITY = {"gather": 0, "craft": 1}

_lock = threading.Lock()
_items_cache: Optional[Dict[int, Dict[str, Any]]] = None
_recipes_cache: Optional[Dict[int, List[Dict]]] = None


class DatasetNotFoundError(RuntimeError):
    """Raised when a required cache file is missing."""


def _load(path: str, label: str) -> Any:
    if not os.path.exists(path):
        raise DatasetNotFoundError(
            f"{label} cache not found at {path}. "
            f"Generate it with: python scripts/{label}.py"
        )
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_items() -> Dict[int, Dict[str, Any]]:
    global _items_cache
    with _lock:
        if _items_cache is None:
            raw = _load(ITEMS_PATH, "import_datamining")
            _items_cache = {}
            for key, value in raw.items():
                try:
                    _items_cache[int(key)] = value
                except (TypeError, ValueError):
                    continue
        return _items_cache


def load_recipes() -> Dict[int, List[Dict]]:
    global _recipes_cache
    with _lock:
        if _recipes_cache is None:
            raw = _load(RECIPES_PATH, "import_recipes")
            _recipes_cache = {int(k): v for k, v in raw.items()}
        return _recipes_cache


def has_gathering(item_id: int) -> bool:
    item = load_items().get(int(item_id))
    return bool(item and item.get("node_spots"))


def has_recipe(item_id: int) -> bool:
    return bool(load_recipes().get(int(item_id)))


def classify(item_id: int) -> str:
    """Return the winning source for an item: gather, craft, or unknown."""
    item_id = int(item_id)
    if has_gathering(item_id):
        return "gather"
    if has_recipe(item_id):
        return "craft"
    return "unknown"


def resolve(item_id: int) -> Dict[str, Any]:
    """Return the full record for an item with its source resolved.

    The record always carries every source the item has, plus `source`, the
    winner. Nothing is discarded, so a caller can still ask for a lower-priority
    route explicitly.
    """
    item_id = int(item_id)
    item = load_items().get(item_id)
    recipes = load_recipes().get(item_id) or []

    if item is None and not recipes:
        raise KeyError(item_id)

    sources: List[str] = []
    if item and item.get("node_spots"):
        sources.append("gather")
    if recipes:
        sources.append("craft")

    return {
        "id": item_id,
        "name": (item or {}).get("name") or (recipes[0].get("item_name") if recipes else ""),
        "source": min(sources, key=lambda s: SOURCE_PRIORITY[s]) if sources else "unknown",
        "sources": sources,
        "nodes": (item or {}).get("nodes", []),
        "node_spots": (item or {}).get("node_spots", []),
        "recipes": recipes,
        "has_recursive_material": any(r.get("has_recursive_material") for r in recipes),
    }
