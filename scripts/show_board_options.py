"""Looks for the unreleased games list in the test channel: an embed with columns, a card with lines, and a card with a progress pill on every game.
Clears the test channel first.   python scripts/show_board_options.py --yes"""
import asyncio
import re
import sys

import discord
from discord import ui

from _boot import boot, finish

from bot import board
from bot.botnews import code_chip, date_button
from bot.ctx import fetch_channel
from bot.env import cfg
from bot.games import clean_name, game_lists, progress_cell, rows_by_dev, owner_ids
from bot.look import card_from_embed
from bot.pngs import line_strip, width_strip

NONE = discord.AllowedMentions.none()
NL = chr(10)
SMALL = discord.SeparatorSpacing.small


def counts_title(e):
    """'🛠️ UNRELEASED GAMES · 23 in development'"""
    count = re.sub(r'^[^A-Za-z0-9]+', '', re.sub(r'[*]', '', (e.description or '').split(NL)[0]).strip())
    emoji, _, rest = e.title.partition(' ')
    return f'{emoji} {rest} · {count}'


def chips(e):
    return NL.join('-# ' + code_chip(x) for x in e.footer.text.split(NL))


def embed_version(e):
    """A · the embed: real columns, the counts in the title, a dash line under it, the commands as code chips under the table, a faint line at the bottom."""
    e = discord.Embed.from_dict(e.to_dict())
    e.title = counts_title(e)
    e.description = '─' * 34
    e.add_field(name='​', value=NL.join(code_chip(x) for x in e.footer.text.split(NL)), inline=False)
    e.set_footer(text='​')
    e.set_image(url='attachment://line.png')
    return e, line_strip()


def card_version(e):
    """B · the card: a real line under the title and above the commands (code chips), progress on the same line as the game."""
    view, files = card_from_embed(e, inline_desc=True, plain_count=True)
    return view, files


async def pill_version():
    """C · the card with a progress pill on the right of every game (the first message of several)."""
    lists = game_lists()
    rows = await rows_by_dev([{'name': clean_name(g['name']), 'owners': g['owners'], 'since': g['since'], 'link': g.get('source_link'),
                               'progress': g.get('progress'), 'working': g.get('working'), 'testing_at': g.get('testing_at')} for g in lists['unreleased']])
    items = [ui.Section('### 🛠️ UNRELEASED GAMES · 23 in development', accessory=date_button()), ui.Separator(visible=True, spacing=SMALL)]
    budget, used, dev_games = 22, 0, []
    for r in rows:
        if r['first'] and dev_games:
            break
        dev_games.append(r)
    groups, cur = [], []
    for r in rows:
        if r['first'] and cur:
            groups.append(cur)
            cur = []
        cur.append(r)
    groups.append(cur)
    shown = 0
    for g in groups:
        cost = 1 + 3 * len(g)
        if used + cost > budget + 8:
            break
        used += cost
        shown += 1
        items.append(ui.TextDisplay(f"{g[0]['dev']}"))
        for k, r in enumerate(g):
            branch = '└─' if k == len(g) - 1 else '├─'
            items.append(ui.Section(f"{branch} **{r['name']}**", accessory=ui.Button(style=discord.ButtonStyle.secondary, label=progress_cell(r)[:80], disabled=True, custom_id=f'p{shown}{k}')))
        items.append(ui.Separator(visible=False, spacing=SMALL))
    strip = width_strip()
    items = items[:-1] + [ui.Separator(visible=True, spacing=SMALL), ui.TextDisplay(NL.join('-# ' + code_chip(x) for x in ['/claim · take a game (add its Steam page with link:)', '/progress · set how far it is, if you are working on it, or testing:on', '/release new · the game is out (paste its Roblox link)'])),
                         ui.MediaGallery(discord.MediaGalleryItem(strip))]
    view = ui.LayoutView()
    view.add_item(ui.Container(*items))
    return view, [strip], shown, len(groups)


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await ch.purge(limit=None, bulk=True, reason='Board options')
    _, unreleased, _ = await board.build_embeds()
    e, strip = embed_version(unreleased)
    await ch.send('**A · Embed: real columns. A dash line under the title, the commands as code chips, a faint line at the very bottom**', allowed_mentions=NONE)
    await ch.send(embeds=[e], files=[strip], allowed_mentions=NONE)
    _, unreleased2, _ = await board.build_embeds()
    view, files = card_version(unreleased2)
    await ch.send('**B · Card: real lines under the title, commands as code chips. Progress sits on the same line as the game**', allowed_mentions=NONE)
    await ch.send(view=view, files=files, allowed_mentions=NONE)
    view, files, shown, total = await pill_version()
    await ch.send(f'**C · Card with a progress pill on the right of every game (real column, real lines). Shown: the first {shown} of {total} devs; the full list would be about 3 messages**', allowed_mentions=NONE)
    await ch.send(view=view, files=files, allowed_mentions=NONE)
    print('done')
    await finish(client)


asyncio.run(main())
