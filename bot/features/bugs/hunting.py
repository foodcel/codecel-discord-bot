"""Bug hunting: replying `!bug` or `!improve` to a message makes a post in the forum for the player who wrote it.
The limit: when 5 of the posts someone saved were false (a dev marked them Not a bug, or an idea Declined), they lose the command and an admin is asked to talk to them."""
import discord

from bot.discord_ui.components import NO_MENTIONS
from bot.core.ctx import fetch_channel
from bot.core.db import kv_del, kv_get, kv_set, now, one
from bot.core.env import cfg

LIMIT = 5


def false_count(user_id):
    """The posts this person saved with bug hunting that a dev marked Not a bug or Declined, since an admin last cleared them."""
    since = int(kv_get(f'hunt_reset:{user_id}') or 0)
    row = one("SELECT COUNT(*) n FROM bugs WHERE saved_by=? AND status IN ('not_a_bug','declined') AND created_at>?", str(user_id), since)
    return row['n'] if row else 0


def blocked(user_id):
    return bool(kv_get(f'hunt_block:{user_id}'))


async def check(user_id):
    """True when this person may not use bug hunting. At the 5th false post it blocks them and asks an admin to look."""
    if blocked(user_id):
        return True
    if false_count(user_id) < LIMIT:
        return False
    kv_set(f'hunt_block:{user_id}', now())
    try:
        ch = await fetch_channel(cfg.modlog_id)
        owner = cfg.owner_id if getattr(cfg, 'owner_id', None) else None
        await ch.send(f"🔎 **UNDER WATCH** · <@{user_id}> saved {LIMIT} false reports with bug hunting and lost the command. "
                      f"An admin should ask what they meant. `/pardon` gives it back."
                      + (f' <@{owner}>' if owner else ''),
                      allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=int(owner))]) if owner else NO_MENTIONS)
    except Exception as e:
        print('hunting alert', repr(e))
    return True


async def after_false(bug):
    """A dev marked a saved post Not a bug or Declined: it may be the person's 5th."""
    if bug and bug.get('saved_by'):
        await check(bug['saved_by'])


def lift(user_id):
    """An admin cleared them (/pardon): the command comes back and the count starts again. True when they were blocked."""
    was = blocked(user_id)
    kv_del(f'hunt_block:{user_id}')
    kv_set(f'hunt_reset:{user_id}', now())
    return was
