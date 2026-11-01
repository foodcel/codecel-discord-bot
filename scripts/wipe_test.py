"""Deletes everything in the test channel (TEST_CHANNEL_ID). Never point it at another channel."""
import asyncio

from _boot import boot, finish

from bot.ctx import fetch_channel
from bot.env import cfg
from bot.previews import clear_channel


async def main():
    client = await boot(claims=False)
    ch = await fetch_channel(cfg.test_id)
    print('wiping', ch.name)
    await clear_channel(ch)
    print('left:', len([m async for m in ch.history(limit=5)]))
    await finish(client)


asyncio.run(main())
