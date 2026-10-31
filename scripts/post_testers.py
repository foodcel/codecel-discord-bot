"""Posts the tester guide and the roster into a channel (and stores where, so they update by themselves). Run where the bot's database is.
    python scripts/post_testers.py --channel=<id> --yes"""
import asyncio
import sys

from _boot import boot, finish

from bot.testers import post_board


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
    ch = await client.fetch_channel(int(arg('channel')))
    removed = await post_board(ch)
    print(f'posted in #{ch.name}; replaced {removed} old message(s)')
    await finish(client)


asyncio.run(main())
