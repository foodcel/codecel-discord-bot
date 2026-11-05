"""Marking bugs fixed, changing statuses, reopening."""
import asyncio

import discord

from bot.features.bugs.nums import label
from bot.features.updates.announce import maybe_offer
from bot.features.games.bounty import owners_for
from bot.discord_ui.components import allowed
from bot.core.ctx import ctx, fetch_channel
from bot.core.db import add_timer, all_, bug_by_id, cancel_timers, now, update_bug
from bot.discord_ui import devlog
from bot.features.bugs.devboard import route_bug, schedule_boards
from bot.features.bugs.fixlog import snapshot_bug
from bot.core.perms import can_manage
from bot.features.bugs.tags import set_tags
from bot.discord_ui.ui import E, EM

DAY = 86400000

NOTE = {
    'investigating': f"{E['investigating']} **INVESTIGATING**{EM}·{EM}A developer is looking into this.",
    'fixing': f"{E['fixing']} **FIXING**{EM}·{EM}A fix is in progress.",
    'not_a_bug': f"{E['notbug']} **NOT A BUG**{EM}·{EM}Reviewed as intended behavior or a feature request. Thanks for reporting! Suggestions go in the suggestions channel.",
    'duplicate': f"{E['duplicate']} **DUPLICATE**{EM}·{EM}This was already reported. Please follow the original report.",
    'declined': f"❌ **DECLINED**{EM}·{EM}The developers decided not to add this. Thanks for the idea! This post is removed in 24 hours.",
}
NOTE_SUGGESTION = {
    'duplicate': f"{E['duplicate']} **DUPLICATE**{EM}·{EM}This was already suggested. Please add your vote to the original post.",
}


def fire(coro, label):
    """Runs a coroutine in the background and logs a failure instead of losing it."""
    async def guard():
        try:
            await coro
        except Exception as e:
            print(label, e)
    return asyncio.ensure_future(guard())


async def _thread(bug):
    """(thread or None, gone). gone: the post no longer exists, so there is nobody to tell. None and not gone: Discord did not answer, try again later."""
    if bug['deleted']:
        return None, True
    try:
        return await ctx.client.fetch_channel(int(bug['thread_id'])), False
    except (discord.NotFound, discord.Forbidden, ValueError):
        return None, True
    except Exception as e:
        print('fixed: thread not reachable now', bug['id'], repr(e)[:100])
        return None, False


async def tell_fixed(bug, update_url=None):
    """Tells the reporter (and the people who 👀'd it) in the post that it is fixed, tags and closes it, and deletes it in 24 hours.
    It is only marked as told once the message is out (or the post is gone); otherwise retry_untold tries again."""
    thread, gone = await _thread(bug)
    if gone:
        update_bug(bug['id'], {'notified': 1})
    if thread:
        await set_tags(thread, status='fixed', kind=bug['kind'])
        extra = []
        try:
            starter = await thread.fetch_message(thread.id)
        except Exception:
            starter = None
        eyes = next((r for r in (starter.reactions if starter else []) if str(r.emoji) == ('🙏' if bug['kind'] == 'suggestion' else '👀')), None)
        if eyes:
            try:
                users = [u async for u in eyes.users(limit=11)]
                extra = [str(u.id) for u in users if not u.bot and str(u.id) != bug['reporter_id']][:10]
            except Exception:
                extra = []
        pings = [bug['reporter_id'], *extra]
        if bug['kind'] == 'suggestion':
            text = (f"{' '.join(f'<@{i}>' for i in pings)}\n{E['fixed']} **ADDED**{EM}·{EM}{bug['title']} ({label(bug)}). Thanks for the idea!\n"
                    'This post closes now and is deleted in 24 hours.')
        else:
            where = f' It is in the new update: {update_url}' if update_url else ''
            text = (f"{' '.join(f'<@{i}>' for i in pings)}\n{E['fixed']} **FIXED**{EM}·{EM}{bug['title']} ({label(bug)}).{where}\nThanks for reporting!\n"
                    'This post closes now and is deleted in 24 hours. If it is still broken, reply here before then.')
        try:
            await thread.send(content=text, allowed_mentions=allowed(users=pings))
        except Exception as e:
            print('fixed msg', e)
            return  # not told: retry_untold tries again
        update_bug(bug['id'], {'notified': 1})
        try:
            await thread.edit(archived=True)
        except Exception:
            pass
        cancel_timers('delete_thread', bug['thread_id'])
        add_timer('delete_thread', bug['thread_id'], now() + DAY)


async def tell_released(ids, update_url):
    """An update went out: the reporters of the bugs in it are told now, with a link to the update. Bugs they were already told about are skipped."""
    for id_ in ids:
        bug = bug_by_id(id_)
        if bug and bug['kind'] == 'bug' and bug['status'] == 'fixed' and not bug['notified'] and not bug['deleted']:
            try:
                await tell_fixed(bug, update_url)
            except Exception as e:
                print('tell released', repr(e)[:120])


async def retry_untold():
    """Bugs that are in a posted update but whose reporter was never told (Discord failed, or the bot restarted mid-way): told now."""
    for bug in all_("SELECT * FROM bugs WHERE kind='bug' AND status='fixed' AND announced=1 AND notified=0 AND deleted=0 ORDER BY id LIMIT 25"):
        try:
            await tell_fixed(bug)
        except Exception as e:
            print('retry untold', bug['id'], repr(e)[:120])


async def mark_fixed(bug, actor_id):
    """A bug marked fixed is only recorded: its reporter hears about it when the update that contains it is released (tell_released).
    An added suggestion is told at once, as before."""
    update_bug(bug['id'], {'status': 'fixed', 'fixed_at': now(), 'fixed_by': actor_id, 'notified': 0, 'announced': 0})
    # Keep the conversation and screenshots: the post is deleted 24h after the reporter is told, but the fix log still offers a transcript.
    fire(snapshot_bug(bug_by_id(bug['id'])), 'snapshot')
    if bug['kind'] == 'suggestion' or not bug['game_tag_id']:
        await tell_fixed(bug)  # a suggestion, or a bug with no game tag (it can never be in an update): told at once
    schedule_boards()
    fire(maybe_offer(bug['game_tag_id']), 'offer')


async def set_bug_status(bug, status, actor_id):
    if status == 'fixed':
        return await mark_fixed(bug, actor_id)
    update_bug(bug['id'], {'status': status, **({'announced': 0, 'notified': 0} if bug['status'] == 'fixed' else {})})
    if bug['status'] == 'fixed':
        fire(maybe_offer(bug['game_tag_id']), 'offer')  # no longer fixed: it leaves the update draft
    thread = None if bug['deleted'] else await fetch_channel(bug['thread_id'])
    if thread:
        await set_tags(thread, status=None if status == 'new' else status, kind=bug['kind'])
        note = (NOTE_SUGGESTION if bug['kind'] == 'suggestion' else {}).get(status) or NOTE.get(status)
        if note:
            try:
                await thread.send(note)
            except Exception:
                pass
        if status in ('not_a_bug', 'duplicate', 'declined'):
            try:
                await thread.edit(archived=True)
            except Exception:
                pass
    if (status == 'declined' or (status == 'duplicate' and bug['kind'] == 'suggestion')) and thread:
        cancel_timers('delete_thread', bug['thread_id'])
        add_timer('delete_thread', bug['thread_id'], now() + DAY)
    schedule_boards()


async def reopen(bug):
    """Reporter said "still broken" inside the 24h window."""
    cancel_timers('delete_thread', bug['thread_id'])
    update_bug(bug['id'], {'status': 'new', 'fixed_at': None, 'announced': 0})
    thread = await fetch_channel(bug['thread_id'])
    if thread:
        await set_tags(thread, status=None)
        try:
            await thread.send(f"{E['duplicate']} **REOPENED**{EM}·{EM}{label(bug)} is back on the board. The developer has been notified.")
        except Exception:
            pass
    await route_bug(bug_by_id(bug['id']))
    fire(maybe_offer(bug['game_tag_id']), 'offer')  # drops it from a pending draft


async def apply_status(ids, status, member, kind=None, via='command'):
    """ids: bug or suggestion numbers. kind: the forum the dev typed in ('bug' or 'suggestion'), or None.
    Returns (done, skipped) lists of short strings for the dev."""
    done = []
    skipped = []
    for id_ in ids:
        n_skipped = len(skipped)
        bug = bug_by_id(id_)
        await _apply_one(id_, bug, status, member, kind, done, skipped)
        if len(skipped) > n_skipped:
            devlog.log_status(member, id_, status, bug, f'Refused: {skipped[-1]}', False, via)
        else:
            devlog.log_status(member, id_, status, bug, 'Done', True, via)
    return done, skipped


async def _apply_one(id_, bug, status, member, kind, done, skipped):
    """One id of apply_status: adds to done or skipped."""
    if not bug or bug['status'] in ('removed', 'closed') or bug['status'].startswith('exploit'):
        skipped.append(f'#{id_} not found')
        return
    from bot.features.bugs.nums import full
    lab = full(bug)
    if kind and bug['kind'] != kind:
        skipped.append(f"{lab} is a {bug['kind']}")
        return
    if bug['kind'] == 'suggestion' and status not in ('fixed', 'declined', 'duplicate', 'new'):
        skipped.append(f'{lab} is a suggestion: use added, declined or duplicate')
        return
    if bug['kind'] == 'bug' and status == 'declined':
        skipped.append(f'{lab} is a bug: use fixed, not a bug or duplicate')
        return
    owners = owners_for(bug['game_tag_id'], bug['game_name'])
    if not can_manage(member, owners):
        skipped.append(f'{lab} not your game')
        return
    try:
        await set_bug_status(bug, status, str(member.id))
        done.append(lab)
        if status in ('not_a_bug', 'declined'):  # bug hunting: this may be someone's 5th false report
            from bot.features.bugs.hunting import after_false
            asyncio.ensure_future(after_false(bug_by_id(id_)))
    except Exception as e:
        print('applyStatus', repr(e))
        skipped.append(f'{lab} error')
