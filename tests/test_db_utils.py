import json
import sqlite3

import pytest

from src import db_utils


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point db_utils at a throwaway SQLite database."""
    db_path = tmp_path / "data.db"
    json_path = tmp_path / "data.json"
    json_path.write_text(
        json.dumps(
            {
                "expansions": [{"id": 1, "name": "A Realm Reborn"}],
                "cities": [{"id": 10, "name": "Limsa Lominsa"}],
                "items": [{"id": 4839, "name": "Laurel", "description": "A fragrant herb."}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(db_utils, "DB_PATH", str(db_path))
    monkeypatch.setattr(db_utils, "JSON_PATH", str(json_path))
    db_utils.init_db()
    db_utils.load_json_to_db()
    return db_path


def test_init_db_creates_tables(temp_db):
    conn = sqlite3.connect(str(temp_db))
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"expansions", "cities", "items"} <= names


def test_load_json_populates_items(temp_db):
    assert (4839, "Laurel", "A fragrant herb.") in db_utils.get_items()


def test_load_json_populates_expansions_and_cities(temp_db):
    assert (1, "A Realm Reborn") in db_utils.get_expansions()
    assert (10, "Limsa Lominsa") in db_utils.get_cities()


def test_get_item_by_name_is_case_insensitive(temp_db):
    assert db_utils.get_item_by_name("laurel") == "Item found: Laurel - A fragrant herb."


def test_get_item_by_name_unknown_returns_none(temp_db):
    assert db_utils.get_item_by_name("Nonexistent Herb") is None
