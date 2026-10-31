"""Posts the tester guide and the roster into a channel (and stores where, so they update by themselves). Run where the bot's database is.
    python scripts/post_testers.py --channel=<id> --yes"""
import asyncio
import json
import sys

from _boot import boot, finish

from bot.db import kv_set
from bot.testers import guide_embed, import_old, roster_embed


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


if '--yes' not in sys.argv or not arg('channel'):
    print('Not posting. Pass --channel=<id> and --yes.')
    sys.exit(0)


async def main():
    client = await boot(members=True, claims=False)
    print('imported', await import_old(), 'testers from the old message')
    ch = await client.fetch_channel(int(arg('channel')))
    g = await ch.send(embed=guide_embed())
    r = await ch.send(embed=roster_embed())
    kv_set('testerboard', json.dumps({'channelId': str(ch.id), 'guide': str(g.id), 'roster': str(r.id)}))
    print('posted', r.jump_url)
    await finish(client)


asyncio.run(main())
