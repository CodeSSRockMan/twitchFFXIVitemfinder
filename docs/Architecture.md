# Twitch Bot Architecture Documentation

This document outlines different architectures for building a Twitch bot that interacts with a local database to handle commands like item lookups from a game (e.g., FFXIV).

> **Note:** The project implements **option 3 (Hybrid)** — the bot and the HTTP
> API run in one process. Options 1 and 2 below are kept for reference.

---

## 1. Single-Process Architecture (Bot + DB)

The bot handles everything: listens to Twitch chat, queries the database, and responds. No web server is used.

**Stack:**
- TwitchIO (or similar Twitch bot framework)
- SQLite or aiosqlite (async)

**Structure:**

- Twitch chat input → TwitchIO bot
- Bot queries SQLite
- Bot sends reply back to Twitch chat

**Example Use Case:**  
User types `!whereis Healing Potion`  
Bot fetches item location from DB and replies in chat.

---

## 2. Dual-Process Architecture (Bot + HTTP API Server)

The Twitch bot and a web API are separate processes. Useful if a web frontend or external integration is needed.

**Stack:**
- TwitchIO for the bot
- FastAPI (or Flask) for the HTTP API
- Shared database (e.g., SQLite, PostgreSQL)

**Structure:**

- Twitch chat input → TwitchIO bot  
- API calls (e.g., `/items/1`) → FastAPI → database  
- Web apps, dashboards, or automation can use the API too

---

## 3. Hybrid Architecture (Bot and API in One Process)

Run both the Twitch bot and the HTTP API in one Python process using asyncio.

**Stack:**
- TwitchIO + FastAPI
- Async database (e.g., aiosqlite)

**Code Example:**

```python
import uvicorn
from fastapi import FastAPI, HTTPException
import asyncio

from src import item_repository

app = FastAPI()

@app.get("/items/{item_id}")
async def get_item(item_id: int):
    item = item_repository.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return {"id": item_id, **item}

@app.get("/items")
async def search_items(q: str, limit: int = 20):
    return {"query": q, "results": item_repository.search_items(q, limit=limit)}

async def main():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, loop="asyncio", lifespan="off")
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())  # non-blocking

    bot = Bot("data.db")
    await bot.start()

asyncio.run(main())
```

**This is the architecture the project actually implements** (see [main.py](../main.py)).
The bot and the HTTP API share one process and one in-process read layer,
`src/item_repository.py`, which loads the normalized dataset once per process.
See [FFXIV Sheets Pipeline](FFXIV_Pipeline.md) for the available endpoints and
for the pipeline that produces the dataset.
