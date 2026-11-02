"""Runs one round of the game watch right now. With --count=<game key> that game is counted as already failed once (so one more failed check marks it down)."""
import asyncio
import json
import sys

from _boot import boot, finish

from bot.db import kv_get, kv_set
from bot.watch import sweep


async def main():
    client = await boot()
    for a in sys.argv:
        if a.startswith('--count='):
            st = json.loads(kv_get('watch') or '{}')
            st[a.split('=', 1)[1]] = {'fails': 1, 'auto': False}
            kv_set('watch', json.dumps(st))
    await sweep()
    print('watch state:', kv_get('watch'))
    await finish(client)


asyncio.run(main())
