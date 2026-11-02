"""The fix log: a pinned board with fixed / open counts per game, each game's fixes, and stored transcripts
(taken when a bug is fixed, because the post is deleted 24 hours later)."""
import io
import json
from datetime import datetime

import discord

from .nums import label
from .components import button, make_view, select
from .ctx import ctx, fetch_channel
from .db import DATA_DIR, all_, bug_by_id, kv_get, kv_set
from .devboard import on_boards_refreshed
from .env import cfg
from .transcript import bug_bundle, pack, plain_md, upload_limit
from .ui import E, EM, EN, GAP, columns, cut, describe, flat, head, lkey, section

PER_PAGE = 8
ARCHIVE = DATA_DIR / 'archive'


def _game_where(tag):
    if tag == 'all':
        return '1=1', []
    if tag == 'none':
        return 'game_tag_id IS NULL', []
    return 'game_tag_id = ?', [tag]


def _zip_path(id_):
    return ARCHIVE / f'bug-{id_}.zip'


def _md_path(id_):
    return ARCHIVE / f'bug-{id_}.md'


async def snapshot_bug(bug):
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    part = await bug_bundle(bug)
    if part['assets']:
        _zip_path(bug['id']).write_bytes(pack([part], upload_limit())['zip'])
    else:
        _md_path(bug['id']).write_text(plain_md(part), encoding='utf8')


async def backfill_snapshots():
    """Fixed bugs from before the log existed."""
    for b in all_("SELECT * FROM bugs WHERE status='fixed'"):
        if _zip_path(b['id']).exists() or _md_path(b['id']).exists():
            continue
        try:
            await snapshot_bug(b)
        except Exception as e:
            print('snapshot', b['id'], e)


def stored_transcript(id_):
    if _zip_path(id_).exists():
        return {'file': discord.File(io.BytesIO(_zip_path(id_).read_bytes()), filename=f'bug-{id_}.zip'),
                'note': 'Zip with the transcript, screenshots and videos.'}
    if _md_path(id_).exists():
        return {'file': discord.File(io.BytesIO(_md_path(id_).read_bytes()), filename=f'bug-{id_}.md'), 'note': ''}
    return None


def stats():
    rows = all_("""SELECT game_tag_id tag, MAX(game_name) name,
        SUM(status='fixed') fixed, SUM(status IN ('new','investigating','fixing')) open, MAX(fixed_at) last_fix
        FROM bugs WHERE kind='bug' GROUP BY game_tag_id""")
    ann = {r['tag_id']: r['n'] for r in all_('SELECT tag_id, COUNT(*) n FROM announcements GROUP BY tag_id')}
    out = []
    for r in rows:
        o = {**r, 'tag': r['tag'] or 'none', 'name': r['name'] or 'Unknown game', 'updates': ann.get(r['tag']) or 0}
        if o['fixed'] or o['open'] or o['updates']:
            out.append(o)
    out.sort(key=lambda r: (-r['fixed'], -r['open'], lkey(r['name'])))
    return out


async def _name_of(id_):
    try:
        m = ctx.guild.get_member(int(id_)) or await ctx.guild.fetch_member(int(id_))
        return m.display_name
    except Exception:
        return str(id_ if id_ is not None else '?')


def log_embed():
    rows = stats()
    f_total = sum(r['fixed'] for r in rows)
    o_total = sum(r['open'] for r in rows)
    e = flat()
    e.title = head(E['log'], 'Bug fix log')
    e.set_footer(text='Pick a game below to see its fixes, updates and transcripts.')
    if not rows:
        return describe(e, 'Nothing yet. Fixed bugs and posted updates show up here.')
    describe(e, f"{E['fixed']} **{f_total}** fixed{GAP}{E['open']} **{o_total}** open")
    lst = rows[:20]
    # Discord shows at most 3 columns per row, so last fix lives in the game dropdown (see log_components).
    columns(e, [
        {'name': head(E['game'], 'Game'), 'lines': [f"**{cut(r['name'], 22)}**" for r in lst]},
        {'name': head(E['fixed'], 'Fixed'), 'lines': [str(r['fixed']) for r in lst]},
        {'name': head(E['open'], 'Open'), 'lines': [str(r['open']) for r in lst]},
    ])
    if len(rows) > 20:
        e.add_field(name='​', value=f'…and {len(rows) - 20} more games', inline=False)
    return e


def _short_date(ts_ms):
    d = datetime.fromtimestamp(ts_ms / 1000)
    return f"{d.strftime('%b')} {d.day}"


def log_components():
    rows = stats()
    if not rows:
        return None
    options = [{'label': f"All games ({sum(r['fixed'] for r in rows)} fixed)", 'value': 'all'}] + [{
        'label': f"{r['name']} ({r['fixed']} fixed)"[:100],
        'description': (f"Last fix {_short_date(r['last_fix'])}" if r['last_fix'] else 'No fixes yet') + f" · {r['open']} open",
        'value': r['tag'],
    } for r in rows[:24]]
    return make_view([[select('fl', "Open a game's log", options)]])


async def _ensure():
    tid = kv_get('logthread')
    t = await fetch_channel(tid) if tid else None
    if t:
        if t.archived:
            try:
                await t.edit(archived=False)
            except Exception:
                pass
        return t
    forum = await fetch_channel(cfg.dev_forum_id)
    made = await forum.create_thread(name='📜 Bug fix log', embeds=[log_embed()], view=log_components())
    kv_set('logthread', made.thread.id)
    try:
        await made.thread.edit(pinned=True)
    except Exception:
        pass
    return made.thread


async def refresh_log():
    t = await _ensure()
    if not t:
        return
    try:
        starter = await t.fetch_message(t.id)
        await starter.edit(content=None, embeds=[log_embed()], view=log_components())
    except Exception as e:
        print('log edit', e)


on_boards_refreshed(refresh_log)


async def render_log(tag, page=0):
    """A game's log page (private): same look, same columns. Returns {'content', 'embeds', 'view'}."""
    where, args = _game_where(tag)
    fixes = all_(f"SELECT * FROM bugs WHERE kind='bug' AND status='fixed' AND {where} ORDER BY fixed_at DESC", *args)
    pages = max(1, -(-len(fixes) // PER_PAGE))
    page = min(max(0, page), pages - 1)
    sl = fixes[page * PER_PAGE: page * PER_PAGE + PER_PAGE]
    allst = stats()
    if tag == 'all':
        s = {'fixed': len(fixes), 'updates': sum(r['updates'] for r in allst), 'open': sum(r['open'] for r in allst)}
    else:
        s = next((r for r in allst if r['tag'] == tag), None)
    name = 'All games' if tag == 'all' else ((s or {}).get('name') or (fixes[0]['game_name'] if fixes else None) or 'Unknown game')
    names = [await _name_of(b['fixed_by']) for b in sl]
    if tag == 'all':
        anns = all_('SELECT * FROM announcements ORDER BY id DESC LIMIT 5')
    else:
        anns = all_('SELECT * FROM announcements WHERE tag_id=? ORDER BY id DESC LIMIT 5', tag)
    e = flat()
    e.title = f"{E['log']}{EM}{name.upper()}{EM}·{EM}FIX LOG"
    in_update = f" · {E['update']} = in a posted update" if any(b['announced'] for b in sl) else ''
    e.set_footer(text=f'Page {page + 1} of {pages}{in_update}')
    n_fixed = s['fixed'] if s else len(fixes)
    n_upd = s['updates'] if s else 0
    n_open = s['open'] if s else 0
    describe(e, f"{E['fixed']} **{n_fixed}** fixed{GAP}{E['update']} **{n_upd}** update{'' if n_upd == 1 else 's'}{GAP}{E['open']} **{n_open}** open")
    if sl:
        columns(e, [
            {'name': head(E['fix'], 'Fix'), 'lines': [f"**{label(b)}**{EN}{cut(b['title'], 28)}{f' {E['update']}' if b['announced'] else ''}" for b in sl]},
            {'name': head(E['date'], 'Fixed'), 'lines': [f"<t:{b['fixed_at'] // 1000}:d>" for b in sl]},
            {'name': head(E['game'], 'Game') if tag == 'all' else head(E['user'], 'Fixed by'),
             'lines': [cut(b['game_name'] or 'Unknown', 18) if tag == 'all' else names[i] for i, b in enumerate(sl)]},
        ])
    else:
        section(e, head(E['fix'], 'Fixes'), 'No fixes logged yet.')
    if anns:
        section(e, head(E['update'], 'Updates posted'), '\n'.join(
            f"<t:{a['posted_at'] // 1000}:d> · {len(json.loads(a['bug_ids']))} fixes · [view]({a['url']})"
            f"{f' · {a['game_name']}' if tag == 'all' else ''}" for a in anns))
    rows = [[
        button(f'flp:{tag}:{page - 1}', '◀ Prev', discord.ButtonStyle.secondary, page == 0),
        button('flp:noop:0', f'{page + 1} / {pages}', discord.ButtonStyle.secondary, True),
        button(f'flp:{tag}:{page + 1}', 'Next ▶', discord.ButtonStyle.secondary, page >= pages - 1),
    ]]
    if sl:
        rows.append([select(f'flt:{tag}', '📋 Transcript of a fix',
                            [{'label': f"{label(b)} {b['title']}"[:100], 'value': str(b['id'])} for b in sl])])
    return {'content': None, 'embeds': [e], 'view': make_view(rows)}


async def open_log(i, tag):
    await i.response.defer(ephemeral=True, thinking=True)
    try:
        await i.message.edit(view=log_components())  # resets the dropdown
    except Exception:
        pass
    return await i.edit_original_response(**await render_log(tag, 0))


async def log_page(i, tag, page):
    if tag == 'noop':
        return await i.response.defer()
    await i.response.defer()
    return await i.edit_original_response(**await render_log(tag, int(page)))


async def send_fix_transcript(i, id_):
    await i.response.defer(ephemeral=True, thinking=True)
    t = stored_transcript(int(id_))
    if not t:
        bug = bug_by_id(int(id_))
        return await i.edit_original_response(content=f'No stored transcript for {label(int(id_))}.' if bug else 'That bug is not in the log.')
    return await i.edit_original_response(content=f"Transcript of fix {label(int(id_))}. {t['note']}".strip(), attachments=[t['file']])
