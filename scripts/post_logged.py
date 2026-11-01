"""Posts the usual "LOGGED · #id is sent to the developer" reply on logged, still-open posts that never got one (the first-start import is silent).
Posts that already have a LOGGED reply, archived posts and fixed or closed ones are left alone. Prints the list without --yes. Run on the VM.
    python scripts/post_logged.py [--yes]"""
import asyncio
import sys

import discord

from _boot import boot, finish

from bot.ctx import fetch_channel
from bot.db import all_
from bot.ui import E, EM


async def has_logged(t, me):
    async for m in t.history(limit=100):
        if m.author.id == me and 'LOGGED' in (m.content or ''):
            return True
    return False


async def main():
    client = await boot(claims=False)
    todo, skipped = [], []
    for b in all_("SELECT * FROM bugs WHERE deleted=0 AND routed=1 AND status IN ('new','investigating','fixing') AND source IS NOT 'tester' AND thread_id IS NOT NULL ORDER BY id"):
        t = await fetch_channel(b['thread_id'])
        if not t:
            continue
        if t.archived:
            skipped.append((b['id'], 'archived'))
        elif await has_logged(t, client.user.id):
            continue
        else:
            todo.append((b, t))
    print('need a LOGGED reply:', [b['id'] for b, _ in todo], '| skipped:', skipped)
    if '--yes' in sys.argv:
        for b, t in todo:
            try:
                await t.send(f"{E['new']} **LOGGED**{EM}·{EM}#{b['id']} is sent to the developer. Thanks for the report!", allowed_mentions=discord.AllowedMentions.none())
                print('posted', b['id'])
            except Exception as e:
                print('could not post', b['id'], repr(e))
            await asyncio.sleep(1.5)
    await finish(client)


asyncio.run(main())
