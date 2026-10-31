"""Shared by the scripts: logs in as the bot with a small client (a second session, safe while the bot runs) and
fills in the same shared state the bot uses."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import discord  # noqa: E402

from bot.bounty import refresh_claims  # noqa: E402
from bot.ctx import ctx  # noqa: E402
from bot.env import cfg  # noqa: E402
from bot.tags import load_tags  # noqa: E402


async def boot(members=False, claims=True):
    intents = discord.Intents.none()
    intents.guilds = True
    intents.members = members
    client = discord.Client(intents=intents)
    ctx.client = client
    await client.login(cfg.token)
    asyncio.ensure_future(client.connect())
    await client.wait_until_ready()
    ctx.guild = client.get_guild(int(cfg.guild_id)) or await client.fetch_guild(int(cfg.guild_id))
    await load_tags()
    if claims:
        await refresh_claims()
    return client


async def finish(client):
    await client.close()
