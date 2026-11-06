"""Released / unreleased games, rows sorted by dev. The games in development come from the bounty-board claims.
A dev marks a game released with /release (stored here, so it stays after the bounty-board drops it).
Names typed on the bounty-board ("YOU SHOULD MAKE DELTARUNE PLEASE") are turned into proper titles by Claude once and cached."""
import json
import re
from datetime import datetime, timezone

from discord import app_commands

from bot.discord_ui.card import notice, card
from bot.core.links import roblox_any, web_url
from bot.core.ai import clean_game_names
from bot.features.games.bounty import get_claims
from bot.core.ctx import ctx, fetch_channel
from bot.core.db import all_, kv_del, kv_get, kv_set, now, one, run
from bot.features.bugs.devboard import on_boards_refreshed
from bot.core.perms import level, owns
from bot.discord_ui.ui import E, EM, ZW, cut, lkey

FOOT_UNRELEASED = '\n'.join([
    '/claim new · take a game (add its Steam page with link:)',
    '/progress · set how far it is, if you are working on it, or testing:on',
    '/release new · the game is out (paste its Roblox link)',
    '/release quiet · add it without announcing it',
    '/claim edit · change the link to the original game',
    '/claim drop · drop a game you claimed',
])
FOOT_RELEASED = '\n'.join([
    '/release edit · fix a released game\'s title, link, image or credits',
    '/release undo · move a game back to unreleased',
])
NONE = '__none__'  # value of the "nothing here" autocomplete entry


def key(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def http(u):
    """A real http(s) link (see links.py)."""
    return bool(web_url(u)) and bool(re.match(r'^https?://', u or '', re.I))


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
    unreleased = []
    seen = set()
    sources = {r['key']: r for r in rows}
    for c in get_claims():
        k = key(c['name'])
        seen.add(k)
        if k not in released_keys:
            unreleased.append({'key': k, 'name': c['name'], 'owners': c['owners'], 'since': c['since'],
                               'source_link': (sources.get(k) or {}).get('source_link'),
                               'progress': (sources.get(k) or {}).get('progress'), 'working': (sources.get(k) or {}).get('working'),
                               'testing_at': (sources.get(k) or {}).get('testing_at')})
    # moved back to unreleased after it had left the bounty-board
    for r in rows:
        if r['status'] == 'unreleased' and r['key'] not in seen:
            unreleased.append({'key': r['key'], 'name': r['name'], 'owners': owner_ids(r), 'since': r['since'],
                               'source_link': r['source_link'],
                               'progress': r['progress'], 'working': r['working'], 'testing_at': r.get('testing_at')})
    return {'released': released, 'unreleased': unreleased}


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


NL = chr(10)
GAP_ROW = object()  # marks the blank line between two devs


def bar(percent):
    n = round(percent / 10)
    return f'{chr(0x25B0) * n}{chr(0x25B1) * (10 - n)} {percent}%'


def progress_cell(r):
    """How far a game is, and whether its dev is working on it right now. A game in the testing phase says so instead of a bar."""
    if r.get('testing_at'):
        return '🧪 testing'
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
            out.append([f"{branch} {'🧪 ' if r.get('testing') else ''}{name}", second(r)])  # 🧪: a released game that is still being tested
    return out


def _tree_text(rows):
    """tree_rows as card lines: the dev, then '├─ game · second column', with a blank line between devs."""
    out = []
    for r in rows:
        if r is GAP_ROW:
            out.append('')
            continue
        left, right = r
        out.append(left if not str(right).strip(ZW + ' ') else f'{left} · {right}')
    return NL.join(out)


async def game_embeds(lists=None):
    """The released and the unreleased games as two cards: [(view, files), (view, files)]."""
    lists = lists or game_lists()
    rel = await rows_by_dev([{'name': r.get('title') or clean_name(r['name']), 'owners': owner_ids(r), 'at': r['released_at'], 'link': r['link'], 'testing': bool(r.get('testing_at'))}
                             for r in lists['released']])
    dev = await rows_by_dev([{'name': clean_name(g['name']), 'owners': g['owners'], 'since': g['since'], 'link': g.get('source_link'),
                             'progress': g.get('progress'), 'working': g.get('working'), 'testing_at': g.get('testing_at')} for g in lists['unreleased']])

    def n_games(rows):
        return len({r['name'] for r in rows})
    released = card(f'✅ Released games · {n_games(rel)} released', [
        _tree_text(tree_rows(rel, lambda r: datetime.fromtimestamp(r['at'] / 1000, timezone.utc).strftime('%Y-%m-%d'))) if rel else 'None yet.'],
        FOOT_RELEASED.split(NL))
    unreleased = card(f'🛠️ Unreleased games · {n_games(dev)} in development', [
        _tree_text(tree_rows(dev, progress_cell, counts=True)) if dev else 'None yet.'], FOOT_UNRELEASED.split(NL))
    return [released, unreleased]


# ---- the live board message (posted once with /games post, then kept up to date) ----
async def refresh_game_board():
    from bot.features.games import board
    if board.is_live():  # the bounty board shows the same lists: a progress, link or release change must reach it
        await board.refresh_board()
    try:  # the permanent library (cards.py) lists the released games too
        from bot.features.games.cards import refresh_library
        await refresh_library()
    except Exception as e:
        print('library', repr(e))
    try:  # the board of games in testing (a private channel)
        await refresh_testing_board()
    except Exception as e:
        print('testing board', repr(e))
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
        view, files = (await game_embeds())[1]
        await msg.edit(content=None, embeds=[], view=view, attachments=files)
    except Exception as e:
        print('game board', e)


async def refresh_testing_board():
    """The tester board in #future-games (see testerboard.py)."""
    from bot.features.testers.testerboard import refresh_board
    await refresh_board()


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
    if command == 'release':
        pool = lists['unreleased']
    elif command == 'progress':
        pool = [*lists['unreleased'], *lists['released']]  # testing works for released games too
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

    rel, dev = pick(lists['released']), pick(lists['unreleased'])
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
    await i.response.defer(ephemeral=True, thinking=True)  # the boards below take longer than the 3 seconds Discord waits
    from bot.features.games import board
    if board.is_live():  # releasing a game completes its claim on the bounty board, moving it back reopens it
        board.set_completed(g['name'], not undo)
        await board.reload_claims()
    await refresh_game_board()
    shown = clean_name(g['name'])
    return await i.edit_original_response(view=notice(
        f"{E['warn']} **UNRELEASED**{EM}·{EM}{shown} is back in development." if undo
        else f"{E['fixed']} **RELEASED**{EM}·{EM}{shown} is now in the released list.")[0])


def set_source_link(name, owners, since, link):
    """Saves the link shown on an unreleased game (a row is made for a game that has none yet)."""
    run("""INSERT INTO game_status(key,name,owners,since,status,source_link) VALUES(?,?,?,?,'unreleased',?)
        ON CONFLICT(key) DO UPDATE SET source_link=excluded.source_link""", key(name), name, ','.join(owners), since, link)


async def command_progress(i, opts):
    """Says how far an unreleased game is and whether its dev is working on it right now."""
    reply = i.response.send_message
    name = opts.get('game')
    if name == NONE:
        return await reply('No games are waiting to be released.', ephemeral=True)
    k, rel, dev = _find(name)
    g = dev or rel
    if not g:
        return await reply('That game is not in the list. Claim it on the bounty-board first.', ephemeral=True)
    if not owns(i.user, owner_ids(g)):
        return await reply('Only the dev who owns this game, or an admin, can change it.', ephemeral=True)
    percent, working, testing = opts.get('percent'), opts.get('working'), opts.get('testing')
    link = (opts.get('link') or '').strip()
    if link and link != '-':
        link = roblox_any(link)
        if not link:
            return await reply('That does not look like a Roblox link. Paste the game page, like `https://www.roblox.com/games/123456/Name`.', ephemeral=True)
        if testing != 'on' and not g.get('testing_at'):
            return await reply('The link is for the testers: add `testing:on` too, so the game goes into testing.', ephemeral=True)
    if rel and not dev and (percent is not None or working is not None):
        return await reply('A released game has no progress bar. Use `testing:on` or `testing:off`.', ephemeral=True)
    if percent is None and working is None and testing is None and not link:
        return await reply('Give a percent, say whether you are working on it, put it in testing, or add the testers\' link.', ephemeral=True)
    if percent is not None and not 0 <= percent <= 100:
        return await reply('The percent must be between 0 and 100.', ephemeral=True)
    if working is None and percent is not None and g.get('working') is None:
        working = True  # giving a percent means it is being worked on
    await i.response.defer(ephemeral=True, thinking=True)  # the tag and the boards below take longer than the 3 seconds Discord waits
    reply = i.edit_original_response
    if percent is not None or working is not None:
        set_progress(g['name'], owner_ids(g), g.get('since'), percent, None if working is None else int(bool(working)))
    tag_note = ''
    was_testing = bool(g.get('testing_at'))
    if testing is not None or percent is not None:  # a percent means the game is back in development, unless testing was asked for too
        on = testing == 'on'
        if not one('SELECT 1 FROM game_status WHERE key=?', key(g['name'])):
            set_progress(g['name'], owner_ids(g), g.get('since'), None, None)
        run('UPDATE game_status SET testing_at=? WHERE key=?', now() if on else None, key(g['name']))
        if on:
            tag_note = await _tester_tag_note(clean_name(g['name']))
            if not was_testing:  # newly in testing: a card that pings the Tester role, for a day
                try:
                    from bot.core.env import cfg
                    from bot.features.testers.testerboard import post_card
                    await post_card({'key': key(g['name']), 'name': g.get('title') or clean_name(g['name']), 'owners': owner_ids(g)}, ping=str(i.channel_id) != str(cfg.test_id))
                    tag_note += '\n🙋 Testers were pinged in the future-games channel.'
                except Exception as e:
                    print('tester card', repr(e))
        else:
            run('DELETE FROM game_testers WHERE game_key=?', key(g['name']))
            run('UPDATE game_status SET test_link=NULL WHERE key=?', key(g['name']))  # out of testing: the Play button goes with it
    if link and testing != 'off':
        run('UPDATE game_status SET test_link=? WHERE key=?', None if link == '-' else link, key(g['name']))
        tag_note += '\n▶️ Testers get a Play button for it on the tester board.' if link != '-' else '\n▶️ The Play button was removed.'
        try:
            from bot.features.testers.testerboard import update_card
            await update_card(key(g['name']))  # the "needs testers" card, if it is still up
        except Exception as e:
            print('tester card update', repr(e))
    await refresh_game_board()
    shown = clean_name(g['name'])
    if rel and not dev:
        return await reply(view=notice(f"{E['fixed']} **PROGRESS**{EM}·{EM}{shown} {'🧪 testing' if testing == 'on' else 'not in testing'}{tag_note}")[0])
    now_ = [x for x in game_lists()['unreleased'] if x['key'] == k][0]
    return await reply(view=notice(f"{E['fixed']} **PROGRESS**{EM}·{EM}{shown} {progress_cell(now_)}{tag_note}")[0])


async def _tester_tag_note(name):
    """A game in testing gets its tag in the testers forum at once. Returns a line for the dev."""
    try:
        from bot.features.bugs.tags import ensure_tester_tag
        tag, problem = await ensure_tester_tag(name)
    except Exception as e:
        print('tester tag', repr(e))
        return ''
    return f"\n🏷️ Testers can report it now: its tag **{tag.name}** is ready in the testers forum." if tag else (f'\n⚠️ {problem}' if problem else '')


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
    view, files = (await game_embeds())[1]
    msg = await i.channel.send(view=view, files=files)
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
