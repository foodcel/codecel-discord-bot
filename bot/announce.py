"""Update announcements: drafts that grow as bugs get fixed, and the public embed."""
import json
import re
import time

import aiohttp
import discord

from .ai import draft_bug_fixes, polish_updates
from .bounty import owners_for
from .components import NO_MENTIONS, allowed, button, make_view
from .ctx import fetch_channel
from .db import (create_pending, del_pending, get_game, get_pending, kv_del, kv_get, kv_set, now, run, set_pending,
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


def draft_view(id_):
    return make_view([[
        button(f'ann:post:{id_}', 'Post', discord.ButtonStyle.success),
        button(f'ann:edit:{id_}', 'Edit', discord.ButtonStyle.primary),
        button(f'ann:later:{id_}', 'Later', discord.ButtonStyle.secondary),
    ]])


def _no_channel_warning():
    return f"\n{E['warn']} **NO CHANNEL YET**{EM}·{EM}set one with `/config set`"


def offer_text(game, p):
    owners = ' '.join(f'<@{o}>' for o in p['owners']) + ' ' if p['owners'] else ''
    return (f"{owners}{E['update']} **{len(p['bugIds'])} FIXES READY**{EM}·{EM}{game['name']}"
            + ('' if (game.get('announce_channel_id') or cfg.updates_id) else _no_channel_warning()))


async def draft_payload(pending_id):
    """What the draft message looks like: {'content', 'embeds', 'view', 'allowed_mentions'}."""
    p = get_pending(pending_id)
    game = get_game(p['tagId'])
    warn = '' if (game.get('announce_channel_id') or cfg.updates_id) else _no_channel_warning()
    return {
        'content': offer_text(game, p) if p.get('offer') else f"{E['update']} **DRAFT**{EM}·{EM}{game['name']}{warn}",
        'embeds': await build_embeds(game, p['bugfixes'], p['updates'], p.get('version') or ''),
        'view': draft_view(pending_id),
        'allowed_mentions': NO_MENTIONS,
    }


async def polish_fixes(tag_id, game):
    """Polishes the pending bug fixes with Claude (falls back to raw titles). Returns (fixes, lines)."""
    fixes = unannounced(tag_id)
    lines = [f['title'] for f in fixes]
    try:
        out = await draft_bug_fixes(game['name'], fixes)
        if len(out) == len(fixes):
            lines = out
    except Exception as e:
        print('draftBugFixes', e)
    return fixes, lines


async def maybe_offer(tag_id):
    """Starts an offer once the game has enough fixes (default 3). While the draft is open it keeps growing
    as more bugs are fixed (3 -> 4 -> 5 ...), and edits itself in place."""
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
    _, lines = await polish_fixes(tag_id, game)
    owners = owners_for(tag_id, game['name'])
    pid = create_pending({'tagId': tag_id, 'bugIds': [f['id'] for f in fixes], 'bugfixes': lines, 'updates': [],
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


async def refresh_draft(pid, p, game, fixes):
    have = set(p['bugIds'])
    fresh = [f for f in fixes if f['id'] not in have]
    gone = [i for i in p['bugIds'] if not any(f['id'] == i for f in fixes)]
    if not fresh and not gone:
        return
    bug_ids = list(p['bugIds'])
    bugfixes = list(p['bugfixes'])
    if gone and len(bugfixes) == len(bug_ids):  # reopened bugs leave the draft (only when lines still line up)
        for i in gone:
            k = bug_ids.index(i)
            del bug_ids[k]
            del bugfixes[k]
    else:
        bug_ids = [i for i in bug_ids if i not in gone]
    if fresh:
        lines = [f['title'] for f in fresh]
        try:
            out = await draft_bug_fixes(game['name'], fresh)
            if len(out) == len(fresh):
                lines = out
        except Exception as e:
            print('draftBugFixes', e)
        bug_ids.extend(f['id'] for f in fresh)
        bugfixes.extend(lines)  # manual edits to older lines are kept, new fixes are appended
    nxt = {**p, 'bugIds': bug_ids, 'bugfixes': bugfixes}
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


async def post_announcement(pending_id):
    """Posts the draft in the game's announcement channel. Returns {'ok', 'url'} or {'ok': False, 'msg'}."""
    p = get_pending(pending_id)
    if not p:
        return {'ok': False, 'msg': 'This draft no longer exists.'}
    game = get_game(p['tagId'])
    ch = await fetch_channel(game.get('announce_channel_id') or cfg.updates_id)
    if not ch:
        return {'ok': False, 'msg': 'Set an announcement channel first with `/config set`.'}
    role = game.get('ping_role_id')
    sent = await ch.send(
        content=f'<@&{role}>' if role else None,
        embeds=await build_embeds(game, p['bugfixes'], p['updates'], p.get('version') or ''),
        allowed_mentions=allowed(roles=[role] if role else []))
    for i in p['bugIds']:
        update_bug(i, {'announced': 1})
    run('INSERT INTO announcements(tag_id,game_name,posted_at,url,bug_ids) VALUES(?,?,?,?,?)',
        p['tagId'], game['name'], now(), sent.jump_url, json.dumps(p['bugIds']))
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
