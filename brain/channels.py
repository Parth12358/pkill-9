"""Start every configured audience channel. (PRD B: Channels)

The web plea room is always on (started separately by the server). Discord and
WhatsApp start only when their env is configured, so the brain runs fine with
just the web room. Twitter is the body's job (PRD A), not a channel here.

Each channel feeds incoming messages via plea_room.submit(text, source=...) and
receives ARIA's lines via a sink registered with plea_room.register_sink(...).
"""

from . import discord_bot, whatsapp


def start_all() -> list[str]:
    """Launch configured channels. Returns the list that actually started."""
    started = []
    if discord_bot.start():
        started.append("discord")
    if whatsapp.start():
        started.append("whatsapp")
    return started
