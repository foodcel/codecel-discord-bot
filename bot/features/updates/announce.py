"""Update announcements: drafts that grow as bugs get fixed, and the public embed."""
import asyncio
import json
import time

import discord
from discord import ui

from bot.features.bugs.nums import label
from bot.core.ai import draft_bug_fixes, draft_new_features, polish_updates
from bot.features.games.bounty import owners_for
from bot.discord_ui.components import NO_MENTIONS, allowed, button, select
from bot.core.ctx import ctx, fetch_channel
from bot.core.db import (bug_by_id, create_pending, one, del_pending, get_game, get_pending, kv_del, kv_get, kv_set, now, run, set_pending,
                 update_bug, upsert_game, all_)
from bot.features.bugs.devboard import dev_thread, schedule_boards
from bot.core.env import cfg
from bot.features.bugs.tags import tag_name
from bot.discord_ui.ui import E, EM


def unannounced(tag_id):
    """What an update can announce: every bug marked fixed in the bugs channel (that is the confirmation) and every added suggestion."""
    return all_("SELECT * FROM bugs WHERE game_tag_id=? AND status='fixed' AND announced=0 ORDER BY id", tag_id)


HALF_RULE = '─' * 28  # fills one half of the embed


async def polish_dev_updates(game_name, lines):
    """Dev-written update lines, rewritten by Claude into clear patch-note wording (falls back to what the dev typed)."""
    if not lines:
        return lines
    try:
        out = await polish_updates(game_name, lines)
        if len(out) == len(lines):
            return out
    except Exception as e:
        print('polishUpdates', e)
    return lines


def items(p):
    """The fixes and added suggestions of a draft, as [(key, line)]. Empty when the lines were edited by hand (they no longer line up)."""
    out = []
    if len(p['bugIds']) == len(p['bugfixes']):
        out += [(f'b:{i}', l) for i, l in zip(p['bugIds'], p['bugfixes'])]
    if len(p.get('newIds', [])) == len(p.get('newLines', [])):
        out += [(f'n:{i}', l) for i, l in zip(p.get('newIds', []), p.get('newLines', []))]
    return out


def chosen(p):
    """(bug fix lines, new feature lines) that will be posted: everything the dev did not untick."""
    off = set(p.get('off', []))
    bugs = ([l for i, l in zip(p['bugIds'], p['bugfixes']) if f'b:{i}' not in off]
            if len(p['bugIds']) == len(p['bugfixes']) else list(p['bugfixes']))
    news = ([l for i, l in zip(p.get('newIds', []), p.get('newLines', [])) if f'n:{i}' not in off]
            if len(p.get('newIds', [])) == len(p.get('newLines', [])) else list(p.get('newLines', [])))
    return bugs, news


def chosen_ids(p):
    """The ids of the items that will be posted (they are marked as announced)."""
    off = set(p.get('off', []))
    bug_ids = [i for i in p['bugIds'] if f'b:{i}' not in off] if len(p['bugIds']) == len(p['bugfixes']) else list(p['bugIds'])
    new_ids = ([i for i in p.get('newIds', []) if f'n:{i}' not in off]
               if len(p.get('newIds', [])) == len(p.get('newLines', [])) else list(p.get('newIds', [])))
    return bug_ids, new_ids


def _ago(ms):
    s = max(0, int(time.time() - ms / 1000))
    return f'{s // 86400}d ago' if s >= 86400 else f'{s // 3600}h ago' if s >= 3600 else f'{max(1, s // 60)}m ago'


def item_note(key):
    """Under each item of the draft: who marked it as done and when, and if it is confirmed. A fix counts as confirmed once its 24 hours
    have passed without the player saying it is still broken (a reopened bug leaves the draft by itself)."""
    bug = bug_by_id(int(key[2:]))
    if not bug or not bug['fixed_at']:
        return None
    m = ctx.guild.get_member(int(bug['fixed_by'])) if ctx.guild and (bug['fixed_by'] or '').isdigit() else None
    who = m.display_name if m else 'a dev'
    done = 'added' if bug['kind'] == 'suggestion' else 'fixed'
    sure = '✅ confirmed'
    return f"{label(bug)} · {done} by {who} {_ago(bug['fixed_at'])} · {sure}"[:100]


def draft_view(id_, p=None):
    """The dropdown and the buttons under a draft, as rows of a new-layout message."""
    rows = []
    its = items(p)[:25] if p else []
    if its:
        off = set(p.get('off', []))
        rows.append([select(f'ann:sel:{id_}', 'Choose what to post', [
            {'label': (('🐛 ' if k[0] == 'b' else '✨ ') + l)[:100], 'description': item_note(k), 'value': k, 'default': k not in off}
            for k, l in its], min_values=0, max_values=len(its))])
    rows.append([
        button(f'ann:post:{id_}', 'Post', discord.ButtonStyle.success),
        button(f'ann:edit:{id_}', 'Edit', discord.ButtonStyle.primary),
        button(f'ann:later:{id_}', 'Later', discord.ButtonStyle.secondary),
    ])
    return [ui.ActionRow(*r) for r in rows]


MERGE_HOURS = 12  # updates of a game this close together become one embed
FRESH = '🆕 '  # in front of the lines the latest addition brought, so a reader sees what changed in a card that grew


def mark(lines, fresh):
    return [FRESH + line if line in fresh else line for line in lines]


def recent_announcement(tag_id):
    """The last announcement of the game, if it is young enough to add to (and its message is known)."""
    row = one('SELECT * FROM announcements WHERE tag_id=? ORDER BY id DESC LIMIT 1', tag_id)
    if row and row.get('message_id') and row.get('payload') and now() - row['posted_at'] < MERGE_HOURS * 3600000:
        return row
    return None


def ping_role(game):
    """The role an announcement can ping: the game's own, or the updates role."""
    return game.get('ping_role_id') or cfg.updates_role


def confirm_view(id_, text, recent=None, role=None):
    """The question when Post is pressed: add to the update posted a few hours ago, or post a new one (with or without a ping)."""
    row = []
    if recent:
        row.append(button(f'ann:go:{id_}:merge', 'Add to the earlier update', discord.ButtonStyle.primary))
    if role:
        row.append(button(f'ann:go:{id_}:ping', 'Post new and ping', discord.ButtonStyle.success))
    row.append(button(f'ann:go:{id_}:quiet', 'Post new without ping' if role else 'Post new', discord.ButtonStyle.secondary))
    row.append(button(f'ann:back:{id_}', 'Back', discord.ButtonStyle.secondary))
    view = ui.LayoutView()
    view.add_item(ui.TextDisplay(text))
    view.add_item(ui.ActionRow(*row))
    return view


def _no_channel_warning():
    return f"\n{E['warn']} **NO CHANNEL YET**{EM}·{EM}set one with `/config set`"


def offer_text(game, p):
    owners = ' '.join(f'<@{o}>' for o in p['owners']) + ' ' if p['owners'] else ''
    n = len(p['bugIds']) + len(p.get('newIds', []))
    return (f"{owners}{E['update']} **{n} {'CHANGES' if p.get('newIds') else 'FIXES'} READY**{EM}·{EM}{game['name']}"
            + ('' if (game.get('announce_channel_id') or cfg.updates_id) else _no_channel_warning()))


async def draft_payload(pending_id):
    """What the draft message looks like: {'content', 'embeds', 'view', 'allowed_mentions'}."""
    p = get_pending(pending_id)
    game = get_game(p['tagId'])
    warn = '' if (game.get('announce_channel_id') or cfg.updates_id) else _no_channel_warning()
    bug_lines, new_lines = chosen(p)
    hint = '' if p.get('offer') else '\n-# Untick what you do not want to post. Edit lets you add extra bug fixes and updates. Post when you are ready.'
    from bot.features.games.cards import released_row_for, update_card_items
    head = offer_text(game, p) if p.get('offer') else f"{E['update']} **DRAFT**{EM}·{EM}{game['name']}{warn}{hint}"
    poster = (p.get('owners') or [None])[0]  # the card is drawn exactly as it will be posted
    card, files = update_card_items(game, released_row_for(game['name']), bug_lines, list(p['updates']), new_lines, p.get('version') or '', None, poster=poster)
    view = ui.LayoutView()
    view.add_item(ui.TextDisplay(head))
    for it in card + draft_view(pending_id, p):
        view.add_item(it)
    return {'view': view, 'files': files, 'allowed_mentions': NO_MENTIONS}


def edit_kw(payload):
    """A draft payload as the arguments of an edit (files become attachments)."""
    return {('attachments' if k == 'files' else k): v for k, v in payload.items()}


def split_kinds(fixes):
    return [f for f in fixes if f['kind'] == 'bug'], [f for f in fixes if f['kind'] == 'suggestion']


async def _lines(game_name, items, suggestion):
    """Patch-note lines for fixed bugs, or for added suggestions (falls back to the raw titles)."""
    lines = [f['title'] for f in items]
    if not items:
        return lines
    try:
        out = await (draft_new_features if suggestion else draft_bug_fixes)(game_name, items)
        if len(out) == len(items):
            lines = out
    except Exception as e:
        print('draft lines', e)
    return lines


async def polish_fixes(tag_id, game):
    """Polishes the pending changes with Claude (falls back to raw titles).
    Returns (fixed bugs, their lines, added suggestions, their lines)."""
    bugs, sugs = split_kinds(unannounced(tag_id))
    return bugs, await _lines(game['name'], bugs, False), sugs, await _lines(game['name'], sugs, True)


_offer_locks = {}


async def maybe_offer(tag_id):
    """One at a time per game: '1-5 fixed' fires five of these at once, and each would otherwise post its own draft."""
    if not tag_id:
        return
    lock = _offer_locks.setdefault(tag_id, asyncio.Lock())
    async with lock:
        return await _maybe_offer(tag_id)


async def _maybe_offer(tag_id):
    """Starts an offer once the game has enough changes (default 3: fixed bugs and added suggestions). While the draft is open it
    keeps growing as more are done (3 -> 4 -> 5 ...), and edits itself in place."""
    if not tag_id:
        return
    game = upsert_game(tag_id, tag_name(tag_id) or tag_id)
    fixes = unannounced(tag_id)
    open_ = kv_get(f'offer:{tag_id}')
    if open_:
        pid = int(open_)
        p = get_pending(pid)
        if p and p.get('messageId'):
            return await refresh_draft(pid, p, game, fixes)
        del_pending(pid)  # stale draft from before live updates existed
        kv_del(f'offer:{tag_id}')
    if len(fixes) < max(game['threshold'], game['next_offer_at']):
        return
    bugs, lines, sugs, sug_lines = await polish_fixes(tag_id, game)
    owners = owners_for(tag_id, game['name'])
    pid = create_pending({'tagId': tag_id, 'bugIds': [f['id'] for f in bugs], 'bugfixes': lines,
                          'newIds': [f['id'] for f in sugs], 'newLines': sug_lines, 'updates': [],
                          'version': '', 'owners': owners, 'offer': True})
    t = await dev_thread(owners[0] if owners else 'unclaimed', True)
    if not t:
        return
    p = get_pending(pid)
    payload = await draft_payload(pid)
    payload['allowed_mentions'] = allowed(users=owners)
    sent = await t.send(**payload)
    set_pending(pid, {**p, 'channelId': str(t.id), 'messageId': str(sent.id)})
    kv_set(f'offer:{tag_id}', pid)


async def _merge(ids, lines, current, game, suggestion):
    """Brings one list of ids and its lines up to date: new ones are added, reopened ones leave. Returns (ids, lines, changed)."""
    have = set(ids)
    fresh = [f for f in current if f['id'] not in have]
    gone = [i for i in ids if not any(f['id'] == i for f in current)]
    ids, lines = list(ids), list(lines)
    if gone and len(lines) == len(ids):  # reopened ones leave the draft (only when lines still line up)
        for i in gone:
            k = ids.index(i)
            del ids[k]
            del lines[k]
    else:
        ids = [i for i in ids if i not in gone]
    if fresh:
        lines.extend(await _lines(game['name'], fresh, suggestion))  # manual edits to older lines are kept, new ones are appended
        ids.extend(f['id'] for f in fresh)
    return ids, lines, bool(fresh or gone)


async def refresh_draft(pid, p, game, fixes):
    bugs, sugs = split_kinds(fixes)
    bug_ids, bugfixes, c1 = await _merge(p['bugIds'], p['bugfixes'], bugs, game, False)
    new_ids, new_lines, c2 = await _merge(p.get('newIds', []), p.get('newLines', []), sugs, game, True)
    if not (c1 or c2):
        return
    nxt = {**p, 'bugIds': bug_ids, 'bugfixes': bugfixes, 'newIds': new_ids, 'newLines': new_lines}
    set_pending(pid, nxt)
    ch = await fetch_channel(p['channelId'])
    try:
        msg = await ch.fetch_message(int(p['messageId'])) if ch else None
    except Exception:
        msg = None
    if not msg:
        del_pending(pid)
        kv_del(f"offer:{p['tagId']}")
        return
    payload = await draft_payload(pid)
    try:
        await msg.edit(**edit_kw(payload))
    except discord.HTTPException:  # an offer made before the new look is an old-style message: a new one replaces it
        sent = await ch.send(**{**payload, 'allowed_mentions': NO_MENTIONS})
        set_pending(pid, {**nxt, 'messageId': str(sent.id)})
        try:
            await msg.delete()
        except discord.HTTPException:
            pass


_busy = set()  # drafts being posted right now: a double click must not post twice


def _fresh(ids):
    """The ids that were not announced yet (an older draft of the same fixes may have been posted meanwhile)."""
    return [i for i in ids if (b := bug_by_id(i)) and not b['announced']]


async def post_announcement(pending_id, ping=False):
    if pending_id in _busy:
        return {'ok': False, 'msg': 'This update is being posted already.'}
    _busy.add(pending_id)
    try:
        return await _post_announcement(pending_id, ping)
    finally:
        _busy.discard(pending_id)


async def _post_announcement(pending_id, ping=False):
    """Posts the draft in the game's announcement channel, pinging the updates role only when `ping` is true.
    Returns {'ok', 'url'} or {'ok': False, 'msg'}."""
    p = get_pending(pending_id)
    if not p:
        return {'ok': False, 'msg': 'This draft no longer exists.'}
    bug_lines, new_lines = chosen(p)
    if not bug_lines and not p['updates'] and not new_lines:
        return {'ok': False, 'msg': 'Nothing to post. Tick a fix, or press Edit and write an update.'}
    if (chosen_ids(p)[0] or chosen_ids(p)[1]) and not _fresh(chosen_ids(p)[0] + chosen_ids(p)[1]) and not p['updates']:
        return {'ok': False, 'msg': 'These fixes were already posted in an update.'}
    game = get_game(p['tagId'])
    ch = await fetch_channel(game.get('announce_channel_id') or cfg.updates_id)
    if not ch:
        return {'ok': False, 'msg': 'Set an announcement channel first with `/config set`.'}
    role = ping_role(game) if ping else None
    from bot.features.games.cards import mentions, released_row_for, update_card
    poster = (p.get('owners') or [None])[0]
    view, files = update_card(game, released_row_for(game['name']), bug_lines, list(p['updates']), new_lines, p.get('version') or '', f'<@&{role}>' if role else None, poster=poster)
    sent = await ch.send(view=view, files=files, allowed_mentions=mentions(ch, role))
    b_ids, n_ids = chosen_ids(p)
    ids = b_ids + n_ids  # what was not ticked stays pending for the next update
    for i in ids:
        update_bug(i, {'announced': 1})
    from bot.features.bugs.fixes import tell_released
    asyncio.ensure_future(tell_released(b_ids, sent.jump_url))  # the reporters hear about their fix now that it is released
    run('INSERT INTO announcements(tag_id,game_name,posted_at,url,bug_ids,message_id,channel_id,payload) VALUES(?,?,?,?,?,?,?,?)',
        p['tagId'], game['name'], now(), sent.jump_url, json.dumps(ids), str(sent.id), str(ch.id),
        json.dumps({'bugfixes': bug_lines, 'updates': list(p['updates']) + new_lines, 'changes': list(p['updates']), 'new': new_lines,
                    'version': p.get('version') or '', 'ping_role': role, 'poster': poster}))
    schedule_boards()
    del_pending(pending_id)
    other = kv_get(f"offer:{p['tagId']}")
    if other and int(other) != pending_id:
        del_pending(int(other))  # its buttons now say the draft is gone
    kv_del(f"offer:{p['tagId']}")
    upsert_game(p['tagId'], game['name'], {'next_offer_at': 0})
    return {'ok': True, 'url': sent.jump_url}


async def merge_announcement(pending_id):
    if pending_id in _busy:
        return {'ok': False, 'msg': 'This update is being posted already.'}
    _busy.add(pending_id)
    try:
        return await _merge_announcement(pending_id)
    finally:
        _busy.discard(pending_id)


async def _merge_announcement(pending_id):
    """Adds the ticked items to the game's last announcement (one embed instead of several posts in a row). No new ping."""
    p = get_pending(pending_id)
    if not p:
        return {'ok': False, 'msg': 'This draft no longer exists.'}
    bug_lines, new_lines = chosen(p)
    if not bug_lines and not p['updates'] and not new_lines:
        return {'ok': False, 'msg': 'Nothing to add. Tick a fix, or press Edit and write an update.'}
    if (chosen_ids(p)[0] or chosen_ids(p)[1]) and not _fresh(chosen_ids(p)[0] + chosen_ids(p)[1]) and not p['updates']:
        return {'ok': False, 'msg': 'These fixes were already posted in an update.'}
    game = get_game(p['tagId'])
    row = recent_announcement(p['tagId'])
    ch = await fetch_channel(row['channel_id']) if row else None
    try:
        msg = await ch.fetch_message(int(row['message_id'])) if ch else None
    except Exception:
        msg = None
    if not msg:
        return {'ok': False, 'msg': 'I could not find the earlier update any more. Post a new one.'}
    old = json.loads(row['payload'])
    bugfixes = old['bugfixes'] + [l for l in bug_lines if l not in old['bugfixes']]
    changes_old = old['changes'] if 'changes' in old else old['updates']
    new_old = old.get('new', [])
    changes = changes_old + [l for l in p['updates'] if l not in changes_old]
    new = new_old + [l for l in new_lines if l not in new_old]
    updates = changes + new
    version = p.get('version') or old.get('version') or ''
    fresh = [l for l in bug_lines if l not in old['bugfixes']] + [l for l in p['updates'] if l not in changes_old] + [l for l in new_lines if l not in new_old]
    # an update posted in the old embed look becomes the card in place; the lines this addition brought get a 🆕
    from bot.features.games.cards import released_row_for, update_card
    view, files = update_card(game, released_row_for(game['name']), mark(bugfixes, fresh), mark(changes, fresh), mark(new, fresh), version, f"<@&{old['ping_role']}>" if old.get('ping_role') else None, poster=old.get('poster'))
    await msg.edit(content=None, embeds=[], view=view, attachments=files, allowed_mentions=NO_MENTIONS)
    b_ids, n_ids = chosen_ids(p)
    for i in b_ids + n_ids:
        update_bug(i, {'announced': 1})
    from bot.features.bugs.fixes import tell_released
    asyncio.ensure_future(tell_released(b_ids, msg.jump_url))
    run('UPDATE announcements SET bug_ids=?, payload=? WHERE id=?',
        json.dumps(json.loads(row['bug_ids'] or '[]') + b_ids + n_ids), json.dumps({'bugfixes': bugfixes, 'updates': updates, 'changes': changes, 'new': new, 'version': version, 'ping_role': old.get('ping_role'), 'poster': old.get('poster'), 'fresh': fresh}), row['id'])
    schedule_boards()
    del_pending(pending_id)
    other = kv_get(f"offer:{p['tagId']}")
    if other and int(other) != pending_id:
        del_pending(int(other))  # its buttons now say the draft is gone
    kv_del(f"offer:{p['tagId']}")
    upsert_game(p['tagId'], game['name'], {'next_offer_at': 0})
    return {'ok': True, 'url': msg.jump_url, 'merged': True}


def snooze(pending_id):
    p = get_pending(pending_id)
    if not p:
        return
    upsert_game(p['tagId'], get_game(p['tagId'])['name'], {'next_offer_at': len(unannounced(p['tagId'])) + 3})
    del_pending(pending_id)
    kv_del(f"offer:{p['tagId']}")
