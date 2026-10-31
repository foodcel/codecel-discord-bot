"""Marking bugs fixed, changing statuses, reopening."""
import asyncio

from .announce import maybe_offer
from .bounty import owners_for
from .components import allowed
from .ctx import fetch_channel
from .db import add_timer, bug_by_id, cancel_timers, now, update_bug
from .devboard import route_bug, schedule_boards
from .fixlog import snapshot_bug
from .perms import can_manage
from .tags import set_tags
from .ui import E, EM

DAY = 86400000

NOTE = {
    'investigating': f"{E['investigating']} **INVESTIGATING**{EM}·{EM}A developer is looking into this.",
    'fixing': f"{E['fixing']} **FIXING**{EM}·{EM}A fix is in progress.",
    'not_a_bug': f"{E['notbug']} **NOT A BUG**{EM}·{EM}Reviewed as intended behavior or a feature request. Thanks for reporting! Suggestions go in the suggestions channel.",
    'duplicate': f"{E['duplicate']} **DUPLICATE**{EM}·{EM}This was already reported. Please follow the original report.",
}


def fire(coro, label):
    """Runs a coroutine in the background and logs a failure instead of losing it."""
    async def guard():
        try:
            await coro
        except Exception as e:
            print(label, e)
    return asyncio.ensure_future(guard())


async def mark_fixed(bug, actor_id):
    update_bug(bug['id'], {'status': 'fixed', 'fixed_at': now(), 'fixed_by': actor_id})
    # Keep the conversation and screenshots: the post is deleted in 24h but the fix log still offers a transcript.
    fire(snapshot_bug(bug_by_id(bug['id'])), 'snapshot')
    thread = None if bug['deleted'] else await fetch_channel(bug['thread_id'])
    if thread:
        await set_tags(thread, status='fixed')
        extra = []
        try:
            starter = await thread.fetch_message(thread.id)
        except Exception:
            starter = None
        eyes = next((r for r in (starter.reactions if starter else []) if str(r.emoji) == '👀'), None)
        if eyes:
            try:
                users = [u async for u in eyes.users(limit=11)]
                extra = [str(u.id) for u in users if not u.bot and str(u.id) != bug['reporter_id']][:10]
            except Exception:
                extra = []
        pings = [bug['reporter_id'], *extra]
        try:
            await thread.send(
                content=f"{' '.join(f'<@{i}>' for i in pings)}\n{E['fixed']} **FIXED**{EM}·{EM}{bug['title']} (#{bug['id']}). Thanks for reporting!\n"
                        'This post closes now and is deleted in 24 hours. If it is still broken, reply here before then.',
                allowed_mentions=allowed(users=pings))
        except Exception as e:
            print('fixed msg', e)
        try:
            await thread.edit(archived=True)
        except Exception:
            pass
        cancel_timers('delete_thread', bug['thread_id'])
        add_timer('delete_thread', bug['thread_id'], now() + DAY)
    schedule_boards()
    fire(maybe_offer(bug['game_tag_id']), 'offer')


async def set_bug_status(bug, status, actor_id):
    if status == 'fixed':
        return await mark_fixed(bug, actor_id)
    update_bug(bug['id'], {'status': status})
    thread = None if bug['deleted'] else await fetch_channel(bug['thread_id'])
    if thread:
        await set_tags(thread, status=None if status == 'new' else status)
        if NOTE.get(status):
            try:
                await thread.send(NOTE[status])
            except Exception:
                pass
        if status in ('not_a_bug', 'duplicate'):
            try:
                await thread.edit(archived=True)
            except Exception:
                pass
    schedule_boards()


async def reopen(bug):
    """Reporter said "still broken" inside the 24h window."""
    cancel_timers('delete_thread', bug['thread_id'])
    update_bug(bug['id'], {'status': 'new', 'fixed_at': None, 'announced': 0})
    thread = await fetch_channel(bug['thread_id'])
    if thread:
        await set_tags(thread, status=None)
        try:
            await thread.send(f"{E['duplicate']} **REOPENED**{EM}·{EM}#{bug['id']} is back on the board. The developer has been notified.")
        except Exception:
            pass
    await route_bug(bug_by_id(bug['id']))
    fire(maybe_offer(bug['game_tag_id']), 'offer')  # drops it from a pending draft


async def apply_status(ids, status, member):
    """ids: bug numbers. Returns (done, skipped) lists of short strings for the dev."""
    done = []
    skipped = []
    for id_ in ids:
        bug = bug_by_id(id_)
        if not bug or bug['status'] in ('removed', 'closed') or bug['status'].startswith('exploit'):
            skipped.append(f'#{id_} not found')
            continue
        owners = owners_for(bug['game_tag_id'], bug['game_name'])
        if not can_manage(member, owners):
            skipped.append(f'#{id_} not your game')
            continue
        try:
            await set_bug_status(bug, status, str(member.id))
            done.append(f'#{id_}')
        except Exception as e:
            print('applyStatus', repr(e))
            skipped.append(f'#{id_} error')
    return done, skipped
