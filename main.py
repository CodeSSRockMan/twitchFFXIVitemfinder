import asyncio
import json
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from twitchio.ext import commands
from src import item_repository
from src import source_factory


def _lookup(item_name: str):
    """Resolve a chat name to a single item id.

    Returns the id, or one of the sentinels below so callers can build a reply.
    Search spans both source caches so craftable items are found.
    """
    try:
        matches = item_repository.find_items_by_name(item_name)
    except item_repository.DatasetNotFoundError:
        matches = []
    if not matches:
        try:
            matches = source_factory.find_by_name(item_name)
        except source_factory.DatasetNotFoundError:
            return "error"
    if not matches:
        return "missing"
    if len(matches) > 1:
        return "ambiguous"
    return matches[0]["id"]


def _display_name(item_id: int, fallback: str) -> str:
    item = item_repository.load_items().get(item_id)
    if item and item.get("name"):
        return item["name"]
    recipes = source_factory.load_recipes().get(item_id) or []
    return recipes[0].get("item_name") if recipes else fallback


def _lookup_error(item_name: str, result) -> str:
    if result == "missing":
        return f"[Not found] No item named '{item_name}' was found."
    if result == "ambiguous":
        return f"[Ambiguous] '{item_name}' matched several items. Try the item id instead."
    return "[Error] Item data is unavailable."

app = FastAPI(
    title="FFXIV Item Finder API",
    description="Item and gathering-location data built from the ffxiv-datamining submodule.",
    version="1.0.0",
)

@app.get("/items/{item_id}")
async def get_item(item_id: int):
    """Full record for one item, including every known gathering node."""
    item = item_repository.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return {"id": item_id, **item}

@app.get("/items")
async def search_items(
    q: str = Query(..., min_length=1, description="Case-insensitive item name query"),
    limit: int = Query(20, ge=1, le=200),
):
    """Search items by name. Exact matches rank first."""
    results = item_repository.search_items(q, limit=limit)
    return {"query": q, "count": len(results), "results": results}

def get_secrets():
    try:
        token = os.environ["TWITCH_OAUTH_TOKEN"]
        bot_nick = os.environ["TWITCH_BOT_NICK"]
        channel = os.environ["TWITCH_CHANNEL"]
        prefix = os.environ.get("TWITCH_PREFIX", "f!?")
        return token, bot_nick, channel, prefix
    except KeyError:
        try:
            with open("secrets.json", "r", encoding="utf-8") as f:
                secrets = json.load(f)
            token = secrets["twitch_token"]
            bot_nick = secrets["bot_nick"]
            channel = secrets["channel"]
            prefix = secrets.get("prefix", "f!?")
            return token, bot_nick, channel, prefix
        except Exception as exc:
            raise SystemExit(f"Missing required credentials: {exc}") from None

TOKEN, BOT_NICK, CHANNEL, PREFIX = get_secrets()

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            token=TOKEN,
            prefix=PREFIX,
            initial_channels=[CHANNEL],
            nick=BOT_NICK
        )

    async def event_ready(self):
        print(f"Logged in as | {self.nick}")

    async def event_message(self, message):
        if message.echo:
            return
        await self.handle_commands(message)

    @commands.command(name="isearch")
    async def isearch(self, ctx: commands.Context, *, item_name: str = None):
        if not item_name:
            await ctx.send("Debes especificar el nombre del item. Ejemplo: !isearch Laurel")
            return
        match = _lookup(item_name)
        if match is None:
            await ctx.send(f"[Not found] No item named '{item_name}' was found.")
            return
        if match == "ambiguous":
            await ctx.send(f"[Ambiguous] '{item_name}' matched several items. Try the item id instead.")
            return
        if match == "error":
            await ctx.send("[Error] Item data is unavailable.")
            return
        item = item_repository.get_item(match)
        await ctx.send(item_repository.format_chat_reply(item["name"], item))

    @commands.command(name="icraft")
    async def icraft(self, ctx: commands.Context, *, item_name: str = None):
        """List the materials needed for a recipe."""
        if not item_name:
            await ctx.send("Debes especificar el nombre del item. Ejemplo: !icraft Bronze Hatchet")
            return
        match = _lookup(item_name)
        if not isinstance(match, int):
            await ctx.send(_lookup_error(item_name, match))
            return
        record = source_factory.resolve(match)
        if not record["recipes"]:
            await ctx.send(f"[Craft] {record['name']} has no recipe; use !isearch to find it.")
            return
        await ctx.send(item_repository.format_craft_reply(record["name"], record["recipes"][0]))

    @commands.command(name="ijob")
    async def ijob(self, ctx: commands.Context, *, item_name: str = None):
        """List the crafting jobs that can make an item."""
        if not item_name:
            await ctx.send("Debes especificar el nombre del item. Ejemplo: !ijob Bronze Ingot")
            return
        match = _lookup(item_name)
        if not isinstance(match, int):
            await ctx.send(_lookup_error(item_name, match))
            return
        name = _display_name(match, item_name)
        await ctx.send(item_repository.format_jobs_reply(name, source_factory.jobs_for(match)))

async def main():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, loop="asyncio", lifespan="off")
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())  # non-blocking

    bot = Bot()
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())
