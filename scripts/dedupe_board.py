"""Keeps one copy of each bounty-board message (the ones the saved config points to) and deletes the extra copies. Run on the VM."""
import asyncio

import discord

from _boot import boot, finish

from bot.features.games import board
from bot.core.ctx import fetch_channel


async def main():
    client = await boot()
    c = board.board_cfg()
    keep = {str(c[k]) for k in ('top', 'claims', 'completed') if c.get(k)}
    ch = await fetch_channel(c['channel_id'])
    print('config keeps', keep)
    async for m in ch.history(limit=50):
        if str(m.id) not in keep and (m.embeds or m.type == discord.MessageType.pins_add):
            await m.delete()
            print('deleted extra', m.id, m.embeds[0].title if m.embeds else 'pin notice')
    async for m in ch.history(limit=20, oldest_first=True):
        print(m.id, 'pinned' if m.pinned else '', m.embeds[0].title if m.embeds else m.content[:40])
    await finish(client)


asyncio.run(main())
