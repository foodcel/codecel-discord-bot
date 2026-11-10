"""Gives a bug the right game after the fact (for example when a player picked another game): the bug record, the game in
its post's title, and the dev boards follow. Run on the VM, where the real database is.
    python scripts/set_bug_game.py --bug=83 --game=Peggle"""
import asyncio
import sys

from _boot import boot, finish

from bot.core.ctx import fetch_channel
from bot.core.db import bug_by_id, update_bug
from bot.features.bugs.devboard import refresh_all_boards
from bot.features.bugs.tags import game_tags, retitle


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


async def main():
    client = await boot()
    bug = bug_by_id(int(arg('bug')))
    tag = next((t for t in game_tags() if t['name'].lower() == arg('game').lower()), None)
    if not bug or not tag:
        print('unknown bug or game', bug is not None, [t['name'] for t in game_tags()])
        return await finish(client)
    thread = await fetch_channel(bug['thread_id'])
    update_bug(bug['id'], {'game_tag_id': tag['id'], 'game_name': tag['name']})
    if thread:
        await retitle(thread, bug['game_name'], tag['name'])
    await refresh_all_boards()
    print('bug', bug['id'], 'is now on', tag['name'])
    await finish(client)


asyncio.run(main())
