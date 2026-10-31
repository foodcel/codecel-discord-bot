"""Tells Discord which slash commands this bot has (the board commands only once the bounty board is set up)."""
from .board import is_live
from .commands import BOARD_COMMANDS, COMMANDS
from .ctx import ctx
from .env import cfg


async def register_commands():
    payload = COMMANDS + (BOARD_COMMANDS if is_live() else [])
    await ctx.client.http.bulk_upsert_guild_commands(ctx.client.application_id, int(cfg.guild_id), payload)
