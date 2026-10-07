import asyncio
import json
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from twitchio.ext import commands
from src import item_repository

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
            try:
                matches = item_repository.find_items_by_name(item_name)
            except item_repository.DatasetNotFoundError as exc:
                await ctx.send(f"[Error] {exc}")
                return

            if not matches:
                await ctx.send(f"[Not found] No item named '{item_name}' was found.")
                return
            if len(matches) > 1:
                names = ", ".join(m["name"] for m in matches[:5])
                await ctx.send(f"[Ambiguous] '{item_name}' matched: {names}. Try the item id instead.")
                return

            match = matches[0]
            item = item_repository.get_item(match["id"])
            await ctx.send(item_repository.format_chat_reply(item["name"], item))

async def main():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, loop="asyncio", lifespan="off")
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())  # non-blocking

    bot = Bot()
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())
