"""Lists every message in the bounty board's channel (author, pinned, first words). Run on the VM."""
import asyncio

from _boot import boot, finish

from bot.features.games import board
from bot.core.ctx import fetch_channel


async def main():
    client = await boot()
    c = board.board_cfg()
    print('config:', {k: v for k, v in c.items()})
    ch = await fetch_channel(c['channel_id'])
    print(type(ch).__name__, ch.name)
    async for m in ch.history(limit=100, oldest_first=True):
        first = (m.content or (m.embeds[0].title if m.embeds else '') or '')[:60].replace('\n', ' ')
        print(m.id, m.author.name, 'BOT' if m.author.bot else '', 'pinned' if m.pinned else '', '|', first)
    await finish(client)


asyncio.run(main())
