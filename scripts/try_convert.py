"""Tries to edit a message that has an embed (and a ping) into a card in place. Test channel only. Run on the VM."""
import asyncio

import discord
from discord import ui

from _boot import boot, finish

from bot.ctx import fetch_channel
from bot.env import cfg
from bot.pngs import width_strip


async def main():
    client = await boot(claims=False)
    ch = await fetch_channel(cfg.test_id)
    e = discord.Embed(title='old embed', description='hello')
    msg = await ch.send(content='<@&1562719404473458778>', embed=e, allowed_mentions=discord.AllowedMentions.none())
    view = ui.LayoutView()
    view.add_item(ui.Container(ui.TextDisplay('### now a card')))
    for attempt, kw in (('embeds=[] content=None', {'content': None, 'embeds': []}), ('with attachments', {'content': None, 'embeds': [], 'attachments': [width_strip()]})):
        try:
            await msg.edit(view=view, allowed_mentions=discord.AllowedMentions.none(), **kw)
            print('OK in place:', attempt)
            break
        except Exception as ex:
            print('failed', attempt, repr(ex)[:200])
    await finish(client)


asyncio.run(main())
