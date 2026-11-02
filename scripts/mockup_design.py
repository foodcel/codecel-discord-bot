"""Mockups for the next look: the three posts with a line only under the header and above the footer, and a small example of each idea
(1 date chips, 2 code chips, 4 cover picture, 5 quote block, 6 status dots). Test channel only, made-up testers; the buttons only say they are a mockup.
Clears the channel first.   python scripts/mockup_design.py --yes"""
import asyncio
import sys
import time

import discord
from discord import ui

from _boot import boot, finish

from bot.botnews import testing_news_devs_embeds, tree
from bot.cards import BLUE
from bot.ctx import fetch_channel
from bot.db import one
from bot.env import cfg
from bot.games import key
from bot.pngs import width_strip

NONE = discord.AllowedMentions.none()
NL = chr(10)
NOW = int(time.time())
ASHER, ROBIN = '<@510246875870396438>', '<@941724517481463888>'
_files = []


def line():
    return ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)


def small(*lines):
    return ui.TextDisplay(NL.join('-# ' + x for x in lines))


def cover(name):
    row = one('SELECT art_url, icon_url, hero_url FROM game_status WHERE key=?', key(name)) or {}
    return row.get('art_url') or row.get('icon_url') or row.get('hero_url')


def wrap(*items, accent=None):
    """The width strip first (every post the same width), then the card."""
    strip = width_strip()
    _files.append(strip)
    view = ui.LayoutView()
    view.add_item(ui.MediaGallery(discord.MediaGalleryItem(strip)))
    view.add_item(ui.Container(*items, accent_colour=accent))
    return view


def top(text, img=None):
    """The header: the title, with the cover on the right when there is one."""
    return ui.Section(text, accessory=ui.Thumbnail(img)) if img else ui.TextDisplay(text)


# ---- the three posts ----
def mock_a():
    """A · Announcement: title, one line, the groups, one line, the commands."""
    e = testing_news_devs_embeds()[0]
    items = [ui.TextDisplay(f'### {e.title}'), line()]
    items += [ui.TextDisplay(f'**{f.name}**{NL}{f.value}') for f in e.fields]
    items += [line(), small(*e.footer.text.split(NL))]
    return wrap(*items)


def mock_b():
    """B · Tester board: title, one line, the games, one line, the picker, one line, the commands."""
    games = [('Sonic Dimensions', ASHER, NOW - 86400, [ROBIN, ASHER]), ('Jump King', ASHER, NOW - 2 * 86400, []), ('Peggle', ROBIN, NOW - 3 * 86400, [ROBIN])]
    items = [ui.TextDisplay('### 🧪 Tester board'), line()]
    for name, dev, since, testers in games:
        rows = [('Dev', dev), ('Since', f'<t:{since}:D>')] + ([('Tester', t) for t in testers] or [('Testers', 'nobody yet')])
        items.append(ui.TextDisplay(f'**🎮 {name}**{NL}{tree(*rows)}'))
    items += [line(),
              ui.ActionRow(ui.Select(custom_id='mock:pick', placeholder='🙋 Pick the games you test…', min_values=0, max_values=len(games),
                                     options=[discord.SelectOption(label=g[0], value=g[0]) for g in games])),
              line(), small('🙋 · pick the games you test: pick again to change the list', '/progress testing:on · put your game in testing', '/bug · testers report them in the testing channel')]
    return wrap(*items)


def mock_c():
    """C · Update card: the cover on the right, no date under the title, one line, the changes, one line, the thanks and the date at the end."""
    items = [top(f'# Peggle: Update v17', cover('Peggle')), line(),
             ui.TextDisplay(f'### 🐛 Fixes{NL}• The ball no longer sticks to the left peg{NL}• The score saves after every level'),
             ui.TextDisplay(f'### 🔧 Changes{NL}• Fever buckets are a little wider'),
             ui.TextDisplay(f'### ✨ New{NL}• A second map: Harbor'),
             line(), small('Thanks to everyone who reported these.', f'Posted by {ROBIN} · Found a bug? <#{cfg.bugs_id}> · <t:{NOW}:D>'),
             ui.ActionRow(ui.Button(style=discord.ButtonStyle.link, label='Play now', url='https://www.roblox.com', emoji='▶️'))]
    return wrap(*items)


# ---- the ideas, one small example each ----
def idea_1():
    """Date chips: they show in each reader's own time and can count up."""
    return wrap(ui.TextDisplay(f'### 1 · Date chips'), line(),
                ui.TextDisplay(NL.join([f'**Full** · <t:{NOW}:F>', f'**Short** · <t:{NOW}:D>', f'**Time** · <t:{NOW}:t>', f'**Counting** · <t:{NOW - 7200}:R>  (updates by itself)',
                                        f'**In a post** · Testing since <t:{NOW - 2 * 86400}:R>'])))


def idea_2():
    """Code chips: exact values in a grey box."""
    return wrap(ui.TextDisplay('### 2 · Code chips'), line(),
                ui.TextDisplay(NL.join(['**Without**', 'Device · iPhone 17 Pro', 'Build · 0.745.0.7451137', 'Type /progress testing:on to start', '',
                                        '**With**', 'Device · `iPhone 17 Pro`', 'Build · `0.745.0.7451137`', 'Type `/progress testing:on` to start'])))


def idea_4():
    """The game's cover on the right, on the posts that have none."""
    return wrap(top(f'### 🧪 Peggle needs testers{NL}-# dev {ROBIN}{NL}Press the button to join.', cover('Peggle')), line(),
                small('🙋 · volunteer as a tester'),
                ui.ActionRow(ui.Button(custom_id='mock:join', label='I want to test', style=discord.ButtonStyle.success, emoji='🙋')))


def idea_5():
    """A quote block for the player's own words."""
    return wrap(ui.TextDisplay(f'### #2 · Homing Dash appears blacked out{NL}-# Sonic Dimensions'), line(),
                ui.TextDisplay(NL.join(['**Without**', "When first opening Tails' shop, Homing Dash is not seen and usually blacked out.", '',
                                        '**With**', "> When first opening Tails' shop, Homing Dash is not seen and usually blacked out.",
                                        f'-# {ROBIN} · iPhone 17 Pro'])))


def idea_6():
    """A coloured dot in front of a game's line: the state before the name."""
    rows = [('🟢', 'Peggle', 'online'), ('🟡', 'Sonic Dimensions', 'in testing'), ('🔴', 'Vyra Station', 'offline'), ('⚪', 'Jump King', 'in development')]
    return wrap(ui.TextDisplay('### 6 · Status dots'), line(),
                ui.TextDisplay(f'**Without**{NL}' + tree(*[(n, s) for _, n, s in rows]) + f'{NL}{NL}**With**{NL}' + tree(*[(f'{d} {n}', s) for d, n, s in rows])))


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await ch.purge(limit=None, bulk=True, reason='Mockups')
    posts = [('**A · Announcement**', mock_a), ('**B · Tester board**', mock_b), ('**C · Update card**', mock_c),
             ('**Idea 1 · date chips**', idea_1), ('**Idea 2 · code chips**', idea_2), ('**Idea 4 · cover picture**', idea_4),
             ('**Idea 5 · quote block**', idea_5), ('**Idea 6 · status dots**', idea_6)]
    for label, make in posts:
        _files.clear()
        view = make()
        await ch.send(label, allowed_mentions=NONE)
        await ch.send(view=view, files=list(_files), allowed_mentions=NONE)
    print('done')
    await finish(client)


asyncio.run(main())
