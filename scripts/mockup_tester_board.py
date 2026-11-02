"""Three looks for a tester board: each game in testing, with a button for helpers to volunteer. Shown in the test channel with made-up volunteers
(the buttons only say they are a mockup). Clears the channel first.   python scripts/mockup_tester_board.py --yes"""
import asyncio
import sys

import discord
from discord import ui

from _boot import boot, finish

from bot.botnews import make, tree
from bot.cards import BLUE
from bot.ctx import fetch_channel
from bot.db import one
from bot.env import cfg
from bot.games import key
from bot.pngs import width_strip
from bot.ui import E, flat, head, section, gap

NONE = discord.AllowedMentions.none()
NL = chr(10)
ASHER = '<@510246875870396438>'
GAMES = [  # (name, dev, testing since, volunteers: (name, device, free))
    ('Sonic Dimensions', ASHER, 'Nov 2', [('Nova', 'Xbox', 'evenings'), ('Kai', 'PC', 'weekends')]),
    ('Jump King', ASHER, 'Nov 1', [('Mira', 'PS5', 'any time')]),
    ('Peggle', '<@941724517481463888>', 'Oct 30', []),
]
FOOTER = [
    '🙋 · press to volunteer as a tester',
    '🚪 · leave a game you no longer test',
    '/progress testing:on · put your game in testing',
]


def cover(name):
    row = one('SELECT art_url, icon_url, hero_url FROM game_status WHERE key=?', key(name)) or {}
    return row.get('art_url') or row.get('icon_url') or row.get('hero_url')


def testers_tree(vols):
    return tree(*[(n, f'{d} · {f}') for n, d, f in vols]) if vols else '└─ nobody yet, press 🙋 to be the first'


def mock_a():
    """A · A card per game: cover on the right, the volunteers listed, buttons to join or leave."""
    out = []
    for name, dev, since, vols in GAMES:
        text = f'### {name}{NL}-# 🧪 testing since {since} · dev {dev}'
        img = cover(name)
        head_item = ui.Section(text, accessory=ui.Thumbnail(img)) if img else ui.TextDisplay(text)
        view = ui.LayoutView()
        view.add_item(ui.Container(
            head_item,
            ui.TextDisplay(f'**🙋 Testers ({len(vols)})**{NL}{testers_tree(vols)}'),
            ui.ActionRow(ui.Button(custom_id='mock:join', label='I want to test', style=discord.ButtonStyle.success, emoji='🙋'),
                         ui.Button(custom_id='mock:leave', label='Leave', style=discord.ButtonStyle.secondary, emoji='🚪')),
            accent_colour=BLUE))
        out.append({'view': view})
    return out


def mock_b():
    """B · One board: every game in the tree look with its volunteers, and one dropdown to volunteer for a game."""
    e = flat()
    e.title = head('🧪', 'Tester board')
    for name, dev, since, vols in GAMES:
        rows = [('Dev', dev), ('Since', since), ('Testers', ', '.join(f'{n} ({d})' for n, d, _ in vols) or 'nobody yet')]
        section(e, head('🎮', name), tree(*rows))
    gap(e)
    e.set_footer(text=NL.join(FOOTER))
    e.set_image(url='attachment://width.png')
    view = ui.View(timeout=None)
    view.add_item(ui.Select(custom_id='mock:pick', placeholder='🙋 Volunteer to test a game…',
                            options=[discord.SelectOption(label=g[0], description=f'testing since {g[2]}') for g in GAMES]))
    view.add_item(ui.Button(custom_id='mock:leave', label='Leave a game', style=discord.ButtonStyle.secondary, emoji='🚪', row=1))
    return [{'embeds': [e], 'files': [width_strip()], 'view': view}]


def mock_c():
    """C · An embed per game in the announcement look, with the cover top right and two buttons."""
    out = []
    for name, dev, since, vols in GAMES:
        e = make(name, [
            ('👤', 'Dev', [('Dev', dev), ('Testing since', since)]),
            ('🙋', f'Volunteer testers ({len(vols)})', [(n, f'{d} · {f}') for n, d, f in vols] or [('Nobody yet', 'press 🙋 to be the first')])],
            ['🙋 · volunteer as a tester', '🚪 · leave'], emoji='🧪')
        img = cover(name)
        if img:
            e.set_thumbnail(url=img)
        view = ui.View(timeout=None)
        view.add_item(ui.Button(custom_id='mock:join', label='I want to test', style=discord.ButtonStyle.success, emoji='🙋'))
        view.add_item(ui.Button(custom_id='mock:leave', label='Leave', style=discord.ButtonStyle.secondary, emoji='🚪'))
        out.append({'embeds': [e], 'files': [width_strip()], 'view': view})
    return out


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await ch.purge(limit=None, bulk=True, reason='Mockups')
    for label, make_msgs in (('**A · A card per game**', mock_a), ('**B · One board with a dropdown**', mock_b), ('**C · An embed per game**', mock_c)):
        await ch.send(label + '  (made-up testers, the buttons do nothing yet)', allowed_mentions=NONE)
        for kw in make_msgs():
            await ch.send(allowed_mentions=NONE, **kw)
    print('done')
    await finish(client)


asyncio.run(main())
