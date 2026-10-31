"""One forum post per dev in #dev-bugs. The first message is the board: a summary and two dropdowns.
Bugs are browsed in a private page (see bugview.py), never posted as messages."""
import asyncio

import discord

from .bounty import all_owner_ids, owners_for
from .components import allowed, button, make_view, select
from .ctx import ctx, fetch_channel
from .db import all_, get_prefs, kv_get, kv_keys, kv_set, run, update_bug
from .env import cfg
from .ui import (E, EM, EN, GAP, SEVERITY, STATUS, ZW, columns, cut, describe, flat, head, labeled, lkey, sentence)

_locks = {}


async def _serial(key, fn):
    """Runs fn one at a time per key (so two bugs never create the same dev post twice)."""
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        try:
            return await fn()
        except Exception as e:
            print('devboard', repr(e))
            return None


def kind_of(key):
    """Board keys: a user id, or 'unclaimed' for the bug boards; the same with an S in front for the suggestion boards."""
    return 'suggestion' if key.startswith('S') else 'bug'


def base_key(key):
    return key[1:] if key.startswith('S') else key


def open_bugs_for(key):
    kind, base = kind_of(key), base_key(key)
    statuses = "('new','investigating','fixing')" if kind == 'bug' else "('new')"
    order = 'votes DESC, id' if kind == 'suggestion' else 'id'  # suggestions: the most voted first
    rows = all_(f"SELECT * FROM bugs WHERE kind=? AND routed=1 AND deleted=0 AND status IN {statuses} ORDER BY {order}", kind)
    out = []
    for b in rows:
        owners = owners_for(b['game_tag_id'], b['game_name'])
        if (len(owners) == 0) if base == 'unclaimed' else (base in owners):
            out.append(b)
    return out


def board_embed(key):
    bugs = open_bugs_for(key)
    kind, base = kind_of(key), base_key(key)
    e = flat()
    if kind == 'suggestion':
        e.title = head(E['game'] if base == 'unclaimed' else '💡', 'Unclaimed games' if base == 'unclaimed' else 'Your suggestion board')
        e.set_footer(text='Pick a game below to browse its suggestions. You can also type "12 added", "1-5 added", "7 declined" here.')
        if not bugs:
            return describe(e, 'No open suggestions 🎉')
        ordered = sorted(bugs, key=lambda b: (-b['votes'], b['id']))  # most votes at the top
        describe(e, f"{E['new']} **{len(bugs)}** open{GAP}🙏 **{sum(b['votes'] for b in bugs)}** votes")
        lst = ordered[:15]
        columns(e, [
            {'name': head('💡', 'Suggestion'), 'lines': [f"**#{b['id']}**{EN}{'⚠️ ' if b['low_info'] else ''}{cut(b['title'], 24 if b['low_info'] else 26)}" for b in lst]},
            {'name': head(E['game'], 'Game'), 'lines': [cut(b['game_name'] or 'Unknown', 18) for b in lst]},
            {'name': head('🙏', 'Votes'), 'lines': [str(b['votes']) for b in lst]},
        ])
        if len(ordered) > 15:
            e.add_field(name=ZW, value=f'…and {len(ordered) - 15} more. Pick a game below to see them.', inline=False)
        return e
    e.title = head(E['game'] if base == 'unclaimed' else '😊', 'Unclaimed games' if base == 'unclaimed' else 'Your bug board')
    e.set_footer(text='Pick a game below to browse its bugs. You can also type "12 fixed", "1-5 fixed", "7 investigating" here.')
    if not bugs:
        return describe(e, 'No open bugs 🎉')
    ordered = sorted(bugs, key=lambda b: (lkey(b['game_name'] or ''), b['id']))

    def n(s):
        return len([b for b in bugs if b['status'] == s])

    # "open" = not picked up yet (status New). Investigating and fixing are counted on their own.
    describe(e, f"{E['open']} **{n('new')}** open{GAP}{E['investigating']} **{n('investigating')}** investigating{GAP}{E['fixing']} **{n('fixing')}** fixing")
    lst = ordered[:15]
    columns(e, [
        {'name': head(E['open'], 'Bug'), 'lines': [f"**#{b['id']}**{EN}{'⚠️ ' if b['low_info'] else ''}{cut(b['title'], 24 if b['low_info'] else 26)}" for b in lst]},
        {'name': head(E['game'], 'Game'), 'lines': [cut(b['game_name'] or 'Unknown', 18) for b in lst]},
        {'name': head(E['status'], 'Status'), 'lines': [STATUS.get(b['status'], b['status']) for b in lst]},
    ])
    if len(ordered) > 15:
        e.add_field(name=ZW, value=f'…and {len(ordered) - 15} more. Pick a game below to see them.', inline=False)
    return e


def board_components(key):
    """Game picker + transcript picker. None when there is nothing open."""
    bugs = open_bugs_for(key)
    if not bugs:
        return None
    by = {}
    for b in bugs:
        k = b['game_tag_id'] or 'none'
        e = by.setdefault(k, {'name': b['game_name'] or 'Unknown game', 'n': 0})
        e['n'] += 1
    options = [{'label': f'All games ({len(bugs)})', 'value': 'all'}] + [
        {'label': f"{e['name']} ({e['n']})"[:100], 'value': k} for k, e in list(by.items())[:24]]
    return make_view([
        [select(f'bd:{key}', "Open a game's suggestions" if kind_of(key) == 'suggestion' else "Open a game's bugs", options)],
        [select(f'trpick:{key}', '📋 Transcript by game', options)],
    ])


async def _display_name(user_id):
    try:
        m = ctx.guild.get_member(int(user_id)) or await ctx.guild.fetch_member(int(user_id))
        return m.display_name or user_id
    except Exception:
        return user_id


async def _dev_thread(key, create):
    tid = kv_get('devthread:' + key)
    t = await fetch_channel(tid) if tid else None
    if t:
        if t.archived:
            try:
                await t.edit(archived=False)
            except Exception:
                pass
        return t
    if not create:
        return None
    kind, base = kind_of(key), base_key(key)
    forum = await fetch_channel(cfg.dev_suggestions_id if kind == 'suggestion' else cfg.dev_forum_id)
    if forum is None:
        return None
    word = 'suggestions' if kind == 'suggestion' else 'bugs'
    name = 'Unclaimed games' if base == 'unclaimed' else f'{await _display_name(base)} — {word}'
    made = await forum.create_thread(name=name[:100], embeds=[board_embed(key)], view=board_components(key))
    kv_set('devthread:' + key, made.thread.id)
    try:
        await made.thread.edit(pinned=True)
    except Exception:
        pass
    return made.thread


async def dev_thread(key, create=True):
    return await _serial('t:' + key, lambda: _dev_thread(key, create))


async def refresh_board(key):
    t = await dev_thread(key, len(open_bugs_for(key)) > 0)
    if not t:
        return
    try:
        starter = await t.fetch_message(t.id)
        await starter.edit(embeds=[board_embed(key)], view=board_components(key))
    except Exception as e:
        print('board edit', e)


_hooks = []


def on_boards_refreshed(fn):
    """Lets the fix log, the games board and the game names refresh together with the boards."""
    _hooks.append(fn)


async def refresh_all_boards():
    keys = [r['k'][len('devthread:'):] for r in kv_keys('devthread:')]
    for o in all_owner_ids():
        keys.append(o)
        if cfg.dev_suggestions_id:
            keys.append('S' + o)
    keys.append('unclaimed')
    if cfg.dev_suggestions_id:
        keys.append('Sunclaimed')
    else:
        keys = [k for k in keys if kind_of(k) == 'bug']
    for k in dict.fromkeys(keys):
        try:
            await refresh_board(k)
        except Exception as e:
            print('refresh', k, e)
    for fn in _hooks:
        try:
            await fn()
        except Exception as e:
            print('board hook', e)


_board_timer = None


def schedule_boards():
    """Refreshes every board in 3 seconds (a burst of changes becomes one refresh)."""
    global _board_timer
    if _board_timer:
        _board_timer.cancel()

    async def go():
        try:
            await refresh_all_boards()
        except Exception as e:
            print('boards', e)

    _board_timer = asyncio.get_running_loop().call_later(3, lambda: asyncio.ensure_future(go()))


async def _delete_later(m, seconds):
    await asyncio.sleep(seconds)
    try:
        await m.delete()
    except Exception:
        pass


async def route_bug(bug, silent=False):
    """New bug: update the boards and ghost-ping the owner (message is deleted right after, the notification stays)."""
    owners = owners_for(bug['game_tag_id'], bug['game_name'])
    suggestion = bug.get('kind') == 'suggestion'
    if suggestion and not cfg.dev_suggestions_id:
        update_bug(bug['id'], {'routed': 1})
        return
    prefix = 'S' if suggestion else ''
    keys = [prefix + o for o in owners] if owners else [prefix + 'unclaimed']
    update_bug(bug['id'], {'routed': 1})
    for key in keys:
        base = base_key(key)
        t = await dev_thread(key, True)
        if not t or silent or base == 'unclaimed' or not get_prefs(base)['bugs']:
            continue  # devs can turn this ping off with /pings
        try:
            m = await t.send(
                content=f"<@{base}> {E['new']} **{'NEW SUGGESTION' if suggestion else 'NEW BUG'}**{EM}·{EM}#{bug['id']}{EM}·{EM}{bug['game_name'] or 'Unknown game'}"
                        f"{f'{EM}·{EM}⚠️ low info' if bug.get('low_info') else ''}",
                allowed_mentions=allowed(users=[base]))
        except Exception as e:
            print('ping', e)
            m = None
        if m:
            asyncio.ensure_future(_delete_later(m, 2.5))
    schedule_boards()


EXP_STATUS = {
    'exploit': 'RECEIVED', 'exploit_investigating': 'INVESTIGATING', 'exploit_fixed': 'FIXED', 'exploit_closed': 'CLOSED, NOT AN EXPLOIT',
}


def exploit_status_line(status, silent=False, dm_ok=True):
    """The line under the title: what happened to the post, and what the reporter was told."""
    return (f"{E['lock']} **{'OLD POST, NOT REMOVED' if silent else 'POST REMOVED FROM #BUGS'}**{GAP}{EXP_STATUS.get(status, 'RECEIVED')}"
            f"{'' if dm_ok else f'{GAP}COULD NOT DM THE REPORTER'}")


def exploit_buttons(bug_id, status):
    """Status buttons on the card. Every change also messages the reporter, because their post was deleted."""
    if status in ('exploit_fixed', 'exploit_closed'):
        return None
    items = []
    if status == 'exploit':
        items.append(button(f'exp:{bug_id}:investigating', f"{E['investigating']} Investigating", discord.ButtonStyle.secondary))
    items.append(button(f'exp:{bug_id}:fixed', f"{E['fixed']} Fixed", discord.ButtonStyle.success))
    items.append(button(f'exp:{bug_id}:closed', f"{E['notbug']} Not an exploit", discord.ButtonStyle.secondary))
    return make_view([items])


def exploit_card(bug, text, silent, status='exploit', dm_ok=True):
    """The card for a possible exploit report. It goes straight into the owner's dev board, not into #mod-log."""
    e = flat()
    e.title = head(E['lock'], 'High priority · possible exploit')
    e.set_footer(text='Do not discuss exploit details in public channels.')
    describe(e, exploit_status_line(status, silent, dm_ok))
    columns(e, [
        {'name': head(E['user'], 'Reporter'), 'lines': [f"<@{bug['reporter_id']}>"]},
        {'name': head(E['game'], 'Game'), 'lines': [bug['game_name'] or 'Unknown']},
        {'name': head(E['severity'], 'Severity'), 'lines': [SEVERITY.get(bug['severity']) or '?']},
    ])
    summary = f"{sentence(bug['summary'])}\n" if bug.get('summary') else ''
    labeled(e, head(E['note'], 'Report'), f"**{bug['title'] or 'Untitled'}**\n{summary}>>> {str(text or '')[:700]}")
    return e


async def post_exploit(bug, text, silent, dm_ok=True):
    """Posts the exploit card at once as a normal message in the dev board post of every owner (or Unclaimed).
    Owners are pinged unless they turned exploit pings off. Unclaimed pings the dev role. Old posts imported silently never ping."""
    owners = owners_for(bug['game_tag_id'], bug['game_name'])
    keys = owners if owners else ['unclaimed']
    card = exploit_card(bug, text, silent, 'exploit', dm_ok)
    view = None if silent else exploit_buttons(bug['id'], 'exploit')
    for key in keys:
        t = await dev_thread(key, True)
        if not t:
            continue
        if silent:
            ping = None
        elif key == 'unclaimed':
            ping = f'<@&{cfg.dev_role}>'
        else:
            ping = f'<@{key}>' if get_prefs(key)['exploits'] else None
        try:
            await t.send(
                content=f"{f'{ping} ' if ping else ''}{E['lock']} **HIGH PRIORITY**", embeds=[card], view=view,
                allowed_mentions=allowed(
                    users=[key] if ping and key != 'unclaimed' else [],
                    roles=[cfg.dev_role] if ping and key == 'unclaimed' else []))
        except Exception as e:
            print('exploit post', e)


async def clear_bug_messages():
    """One-time cleanup: removes the per-bug messages the bot used to post (keeps the board message and dev chat)."""
    for r in kv_keys('devthread:'):
        t = await dev_thread(r['k'][len('devthread:'):], False)
        if not t:
            continue
        mine = []
        try:
            async for m in t.history(limit=None):
                if m.author.id == ctx.client.user.id and m.id != t.id:
                    mine.append(m)
        except Exception:
            pass
        for i in range(0, len(mine), 90):
            try:
                await t.delete_messages(mine[i:i + 90])
            except Exception:
                pass
        for m in mine:
            try:
                await m.delete()
            except Exception:
                pass
    run('DELETE FROM bug_msgs')
