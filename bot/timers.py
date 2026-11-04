"""Delayed jobs stored in the database: delete a fixed post after 24h, lift a 7-day ban, close a report that never got its missing info."""
import discord

from .ctx import ctx, fetch_channel, remove_thread_notice
from .db import all_, bug_by_thread, now, run, update_bug
from .devboard import schedule_boards
from .tags import set_tags
from .ui import E, EM


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
        from .giveaway import end
        await end(int(t['target']))
    elif t['kind'] == 'gw_claim':  # the claim window closed
        from .giveaway import claim_expired
        await claim_expired(int(t['target']))
    elif t['kind'] == 'unban':
        try:
            await ctx.guild.unban(discord.Object(id=int(t['target'])), reason='7-day ban finished')
        except Exception:
            pass
    elif t['kind'] == 'stale':
        bug = bug_by_thread(t['target'])
        if not bug or bug['status'] != 'needs_info':
            return
        thread = await fetch_channel(t['target'])
        update_bug(bug['id'], {'status': 'closed'})
        if thread:
            await set_tags(thread, status=None)
            try:
                await thread.send(f"{E['warn']} **CLOSED**{EM}·{EM}The missing details never came in. Post a new report with everything filled in and it will be looked at. <@{bug['reporter_id']}>")
            except Exception:
                pass
            try:
                await thread.edit(archived=True)
            except Exception:
                pass


async def run_timers():
    """Overdue timers also run on startup, so a PC that was off catches up."""
    for t in all_('SELECT * FROM timers WHERE run_at<=? ORDER BY run_at', now()):
        run('DELETE FROM timers WHERE id=?', t['id'])
        try:
            await _exec(t)
        except Exception as e:
            print('timer', t['kind'], repr(e))
