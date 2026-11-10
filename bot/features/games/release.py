"""/release new and /release edit. A dev pastes the Roblox link of a finished game: the bot fetches the game's name, creator and hero image
from Roblox, credits the dev who owns it, and takes the original studio from the Steam page given on /claim (or the dev's own words).
Only text and the Roblox hero image are used: nothing is taken from Steam but the studio name."""
import asyncio
import json
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

from bot.core.ctx import fetch_channel
from bot.core.db import create_pending, now, one, run
from bot.core.env import cfg
from bot.features.games.games import NONE, _find, clean_name, owner_ids, refresh_game_board
from bot.core.links import roblox_game, roblox_place
from bot.core.perms import level, owns
from bot.discord_ui.ui import E, EM
from bot.core.env import ROOT

STEAM_APP = re.compile(r'store\.steampowered\.com/app/(\d+)', re.I)
HERO_DIR = ROOT / 'data' / 'heroes'
MAX_IMAGE = 8 * 1024 * 1024
NL = chr(10)


def _get(url, timeout=15):
    """Plain urllib in a thread: aiohttp hangs on Roblox from the VM while this answers in a fraction of a second."""
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'codecel-bot'}), timeout=timeout) as r:
        return r.read()


async def _json(url):
    try:
        return json.loads(await asyncio.to_thread(_get, url))
    except Exception as e:
        print('release fetch', url[:60], repr(e))
        return None


async def roblox_info(link):
    """{'place_id', 'name', 'creator', 'hero_url'} from a Roblox game link; None when it is not one. Fields Roblox does not answer stay empty."""
    place = roblox_place(link)
    if not place:
        return None
    out = {'place_id': place, 'name': None, 'creator': None, 'hero_url': None, 'icon_url': None}
    u = await _json(f'https://apis.roblox.com/universes/v1/places/{out["place_id"]}/universe')
    uid = (u or {}).get('universeId')
    if not uid:
        i = await _json(f'https://thumbnails.roblox.com/v1/places/gameicons?placeIds={out["place_id"]}&returnPolicy=PlaceHolder&size=512x512&format=Png&isCircular=false')
        out['icon_url'] = ((((i or {}).get('data')) or [{}])[0]).get('imageUrl')
        out['hero_url'] = out['icon_url']
        return out
    g = await _json(f'https://games.roblox.com/v1/games?universeIds={uid}')
    row = ((g or {}).get('data') or [{}])[0]
    out['name'] = row.get('name')
    out['creator'] = (row.get('creator') or {}).get('name')
    i = await _json(f'https://thumbnails.roblox.com/v1/games/icons?universeIds={uid}&size=512x512&format=Png&isCircular=false')
    first = (((i or {}).get('data')) or [{}])[0]
    if first.get('state') == 'Completed':
        out['icon_url'] = first.get('imageUrl')
    for url in (f'https://thumbnails.roblox.com/v1/games/multiget/thumbnails?universeIds={uid}&size=768x432&format=Png&isCircular=false',
                f'https://thumbnails.roblox.com/v1/games/icons?universeIds={uid}&size=512x512&format=Png&isCircular=false'):
        t = await _json(url)
        data = (t or {}).get('data') or [{}]
        first = data[0]
        first = ((first.get('thumbnails') or [None])[0]) if 'thumbnails' in first else first
        if first and first.get('state') == 'Completed' and first.get('imageUrl'):
            out['hero_url'] = first['imageUrl']
            break
    out['hero_url'] = out['hero_url'] or out['icon_url']
    return out


async def steam_studio(link):
    """The studio named on the game's Steam page (the link given on /claim); None when the link is not a Steam page or has none."""
    m = STEAM_APP.search(link or '')
    if not m:
        return None
    d = await _json(f'https://store.steampowered.com/api/appdetails?appids={m.group(1)}&filters=developers')
    devs = (((d or {}).get(m.group(1)) or {}).get('data') or {}).get('developers') or []
    return ' / '.join(devs[:2]) or None


def _exists(url):
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'codecel-bot'})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def _norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s or '').lower())


async def steam_art(source_link, name):
    """The original game's pictures on Steam: its cover (for the small picture) and its wide art (for the new-game card).
    The Steam link given on /claim is used; without one the Steam store is searched for the exact name. Nothing found = empty fields."""
    out = {'art_url': None, 'art_hero_url': None, 'studio': None}
    m = STEAM_APP.search(source_link or '')
    app = m.group(1) if m else None
    if not app and name:
        d = await _json('https://store.steampowered.com/api/storesearch/?term=' + urllib.parse.quote(name) + '&l=english&cc=US')
        hit = next((i for i in (d or {}).get('items', []) if i.get('type') == 'app' and _norm(i.get('name')) == _norm(name)), None)
        app = str(hit['id']) if hit else None
    if not app:
        return out
    base = f'https://cdn.cloudflare.steamstatic.com/steam/apps/{app}/'
    for field, files in (('art_url', ('library_600x900.jpg', 'header.jpg')), ('art_hero_url', ('library_hero.jpg', 'header.jpg'))):
        for f in files:
            if await asyncio.to_thread(_exists, base + f):
                out[field] = base + f
                break
    out['studio'] = await steam_studio(f'https://store.steampowered.com/app/{app}/')
    return out


async def save_hero(k, att):
    """Keeps a picture the dev attached (their own hero image). Returns the saved path, or an error text starting with '!'."""
    if not att or not str(att.get('content_type') or '').startswith('image/'):
        return '!The hero image must be a picture.'
    if (att.get('size') or 0) > MAX_IMAGE:
        return '!The hero image must be under 8 MB.'
    ext = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp'}.get(att['content_type'].split(';')[0], 'png')
    HERO_DIR.mkdir(parents=True, exist_ok=True)
    safe = _safe(k)
    path = HERO_DIR / f'{safe}.{ext}'
    for old in HERO_DIR.glob(f'{safe}.*'):
        old.unlink(missing_ok=True)
    try:
        path.write_bytes(await asyncio.to_thread(_get, att['url'], 30))
    except Exception as e:
        print('hero save', repr(e))
        return '!I could not download that picture.'
    return str(path)


def summary(row, shown):
    hero = 'your picture' if row.get('hero_file') else ('from Roblox' if row.get('hero_url') else 'none yet')
    lines = [
        f"{shown}" + (f" (on Roblox as **{row['roblox_name']}**)" if row.get('roblox_name') and row['roblox_name'] != shown else ''),
        f"Ported by <@{owner_ids(row)[0]}>" + (f" · Roblox creator **{row['creator']}**" if row.get('creator') else ''),
        f"Original: **{row['original_name'] or shown}**" + (f" by **{row['studio']}**" if row.get('studio') else ' (studio not found: add it with `/release edit studio:`)'),
        f'Hero image: {hero}' + ('' if row.get('hero_file') or row.get('hero_url') else ' (add one with `/release edit image:`)'),
    ]
    return NL.join(f'{EM}{ln}' if n else ln for n, ln in enumerate(lines))


def _safe(k):
    return re.sub(r'[^a-z0-9]+', '-', k.lower()).strip('-')[:60] or 'game'


def finalize_hero(k, draft_path):
    """A picture saved with a draft becomes the game's hero image when the draft is posted. Returns the final path, or None."""
    if not draft_path or not Path(draft_path).exists():
        return None
    HERO_DIR.mkdir(parents=True, exist_ok=True)
    safe = _safe(k)
    dest = HERO_DIR / f'{safe}{Path(draft_path).suffix}'
    for old in HERO_DIR.glob(f'{safe}.*'):
        old.unlink(missing_ok=True)
    shutil.move(draft_path, dest)
    return str(dest)


def in_test_channel(i):
    return str(getattr(i, 'channel_id', None) or getattr(getattr(i, 'channel', None), 'id', '')) == str(cfg.test_id)


async def command_release_new(i, opts, quiet=False):
    """/release new game link [image] [studio] [original] [ping] [note]. quiet (/release quiet): nothing is announced: no card, no ping, and the
    game can never get a card later. Nothing is posted by the command itself: the dev gets a preview with Post / Edit / Cancel buttons."""
    reply = i.response.send_message
    name = opts.get('game')
    if name == NONE:
        return await reply('No games are waiting to be released.', ephemeral=True)
    k, rel, dev = _find(name)
    if not dev:
        return await reply('That game is already released. Use `/release edit` to change it.' if rel
                           else 'That game is not in the unreleased list. Claim it on the bounty-board first.', ephemeral=True)
    if not owns(i.user, owner_ids(dev)):
        return await reply('Only the dev who owns this game, or an admin, can release it.', ephemeral=True)
    link = (opts.get('link') or '').strip()
    if not link:  # a game released before (then moved back) keeps the Roblox link it had
        link = ((one('SELECT link FROM game_status WHERE key=?', k) or {}).get('link') or '').strip()
    link = roblox_game(link)
    if not link:
        return await reply('Paste the Roblox game page link: it looks like https://www.roblox.com/games/123456/Name', ephemeral=True)
    ping = 'none' if quiet else (opts.get('ping') or 'everyone')
    test = in_test_channel(i)
    await i.response.defer(ephemeral=True, thinking=True)
    info = await roblox_info(link) or {}
    hero_file = None
    if opts.get('image') and not test:
        hero_file = await save_hero(k + '-draft', opts['image'])
        if hero_file.startswith('!'):
            return await i.edit_original_response(content=hero_file[1:])
    original = (opts.get('original') or '').strip() or clean_name(dev['name'])
    art = await steam_art(dev.get('source_link'), original)
    studio = (opts.get('studio') or '').strip() or await steam_studio(dev.get('source_link')) or art['studio']
    mine = (opts.get('image') or {}).get('url') if opts.get('image') else None
    from bot.features.games import reldraft
    from bot.features.games.cards import _hero
    await asyncio.to_thread(_hero, reldraft.draft_row({'key': k, 'name': dev['name'], 'owners': '', 'link': link, 'info': info, 'art': art, 'studio': studio,
                                                       'original': original, 'hero_file': hero_file, 'mine': mine if test else None}))  # the cropped picture is made now, not at Post
    pid = create_pending({'kind': 'release', 'user': str(i.user.id), 'game': name, 'key': k, 'name': dev['name'], 'owners': ','.join(owner_ids(dev)),
                          'since': dev.get('since'), 'quiet': quiet, 'link': link, 'info': info, 'art': art, 'studio': studio, 'original': original,
                          'note': (opts.get('description') or '').strip()[:140] or None, 'ping': ping, 'title': None, 'hero_file': hero_file,
                          'mine': mine if test else None, 'test': test})
    return await i.edit_original_response(**reldraft.payload(pid))


async def commit_release(i, d):
    """The Post button of a release draft. Returns (done, text): text is what to show, or why it could not be posted yet (the draft stays)."""
    from bot.features.bugs.guard import card_limit_reason, cooldown_left
    from bot.features.bugs.guard import note as log_note
    from bot.features.games.reldraft import draft_row
    k, quiet, ping, test = d['key'], d['quiet'], d['ping'], d['test']
    if (ping == 'releases' and not cfg.releases_role) or (ping == 'updates' and not cfg.updates_role):
        return False, f'The {ping.title()} role is not set up yet, so I cannot ping it. Pick another ping, or ask an admin.'
    admin = level(i.user) == 'admin'
    wait = 0 if (admin or test or quiet) else cooldown_left(i.user.id)
    if wait:
        return False, f'Slow down: wait {wait // 60 + 1} more minute(s) before the next `/release new`.'
    row = draft_row(d)
    shown = clean_name(d['name'])
    if test:  # a dry run: draw the card and the library row in the test channel, change nothing
        return True, await preview(row, shown, '/release quiet' if quiet else '/release new', (card_limit_reason(i.user.id, admin) if ping != 'none' else None) or '', ping, quiet)
    _, rel, dev = _find(d['game'])
    if not dev:
        return True, 'That game is already released.'
    hero_file = finalize_hero(k, d.get('hero_file'))
    info, art = d['info'], d['art']
    run("""INSERT INTO game_status(key,name,owners,since,status,released_at,released_by,link,place_id,roblox_name,creator,hero_url,icon_url,hero_file,studio,original_name,notes)
        VALUES(?,?,?,?,'released',?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(key) DO UPDATE SET status='released', released_at=excluded.released_at, released_by=excluded.released_by, link=excluded.link,
        owners=excluded.owners, name=excluded.name, place_id=excluded.place_id, roblox_name=excluded.roblox_name, creator=excluded.creator,
        hero_url=excluded.hero_url, icon_url=excluded.icon_url, hero_file=COALESCE(excluded.hero_file, game_status.hero_file), studio=excluded.studio, original_name=excluded.original_name, notes=COALESCE(excluded.notes, game_status.notes)""",
        k, dev['name'], ','.join(owner_ids(dev)), dev.get('since'), now(), str(i.user.id), d['link'], info.get('place_id'), info.get('name'),
        info.get('creator'), info.get('hero_url'), info.get('icon_url'), hero_file, d['studio'], d['original'], d['note'])
    run('UPDATE game_status SET art_url=?, art_hero_url=?, title=? WHERE key=?', art['art_url'], art['art_hero_url'], d.get('title'), k)
    from bot.features.games import board
    if board.is_live():  # releasing a game completes its claim on the bounty board
        board.set_completed(dev['name'], True)
        await board.reload_claims()
    await refresh_game_board()
    row = _row(k)
    from bot.features.games.cards import post_new_game_card, test_channel
    warn = ''
    if quiet:  # nothing is announced, and it can never get a card later
        run('UPDATE game_status SET card_at=? WHERE key=?', now(), k)
        return True, f"🔇 **ADDED QUIETLY**{EM}·{EM}{summary(row, shown)}{warn}\nNo card and no ping: it is only in the library and on the boards."
    log_note(i.user.id, 'release')
    why_not = card_limit_reason(i.user.id, admin) if ping != 'none' else None
    why_not = why_not or ('this game already had its new-game card' if row.get('card_at') else None)
    blocked = f'ℹ️ The game is released, but no new-game card was posted: {why_not}. An admin can post it.' if why_not else ''
    try:
        sent = None if why_not else await post_new_game_card(row, ping)
        if sent and ping != 'none':
            log_note(i.user.id, 'card')
        if sent:
            run('UPDATE game_status SET card_at=? WHERE key=?', now(), k)
        if sent and ping == 'everyone' and not test_channel(sent.channel) and not sent.mention_everyone:
            warn += NL + "⚠️ The card is up, but Discord did not register the @everyone ping. Ask an admin to check the bot's Mention Everyone permission."
    except Exception as e:
        print('new game card', repr(e))
        warn += NL + "⚠️ The game is released, but I could not post its new-game card."
    return True, f"{E['fixed']} **RELEASED**{EM}·{EM}{summary(row, shown)}{warn}{(NL + blocked) if blocked else ''}"


async def preview(row, shown, what, note='', ping='everyone', quiet=False):
    """Test channel: nothing is saved and nothing goes to the real boards or #games. The card and the library row are drawn here instead."""
    import discord
    from bot.features.games.cards import games_page, new_game_card, ping_target
    ch = await fetch_channel(cfg.test_id)
    none = discord.AllowedMentions.none()
    if not quiet:  # a quiet release has no card
        view, files = new_game_card(row, ping_target(ping)[0])
        await ch.send(view=view, files=files, allowed_mentions=none)
    view2, files2 = games_page([row], False, False)
    await ch.send(view=view2, files=files2, allowed_mentions=none)
    return f"🧪 **TEST**{EM}·{EM}{what}. Nothing was saved, and nothing was posted in #games. It is in <#{cfg.test_id}>:\n{summary(row, shown)}" + (NL + '🛡️ In a real release: ' + note if note else '')


def _row(k):
    return one('SELECT * FROM game_status WHERE key=?', k)


async def command_release_edit(i, opts):
    """/release edit game [title] [link] [image] [studio] [original] [online] [note]: only what is given changes. A preview with Save / Cancel comes first."""
    reply = i.response.send_message
    name = opts.get('game')
    if name == NONE:
        return await reply('No games are released yet.', ephemeral=True)
    k, rel, _ = _find(name)
    if not rel:
        return await reply('That game is not in the released list.', ephemeral=True)
    if not owns(i.user, owner_ids(rel)):
        return await reply('Only the dev who owns this game, or an admin, can change it.', ephemeral=True)
    changes = {}
    title = (opts.get('title') or '').strip()
    if title:
        changes['title'] = title[:100]
    for field in ('studio', 'original'):
        v = (opts.get(field) or '').strip()
        if v:
            changes['original_name' if field == 'original' else 'studio'] = v[:100]
    if opts.get('online') in ('online', 'offline'):
        changes['online'] = 1 if opts['online'] == 'online' else 0
    n = (opts.get('description') or '').strip()
    if n:  # a short line under the game; a single - removes it
        changes['notes'] = None if n == '-' else n[:140]
    link = (opts.get('link') or '').strip()
    if link and not roblox_game(link):
        return await reply('Paste the Roblox game page link: it looks like https://www.roblox.com/games/123456/Name', ephemeral=True)
    link = roblox_game(link) if link else link
    if not changes and not link and not opts.get('image'):
        return await reply('Nothing to change. Give a title, link, image, studio, original, description or online.', ephemeral=True)
    await i.response.defer(ephemeral=True, thinking=True)
    test = in_test_channel(i)
    if link:
        info = await roblox_info(link) or {}
        changes.update({'link': link, 'place_id': info.get('place_id'), 'roblox_name': info.get('name'), 'creator': info.get('creator')})
        if info.get('hero_url'):
            changes['hero_url'] = info['hero_url']
        if info.get('icon_url'):
            changes['icon_url'] = info['icon_url']
    if opts.get('image') and test:
        changes['hero_url'] = opts['image'].get('url')
        changes['art_url'] = None
    elif opts.get('image'):
        saved = await save_hero(k + '-draft', opts['image'])
        if saved.startswith('!'):
            return await i.edit_original_response(content=saved[1:])
        changes['hero_file'] = saved
    if 'original_name' in changes:
        art = await steam_art(rel.get('source_link'), changes['original_name'])
        changes.update({'art_url': art['art_url'], 'art_hero_url': art['art_hero_url']})
    from bot.features.games import reldraft
    pid = create_pending({'kind': 'edit', 'user': str(i.user.id), 'key': k, 'rel': rel, 'changes': changes, 'test': test})
    return await i.edit_original_response(**reldraft.payload(pid))


async def commit_edit(i, d):
    """The Save button of an edit draft. Returns (done, text)."""
    k, changes, rel = d['key'], dict(d['changes']), d['rel']
    if d['test']:
        merged = {**rel, **changes}
        return True, await preview(merged, merged.get('title') or clean_name(merged['name']), '/release edit')
    if changes.get('hero_file'):
        changes['hero_file'] = finalize_hero(k, changes['hero_file'])
    if 'online' in changes:
        from bot.features.games.watch import forget
        forget(k)  # by hand: the automatic watch starts from nothing for this game
    if changes:
        sets = ','.join(f'{c}=?' for c in changes)
        run(f'UPDATE game_status SET {sets} WHERE key=?', *changes.values(), k)
    await refresh_game_board()
    row = _row(k)
    return True, f"{E['fixed']} **UPDATED**{EM}·{EM}{summary(row, row.get('title') or clean_name(row['name']))}"
