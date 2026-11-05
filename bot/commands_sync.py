"""Tells Discord which slash commands this bot has (the board commands only once the bounty board is set up)."""
import hashlib
import json

from .board import is_live
from .commands import BOARD_COMMANDS, COMMANDS
from .ctx import ctx
from .db import kv_get, kv_set
from .env import cfg


# Who sees a command in the picker. Discord hides it from everyone without the permission (admins always see it). The bot still checks the role when it is run.
ADMIN = '8'                     # Administrator
MANAGE_EVENTS = str(1 << 33)  # the Giveaway Manager role gets this permission to see /giveaway (admins always do)
DEV = str(1 << 10)              # View Channels: the Developers role has it on the role itself (it cannot lose it without losing the server), Tester, Helpers and @everyone do not. Pin Messages was used first and broke when it was taken off the role.
LOCKED = {'giveaway': MANAGE_EVENTS, **{n: ADMIN for n in ('mog', 'Mog', 'preview', 'botrules', 'games', 'bounty-board', 'assign', 'exclude', 'include')},
          **{n: DEV for n in ('config', 'update', 'strikes', 'pardon', 'pings', 'release', 'unrelease', 'gamelink', 'progress', 'claim', 'unclaim')}}


def locked(commands):
    return [{**c, 'default_member_permissions': LOCKED[c['name']]} if c['name'] in LOCKED else c for c in commands]


async def register_commands():
    """Sends the list only when it changed since the last time: Discord rate limits this call, and restarts are common."""
    payload = locked(COMMANDS + (BOARD_COMMANDS if is_live() else []))
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if kv_get('commands_hash') == digest:
        return
    await ctx.client.http.bulk_upsert_guild_commands(ctx.client.application_id, int(cfg.guild_id), payload)
    kv_set('commands_hash', digest)
