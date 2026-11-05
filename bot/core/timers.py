"""Delayed jobs stored in the database: delete a fixed post after 24h, lift a 7-day ban, close a report that never got its missing info, end a giveaway.
A job is removed only after it worked. One that fails is tried again 5, 10, 15... minutes later, up to MAX_TRIES times, then dropped (logged)."""
import asyncio

import discord

from bot.core.ctx import ctx, fetch_channel, remove_thread_notice
from bot.core.db import all_, bug_by_thread, now, run, update_bug
from bot.features.bugs.devboard import schedule_boards


async def _exec(t):
    if t['kind'] == 'delete_thread':
        bug = bug_by_thread(t['target'])
        if bug and bug['status'] not in ('fixed', 'duplicate', 'declined'):
            return  # reopened meanwhile
        thread = await fetch_channel(t['target'])
        if thread:
            await remove_thread_notice(thread)
            try:
                await thread.delete(reason='Fixed or duplicate bug, 24h passed')
            except Exception as e:
                print('delete thread', e)
        if bug:
            update_bug(bug['id'], {'deleted': 1})
        schedule_boards()
    elif t['kind'] == 'delete_card':  # the 3-day new-game card goes away (the game stays in the library)
        channel_id, message_id = t['target'].split(':')
        ch = await fetch_channel(channel_id)
        try:
            await (await ch.fetch_message(int(message_id))).delete()
        except Exception as e:
            print('delete card', repr(e))
    elif t['kind'] == 'gw_end':  # a giveaway's time is up
        from bot.features.giveaways.giveaway import end
        await end(int(t['target']))
    elif t['kind'] == 'gw_claim':  # the claim window closed
        from bot.features.giveaways.giveaway import claim_expired
        await claim_expired(int(t['target']))
    elif t['kind'] == 'unban':
        try:
            await ctx.guild.unban(discord.Object(id=int(t['target'])), reason='7-day ban finished')
        except discord.NotFound:
            pass  # already unbanned
    elif t['kind'] == 'stale':
        bug = bug_by_thread(t['target'])
        if not bug or bug['status'] != 'needs_info':
            return
        from bot.features.bugs.intake import log_unanswered
        await log_unanswered(bug)  # never closed: a report with missing details still reaches the developer


MAX_TRIES = 5
_lock = asyncio.Lock()


async def run_timers():
    """Overdue timers also run on startup, so a bot that was off catches up. Only one run at a time (the loop and the catch-up both call it)."""
    if _lock.locked():
        return
    async with _lock:
        for t in all_('SELECT * FROM timers WHERE run_at<=? ORDER BY run_at', now()):
            try:
                await _exec(t)
            except Exception as e:
                tries = (t.get('tries') or 0) + 1
                print('timer', t['kind'], t['target'], 'failed', tries, repr(e)[:200])
                if tries < MAX_TRIES:
                    run('UPDATE timers SET tries=?, run_at=? WHERE id=?', tries, now() + tries * 300000, t['id'])
                    continue
                print('timer given up', t['kind'], t['target'])
            run('DELETE FROM timers WHERE id=?', t['id'])
