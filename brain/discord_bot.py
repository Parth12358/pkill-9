"""Discord channel for the plea room. (PRD B: Channels — optional)

One approved channel: audience messages there feed the loop; ARIA's lines post
back. Behind env, so the brain runs fine without it.

  DISCORD_BOT_TOKEN   bot token (dev portal; enable the Message Content intent)
  DISCORD_CHANNEL_ID  the one channel id it reads/writes

The `discord` package is imported lazily so this module loads even if it isn't
installed. Runs its own asyncio loop in a background thread; the outgoing sink
hands lines to that loop thread-safely.
"""

import asyncio
import os
import threading

from . import plea_room


def is_configured() -> bool:
    return bool(os.environ.get("DISCORD_BOT_TOKEN") and os.environ.get("DISCORD_CHANNEL_ID"))


def start() -> bool:
    """Start the Discord bot in a background thread. Returns True if launched."""
    if not is_configured():
        return False
    try:
        import discord  # lazy: no hard dependency unless Discord is used
    except ImportError:
        print("[discord] discord.py not installed — skipping (pip install discord.py)")
        return False

    token = os.environ["DISCORD_BOT_TOKEN"]
    channel_id = int(os.environ["DISCORD_CHANNEL_ID"])

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    loop_holder = {}

    @client.event
    async def on_ready():
        loop_holder["loop"] = asyncio.get_running_loop()
        print(f"[discord] connected as {client.user}, watching channel {channel_id}")

    @client.event
    async def on_message(message):
        if message.author == client.user or message.channel.id != channel_id:
            return
        plea_room.submit(message.content, source="discord")

    async def _send(text: str):
        ch = client.get_channel(channel_id)
        if ch is not None:
            await ch.send(text[:1900])

    def sink(text: str):
        loop = loop_holder.get("loop")
        if loop is not None:
            asyncio.run_coroutine_threadsafe(_send(text), loop)

    plea_room.register_sink(sink)

    def _run():
        client.run(token, log_handler=None)

    threading.Thread(target=_run, daemon=True, name="discord-bot").start()
    return True
