"""Runs on startup: handles everything that happened while the bot was off."""
import discord

from .ctx import ctx, fetch_channel
from .db import all_, bug_by_thread, kv_get, kv_set, now
from .devboard import refresh_all_boards
from .env import cfg
from .intake import analyze_and_act, intake_thread
from .router import handle_message
from .timers import run_timers


async def _replay(thread, after_id):
    try:
        msgs = [m async for m in thread.history(after=discord.Object(id=int(after_id)), limit=100, oldest_first=True)]
    except Exception:
        msgs = []
    for m in msgs:
        try:
            await handle_message(m)
        except Exception as e:
            print(repr(e))


def _changed(thread, last):
    return bool(thread.last_message_id) and bool(last) and str(thread.last_message_id) != str(last)


async def catchup():
    # The first run imports existing posts silently (no replies, no strikes, no tag changes).
    silent = not kv_get('baseline_done')
    await run_timers()

    active_all = await ctx.guild.active_threads()
    forum = await fetch_channel(cfg.bugs_id)
    active = [t for t in active_all if t.parent_id == forum.id]
    archived = [t async for t in forum.archived_threads(limit=50)]
    for t in sorted([*active, *archived], key=lambda t: t.created_at):
        bug = bug_by_thread(t.id)
        if not bug:
            try:
                await intake_thread(t, silent=silent)
            except Exception as e:
                print(repr(e))
            continue
        if _changed(t, bug['last_msg_id']):
            await _replay(t, bug['last_msg_id'])

    # Tester threads: dev commands and "still broken" replies typed while the bot was off.
    testing = await fetch_channel(cfg.testing_id) if cfg.testing_id else None
    if testing:
        for t in active_all:
            if t.parent_id != testing.id:
                continue
            bug = bug_by_thread(t.id)
            if bug and _changed(t, bug['last_msg_id']):
                await _replay(t, bug['last_msg_id'])

    # Reports whose analysis failed earlier (outage, daily cap).
    stuck = all_("SELECT * FROM bugs WHERE status='new' AND routed=0 AND deleted=0 AND source IS NOT 'tester' AND created_at>?",
                 now() - 7 * 86400000)
    for bug in stuck:
        t = await fetch_channel(bug['thread_id'])
        if t:
            try:
                await analyze_and_act(bug, t, silent=silent)
            except Exception as e:
                print(repr(e))

    # Dev board messages typed while offline.
    dev = await fetch_channel(cfg.dev_forum_id)
    for t in active_all:
        if t.parent_id != dev.id:
            continue
        last = kv_get(f'devlast:{t.id}')
        if not last:
            if t.last_message_id:
                kv_set(f'devlast:{t.id}', t.last_message_id)
            continue
        if t.last_message_id and str(t.last_message_id) != last:
            await _replay(t, last)

    if silent:
        kv_set('baseline_done', '1')
    await refresh_all_boards()
