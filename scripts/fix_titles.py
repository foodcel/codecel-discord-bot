"""Finds logged bugs whose forum post was never renamed to "#<id> <title>" and renames them (with --yes). Run on the VM.
    python scripts/fix_titles.py [--yes]"""
import asyncio
import sys

from _boot import boot, finish

from bot.ctx import fetch_channel
from bot.db import all_
from bot.ui import cut


async def main():
    client = await boot(claims=False)
    todo = []
    for b in all_("SELECT * FROM bugs WHERE deleted=0 AND thread_id IS NOT NULL AND source IS NOT 'tester' ORDER BY id"):
        t = await fetch_channel(b['thread_id'])
        if not t:
            continue
        only = [a.split('=')[1] for a in sys.argv if a.startswith('--only=')]
        if only and str(b['id']) not in only[0].split(','):
            continue
        if not t.name.startswith(f"#{b['id']} "):
            todo.append((b, t))
    print('posts without their number:', [(b['id'], t.name[:50]) for b, t in todo])
    if '--yes' in sys.argv:
        for b, t in todo:
            try:
                if t.archived:
                    await t.edit(archived=False)
                await t.edit(name=cut(f"#{b['id']} {b['title']}", 100))
                print('renamed', b['id'])
            except Exception as e:
                print('could not rename', b['id'], repr(e))
            await asyncio.sleep(2)
    await finish(client)


asyncio.run(main())
