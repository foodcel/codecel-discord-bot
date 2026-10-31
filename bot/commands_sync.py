"""Tells Discord which slash commands this bot has (the board commands only once the bounty board is set up)."""
import hashlib
import json

from .board import is_live
from .commands import BOARD_COMMANDS, COMMANDS
from .ctx import ctx
from .db import kv_get, kv_set
from .env import cfg


async def register_commands():
    """Sends the list only when it changed since the last time: Discord rate limits this call, and restarts are common."""
    payload = COMMANDS + (BOARD_COMMANDS if is_live() else [])
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if kv_get('commands_hash') == digest:
        return
    await ctx.client.http.bulk_upsert_guild_commands(ctx.client.application_id, int(cfg.guild_id), payload)
    kv_set('commands_hash', digest)
