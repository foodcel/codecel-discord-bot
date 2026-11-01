"""Removes the pins this bot made in the library channel (the library is kept by a guard now, not by pins). Run on the VM."""
import asyncio

from _boot import boot, finish

from bot.ctx import fetch_channel
from bot.db import kv_get
import json


async def main():
    client = await boot()
    ch = await fetch_channel(json.loads(kv_get('library'))['channel'])
    n = 0
    async for m in ch.pins(limit=50):
        if m.author.id == client.user.id:
            await m.unpin()
            n += 1
    async for m in ch.history(limit=60):
        if m.type.name == 'pins_add':
            await m.delete()
    print('unpinned', n)
    await finish(client)


asyncio.run(main())
