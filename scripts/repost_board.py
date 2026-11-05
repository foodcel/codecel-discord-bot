"""Clears the bounty board's channel and posts the three pinned messages again, in order, with no "pinned a message" lines. Run on the VM."""
import asyncio

import discord

from _boot import boot, finish

from bot.features.games import board
from bot.core.ctx import fetch_channel


async def main():
    client = await boot()
    c = board.board_cfg()
    ch = await fetch_channel(c['channel_id'])
    gone = 0
    async for m in ch.history(limit=None):
        try:
            await m.delete()
            gone += 1
        except Exception as e:
            print('could not delete', m.id, repr(e))
    print('deleted', gone)
    board.save_cfg({k: v for k, v in c.items() if k != 'testing'} | {'top': None, 'claims': None, 'completed': None})
    await board.refresh_board()
    n = 0
    async for m in ch.history(limit=50):
        if m.type == discord.MessageType.pins_add:
            await m.delete()
            n += 1
    print('pin notices removed', n)
    async for m in ch.history(limit=20, oldest_first=True):
        print(m.id, 'pinned' if m.pinned else '', (m.embeds[0].title if m.embeds else m.content)[:40])
    await finish(client)


asyncio.run(main())
