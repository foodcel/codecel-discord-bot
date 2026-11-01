"""/release new and /release edit. A dev pastes the Roblox link of a finished game: the bot fetches the game's name, creator and hero image
from Roblox, credits the dev who owns it, and takes the original studio from the Steam page given on /claim (or the dev's own words).
Only text and the Roblox hero image are used: nothing is taken from Steam but the studio name."""
import asyncio
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from .ctx import fetch_channel
from .db import now, run
from .env import cfg
from .games import NONE, _find, clean_name, http, key, owner_ids, refresh_game_board
from .perms import level, owns
from .ui import E, EM

ROBLOX_GAME = re.compile(r'roblox\.com/(?:[a-z]{2}/)?games/(\d+)', re.I)
STEAM_APP = re.compile(r'store\.steampowered\.com/app/(\d+)', re.I)
HERO_DIR = Path(__file__).resolve().parent.parent / 'data' / 'heroes'
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
    m = ROBLOX_GAME.search(link or '')
    if not m:
        return None
    out = {'place_id': m.group(1), 'name': None, 'creator': None, 'hero_url': None, 'icon_url': None}
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
    safe = re.sub(r'[^a-z0-9]+', '-', k.lower()).strip('-')[:60] or 'game'
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


async def command_release_new(i, opts):
    """/release new game link [image] [studio] [original]"""
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
    if not ROBLOX_GAME.search(link):
        return await reply('Paste the Roblox game link: it looks like roblox.com/games/123456/Name', ephemeral=True)
    ping = opts.get('ping') or 'everyone'
    if (ping == 'releases' and not cfg.releases_role) or (ping == 'updates' and not cfg.updates_role):
        return await reply(f'The {ping.title()} role is not set up yet, so I cannot ping it. Pick another ping, or ask an admin.', ephemeral=True)
    from .guard import card_limit_reason, check_release, cooldown_left, note
    admin = level(i.user) == 'admin'
    wait = 0 if (admin or in_test_channel(i)) else cooldown_left(i.user.id)
    if wait:
        return await reply(f'Slow down: wait {wait // 60 + 1} more minute(s) before the next `/release new`.', ephemeral=True)
    await i.response.defer(ephemeral=True, thinking=True)
    info = await roblox_info(link) or {}
    hero_file = None
    if opts.get('image') and not in_test_channel(i):
        hero_file = await save_hero(k, opts['image'])
        if hero_file.startswith('!'):
            return await i.edit_original_response(content=hero_file[1:])
    original = (opts.get('original') or '').strip() or clean_name(dev['name'])
    art = await steam_art(dev.get('source_link'), original)
    studio = (opts.get('studio') or '').strip() or await steam_studio(dev.get('source_link')) or art['studio']
    mine = (opts.get('image') or {}).get('url') if opts.get('image') else None
    verdict = await check_release([art['art_hero_url'], art['art_url'], info.get('hero_url'), info.get('icon_url'), mine],
                                  [original, info.get('name'), studio], hero_file)
    blocked = None
    if verdict['flagged']:  # nothing from this release is shown: the pictures are removed and there is no card
        blocked = f"🚫 A picture or word looks like **{verdict['reason']}**, so I removed the pictures and did not post the card or the @everyone ping."
    elif not verdict['ok']:
        blocked = '⚠️ I could not check the pictures, so I did not post the card or the @everyone ping. An admin can post it.'
    if blocked:
        if hero_file:
            Path(hero_file).unlink(missing_ok=True)
        hero_file = None
        if verdict['flagged']:
            info = {**info, 'hero_url': None, 'icon_url': None}
            art = {**art, 'art_url': None, 'art_hero_url': None}
            mine = None
    if in_test_channel(i):  # a dry run: draw the card and the library row, change nothing
        row = {'key': k, 'name': dev['name'], 'owners': ','.join(owner_ids(dev)), 'link': link, 'place_id': info.get('place_id'), 'roblox_name': info.get('name'),
               'creator': info.get('creator'), 'hero_url': mine or info.get('hero_url'), 'icon_url': info.get('icon_url'), 'hero_file': None,
               'studio': studio, 'original_name': original, 'art_url': None if mine else art['art_url'], 'art_hero_url': None if mine else art['art_hero_url'], 'title': None}
        return await preview(i, row, clean_name(dev['name']), '/release new', blocked or (card_limit_reason(i.user.id, admin) if ping != 'none' else None) or '', ping)
    run("""INSERT INTO game_status(key,name,owners,since,status,released_at,released_by,link,place_id,roblox_name,creator,hero_url,icon_url,hero_file,studio,original_name)
        VALUES(?,?,?,?,'released',?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(key) DO UPDATE SET status='released', released_at=excluded.released_at, released_by=excluded.released_by, link=excluded.link,
        owners=excluded.owners, name=excluded.name, place_id=excluded.place_id, roblox_name=excluded.roblox_name, creator=excluded.creator,
        hero_url=excluded.hero_url, icon_url=excluded.icon_url, hero_file=COALESCE(excluded.hero_file, game_status.hero_file), studio=excluded.studio, original_name=excluded.original_name""",
        k, dev['name'], ','.join(owner_ids(dev)), dev.get('since'), now(), str(i.user.id), link, info.get('place_id'), info.get('name'),
        info.get('creator'), info.get('hero_url'), info.get('icon_url'), hero_file, studio, original)
    run('UPDATE game_status SET art_url=?, art_hero_url=? WHERE key=?', art['art_url'], art['art_hero_url'], k)
    from . import board
    if board.is_live():  # releasing a game completes its claim on the bounty board
        board.set_completed(dev['name'], True)
        await board.reload_claims()
    await refresh_game_board()
    row = _row(k)
    from .cards import post_new_game_card, test_channel
    from .tags import ensure_game_tags
    warn = ''
    try:  # the game gets its tag in the bugs and improvements forums
        made, problems = await ensure_game_tags(clean_name(dev['name']))
        if made:
            warn += chr(10) + f"🏷️ Made the **{clean_name(dev['name'])}** tag in the {' and '.join(made)} forum."
        warn += ''.join(chr(10) + '⚠️ ' + p for p in problems)
    except Exception as e:
        print('game tags', repr(e))
    note(i.user.id, 'release')
    why_not = blocked or (card_limit_reason(i.user.id, admin) if ping != 'none' else None) or ('this game already had its new-game card' if row.get('card_at') else None)
    if why_not and not blocked:
        blocked = f'ℹ️ The game is released, but no new-game card was posted: {why_not}. An admin can post it.'
    try:
        sent = None if why_not else await post_new_game_card(row, ping)
        if sent and ping != 'none':
            note(i.user.id, 'card')
        if sent:
            run('UPDATE game_status SET card_at=? WHERE key=?', now(), k)
        if sent and ping == 'everyone' and not test_channel(sent.channel) and not sent.mention_everyone:
            warn = chr(10) + "⚠️ The card is up, but Discord did not register the @everyone ping. Ask an admin to check the bot's Mention Everyone permission."
    except Exception as e:
        print('new game card', repr(e))
        warn = chr(10) + "⚠️ The game is released, but I could not post its new-game card."
    return await i.edit_original_response(content=f"{E['fixed']} **RELEASED**{EM}·{EM}{summary(row, clean_name(dev['name']))}{warn}{(chr(10) + blocked) if blocked else ''}")


def in_test_channel(i):
    return str(getattr(i, 'channel_id', None) or getattr(getattr(i, 'channel', None), 'id', '')) == str(cfg.test_id)


async def preview(i, row, shown, what, note='', ping='everyone'):
    """Test channel: nothing is saved and nothing goes to the real boards or #games. The card and the library row are drawn here instead."""
    import discord
    from .cards import games_page, new_game_card
    ch = await fetch_channel(cfg.test_id)
    none = discord.AllowedMentions.none()
    from .cards import ping_target
    view, files = new_game_card(row, ping_target(ping)[0])
    await ch.send(view=view, files=files, allowed_mentions=none)
    view2, files2 = games_page([row], False, False)
    await ch.send(view=view2, files=files2, allowed_mentions=none)
    return await i.edit_original_response(content=f"🧪 **TEST**{EM}·{EM}{what}. Nothing was saved, and nothing was posted in #games. Here is what it would look like in <#{cfg.test_id}>:\n{summary(row, shown)}" + (chr(10) + '🛡️ In a real release: ' + note if note else ''))


def _row(k):
    from .db import one
    return one('SELECT * FROM game_status WHERE key=?', k)


async def command_release_edit(i, opts):
    """/release edit game [title] [link] [image] [studio] [original]: only what is given changes."""
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
    link = (opts.get('link') or '').strip()
    if link and not ROBLOX_GAME.search(link):
        return await reply('Paste the Roblox game link: it looks like roblox.com/games/123456/Name', ephemeral=True)
    if not changes and not link and not opts.get('image'):
        return await reply('Nothing to change. Give a title, link, image, studio or original.', ephemeral=True)
    await i.response.defer(ephemeral=True, thinking=True)
    if link:
        info = await roblox_info(link) or {}
        changes.update({'link': link, 'place_id': info.get('place_id'), 'roblox_name': info.get('name'), 'creator': info.get('creator')})
        if info.get('hero_url'):
            changes['hero_url'] = info['hero_url']
        if info.get('icon_url'):
            changes['icon_url'] = info['icon_url']
    if opts.get('image') and in_test_channel(i):
        changes['hero_url'] = opts['image'].get('url')
        changes['art_url'] = None
    elif opts.get('image'):
        saved = await save_hero(k, opts['image'])
        if saved.startswith('!'):
            return await i.edit_original_response(content=saved[1:])
        from .guard import check_release
        verdict = await check_release([], [title], saved)
        if verdict['flagged'] or not verdict['ok']:
            Path(saved).unlink(missing_ok=True)
            return await i.edit_original_response(content=(f"🚫 That picture looks like **{verdict['reason']}**, so I did not save it." if verdict['flagged']
                                                         else '⚠️ I could not check that picture, so I did not save it. Try again in a moment.'))
        changes['hero_file'] = saved
    if 'original_name' in changes:
        art = await steam_art(rel.get('source_link'), changes['original_name'])
        changes.update({'art_url': art['art_url'], 'art_hero_url': art['art_hero_url']})
    if in_test_channel(i):  # a dry run: show the result, change nothing
        merged = {**rel, **changes}
        return await preview(i, merged, merged.get('title') or clean_name(merged['name']), '/release edit')
    sets = ','.join(f'{c}=?' for c in changes)
    run(f'UPDATE game_status SET {sets} WHERE key=?', *changes.values(), k)
    await refresh_game_board()
    row = _row(k)
    return await i.edit_original_response(content=f"{E['fixed']} **UPDATED**{EM}·{EM}{summary(row, row.get('title') or clean_name(row['name']))}")
