"""Update announcements: drafts that grow as bugs get fixed, and the public embed."""
import json
import re
import time

import aiohttp
import discord

from .ai import draft_bug_fixes, draft_new_features, polish_updates
from .bounty import owners_for
from .components import NO_MENTIONS, allowed, button, make_view, select
from .ctx import ctx, fetch_channel
from .db import (bug_by_id, create_pending, del_pending, get_game, get_pending, kv_del, kv_get, kv_set, now, run, set_pending,
                 update_bug, upsert_game, all_)
from .devboard import dev_thread, schedule_boards
from .env import cfg
from .tags import tag_name
from .ui import E, EM, GAP, columns, describe, flat, head, section


def unannounced(tag_id):
    return all_("SELECT * FROM bugs WHERE game_tag_id=? AND status='fixed' AND announced=0 ORDER BY id", tag_id)


async def resolve_icon(game):
    if game.get('icon_url'):
        return game['icon_url']
    m = re.search(r'roblox\.com/(?:[a-z-]+/)?games/(\d+)', game.get('link') or '', re.I)
    if not m:
        return None
    try:
        url = (f'https://thumbnails.roblox.com/v1/places/gameicons?placeIds={m.group(1)}'
               '&returnPolicy=PlaceHolder&size=256x256&format=Png&isCircular=false')
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                data = (await r.json()).get('data') or []
        img = data[0].get('imageUrl') if data else None
        if img:
            upsert_game(game['tag_id'], game['name'], {'icon_url': img})
        return img or None
    except Exception:
        return None


def chunk_lines(lines, mx=1000):
    out = []
    cur = ''
    for l in lines:
        line = f'• {l}\n'
        if len(cur) + len(line) > mx:
            out.append(cur.rstrip())
            cur = ''
        cur += line
    if cur:
        out.append(cur.rstrip())
    return out


def http_url(u):
    return bool(re.match(r'^https?://', u or '', re.I))


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


async def build_embeds(game, bugfixes, updates, version=''):
    """The public announcement: same flat look, game icon top right, game name links to the game."""
    icon = await resolve_icon(game)
    fix_chunks = chunk_lines(bugfixes, 880)
    upd_chunks = chunk_lines(updates, 880)
    first = flat()
    first.title = f"{game['name'].upper()}{f'{EM}·{EM}{version}' if version else ''}"
    describe(first, f"{E['update']} **UPDATE**{GAP}{E['date']} <t:{int(time.time())}:D>"
                    f"{f'{GAP}[PLAY]({game['link']})' if http_url(game.get('link')) else ''}")
    if http_url(game.get('link')):
        first.url = game['link']
    if http_url(icon):
        first.set_thumbnail(url=icon)
    embeds = [first]
    state = {'cur': first, 'size': 300}

    def room(chars):  # start a new embed when this one is full
        if len(state['cur'].fields) >= 22 or state['size'] + chars > 5000:
            state['cur'] = flat()
            embeds.append(state['cur'])
            state['size'] = 0
        state['size'] += chars

    if fix_chunks and upd_chunks:
        # Bug fixes and updates side by side, so the full width of the embed is used.
        for i in range(max(len(fix_chunks), len(upd_chunks))):
            a = fix_chunks[i] if i < len(fix_chunks) else None
            b = upd_chunks[i] if i < len(upd_chunks) else None
            room((len(a) if a else 0) + (len(b) if b else 0) + 120)
            columns(state['cur'], [
                {'name': head(E['open'], 'Bug fixes (cont.)' if i else 'Bug fixes'), 'lines': a.split('\n') if a else ['—']},
                {'name': head('✨', 'Updates (cont.)' if i else 'Updates'), 'lines': b.split('\n') if b else ['—']},
            ], HALF_RULE)
    elif fix_chunks or upd_chunks:
        only = fix_chunks or upd_chunks
        label = ['Bug fixes', E['open']] if fix_chunks else ['Updates', '✨']
        for i, v in enumerate(only):
            room(len(v) + 80)
            section(state['cur'], head(label[1], f'{label[0]} (cont.)' if i else label[0]), v)
    else:
        room(80)
        section(state['cur'], head('✨', 'Update'), 'Small improvements.')
    embeds[-1].set_footer(text='Thanks to everyone who reported these.')
    return embeds[:10]


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
    sure = '✅ confirmed' if time.time() * 1000 - bug['fixed_at'] > 86400000 else '⏳ can still be reopened'
    return f"#{bug['id']} · {done} by {who} {_ago(bug['fixed_at'])} · {sure}"[:100]


def draft_view(id_, p=None):
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
    return make_view(rows)


def ping_role(game):
    """The role an announcement can ping: the game's own, or the updates role."""
    return game.get('ping_role_id') or cfg.updates_role


def confirm_view(id_):
    return make_view([[
        button(f'ann:go:{id_}:ping', 'Post and ping', discord.ButtonStyle.success),
        button(f'ann:go:{id_}:quiet', 'Post without ping', discord.ButtonStyle.secondary),
        button(f'ann:back:{id_}', 'Back', discord.ButtonStyle.secondary),
    ]])


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
    return {
        'content': offer_text(game, p) if p.get('offer') else f"{E['update']} **DRAFT**{EM}·{EM}{game['name']}{warn}{hint}",
        'embeds': await build_embeds(game, bug_lines, list(p['updates']) + new_lines, p.get('version') or ''),
        'view': draft_view(pending_id, p),
        'allowed_mentions': NO_MENTIONS,
    }


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


async def maybe_offer(tag_id):
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
    payload['content'] = offer_text(game, p)
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
    await msg.edit(content=offer_text(game, nxt), embeds=payload['embeds'], view=payload['view'], allowed_mentions=NO_MENTIONS)


def all_updates(p):
    """What the update lists under "new": the lines a dev typed, then the suggestions that were added."""
    return list(p['updates']) + list(p.get('newLines', []))


async def post_announcement(pending_id, ping=False):
    """Posts the draft in the game's announcement channel, pinging the updates role only when `ping` is true.
    Returns {'ok', 'url'} or {'ok': False, 'msg'}."""
    p = get_pending(pending_id)
    if not p:
        return {'ok': False, 'msg': 'This draft no longer exists.'}
    bug_lines, new_lines = chosen(p)
    if not bug_lines and not p['updates'] and not new_lines:
        return {'ok': False, 'msg': 'Nothing to post. Tick a fix, or press Edit and write an update.'}
    game = get_game(p['tagId'])
    ch = await fetch_channel(game.get('announce_channel_id') or cfg.updates_id)
    if not ch:
        return {'ok': False, 'msg': 'Set an announcement channel first with `/config set`.'}
    role = ping_role(game) if ping else None
    sent = await ch.send(
        content=f'<@&{role}>' if role else None,
        embeds=await build_embeds(game, bug_lines, list(p['updates']) + new_lines, p.get('version') or ''),
        allowed_mentions=allowed(roles=[role] if role else []))
    b_ids, n_ids = chosen_ids(p)
    ids = b_ids + n_ids  # what was not ticked stays pending for the next update
    for i in ids:
        update_bug(i, {'announced': 1})
    run('INSERT INTO announcements(tag_id,game_name,posted_at,url,bug_ids) VALUES(?,?,?,?,?)',
        p['tagId'], game['name'], now(), sent.jump_url, json.dumps(ids))
    schedule_boards()
    del_pending(pending_id)
    kv_del(f"offer:{p['tagId']}")
    upsert_game(p['tagId'], game['name'], {'next_offer_at': 0})
    return {'ok': True, 'url': sent.jump_url}


def snooze(pending_id):
    p = get_pending(pending_id)
    if not p:
        return
    upsert_game(p['tagId'], get_game(p['tagId'])['name'], {'next_offer_at': len(unannounced(p['tagId'])) + 3})
    del_pending(pending_id)
    kv_del(f"offer:{p['tagId']}")
