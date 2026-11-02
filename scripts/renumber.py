"""Gives every bug and suggestion post its number within its game (Sonic Dimensions #3): renames the posts that start with the old global number.
Run on the VM:  python scripts/renumber.py --yes"""
import asyncio
import re
import sys

from _boot import boot, finish

from bot import nums
from bot.db import all_


async def main():
    client = await boot(claims=False)
    done = skipped = 0
    for b in all_("SELECT * FROM bugs WHERE thread_id IS NOT NULL AND thread_id != '0' AND deleted=0 ORDER BY id"):
        try:
            t = await client.fetch_channel(int(b['thread_id']))
        except Exception:
            skipped += 1
            continue
        m = re.match(r'^#(\d+)\s+(.*)$', t.name, re.S)
        if not m:
            skipped += 1
            continue
        new = f"{nums.label(b)} {m.group(2)}"[:100]
        if new == t.name:
            continue
        print(t.name[:40], '->', new[:40])
        if '--yes' in sys.argv:
            try:
                await t.edit(name=new, archived=False) if t.archived else await t.edit(name=new)
                done += 1
            except Exception as e:
                print('  could not rename', repr(e))
            await asyncio.sleep(1)
    print('renamed', done, 'skipped', skipped)
    await finish(client)


asyncio.run(main())
