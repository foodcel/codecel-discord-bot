"""Tells Discord which slash commands this bot has (the board commands only once the bounty board is set up)."""
import hashlib
import json

from bot.features.games.board import is_live
from bot.discord_ui.commands import BOARD_COMMANDS, COMMANDS
from bot.core.ctx import ctx
from bot.core.db import kv_get, kv_set
from bot.core.env import cfg


# Who sees a command in the picker is NOT decided here: a permission bit breaks when someone edits a role. The dev and admin commands are hidden by role with
# Discord's per-command rules (Integrations), set with scripts/lock_commands.py. A new dev or admin command is open to everyone in the picker until it is added to
# that script and the script is run again (the bot still refuses people who may not use it).


async def register_commands():
    """Sends the list only when it changed since the last time: Discord rate limits this call, and restarts are common."""
    payload = COMMANDS + (BOARD_COMMANDS if is_live() else [])
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if kv_get('commands_hash') == digest:
        return
    await ctx.client.http.bulk_upsert_guild_commands(ctx.client.application_id, int(cfg.guild_id), payload)
    kv_set('commands_hash', digest)
