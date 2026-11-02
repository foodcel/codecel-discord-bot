"""Three mockups of thin divider lines between the parts of a post (like the reference): the announcement, the tester board and the update card.
Shown in the test channel, made-up testers, buttons only say they are a mockup. Clears the channel first.   python scripts/mockup_lines.py --yes"""
import asyncio
import sys
import time

import discord
from discord import ui

from _boot import boot, finish

from bot.botnews import testing_news_devs_embeds, tree
from bot.ctx import fetch_channel
from bot.env import cfg
from bot.pngs import width_strip

NONE = discord.AllowedMentions.none()
NL = chr(10)
LINE = dict(visible=True, spacing=discord.SeparatorSpacing.small)
NOW = int(time.time())


def line():
    return ui.Separator(**LINE)


def wrap(*items):
    """The width strip first, then the card."""
    view = ui.LayoutView()
    view.add_item(ui.MediaGallery(discord.MediaGalleryItem(width_strip_file())))
    view.add_item(ui.Container(*items))
    return view


_strip = None


def width_strip_file():
    global _strip
    _strip = width_strip()
    return _strip


def mock_a():
    """A · The announcement: a line between every group, the commands under the last line, the date as a chip."""
    e = testing_news_devs_embeds()[0]
    items = [ui.TextDisplay(f'### {e.title}')]
    for f in e.fields:
        items += [line(), ui.TextDisplay(f'**{f.name}**{NL}{f.value}')]
    items += [line(), ui.TextDisplay(NL.join('-# ' + x for x in e.footer.text.split(NL))), ui.TextDisplay(f'-# <t:{NOW}:F>')]
    return wrap(*items)


def mock_b():
    """B · The tester board: a line between the games, the dropdown under the last line."""
    games = [('Sonic Dimensions', '<@510246875870396438>', NOW - 86400, ['<@941724517481463888>', '<@510246875870396438>']),
             ('Jump King', '<@510246875870396438>', NOW - 2 * 86400, []),
             ('Peggle', '<@941724517481463888>', NOW - 3 * 86400, ['<@941724517481463888>'])]
    items = [ui.TextDisplay(f'### 🧪 Tester board')]
    for name, dev, since, testers in games:
        rows = [('Dev', dev), ('Since', f'<t:{since}:D>')] + ([('Tester', t) for t in testers] or [('Testers', 'nobody yet')])
        items += [line(), ui.TextDisplay(f'**🎮 {name}**{NL}{tree(*rows)}')]
    items += [line(),
              ui.ActionRow(ui.Select(custom_id='mock:pick', placeholder='🙋 Volunteer to test a game…', options=[discord.SelectOption(label=g[0], value=g[0]) for g in games])),
              ui.ActionRow(ui.Button(custom_id='mock:leave', label='Leave a game', style=discord.ButtonStyle.secondary, emoji='🚪')),
              line(), ui.TextDisplay(NL.join(['-# 🙋 · pick a game in the list to volunteer', '-# /progress testing:on · put your game in testing']))]
    return wrap(*items)


def mock_c():
    """C · The update card: a line between Fixes, Changes and New, then the thanks and the date."""
    head = ui.TextDisplay(f'# Peggle: Update v17{NL}-# <t:{NOW}:D>')
    items = [head, line(),
             ui.TextDisplay(f'### 🐛 Fixes{NL}• The ball no longer sticks to the left peg{NL}• The score saves after every level'),
             line(),
             ui.TextDisplay(f'### 🔧 Changes{NL}• Fever buckets are a little wider'),
             line(),
             ui.TextDisplay(f'### ✨ New{NL}• A second map: Harbor'),
             line(),
             ui.TextDisplay(f'-# Thanks to everyone who reported these.{NL}-# Posted by <@941724517481463888> · Found a bug? <#{cfg.bugs_id}>'),
             ui.ActionRow(ui.Button(style=discord.ButtonStyle.link, label='Play now', url='https://www.roblox.com', emoji='▶️'))]
    return wrap(*items)


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await ch.purge(limit=None, bulk=True, reason='Mockups')
    for label, make in (('**A · Announcement with lines**', mock_a), ('**B · Tester board with lines**', mock_b), ('**C · Update card with lines**', mock_c)):
        await ch.send(label, allowed_mentions=NONE)
        view = make()
        await ch.send(view=view, files=[_strip], allowed_mentions=NONE)
    print('done')
    await finish(client)


asyncio.run(main())
