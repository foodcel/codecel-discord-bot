"""How many server boosts each member has given, read from the boosters channel (Discord posts a message there for every boost, and the number of
boosts when someone boosts several times at once). Discord does not give a bot this number any other way.
A member who boosts now (member.premium_since) counts at least 1 even when the channel has no message for them (a boost from before the channel,
or a deleted message). The numbers are kept for a few minutes: a giveaway asks for every entrant."""
import asyncio
import time

import discord

from .ctx import ctx, fetch_channel
from .env import cfg

KINDS = {discord.MessageType.premium_guild_subscription, discord.MessageType.premium_guild_tier_1,
         discord.MessageType.premium_guild_tier_2, discord.MessageType.premium_guild_tier_3}
_counts, _at = {}, 0.0
_lock = asyncio.Lock()
_task = None


def refresh_soon():
    """For buttons: the numbers are read again in the background when they are older than 5 minutes; the button uses what is known now."""
    global _task
    if time.time() - _at >= 300 and (_task is None or _task.done()):
        _task = asyncio.ensure_future(_safe_refresh())


async def _safe_refresh():
    try:
        await refresh()
    except Exception as e:
        print('boosts refresh', repr(e)[:120])


async def refresh(force=False):
    """Reads the whole channel again (it only holds boost messages and a few chats, so it is small). One read at a time."""
    async with _lock:
        await _refresh(force)


async def _refresh(force=False):
    global _counts, _at
    if not force and time.time() - _at < 300:
        return
    ch = await fetch_channel(cfg.boosters_id) or ctx.guild.system_channel
    if not ch:
        return
    counts = {}
    async for msg in ch.history(limit=None):
        if msg.type in KINDS:
            n = int((msg.content or '').strip()) if (msg.content or '').strip().isdigit() else 1
            counts[msg.author.id] = counts.get(msg.author.id, 0) + n
    _counts, _at = counts, time.time()


def boosting(member):
    """Still boosting: they hold the Server Booster role (Discord takes it away when the last boost ends)."""
    role = ctx.guild.premium_subscriber_role
    return bool(role and role in member.roles) if role else bool(getattr(member, 'premium_since', None))


def count(member):
    """The boosts a member has now: 0 when they no longer have the Server Booster role, else what the channel says (at least 1)."""
    if not boosting(member):
        return 0
    return max(1, _counts.get(member.id, 0))
