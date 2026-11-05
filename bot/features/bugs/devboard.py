"""One forum post per dev in #dev-bugs. The first message is the board: a summary and two dropdowns.
Bugs are browsed in a private page (see bugview.py), never posted as messages."""
import asyncio

import discord
from discord import ui

from bot.discord_ui.card import card, row
from bot.features.bugs.nums import label
from bot.features.games.bounty import all_owner_ids, owners_for
from bot.discord_ui.components import allowed, button, make_view, select
from bot.core.ctx import ctx, fetch_channel
from bot.core.db import all_, get_prefs, kv_get, kv_keys, kv_set, update_bug
from bot.core.env import cfg
from bot.discord_ui.ui import E, EM, GAP, SEVERITY, STATUS, cut, lkey, sentence

_locks = {}
NL = chr(10)


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


def board_card(key):
    """A dev's board as a card: the counts in the title, the open reports in a tree under each game, the commands in the footer, the pickers below."""
    import discord
    from discord import ui
    from bot.discord_ui.card import clone_rows
    from bot.features.bugs.nums import label
    from bot.discord_ui.pngs import with_strip
    from bot.features.updates.botnews import date_button
    bugs = open_bugs_for(key)
    kind, base = kind_of(key), base_key(key)
    suggestion = kind == 'suggestion'
    if suggestion:
        title = f"{'🎮 Unclaimed games' if base == 'unclaimed' else '💡 Your suggestion board'} · {len(bugs)} open · 🙏 {sum(b['votes'] for b in bugs)} votes"
        foot = 'Pick a game below to browse its suggestions. Type `sonic 3 added`, `sonic 1-5 added` or `sonic 7 declined` here.'
    else:
        n = lambda s: len([b for b in bugs if b['status'] == s])
        title = f"{'🎮 Unclaimed games' if base == 'unclaimed' else '😊 Your bug board'} · 🐛 {n('new')} open · 🔎 {n('investigating')} investigating · 🛠️ {n('fixing')} fixing"
        foot = 'Pick a game below to browse its bugs. Type `sonic 3 fixed`, `sonic 1-5 fixed` or `sonic 7 investigating` here.'
    by = {}
    for b in sorted(bugs, key=lambda b: (lkey(b['game_name'] or ''), -b['votes'] if suggestion else 0, b['id'])):
        by.setdefault(b['game_name'] or 'Unknown game', []).append(b)
    blocks, shown = [], 0
    for game, lst in by.items():
        lines = []
        for k, b in enumerate(lst):
            if shown >= 36:
                break
            shown += 1
            tail = f"🙏 {b['votes']}" if suggestion else STATUS.get(b['status'], b['status'])
            lines.append(f"{'└─' if k == len(lst) - 1 else '├─'} **{label(b)}** · {'⚠️ ' if b['low_info'] else ''}{cut(b['title'], 30)} · {tail}")
        if lines:
            blocks.append(f'**🎮 {game}** · {len(lst)}' + chr(10) + chr(10).join(lines))
    if len(bugs) > shown:
        blocks.append(f'…and {len(bugs) - shown} more. Pick a game below to see them.')
    body = (chr(10) * 2).join(blocks) or ('No open suggestions 🎉' if suggestion else 'No open bugs 🎉')
    head = ui.Section(f'### {title}', accessory=date_button()) if len(title) <= 44 else ui.TextDisplay(f'### {title}')
    view = ui.LayoutView(timeout=None)
    parts, strip_ = with_strip([head, ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small), ui.TextDisplay(body),
                                ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small), ui.TextDisplay('-# ' + foot)])
    view.add_item(ui.Container(*parts))
    for r in clone_rows(board_components(key)):
        view.add_item(r)
    return view, [strip_]


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


async def board_name(key):
    """The title of a dev's board post: the dev's name as it is now."""
    kind, base = kind_of(key), base_key(key)
    word = 'suggestions' if kind == 'suggestion' else 'bugs'
    return ('Unclaimed games' if base == 'unclaimed' else f'{await _display_name(base)} — {word}')[:100]


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
    kind = kind_of(key)
    forum = await fetch_channel(cfg.dev_suggestions_id if kind == 'suggestion' else cfg.dev_forum_id)
    if forum is None:
        return None
    name = await board_name(key)
    view, files = board_card(key)
    made = await forum.create_thread(name=name[:100], view=view, files=files)
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
    want = await board_name(key)
    if want and t.name != want:  # the dev changed their name: the post follows
        try:
            await t.edit(name=want)
        except Exception as e:
            print('board rename', e)
    try:
        starter = await t.fetch_message(t.id)
        view, files = board_card(key)
        await starter.edit(content=None, embeds=[], view=view, attachments=files)  # an old embed board turns into the card in place
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
                content=f"<@{base}> {E['new']} **{'NEW SUGGESTION' if suggestion else 'NEW BUG'}**{EM}·{EM}{label(bug)}{EM}·{EM}{bug['game_name'] or 'Unknown game'}"
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
    """Status buttons on the card (a list of ActionRows). Every change also messages the reporter, because their post was deleted."""
    if status in ('exploit_fixed', 'exploit_closed'):
        return []
    items = []
    if status == 'exploit':
        items.append(button(f'exp:{bug_id}:investigating', f"{E['investigating']} Investigating", discord.ButtonStyle.secondary))
    items.append(button(f'exp:{bug_id}:fixed', f"{E['fixed']} Fixed", discord.ButtonStyle.success))
    items.append(button(f'exp:{bug_id}:closed', f"{E['notbug']} Not an exploit", discord.ButtonStyle.secondary))
    return [ui.ActionRow(*items)]


def exploit_card(bug, text, silent, status='exploit', dm_ok=True, ping=None):
    """The card for a possible exploit report, posted straight into the owner's dev board: (view, files). The report text is in the database
    (bugs.body), so a button press redraws the card from there."""
    facts = NL.join([row('Reporter', f"<@{bug['reporter_id']}>"), row('Game', bug['game_name'] or 'Unknown'), row('Severity', SEVERITY.get(bug['severity']) or '?')])
    summary = f"{sentence(bug['summary'])}{NL}" if bug.get('summary') else ''
    report = f"**{E['note']} {bug['title'] or 'Untitled'}**{NL}{summary}>>> {str(text or '')[:700]}"
    return card(f"{E['lock']} High priority · possible exploit", [exploit_status_line(status, silent, dm_ok), facts, report],
                ['Do not discuss exploit details in public channels.'], ping=ping,
                inside=[] if silent else exploit_buttons(bug['id'], status))


async def post_exploit(bug, text, silent, dm_ok=True):
    """Posts the exploit card at once as a normal message in the dev board post of every owner (or Unclaimed).
    Owners are pinged unless they turned exploit pings off. Unclaimed pings the dev role. Old posts imported silently never ping."""
    owners = owners_for(bug['game_tag_id'], bug['game_name'])
    keys = owners if owners else ['unclaimed']
    update_bug(bug['id'], {'body': str(text or '')[:3000]})  # kept, so the card can be redrawn and nothing is lost when the post is deleted
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
            view, files = exploit_card(bug, text, silent, 'exploit', dm_ok, ping=ping)
            await t.send(
                view=view, files=files,
                allowed_mentions=allowed(
                    users=[key] if ping and key != 'unclaimed' else [],
                    roles=[cfg.dev_role] if ping and key == 'unclaimed' else []))
        except Exception as e:
            print('exploit post', e)


async def notify_info(bug, msg):
    """Someone added to a logged report: ghost-ping the owners (the message is deleted right after, the notification stays)."""
    owners = owners_for(bug['game_tag_id'], bug['game_name'])
    suggestion = bug.get('kind') == 'suggestion'
    prefix = 'S' if suggestion else ''
    for o in owners:
        key = prefix + o
        if not get_prefs(o)['bugs']:
            continue  # devs can turn their pings off with /pings
        t = await dev_thread(key, False)
        if not t:
            continue
        try:
            m = await t.send(content=f"<@{o}> 📎 **NEW INFO**{EM}·{EM}{label(bug)}{EM}·{EM}{bug['game_name'] or 'Unknown game'}{EM}·{EM}{msg.jump_url}",
                             allowed_mentions=allowed(users=[o]))
        except Exception as e:
            print('info ping', e)
            m = None
        if m:
            asyncio.ensure_future(_delete_later(m, 2.5))

