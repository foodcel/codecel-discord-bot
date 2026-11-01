"""Deletes this bot's messages in the library channel that are not part of the saved library (a double post). Run on the VM."""
import asyncio
import json

from _boot import boot, finish

from bot.ctx import fetch_channel
from bot.db import kv_get


async def main():
    client = await boot()
    conf = json.loads(kv_get('library'))
    keep = {int(i) for i in conf['messages']}
    ch = await fetch_channel(conf['channel'])
    n = 0
    async for m in ch.history(limit=60):
        if m.author.id == client.user.id and m.id not in keep:
            await m.delete()
            n += 1
    print('kept', sorted(keep), '| deleted extras:', n)
    await finish(client)


asyncio.run(main())
