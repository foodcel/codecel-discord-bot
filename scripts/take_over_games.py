"""Makes #games this bot's alone: saves a copy of everything in it, deletes every message, remembers the rival bot (its posts are removed from now on),
and posts the library again. Run on the VM. Needs --yes.   python scripts/take_over_games.py --rival=<bot user id> --yes"""
import asyncio
import json
import sys
import time
from pathlib import Path

from _boot import boot, finish

from bot.cards import refresh_library
from bot.ctx import fetch_channel
from bot.db import kv_set

CHANNEL = 1562940878685872149


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


async def main():
    client = await boot()
    ch = await fetch_channel(CHANNEL)
    msgs = [m async for m in ch.history(limit=500, oldest_first=True)]
    print(len(msgs), 'messages | authors:', sorted({str(m.author) for m in msgs}))
    if '--yes' not in sys.argv:
        return await finish(client)
    out = Path(__file__).resolve().parent.parent / 'data' / f'backup-games-{int(time.time())}.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps([{'id': m.id, 'author': str(m.author), 'at': m.created_at.isoformat(), 'content': m.content,
                                'reactions': [(str(r.emoji), r.count) for r in m.reactions]} for m in msgs], ensure_ascii=False, indent=1), encoding='utf8')
    print('backup:', out)
    kv_set('library_rivals', arg('rival'))
    kv_set('library', json.dumps({'channel': str(ch.id), 'messages': [], 'digests': []}))  # so deleting does not trigger a re-post mid-wipe
    for i in range(0, len(msgs), 100):
        chunk = msgs[i:i + 100]
        try:
            await (ch.delete_messages(chunk) if len(chunk) > 1 else chunk[0].delete())
        except Exception as e:
            print('bulk failed, one by one:', repr(e))
            for m in chunk:
                try:
                    await m.delete()
                except Exception:
                    pass
    print('deleted', len(msgs), '| left:', len([m async for m in ch.history(limit=20)]))
    await refresh_library(force=True)
    print('library posted | rivals:', arg('rival'))
    await finish(client)


asyncio.run(main())
