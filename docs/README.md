# FFXIV Item Location Database Schema

This document describes the JSON schema and folder structure for the Twitch Bot project, which stores expansions, cities, locations, NPCs, items, crafting recipes, and item sourcing information for Final Fantasy XIV.

See [FFXIV Sheets Pipeline](docs/FFXIV_Pipeline.md) for the CSV/EXD importer, normalization, and submodule integration.

---

## Folder Structure

- `src/` - Source code and database utilities
- `tests/` - Test files
- `docs/` - Documentation files
- `.venv/` - Virtual environment
- `requirements.txt` - Python dependencies

---

## Schema Overview

### 1. `expansions`
Game expansions where items and locations belong.

| Field         | Type    | Description                     |
|---------------|---------|---------------------------------|
| `id`          | Integer | Unique ID                      |
| `name`        | String  | Expansion name                 |
| `release_date`| String  | Release date (YYYY-MM-DD)      |
| `description` | String  | Brief description              |
| `version`     | String  | Game version or patch number   |

---

### 2. `cities`
Main cities within the game world.

| Field         | Type    | Description                     |
|---------------|---------|---------------------------------|
| `id`          | Integer | Unique ID                      |
| `name`        | String  | City name                     |
| `region`      | String  | Region or continent            |
| `coordinates` | Object  | Coordinates `{x, y}` on map    |
| `description` | String  | Brief description              |

---

### 3. `locations`
Zones, dungeons, raids, or other areas.

| Field         | Type    | Description                     |
|---------------|---------|---------------------------------|
| `id`          | Integer | Unique ID                      |
| `name`        | String  | Location name                 |
| `type`        | String  | Type (Zone, Dungeon, Raid, etc)|
| `region`      | String  | Region or continent            |
| `coordinates` | Object  | Coordinates `{x, y}` on map    |
| `description` | String  | Brief description              |

---

### 4. `npcs`
Non-player characters: vendors, mobs, quest givers.

| Field         | Type    | Description                     |
|---------------|---------|---------------------------------|
| `id`          | Integer | Unique ID                      |
| `name`        | String  | NPC name                      |
| `type`        | String  | Vendor, Mob, QuestGiver, etc. |
| `location_id` | Integer | Link to `locations` or `cities`|
| `coordinates` | Object  | Coordinates `{x, y}` on map    |
| `description` | String  | Brief description              |

---

### 5. `items`
In-game items.

| Field            | Type    | Description                    |
|------------------|---------|--------------------------------|
| `id`             | Integer | Unique ID                     |
| `name`           | String  | Item name                    |
| `description`    | String  | Item description             |
| `expansion_id`   | Integer | Link to `expansions`          |
| `item_type`      | String  | Weapon, Consumable, Material, etc.|
| `rarity`         | String  | Common, Rare, Legendary, etc. |
| `level_requirement` | Integer | Required level to use         |
| `icon_url`       | String  | URL to item icon image       |

---

### 6. `item_sources`
Multiple ways to obtain an item.

| Field         | Type    | Description                             |
|---------------|---------|-----------------------------------------|
| `id`          | Integer | Unique ID                              |
| `item_id`     | Integer | Link to `items`                        |
| `source_type` | String  | Drop, Vendor, Quest, Crafted, Gathered|
| `source_id`   | Integer | Link to `npcs` or quests (nullable)   |
| `location_id` | Integer | Link to `locations` (nullable)        |
| `details`     | String  | Additional info (e.g. drop chance)     |

---

### 7. `recipes`
Crafting recipes for items.

| Field           | Type    | Description                      |
|-----------------|---------|---------------------------------|
| `id`            | Integer | Unique ID                      |
| `item_id`       | Integer | Crafted item ID                |
| `job`           | String  | Crafting job name              |
| `required_level`| Integer | Required crafting level        |

---

### 8. `recipe_ingredients`
Ingredients needed per recipe.

| Field             | Type    | Description                       |
|-------------------|---------|----------------------------------|
| `recipe_id`       | Integer | Link to `recipes`                |
| `ingredient_item_id` | Integer | Link to `items` as ingredient  |
| `quantity`        | Integer | Quantity required               |
| `method`          | String  | Crafted, Gathered, Drop, Vendor |

---

### 9. `jobs`
Which jobs can gather or craft an item.

| Field           | Type    | Description                      |
|-----------------|---------|---------------------------------|
| `item_id`       | Integer | Link to `items`                 |
| `job`           | String  | Job name (e.g., Miner, Alchemist) |
| `gathering_level` | Integer | Level required for gathering/crafting |

---

### 10. `aetherytes`
Teleport points in the game world.

| Field         | Type    | Description                      |
|---------------|---------|---------------------------------|
| `id`          | Integer | Unique ID                      |
| `name`        | String  | Aetheryte name                |
| `location_id` | Integer | Linked location or city       |
| `coordinates` | Object  | Coordinates `{x, y}` on map    |
| `description` | String  | Brief description              |

---

### 11. `cardinal_directions`
Standard compass directions.

| Field | Type   | Description  |
|-------|--------|--------------|
| `code`| String | Direction code (N, NE, E, etc.)|
| `name`| String | Direction full name            |

---

### 12. `item_locations`
Links items to locations, including aetheryte and direction.

| Field              | Type    | Description                        |
|--------------------|---------|-----------------------------------|
| `item_id`          | Integer | Link to `items`                  |
| `location_id`      | Integer | Link to `locations`              |
| `aetheryte_id`     | Integer | Link to `aetherytes`             |
| `cardinal_direction`| String  | Rough direction from aetheryte  |
| `details`          | String  | Additional guidance info         |

---

# Usage Notes

- Items can have **multiple sources** (vendors, drops, crafted, gathered).
- Crafting recipes are **recursive** via `recipe_ingredients`, allowing ingredients to themselves be crafted or gathered.
- NPCs link to locations and represent vendors, mobs, or quest givers.
- Cardinal directions and aetherytes assist with navigation hints.
- This schema is designed to scale and evolve as you add more data.

---
