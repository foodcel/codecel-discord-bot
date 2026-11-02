"""Two looks for the unreleased games list in the test channel: an embed with real columns plus lines, and a card with lines but no columns.
Clears the test channel first.   python scripts/show_board_options.py --yes"""
import asyncio
import re
import sys

import discord

from _boot import boot, finish

from bot import board
from bot.ctx import fetch_channel
from bot.env import cfg
from bot.look import card_from_embed
from bot.pngs import line_strip
from bot.ui import head

NONE = discord.AllowedMentions.none()


def with_lines(e):
    """The embed with the counts in its title, a line under the title and a line above the footer (the faint strip as the embed's picture)."""
    count = re.sub(r'[*]', '', (e.description or '').split(chr(10))[0]).strip()
    count = re.sub(r'^[^A-Za-z0-9]+', '', count)
    title = e.title.split(' ', 1)
    e.title = f'{title[0]} {title[1]} · {count}'
    e.description = '─' * 46
    strip = line_strip()
    e.set_image(url='attachment://line.png')
    return e, strip


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await ch.purge(limit=None, bulk=True, reason='Board options')
    _, unreleased, _ = await board.build_embeds()
    foot = unreleased.footer.text
    e, strip = with_lines(await_copy(unreleased))
    await ch.send('**A · Embed: real columns, counts in the title, a line under the title and above the footer**', allowed_mentions=NONE)
    await ch.send(embeds=[e], files=[strip], allowed_mentions=NONE)
    _, unreleased2, _ = await board.build_embeds()
    view, files = card_from_embed(unreleased2, inline_desc=True, plain_count=True)
    await ch.send('**B · Card: real lines, counts in the title, no side-by-side columns**', allowed_mentions=NONE)
    await ch.send(view=view, files=files, allowed_mentions=NONE)
    print('done')
    await finish(client)


def await_copy(e):
    return discord.Embed.from_dict(e.to_dict())


asyncio.run(main())
