"""Cards in Discord's newer message layout: the permanent game library, the 3-day new-game card, and the update card.
One look: a hero image, a big title, a few grey lines, and a Play button. Nothing here pings in the test channel."""
import asyncio
import hashlib
import io
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import ui

from .ctx import ctx, fetch_channel
from .pngs import width_strip
from .db import add_timer, all_, cancel_timers, kv_get, kv_set, now, one
from .env import cfg
from .games import clean_name, game_lists, key, owner_ids

BANNER = Path(__file__).resolve().parent.parent / 'assets' / 'games-banner.gif'
PLATFORMS = '📱 💻 🎮'
PAGE = 6  # games per library message (a message holds 40 pieces; a game card takes 6)
CARD_DAYS = 3
LONG = discord.SeparatorSpacing.large
FOOTER = '-# Fan-made Roblox experiences. The original games, brands and music belong to their owners; no affiliation is implied.'
COMMUNITY = ('**A community built on a love of games** 💙' + chr(10) + 'Got an idea for the next one? Drop it in <#1562961976387174452>. '
             'Found a bug? Report it in <#1563046117984444557> or use `/bug`.')
_lock = asyncio.Lock()
NL = chr(10)


HERO_RATIO = 3.1  # every new-game picture is cut to the same wide shape (width / height)
CROP_DIR = Path(__file__).resolve().parent.parent / 'data' / 'heroes' / 'crop'


def _cut(data, name):
    """The picture cut from the middle to the wide shape every new-game card uses. Returns a file path, or None when it cannot be done."""
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    if getattr(img, 'is_animated', False):
        return None  # a moving picture stays as it is
    img = img.convert('RGB')
    w, h = img.size
    if w / h > HERO_RATIO:
        nw = int(h * HERO_RATIO)
        box = ((w - nw) // 2, 0, (w - nw) // 2 + nw, h)
    else:
        nh = int(w / HERO_RATIO)
        box = (0, (h - nh) // 2, w, (h - nh) // 2 + nh)
    img = img.crop(box)
    if img.width > 1600:
        img = img.resize((1600, int(1600 / HERO_RATIO)))
    CROP_DIR.mkdir(parents=True, exist_ok=True)
    path = CROP_DIR / f'{name}.jpg'
    img.save(path, 'JPEG', quality=90)
    return path


def _cropped(source):
    """(file path of the cropped picture) for a link or a saved file; the link is downloaded once and kept. None: use the original."""
    try:
        if str(source).startswith('http'):
            name = hashlib.sha1(source.encode()).hexdigest()[:16]
            path = CROP_DIR / f'{name}.jpg'
            if path.exists():
                return path
            req = urllib.request.Request(source, headers={'User-Agent': 'codecel-bot'})
            with urllib.request.urlopen(req, timeout=15) as r:
                return _cut(r.read(), name)
        p = Path(source)
        name = hashlib.sha1(f'{p}{p.stat().st_mtime}'.encode()).hexdigest()[:16]
        if (CROP_DIR / f'{name}.jpg').exists():
            return CROP_DIR / f'{name}.jpg'
        return _cut(p.read_bytes(), name)
    except Exception as e:
        print('hero crop', repr(e))
        return None


def _hero(row):
    """(media for a gallery, file or None) of a released game: the picture the dev attached, else the original game's wide art, else the one from Roblox.
    All of them are cut to the same wide shape."""
    if row.get('hero_file') and Path(row['hero_file']).exists():
        c = _cropped(row['hero_file'])
        f = discord.File(c, filename=f'hero-{c.stem}.jpg') if c else discord.File(row['hero_file'])
        return f, f
    url = row.get('art_hero_url') or row.get('hero_url')
    if not url:
        return None, None
    c = _cropped(url)
    if c:
        f = discord.File(c, filename=f'hero-{c.stem}.jpg')
        return f, f
    return url, None


def _title(row):
    return row.get('title') or clean_name(row['name'])


def _credits(row, platforms=False):
    """The grey line under a game: the original game's studio, and who ported it."""
    parts = [PLATFORMS] if platforms else []
    if row.get('studio'):
        parts.append(f"Original game: {row['studio']}")
    owners = owner_ids(row)
    if owners:
        parts.append(f'ported by <@{owners[0]}>')
    return '-# ' + ' · '.join(parts) if parts else ''


def _name_line(row, big=False):
    """The name the way the old library had it: the original game, and where it is called something else on Roblox, the Roblox name is the link."""
    title, link, rb = _title(row), row.get('link'), row.get('roblox_name')
    pre = '# ' if big else ''
    if rb and key(rb) != key(title):
        shown = f'**[{rb}]({link})**' if link else f'**{rb}**'
        return f'{pre}**{title}** · on Roblox as {shown}' if not big else f'# {title}\non Roblox as {shown}'
    return f'{pre}**[{title}]({link})**' if link and not big else (f'# {title}' if big else f'**{title}**')


def _note(row):
    """The dev's short heads-up under a game (multiplayer, bugs, one map only...)."""
    return f"💬 {row['notes']}" if row.get('notes') else ''


def _offline(label):
    """A grey button that does nothing: the game is down for now."""
    return ui.Button(style=discord.ButtonStyle.link, label=label, url='https://www.roblox.com', emoji='⏸️', disabled=True)


def _play(url, label='Play'):
    return ui.Button(style=discord.ButtonStyle.link, label=label, url=url, emoji='▶️')


HUBS = {  # the console hubs sit at the top of the library, side by side
    'vyrastation': ('🟦', 'Vyra Station', 'PS4-style console hub. Boot it up and pick a game.'),
    'xblocks': ('🟩', 'X-Blocks 360', 'Xbox 360-style console hub. Metro dashboard, achievements.'),
}
HUB_CREDIT = '-# Interface inspired by PlayStation 4 (Sony Interactive Entertainment) and Xbox 360 (Microsoft).'
RED, BLUE = 0xC8161D, 0x13294B  # the two bars the library has always had


def hub_of(row):
    for k in (key(row['name']), key(_title(row))):
        if k.startswith('xblocks'):
            return 'xblocks'
        if k in HUBS:
            return k
    return None


def _icon(row):
    """(Thumbnail, file or None): the picture the dev attached, else the original game's cover on Steam, else the Roblox game icon."""
    if row.get('hero_file') and Path(row['hero_file']).exists():
        f = discord.File(row['hero_file'])
        return ui.Thumbnail(f), f
    url = row.get('art_url') or row.get('icon_url') or row.get('hero_url')
    return (ui.Thumbnail(url), None) if url else (None, None)


def game_row(row):
    """One game: its name, the platforms, the original game's studio and who made it, a picture on the right, and a Play now button."""
    icon, f = _icon(row)
    text = NL.join(x for x in [_name_line(row), PLATFORMS, _credits(row), _note(row)] if x)
    items = [ui.Section(text, accessory=icon)] if icon else [ui.TextDisplay(text)]
    if row.get('online') == 0:
        items.append(ui.ActionRow(_offline('Offline for now')))
    elif row.get('link'):
        items.append(ui.ActionRow(_play(row['link'], 'Play now')))
    return items, [f] if f else []


def library_plan(rows):
    """What the messages hold: the hubs page first, then the other games PAGE at a time."""
    hubs = {}
    others = []
    for r in rows:
        h = hub_of(r)
        if h and h not in hubs:
            hubs[h] = r
        else:
            others.append(r)
    plan = [{'kind': 'hubs', 'rows': [hubs[h] for h in HUBS if h in hubs]}]
    for i in range(0, len(others), PAGE):
        plan.append({'kind': 'games', 'rows': others[i:i + PAGE], 'first': i == 0})
    if plan[-1]['kind'] == 'games' and len(plan[-1]['rows']) < PAGE:
        plan[-1]['footer'] = True
    else:  # no games, or a full last page: the footer card is a message of its own
        plan.append({'kind': 'footer', 'rows': []})
    return plan


def hubs_page(rows):
    children, files = [], []
    if BANNER.exists():
        f = discord.File(BANNER, filename='games-banner.gif')
        files.append(f)
        children.append(ui.MediaGallery(discord.MediaGalleryItem(f)))
    children.append(ui.TextDisplay('## 🎮 Redwing Game Library' + NL + 'Everything we make, in one place. Start in a **console hub** or jump straight into a game below.'))
    buttons = []
    if rows:
        children += [ui.Separator(visible=True, spacing=LONG), ui.TextDisplay('### 🕹️ Console hubs')]
    for r in rows:
        emoji, name, blurb = HUBS[hub_of(r)]
        down = r.get('online') == 0
        text = NL.join([f'**{emoji} {name}** · 🔴 Offline' if down else f'**{emoji} {name}**', 'Offline for now. It will be back.' if down else blurb, PLATFORMS])
        icon, f = _icon(r)
        if f:
            files.append(f)
        children.append(ui.Section(text, accessory=icon) if icon else ui.TextDisplay(text))
        if down:
            buttons.append(_offline(f'{name} · Offline'))
        elif r.get('link'):
            buttons.append(_play(r['link'], f'Play {name}'))
    if buttons:
        children.append(ui.ActionRow(*buttons))
    view = ui.LayoutView()
    view.add_item(ui.Container(*children, accent_colour=RED))
    return view, files


def footer_card():
    """The library's footer: where to suggest games and report bugs, then the credits."""
    return ui.Container(ui.TextDisplay(COMMUNITY), ui.Separator(visible=True, spacing=LONG), ui.TextDisplay(FOOTER + ' ' + HUB_CREDIT[3:]), accent_colour=BLUE)


def games_page(rows, first, last):
    """One message of games: every game is a card of its own (a 6-piece container), with the footer card at the end."""
    view = ui.LayoutView()
    strip = width_strip()  # makes the message as wide as Discord allows, like every other message of the library
    view.add_item(ui.MediaGallery(discord.MediaGalleryItem(strip)))
    files = [strip]
    for r in rows:
        items, fs = game_row(r)
        view.add_item(ui.Container(*items, accent_colour=BLUE))
        files += fs
    if last:  # the footer card fits under up to 5 games; it also keeps a short last page full width
        view.add_item(footer_card())
    return view, files


def library_pages(rows):
    """[(view, files)], one per message: the hubs, then the games."""
    plan = library_plan(rows)
    out = []
    for n, p in enumerate(plan):
        if p['kind'] == 'hubs':
            out.append(hubs_page(p['rows']))
        elif p['kind'] == 'games':
            out.append(games_page(p['rows'], p.get('first'), p.get('footer')))
        else:
            view = ui.LayoutView()
            view.add_item(footer_card())
            out.append((view, []))
    return out


def ping_target(choice):
    """(text shown in the card, role id or None, pings everyone) for a /release new ping choice. Text None = no ping."""
    if choice == 'updates' and cfg.updates_role:
        return f'<@&{cfg.updates_role}>', cfg.updates_role, False
    if choice == 'releases' and cfg.releases_role:
        return f'<@&{cfg.releases_role}>', cfg.releases_role, False
    if choice in (None, 'everyone'):
        return '@everyone', None, True
    return None, None, False


def new_game_card(row, ping_text='@everyone'):
    """The card that appears for 3 days when a game is released. It pings what the dev chose (default @everyone)."""
    container, files = new_game_container(row, ping_text)
    view = ui.LayoutView()
    view.add_item(container)
    return view, files


def new_game_container(row, ping_text='@everyone'):
    media, f = _hero(row)
    children = []
    if ping_text:
        children.append(ui.TextDisplay(ping_text))
    if media is not None:
        children.append(ui.MediaGallery(discord.MediaGalleryItem(media)))
    children.append(ui.TextDisplay(NL.join(x for x in ['-# 🎉 NEW GAME', _name_line(row, big=True), PLATFORMS, _credits(row), _note(row)] if x)))
    if row.get('link'):
        children.append(ui.ActionRow(_play(row['link'], 'Play now')))
    return ui.Container(*children), [f] if f else []


def _bullets(lines, limit):
    out, used = [], 0
    for ln in lines:
        item = f'• {ln}'
        if used + len(item) > limit:
            out.append(f'• …and {len(lines) - len(out)} more')
            break
        out.append(item)
        used += len(item) + 1
    return NL.join(out)


def update_card(game, row, bugfixes, changes, new, version='', ping_text=None, when=None, poster=None):
    """The update post as a message: (view, files). See update_card_items."""
    items, files = update_card_items(game, row, bugfixes, changes, new, version, ping_text, when, poster)
    view = ui.LayoutView()
    for it in items:
        view.add_item(it)
    return view, files


def update_card_items(game, row, bugfixes, changes, new, version='', ping_text=None, when=None, poster=None):
    """An update post: a big title, the date, Fixes / Changes / New, a footer (who posted it, where to report a bug) and a Play now button.
    The game's cover is the small picture at the top right. `row` is the released-game row (may be None). ping_text is a mention shown in the card ('<@&role>'), None for no ping."""
    children = []
    strip = width_strip()
    if ping_text:
        children.append(ui.TextDisplay(ping_text))
    title = f"# {game['name']} — Update" + (f' {version}' if version else '')
    date = (when or datetime.now(timezone.utc)).strftime('%b %d, %Y').replace(' 0', ' ')
    head = f'{title}\n-# {date}'
    cover = (row or {}).get('art_url') or (row or {}).get('icon_url') or (row or {}).get('hero_url')  # a link, so nothing has to be uploaded
    children.append(ui.Section(head, accessory=ui.Thumbnail(cover)) if cover else ui.TextDisplay(head))  # the small picture sits top right
    first = True
    for heading, lines in (('🐛 Fixes', bugfixes), ('🔧 Changes', changes), ('✨ New', new)):
        if lines:
            # one blank line (an invisible character) above every section after the first
            children.append(ui.TextDisplay(('' if first else 'ㅤ\n') + f'### {heading}\n' + _bullets(lines, 1200)))
            first = False
    if not bugfixes and not changes and not new:
        children.append(ui.TextDisplay('Small improvements.'))
    who = f'Posted by <@{poster}> · ' if poster else ''
    children += [ui.Separator(visible=True, spacing=LONG),
                 ui.TextDisplay(f'-# Thanks to everyone who reported these.\n-# {who}Found a bug? <#{cfg.bugs_id}>')]
    link = (row or {}).get('link') or game.get('link')
    if link and str(link).startswith('http'):
        children.append(ui.ActionRow(_play(link, 'Play now')))
    return [ui.MediaGallery(discord.MediaGalleryItem(strip)), ui.Container(*children)], [strip]  # the strip: the same width for every update card


def released_row_for(name):
    """The released-game row of a game name (the hero image, link and credits live there). A game written a little differently on the board
    ("Deltarune" for "YOU SHOULD MAKE DELTARUNE PLEASE") or by its Roblox name matches too, as long as only one game fits."""
    k = key(name)
    rows = all_("SELECT * FROM game_status WHERE status='released'")
    names = lambda r: [key(r.get(c) or '') for c in ('name', 'title', 'roblox_name')]
    for r in rows:
        if k in names(r):
            return r
    hits = [r for r in rows if k and any(len(x) >= 4 and (k in x or x in k) for x in names(r))]
    return hits[0] if len(hits) == 1 else None


def test_channel(ch):
    return str(getattr(ch, 'id', ch)) == str(cfg.test_id)


def mentions(ch, role):
    """The test channel never notifies anyone: the Updates mention shows but does not ping."""
    if not role or test_channel(ch):
        return discord.AllowedMentions.none()
    return discord.AllowedMentions(roles=[discord.Object(id=int(role))])


# ---- the permanent library ----
def library_config():
    raw = kv_get('library')
    return json.loads(raw) if raw else None


async def refresh_library(force=False):
    """Rewrites the library messages from the released games. Does nothing until a library was posted (scripts/post_library.py)."""
    async with _lock:
        conf = library_config()  # read inside the lock: a call that waited must see what the call before it saved, or it posts a second copy
        if not conf:
            return
        ch = await fetch_channel(conf['channel'])
        if not ch:
            return
        try:  # a rival bot's posts in this channel are removed on every refresh too
            async for m in ch.history(limit=60):
                if is_foreign(m):
                    await m.delete()
        except Exception as e:
            print('rival sweep', repr(e))
        rows = in_library(game_lists()['released'])
        pages = library_pages(rows)
        ids, digests = conf['messages'], conf.get('digests', [])
        shown = [json.dumps([p['kind'], p.get('footer'), p['rows']], default=str) for p in library_plan(rows)]
        new_ids, new_digests = [], []
        reposted = False  # once one message of the library had to be sent again, the ones after it are sent again too, so the order stays right
        for n, (view, files) in enumerate(pages):
            digest = hashlib.md5((shown[n] + str(n) + str(len(pages))).encode()).hexdigest()
            msg = None
            if n < len(ids) and reposted:
                try:
                    await (await ch.fetch_message(int(ids[n]))).delete()
                except Exception:
                    pass
            elif n < len(ids):
                try:
                    msg = await ch.fetch_message(int(ids[n]))
                except Exception:
                    msg = None
            if msg and not force and n < len(digests) and digests[n] == digest:
                new_ids.append(msg.id)
                new_digests.append(digest)
                continue
            if msg:
                await msg.edit(view=view, attachments=files, allowed_mentions=discord.AllowedMentions.none())
            else:
                msg = await ch.send(view=view, files=files, allowed_mentions=discord.AllowedMentions.none())
                reposted = True
            new_ids.append(msg.id)
            new_digests.append(digest)
        for extra in ids[len(pages):]:
            try:
                await (await ch.fetch_message(int(extra))).delete()
            except Exception:
                pass
        kv_set('library', json.dumps({'channel': str(ch.id), 'messages': [str(i) for i in new_ids], 'digests': new_digests}))
        await restore_cards(ch, force=reposted)
        # only one library is ever live: any other message of this bot in the channel that is not a new-game card is a double post and goes
        cards = {t['target'].split(':')[-1] for t in all_("SELECT target FROM timers WHERE kind='delete_card'")}
        keep = {str(i) for i in new_ids} | cards
        try:
            async for m in ch.history(limit=60):
                if m.author.id == ctx.client.user.id and str(m.id) not in keep:
                    await m.delete()
        except Exception as e:
            print('library double sweep', repr(e))


async def post_new_game_card(row, ping='everyone'):
    """The 3-day card for a game that was just released: in the library's channel, pinging @everyone (not in the test channel)."""
    conf = library_config()
    if not conf:
        return None
    ch = await fetch_channel(conf['channel'])
    if not ch:
        return None
    text, role, everyone = ping_target(ping)
    view, files = new_game_card(row, text)
    allowed = (discord.AllowedMentions.none() if test_channel(ch)
               else discord.AllowedMentions(everyone=everyone, roles=[discord.Object(id=int(role))] if role else False))
    sent = await ch.send(view=view, files=files, allowed_mentions=allowed)
    add_timer('delete_card', f'{ch.id}:{sent.id}', now() + CARD_DAYS * 86400000)
    register_card(sent.id, row['key'], now() + CARD_DAYS * 86400000, hold=True)
    return sent


# ---- the library channel belongs to this bot ----
def rival_ids():
    """Ids of the other bots whose posts are removed from the library channel (kv 'library_rivals', comma separated)."""
    return {x for x in (kv_get('library_rivals') or '').split(',') if x}


def is_rival(m):
    """A message of a rival bot: a bot (or a webhook) on the list, or any bot or webhook that calls itself Redwing. Never this bot's own."""
    if ctx.client and ctx.client.user and m.author.id == ctx.client.user.id:
        return False
    if not (m.author.bot or m.webhook_id):
        return False
    return str(m.author.id) in rival_ids() or str(m.webhook_id or '') in rival_ids() or (m.author.name or '').lower().startswith('redwing')


def is_foreign(m):
    """In the library channel only this bot and people may speak: any other bot or webhook message is foreign."""
    if ctx.client and ctx.client.user and m.author.id == ctx.client.user.id:
        return False
    return bool(m.author.bot or m.webhook_id)


async def purge_webhooks(ch):
    """Deletes every webhook of the library channel (a webhook is how a bot posts around the channel permissions)."""
    for w in await ch.webhooks():
        try:
            await w.delete(reason='The library channel belongs to the library bot')
        except Exception as e:
            print('webhook delete', repr(e))


def in_library_channel(channel_id):
    conf = library_config()
    return bool(conf) and str(channel_id) == str(conf['channel'])


async def purge_rivals(message):
    """Deletes a message of a rival bot in the library channel. True when it was one."""
    if is_foreign(message) and in_library_channel(message.channel.id):
        try:
            await message.delete()
        except discord.NotFound:
            pass
        except Exception as e:
            print('rival delete', repr(e))
        return True
    return False


async def keep_library():
    """Puts the library back when a message of it was deleted, and clears any rival message that got in. Safe to call often."""
    await refresh_library()


# ---- the new-game cards are kept too: a card that was deleted comes back (silent) until its 3 days are over ----
def _cards_conf():
    try:
        return json.loads(kv_get('library_cards') or '[]')
    except Exception:
        return []


def register_card(msg_id, game_key, leave_at, hold=False):
    cards = [c for c in _cards_conf() if c['leave_at'] > now()] + [{'msg': str(msg_id), 'key': game_key, 'leave_at': leave_at, 'hold': hold}]
    kv_set('library_cards', json.dumps(cards))


def in_library(rows):
    """A game with a live new-game card is not in the library yet: it is added when its 3 days are over (the next refresh)."""
    held = {c['key'] for c in _cards_conf() if c.get('hold') and c['leave_at'] > now()}
    return [r for r in rows if r['key'] not in held]


async def restore_cards(ch, force=False):
    """Re-posts, without any ping, every new-game card whose message is gone and whose 3 days are not over."""
    out = []
    for c in [c for c in _cards_conf() if c['leave_at'] > now()]:
        try:
            old = await ch.fetch_message(int(c['msg']))
            if not force:
                out.append(c)
                continue
            await old.delete()  # the library was sent again: the cards go below it again
        except discord.NotFound:
            pass
        except Exception:
            out.append(c)  # could not check: leave it
            continue
        row = one("SELECT * FROM game_status WHERE key=? AND status='released'", c['key'])
        if not row:
            continue
        view, files = new_game_card(row, None)
        sent = await ch.send(view=view, files=files, allowed_mentions=discord.AllowedMentions.none())
        cancel_timers('delete_card', f"{ch.id}:{c['msg']}")
        add_timer('delete_card', f'{ch.id}:{sent.id}', c['leave_at'])
        out.append({**c, 'msg': str(sent.id)})
    kv_set('library_cards', json.dumps(out))


def expected_ids():
    """Every message that must be in the channel at all times: the library and the live new-game cards."""
    conf = library_config()
    ids = [str(x) for x in conf['messages']] if conf else []
    return ids + [c['msg'] for c in _cards_conf() if c['leave_at'] > now()]


async def guard_tick():
    """Once a second: every message of the library and every live card is still there, or it is sent again at once.
    One request when all is well (the newest 100 messages); a message that is not among them is looked up, and only a missing one is re-posted."""
    conf = library_config()
    if not conf or not conf['messages']:
        return
    ch = ctx.client.get_channel(int(conf['channel'])) or await fetch_channel(conf['channel'])
    if not ch:
        return
    try:
        await purge_webhooks(ch)
    except Exception as e:
        print('webhook sweep', repr(e))
    want = expected_ids()
    msgs = [m async for m in ch.history(limit=100)]
    seen = {str(m.id) for m in msgs}
    for m in msgs:  # a rival bot's message is deleted the second it is seen (the gateway event usually deletes it first)
        if is_foreign(m):
            try:
                await m.delete()
            except discord.NotFound:
                pass
    for mid in want:
        if mid in seen:
            continue
        try:
            await ch.fetch_message(int(mid))  # older than the newest 100, but still there
        except discord.NotFound:
            await refresh_library()  # gone: everything that is missing is posted again
            return


async def guard_loop():
    """Always on. A once-a-second watch, plus a full refresh every 90 seconds (doubles, rival bots, edited games)."""
    n = 0
    while True:
        try:
            n += 1
            await (refresh_library() if n % 90 == 0 else guard_tick())
        except Exception as e:
            print('library guard', repr(e))
            await asyncio.sleep(4)
        await asyncio.sleep(1)

