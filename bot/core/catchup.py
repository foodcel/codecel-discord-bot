"""Runs on startup: handles everything that happened while the bot was off."""
import discord

from bot.core.ctx import ctx, fetch_channel
from bot.core.db import all_, bug_by_thread, kv_get, kv_set, now
from bot.features.bugs.devboard import refresh_all_boards
from bot.core.env import cfg
from bot.features.bugs.intake import analyze_and_act, intake_thread
from bot.discord_ui.router import handle_message
from bot.features.bugs import suggest
from bot.core.timers import run_timers


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
    stuck = all_("SELECT * FROM bugs WHERE kind='bug' AND status='new' AND routed=0 AND deleted=0 AND source IS NOT 'tester' AND created_at>?",
                 now() - 7 * 86400000)
    for bug in stuck:
        t = await fetch_channel(bug['thread_id'])
        if t:
            try:
                await analyze_and_act(bug, t, silent=silent)
            except Exception as e:
                print(repr(e))

    # The suggestions forum: new posts (the first time they are imported silently: no replies, no tags), replies typed while off.
    if cfg.suggestions_id:
        silent_s = not kv_get('suggest_baseline')
        sforum = await fetch_channel(cfg.suggestions_id)
        sactive = [t for t in active_all if t.parent_id == sforum.id]
        sarchived = [t async for t in sforum.archived_threads(limit=50)]
        for t in sorted([*sactive, *sarchived], key=lambda t: t.created_at):
            bug = bug_by_thread(t.id)
            if not bug:
                try:
                    await suggest.intake_suggestion(t, silent=silent_s)
                except Exception as e:
                    print(repr(e))
            elif _changed(t, bug['last_msg_id']):
                await _replay(t, bug['last_msg_id'])
        for bug in all_("SELECT * FROM bugs WHERE kind='suggestion' AND status='new' AND routed=0 AND deleted=0 AND created_at>?",
                        now() - 7 * 86400000):
            t = await fetch_channel(bug['thread_id'])
            if t:
                try:
                    await suggest.analyze_and_act(bug, t, silent=silent_s)
                except Exception as e:
                    print(repr(e))
        if silent_s:
            kv_set('suggest_baseline', '1')

    # Dev board messages typed while offline.
    dev_ids = {fid for fid in (cfg.dev_forum_id, cfg.dev_suggestions_id) if fid}
    for t in active_all:
        if str(t.parent_id) not in dev_ids:
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
