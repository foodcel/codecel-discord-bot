"""Posts the game library in a channel and remembers it: from then on every release, edit, unrelease and link change updates it,
and /release new puts its 3-day card in the same channel. Run on the VM (the real database lives there).
    python scripts/post_library.py --channel=<id> [--yes]   (without --yes it only says what it would do)"""
import asyncio
import json
import sys

from _boot import boot, finish

from bot.features.games.cards import library_pages, refresh_library
from bot.core.ctx import fetch_channel
from bot.core.db import kv_set
from bot.features.games.games import game_lists


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


async def main():
    client = await boot()
    ch = await fetch_channel(arg('channel'))
    rows = game_lists()['released']
    print('channel', ch.name, '| released games:', len(rows), '| messages:', len(library_pages(rows)))
    if '--yes' in sys.argv:
        kv_set('library', json.dumps({'channel': str(ch.id), 'messages': [], 'digests': []}))
        await refresh_library(force=True)
        print('posted')
    await finish(client)


asyncio.run(main())
