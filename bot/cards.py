"""Cards in Discord's newer message layout: the permanent game library, the 3-day new-game card, and the update card.
One look: a hero image, a big title, a few grey lines, and a Play button. Nothing here pings in the test channel."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import ui

from .ctx import fetch_channel
from .db import add_timer, kv_get, kv_set, now, one
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


def _hero(row):
    """(media for a gallery, file or None) of a released game: the picture the dev attached, else the original game's wide art, else the one from Roblox."""
    if row.get('hero_file') and Path(row['hero_file']).exists():
        f = discord.File(row['hero_file'])
        return f, f
    url = row.get('art_hero_url') or row.get('hero_url')
    return (url, None) if url else (None, None)


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
    text = NL.join(x for x in [_name_line(row), PLATFORMS, _credits(row)] if x)
    icon, f = _icon(row)
    items = [ui.Section(text, accessory=icon)] if icon else [ui.TextDisplay(text)]
    if row.get('link'):
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
        text = NL.join([f'**{emoji} {name}**', blurb, PLATFORMS])
        icon, f = _icon(r)
        if f:
            files.append(f)
        children.append(ui.Section(text, accessory=icon) if icon else ui.TextDisplay(text))
        if r.get('link'):
            buttons.append(_play(r['link'], f'Play {name}'))
    if buttons:
        children.append(ui.ActionRow(*buttons))
    view = ui.LayoutView()
    view.add_item(ui.Container(*children))
    return view, files


def footer_card():
    """The library's footer: where to suggest games and report bugs, then the credits."""
    return ui.Container(ui.TextDisplay(COMMUNITY), ui.Separator(visible=True, spacing=LONG), ui.TextDisplay(FOOTER + ' ' + HUB_CREDIT[3:]))


def games_page(rows, first, last):
    """One message of games: every game is a card of its own (a 6-piece container), with the footer card at the end."""
    view = ui.LayoutView()
    files = []
    for r in rows:
        items, fs = game_row(r)
        view.add_item(ui.Container(*items))
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


def new_game_card(row, ping=True):
    """The card that appears for 3 days when a game is released. It pings @everyone."""
    media, f = _hero(row)
    children = []
    if ping:
        children.append(ui.TextDisplay('@everyone'))
    if media is not None:
        children.append(ui.MediaGallery(discord.MediaGalleryItem(media)))
    children.append(ui.TextDisplay(NL.join(x for x in ['-# 🎉 NEW GAME', _name_line(row, big=True), PLATFORMS, _credits(row)] if x)))
    if row.get('link'):
        children.append(ui.ActionRow(_play(row['link'], 'Play now')))
    view = ui.LayoutView()
    view.add_item(ui.Container(*children))
    return view, [f] if f else []


def _bullets(lines, limit):
    out, used = [], 0
    for ln in lines:
        item = f'• {ln}'
        if used + len(item) > limit:
            out.append(f'• …and {len(lines) - len(out)} more')
            break
        out.append(item)
        used += len(item) + 1
    return '\n'.join(out)


def update_card(game, row, bugfixes, changes, new, version='', ping_role=None, when=None):
    """An update post: a big title, Fixes and New, a Play button. No hero image (that is for the new-game card). `row` is the released-game row (may be None)."""
    children = []
    if ping_role:
        children.append(ui.TextDisplay(f'<@&{ping_role}>'))
    title = f"# {game['name']} — Update" + (f' {version}' if version else '')
    date = (when or datetime.now(timezone.utc)).strftime('%b %d, %Y').replace(' 0', ' ')
    children.append(ui.TextDisplay(f'{title}\n-# {date}'))
    if bugfixes:
        children.append(ui.TextDisplay('### 🐛 Fixes\n' + _bullets(bugfixes, 1200)))
    if changes:
        children.append(ui.TextDisplay('### 🔧 Changes\n' + _bullets(changes, 1200)))
    if new:
        children.append(ui.TextDisplay('### ✨ New\n' + _bullets(new, 1200)))
    if not bugfixes and not changes and not new:
        children.append(ui.TextDisplay('Small improvements.'))
    children += [ui.Separator(visible=True, spacing=LONG), ui.TextDisplay('-# Thanks to everyone who reported these.')]
    link = (row or {}).get('link') or game.get('link')
    if link and link.startswith('http'):
        children.append(ui.ActionRow(_play(link, 'Play now')))
    view = ui.LayoutView()
    view.add_item(ui.Container(*children))
    return view, []


def released_row_for(name):
    """The released-game row of a game name (the hero image, link and credits live there)."""
    return one('SELECT * FROM game_status WHERE key=? AND status=?', key(name), 'released')


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
    conf = library_config()
    if not conf:
        return
    async with _lock:
        ch = await fetch_channel(conf['channel'])
        if not ch:
            return
        rows = game_lists()['released']
        pages = library_pages(rows)
        ids, digests = conf['messages'], conf.get('digests', [])
        shown = [json.dumps([p['kind'], p.get('footer'), p['rows']], default=str) for p in library_plan(rows)]
        new_ids, new_digests = [], []
        for n, (view, files) in enumerate(pages):
            digest = hashlib.md5((shown[n] + str(n) + str(len(pages))).encode()).hexdigest()
            msg = None
            if n < len(ids):
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
            new_ids.append(msg.id)
            new_digests.append(digest)
        for extra in ids[len(pages):]:
            try:
                await (await ch.fetch_message(int(extra))).delete()
            except Exception:
                pass
        kv_set('library', json.dumps({'channel': str(ch.id), 'messages': [str(i) for i in new_ids], 'digests': new_digests}))


async def post_new_game_card(row):
    """The 3-day card for a game that was just released: in the library's channel, pinging @everyone (not in the test channel)."""
    conf = library_config()
    if not conf:
        return None
    ch = await fetch_channel(conf['channel'])
    if not ch:
        return None
    view, files = new_game_card(row)
    allowed = discord.AllowedMentions.none() if test_channel(ch) else discord.AllowedMentions(everyone=True)
    sent = await ch.send(view=view, files=files, allowed_mentions=allowed)
    add_timer('delete_card', f'{ch.id}:{sent.id}', now() + CARD_DAYS * 86400000)
    return sent
