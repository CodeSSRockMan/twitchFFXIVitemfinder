import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data.db')
JSON_PATH = os.path.join(os.path.dirname(__file__), 'data.json')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS expansions (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS cities (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT
    )''')
    conn.commit()
    conn.close()

def load_json_to_db():
    with open(JSON_PATH, 'r') as f:
        data = json.load(f)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Insert expansions
    for exp in data.get('expansions', []):
        c.execute('INSERT OR IGNORE INTO expansions (id, name) VALUES (?, ?)', (exp['id'], exp['name']))
    # Insert cities
    for city in data.get('cities', []):
        c.execute('INSERT OR IGNORE INTO cities (id, name) VALUES (?, ?)', (city['id'], city['name']))
    # Insert items
    for item in data.get('items', []):
        c.execute('INSERT OR IGNORE INTO items (id, name, description) VALUES (?, ?, ?)', (item['id'], item['name'], item['description']))
    conn.commit()
    conn.close()

def get_expansions():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM expansions')
    result = c.fetchall()
    conn.close()
    return result

def get_cities():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM cities')
    result = c.fetchall()
    conn.close()
    return result

def get_items():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM items')
    result = c.fetchall()
    conn.close()
    return result

def get_item_by_name(item_name: str):
    """
    Search for an item by name (case-insensitive) in the items table.
    Returns a formatted message if found, else None.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT name, description FROM items WHERE LOWER(name) = LOWER(?)', (item_name,))
    row = c.fetchone()
    conn.close()
    if row:
        name, description = row
        return f"Item found: {name} - {description}"
    else:
        return None

if __name__ == "__main__":
    init_db()
    load_json_to_db()
    print("Expansions:", get_expansions())
    print("Cities:", get_cities())
    print("Items:", get_items())
