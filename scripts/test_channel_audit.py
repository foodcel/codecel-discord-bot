"""Shows what is left in the test channel (messages and threads); with --delete-threads it removes the threads: python scripts/test_channel_audit.py [--delete-threads]. Run on the VM."""
import asyncio
import sys

from _boot import boot, finish

from bot.core.ctx import fetch_channel
from bot.core.env import cfg


async def main():
    client = await boot(claims=False)
    ch = await fetch_channel(cfg.test_id)
    msgs = [m async for m in ch.history(limit=100)]
    print('messages:', len(msgs), [(m.author.name, (m.content or '')[:40], m.type.name, m.pinned) for m in msgs[:12]])
    threads = list(ch.threads)
    try:
        threads += [t async for t in ch.archived_threads(limit=100)]
    except Exception as e:
        print('archived threads not readable:', e)
    print('threads:', [(t.id, t.name, t.archived) for t in threads])
    print('pins:', len(await ch.pins()))
    if '--delete-threads' in sys.argv:
        for t in threads:
            await t.delete()
        print('deleted', len(threads), 'threads')
    await finish(client)


asyncio.run(main())
