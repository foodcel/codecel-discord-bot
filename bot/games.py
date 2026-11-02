"""Released / unreleased games, rows sorted by dev. The games in development come from the bounty-board claims.
A dev marks a game released with /release (stored here, so it stays after the bounty-board drops it).
Names typed on the bounty-board ("YOU SHOULD MAKE DELTARUNE PLEASE") are turned into proper titles by Claude once and cached."""
import json
import re
from datetime import datetime, timezone

from discord import app_commands

from .ai import clean_game_names
from .bounty import get_claims
from .ctx import ctx, fetch_channel
from .db import all_, kv_del, kv_get, kv_set, now, one, run
from .devboard import on_boards_refreshed
from .perms import level, owns
from .ui import E, EM, ZW, columns, cut, describe, flat, head, lkey, RULE, gap

FOOT_UNRELEASED = '\n'.join([
    '/claim · take a game (add its Steam page with link:)',
    '/progress · set how far it is and if you are working on it',
    '/gamelink · change a game\'s link',
    '/release testing · put it in the testing phase',
    '/release new · the game is out (paste its Roblox link)',
    '/release quiet · add it without announcing it',
    '/unclaim · drop a game you claimed',
])
FOOT_TESTING = '\n'.join([
    '/release testing · put a game in testing, or send it back to development',
    '/release new · testing is done: the game is out',
    '/bug · testers report them in the testing channel',
])
FOOT_RELEASED = '\n'.join([
    '/release edit · fix a released game\'s title, link, image or credits',
    '/gamelink · change a released game\'s Roblox link',
    '/unrelease · move a game back to unreleased',
])
NONE = '__none__'  # value of the "nothing here" autocomplete entry


def key(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def http(u):
    return bool(re.match(r'^https?://', u or '', re.I))


def owner_ids(g):
    o = g.get('owners')
    if isinstance(o, list):
        return o
    return [x for x in str(o or '').split(',') if x]


# ---- proper game names ----
def tidy(s):
    t = re.sub(r'\s+', ' ', re.sub(r'\b(please|pls|bro)\b', '', str(s), flags=re.I)).strip()
    if t == t.upper() and len(t) > 5:
        return re.sub(r'\b\w', lambda m: m.group().upper(), t.lower())
    return t


def clean_name(raw):
    r = one('SELECT clean FROM game_names WHERE key=?', key(raw))
    return r['clean'] if r else tidy(raw)


def shorten(t):
    """Keeps a title inside the column: drops a leading "The" and a "Call of Duty:" prefix when it is too long."""
    s = str(t).strip()
    if len(s) <= 19:
        return s
    s = re.sub(r'^(call of duty|cod):\s*', '', s, flags=re.I)
    return re.sub(r'^(the|a)\s+', '', s, flags=re.I)


async def ensure_names():
    """Asks Claude for the proper title of every name that has none yet. A failed call is retried next time."""
    raws = list(dict.fromkeys([c['name'] for c in get_claims()] + [r['name'] for r in all_('SELECT name FROM game_status')]))
    missing = [r for r in raws if not one('SELECT 1 FROM game_names WHERE key=?', key(r))][:60]
    if not missing:
        return
    titles = None
    try:
        titles = await clean_game_names(missing)
    except Exception as e:
        print('cleanGameNames', e)
    if not titles or len(titles) != len(missing):
        return
    for raw, title in zip(missing, titles):
        run('INSERT OR IGNORE INTO game_names(key,raw,clean,manual) VALUES(?,?,?,0)', key(raw), raw, cut(shorten(title or tidy(raw)), 40))


# ---- the lists ----
def game_lists():
    rows = all_('SELECT * FROM game_status')
    released = sorted((r for r in rows if r['status'] == 'released'), key=lambda r: -(r['released_at'] or 0))
    released_keys = {r['key'] for r in released}
    testing_rows = {r['key']: r for r in rows if r['status'] == 'testing' and r['key'] not in released_keys}
    unreleased = []
    testing = {}
    seen = set()
    sources = {r['key']: r for r in rows}
    for c in get_claims():
        k = key(c['name'])
        seen.add(k)
        if k in testing_rows:  # in the testing phase: shown in its own list, with the owners the board says today
            r = testing_rows[k]
            testing[k] = {'key': k, 'name': c['name'], 'owners': c['owners'], 'since': c['since'], 'source_link': r.get('source_link'), 'link': r.get('link'), 'testing_at': r.get('testing_at')}
            continue
        if k not in released_keys:
            unreleased.append({'key': k, 'name': c['name'], 'owners': c['owners'], 'since': c['since'],
                               'source_link': (sources.get(k) or {}).get('source_link'),
                               'progress': (sources.get(k) or {}).get('progress'), 'working': (sources.get(k) or {}).get('working')})
    # moved back to unreleased after it had left the bounty-board
    for r in rows:
        if r['status'] == 'unreleased' and r['key'] not in seen:
            unreleased.append({'key': r['key'], 'name': r['name'], 'owners': owner_ids(r), 'since': r['since'],
                               'source_link': r['source_link'],
                               'progress': r['progress'], 'working': r['working']})
    for k, r in testing_rows.items():  # in testing after it left the bounty-board
        if k not in testing:
            testing[k] = {'key': k, 'name': r['name'], 'owners': owner_ids(r), 'since': r['since'], 'source_link': r.get('source_link'), 'link': r.get('link'), 'testing_at': r.get('testing_at')}
    return {'released': released, 'unreleased': unreleased, 'testing': sorted(testing.values(), key=lambda g: -(g['testing_at'] or 0))}


# ---- the table ----
async def dev_name(id_):
    try:
        m = ctx.guild.get_member(int(id_)) or await ctx.guild.fetch_member(int(id_))
        return m.display_name
    except Exception:
        return 'Unknown'


async def rows_by_dev(entries):
    """Rows are sorted by dev, so all the games of one dev sit right under each other (dev with most games first).
    A game with two owners shows once under each owner. The dev shows as a mention; 'gap' marks the first row of the next dev."""
    per = {}
    for e in entries:
        for o in (e['owners'] if e['owners'] else ['none']):
            per.setdefault(o, []).append(e)
    devs = []
    for id_, lst in per.items():
        devs.append({'id': id_, 'name': 'No dev' if id_ == 'none' else await dev_name(id_), 'list': lst})
    devs.sort(key=lambda d: (-len(d['list']), lkey(d['name'])))
    out = []
    for n, d in enumerate(devs):
        for k, g in enumerate(sorted(d['list'], key=lambda g: lkey(g['name']))):
            out.append({'dev': '—' if d['id'] == 'none' else f"<@{d['id']}>", 'gap': n > 0 and k == 0, 'first': k == 0, **g})
    return out


GAP_ROW = object()  # marks the blank line between two devs


def table(e, headings, rows):
    """Columns of lines. Game names are cut so no column grows past its share of the embed: that is what keeps
    the columns in the same place in both embeds. A long list is split into several rows of columns (a field holds 1024 characters),
    and the split falls between two devs, never inside one."""
    n = len(headings)
    state = {'chunk': [], 'first': True}
    blank = [ZW] * n

    def size(chunk):
        return [sum(len(r[i]) + 1 for r in chunk) for i in range(n)]

    def emit(chunk):
        columns(e, [{'name': name if state['first'] else ZW, 'lines': [r[i] for r in chunk]} for i, name in enumerate(headings)],
                RULE if state['first'] else '')
        for _ in range(3 - n):  # Discord puts three fields on a row: an empty one keeps the next block of columns on a row of its own
            e.add_field(name=ZW, value=ZW, inline=True)
        state['first'] = False

    for r in rows:
        if r is GAP_ROW:
            if state['chunk']:  # an empty line between two devs (never at the top of a block)
                r = blank
            else:
                continue
        trial = state['chunk'] + [r]
        if state['chunk'] and max(size(trial)) > 1000:
            chunk = state['chunk']
            cuts = [k for k, x in enumerate(chunk) if x is blank]
            if cuts and cuts[-1] > 0:  # carry the dev that is still being written over to the next block of columns
                emit(chunk[:cuts[-1]])
                state['chunk'] = chunk[cuts[-1] + 1:]
            else:
                emit(chunk)
                state['chunk'] = []
        state['chunk'].append(r)
    if state['chunk']:
        emit(state['chunk'])


def bar(percent):
    n = round(percent / 10)
    return f'{chr(0x25B0) * n}{chr(0x25B1) * (10 - n)} {percent}%'


def progress_cell(r):
    """How far a game is, and whether its dev is working on it right now."""
    p, w = r.get('progress'), r.get('working')
    if w == 0:
        return f'⏸ {p}%' if p is not None else '⏸ paused'
    if p is not None:
        return bar(p)
    return '▶ working' if w else '—'


def short_link(u):
    """A Roblox game link without its long name (https://www.roblox.com/games/123456): it opens the same game and keeps the board short."""
    m = re.search(r'roblox\.com/(?:[a-z]{2}/)?games/(\d+)', u or '', re.I)
    return f'https://www.roblox.com/games/{m.group(1)}' if m else u


def tree_rows(rows, second, counts=False):
    """One block per dev: the dev, then the games branching under it (the ones being worked on first), with a blank line between devs.
    `second` makes the text of the second column; `counts` adds "2/7 working" to the dev line."""
    groups = []
    for r in rows:
        if r['first']:
            groups.append([])
        groups[-1].append(r)
    out = []
    for n, g in enumerate(groups):
        if counts:
            g = sorted(g, key=lambda r: 0 if (r.get('working') or (r.get('working') is None and r.get('progress'))) else 1)
        if n:
            out.append(GAP_ROW)
        flagged = [r for r in g if r.get('working') is not None or r.get('progress') is not None]
        active = [r for r in flagged if r.get('working') != 0]
        title = f"{g[0]['dev']} · {len(active)}/{len(g)} working" if counts and flagged else g[0]['dev']
        out.append([title, ZW])
        for k, r in enumerate(g):
            branch = '└─' if k == len(g) - 1 else '├─'
            name = f"[**{cut(r['name'], 18)}**]({short_link(r['link'])})" if http(r['link']) else f"**{cut(r['name'], 18)}**"
            out.append([f'{branch} {name}', second(r)])
    return out


def with_gaps(rows, cells):
    """Table rows, with a blank line between the games of one dev and the next."""
    out = []
    for r in rows:
        if r['gap']:
            out.append(GAP_ROW)
        row = cells(r)
        if not r['first']:  # one mention per dev: a mention is taller than plain text, so one on every row pushes the columns out of line
            row[0] = ZW
        out.append(row)
    return out


def _valid_date(s):
    try:
        datetime.fromisoformat(s)
        return True
    except Exception:
        return False


async def game_embeds(lists=None):
    lists = lists or game_lists()
    rel = await rows_by_dev([{'name': r.get('title') or clean_name(r['name']), 'owners': owner_ids(r), 'at': r['released_at'], 'link': r['link']}
                             for r in lists['released']])
    dev = await rows_by_dev([{'name': clean_name(g['name']), 'owners': g['owners'], 'since': g['since'], 'link': g.get('source_link'),
                             'progress': g.get('progress'), 'working': g.get('working')} for g in lists['unreleased']])

    tst = await rows_by_dev([{'name': clean_name(g['name']), 'owners': g['owners'], 'at': g.get('testing_at'), 'link': g.get('link') or g.get('source_link')}
                             for g in lists.get('testing', [])])

    def n_games(rows):
        return len({r['name'] for r in rows})

    e1 = flat()
    e1.title = head('✅', 'Released games')
    describe(e1, f"{E['fixed']} **{n_games(rel)}** released")
    if rel:
        table(e1, [head(E['game'], 'Games'), head(E['date'], 'Released')], tree_rows(
            rel, lambda r: datetime.fromtimestamp(r['at'] / 1000, timezone.utc).strftime('%Y-%m-%d')))
    else:
        e1.add_field(name=ZW, value='None yet.', inline=False)
    gap(e1)
    e1.set_footer(text=FOOT_RELEASED)

    e2 = flat()
    e2.title = head('🛠️', 'Unreleased games')
    describe(e2, f'🛠️ **{n_games(dev)}** in development')
    if dev:
        table(e2, [head(E['game'], 'Games'), head('📊', 'Progress')], tree_rows(dev, progress_cell, counts=True))
    else:
        e2.add_field(name=ZW, value='None yet.', inline=False)
    gap(e2)
    e2.set_footer(text=FOOT_UNRELEASED)

    e3 = flat()
    e3.title = head('🧪', 'Games in testing')
    describe(e3, f'🧪 **{n_games(tst)}** in testing')
    if tst:
        table(e3, [head(E['game'], 'Games'), head(E['date'], 'Testing since')], tree_rows(
            tst, lambda r: datetime.fromtimestamp(r['at'] / 1000, timezone.utc).strftime('%Y-%m-%d') if r.get('at') else '—'))
    else:
        e3.add_field(name=ZW, value='None right now.', inline=False)
    gap(e3)
    e3.set_footer(text=FOOT_TESTING)
    return [e1, e2, e3]


# ---- the live board message (posted once with /games post, then kept up to date) ----
async def refresh_game_board():
    from . import board
    if board.is_live():  # the bounty board shows the same lists: a progress, link or release change must reach it
        await board.refresh_board()
    try:  # the permanent library (cards.py) lists the released games too
        from .cards import refresh_library
        await refresh_library()
    except Exception as e:
        print('library', repr(e))
    ref = kv_get('gameboard')
    if not ref:
        return
    d = json.loads(ref)
    ch = await fetch_channel(d['channelId'])
    try:
        msg = await ch.fetch_message(int(d['messageId'])) if ch else None
    except Exception:
        msg = None
    if not msg:
        kv_del('gameboard')
        return
    await ensure_names()
    try:
        await msg.edit(embeds=await game_embeds())
    except Exception as e:
        print('game board', e)


async def _refresh_names_and_board():
    # Proper names are made as soon as the bounty-board is read (startup, or when a game is claimed), so the /release list is clean too.
    await ensure_names()
    await refresh_game_board()


on_boards_refreshed(_refresh_names_and_board)


# ---- commands ----
async def autocomplete_games(i, command, focused):
    """Shows the proper name, answers with the typed name (that is what the lists are keyed on)."""
    q = str(focused or '').lower()
    lists = game_lists()
    if command in ('release', 'release-testing'):
        pool = [*lists['unreleased'], *lists['testing']]  # a game in testing can be released too
    elif command == 'progress':
        pool = lists['unreleased']
    elif command in ('unrelease', 'release-edit'):
        pool = lists['released']
    else:
        pool = [*lists['unreleased'], *lists['released']]
    out = [{'name': clean_name(g['name'])[:100], 'value': g['name'][:100]} for g in pool]
    out = [c for c in out if q in c['name'].lower() or q in c['value'].lower()]
    # Discord shows "No options match" for an empty list, which looks broken. Say what is going on instead.
    if not out and not q:
        none = 'No games are released yet' if command == 'unrelease' else 'No games are waiting to be released'
        return await i.response.autocomplete([app_commands.Choice(name=none, value=NONE)])
    await i.response.autocomplete([app_commands.Choice(name=c['name'], value=c['value']) for c in out[:25]])


def _find(name):
    """(key, released game, unreleased game). Matches the typed name, or the proper name shown in the list."""
    k = key(name)
    lists = game_lists()

    def pick(lst):
        return next((g for g in lst if g['key'] == k), None) or next((g for g in lst if key(clean_name(g['name'])) == k), None)

    rel, dev = pick(lists['released']), pick(lists['unreleased']) or pick(lists['testing'])
    found = dev or rel
    return (found['key'] if found else k), rel, dev


async def command_release(i, opts, undo=False):
    reply = i.response.send_message
    name = opts.get('game')
    if name == NONE:
        return await reply('No games are released yet, so there is nothing to move back. Use `/release` first.' if undo
                           else 'No games are waiting to be released.', ephemeral=True)
    k, rel, dev = _find(name)
    g = rel if undo else dev
    if not g:
        return await reply('That game is not in the released list.' if undo
                           else 'That game is not in the unreleased list. Claim it on the bounty-board first.', ephemeral=True)
    if not owns(i.user, owner_ids(g)):
        return await reply('Only the dev who owns this game, or an admin, can change it.', ephemeral=True)
    if undo:
        run("UPDATE game_status SET status='unreleased', released_at=NULL WHERE key=?", k)
    else:
        link = opts.get('link')
        if link and not http(link):
            return await reply('The link must start with http:// or https://', ephemeral=True)
        run("""INSERT INTO game_status(key,name,owners,since,status,released_at,released_by,link) VALUES(?,?,?,?,'released',?,?,?)
            ON CONFLICT(key) DO UPDATE SET status='released', released_at=excluded.released_at, released_by=excluded.released_by,
            link=COALESCE(excluded.link, game_status.link), owners=excluded.owners, name=excluded.name""",
            k, g['name'], ','.join(owner_ids(g)), g.get('since'), now(), str(i.user.id), link or None)
    from . import board
    if board.is_live():  # releasing a game completes its claim on the bounty board, moving it back reopens it
        board.set_completed(g['name'], not undo)
        await board.reload_claims()
    await refresh_game_board()
    shown = clean_name(g['name'])
    return await reply(
        f"{E['warn']} **UNRELEASED**{EM}·{EM}{shown} is back in development." if undo
        else f"{E['fixed']} **RELEASED**{EM}·{EM}{shown} is now in the released list.", ephemeral=True)


def set_source_link(name, owners, since, link):
    """Saves the link shown on an unreleased game (a row is made for a game that has none yet)."""
    run("""INSERT INTO game_status(key,name,owners,since,status,source_link) VALUES(?,?,?,?,'unreleased',?)
        ON CONFLICT(key) DO UPDATE SET source_link=excluded.source_link""", key(name), name, ','.join(owners), since, link)


async def command_gamelink(i, opts):
    """Sets the link shown on a game: the site it is ported from (Steam etc.) while unreleased, its Roblox link once released."""
    reply = i.response.send_message
    name = opts.get('game')
    if name == NONE:
        return await reply('There are no games yet.', ephemeral=True)
    k, rel, dev = _find(name)
    g = dev or rel
    if not g:
        return await reply('I do not know that game. Claim it on the bounty-board first.', ephemeral=True)
    if not owns(i.user, owner_ids(g)):
        return await reply('Only the dev who owns this game, or an admin, can change it.', ephemeral=True)
    link = (opts.get('link') or '').strip()
    if not http(link):
        return await reply('The link must start with http:// or https://', ephemeral=True)
    if dev:
        set_source_link(g['name'], owner_ids(g), g.get('since'), link)
    else:
        run('UPDATE game_status SET link=? WHERE key=?', link, k)
    await refresh_game_board()
    return await reply(f"{E['fixed']} **LINKED**{EM}·{EM}{clean_name(g['name'])} now links to {link}", ephemeral=True)


async def command_progress(i, opts):
    """Says how far an unreleased game is and whether its dev is working on it right now."""
    reply = i.response.send_message
    name = opts.get('game')
    if name == NONE:
        return await reply('No games are waiting to be released.', ephemeral=True)
    k, _, g = _find(name)
    if not g:
        return await reply('That game is not in the unreleased list. Claim it on the bounty-board first.', ephemeral=True)
    if not owns(i.user, owner_ids(g)):
        return await reply('Only the dev who owns this game, or an admin, can change it.', ephemeral=True)
    percent, working = opts.get('percent'), opts.get('working')
    if percent is None and working is None:
        return await reply('Give a percent, or say whether you are working on it.', ephemeral=True)
    if percent is not None and not 0 <= percent <= 100:
        return await reply('The percent must be between 0 and 100.', ephemeral=True)
    if working is None and percent is not None and g.get('working') is None:
        working = True  # giving a percent means it is being worked on
    set_progress(g['name'], owner_ids(g), g.get('since'), percent, None if working is None else int(bool(working)))
    await refresh_game_board()
    now_ = [x for x in game_lists()['unreleased'] if x['key'] == k][0]
    return await reply(f"{E['fixed']} **PROGRESS**{EM}·{EM}{clean_name(g['name'])} {progress_cell(now_)}", ephemeral=True)


def set_progress(name, owners, since, percent, working):
    """Saves how far an unreleased game is and whether it is being worked on (None leaves a value as it is)."""
    run("""INSERT INTO game_status(key,name,owners,since,status,progress,working) VALUES(?,?,?,?,'unreleased',?,?)
        ON CONFLICT(key) DO UPDATE SET progress=COALESCE(excluded.progress, progress), working=COALESCE(excluded.working, working)""",
        key(name), name, ','.join(owners), since, percent, working)


async def command_games(i, sub, opts):
    reply = i.response.send_message
    if level(i.user) != 'admin':
        return await reply('Only admins can use this.', ephemeral=True)
    if sub == 'rename':
        raw = opts.get('game')
        lists = game_lists()
        g = next((x for x in [*lists['unreleased'], *lists['released']] if x['key'] == key(raw)), None)
        if not g:
            return await reply('I do not know that game.', ephemeral=True)
        clean = opts.get('name').strip()
        run('INSERT INTO game_names(key,raw,clean,manual) VALUES(?,?,?,1) ON CONFLICT(key) DO UPDATE SET clean=excluded.clean, manual=1',
            key(raw), g['name'], clean)
        await refresh_game_board()
        return await reply(f'Now shown as **{clean}**.', ephemeral=True)
    await i.response.defer(ephemeral=True, thinking=True)
    await ensure_names()
    old = kv_get('gameboard')
    msg = await i.channel.send(embeds=await game_embeds())
    kv_set('gameboard', json.dumps({'channelId': str(msg.channel.id), 'messageId': str(msg.id)}))
    if old:  # the previous board stops updating, remove it so there is only one
        d = json.loads(old)
        ch = await fetch_channel(d['channelId'])
        try:
            m = await ch.fetch_message(int(d['messageId'])) if ch else None
            if m:
                await m.delete()
        except Exception:
            pass
    return await i.edit_original_response(content='Posted. It updates by itself when a game is released or claimed.')
