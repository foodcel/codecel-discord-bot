"""Keeps only game tags in the bugs forum (Discord allows 20 tags per forum): removes the device and status tags, then makes the tags
of any released game that has none. Prints what it does; changes things only with --yes. Run on the VM."""
import asyncio
import sys

from _boot import boot, finish

from bot.env import cfg
from bot.games import clean_name, game_lists
from bot.tags import ensure_game_tags, load_tags

DROP = {'mobile', 'computer', 'controller', 'investigating', 'needs info', 'fix in progress', 'fixed', 'duplicate', 'not a bug'}


async def main():
    client = await boot(claims=False)
    forum = await client.fetch_channel(int(cfg.bugs_id))
    keep = [t for t in forum.available_tags if t.name.lower() not in DROP]
    gone = [t.name for t in forum.available_tags if t.name.lower() in DROP]
    print('removing:', gone, '| keeping', len(keep), 'game tags:', [t.name for t in keep])
    if '--yes' in sys.argv:
        await forum.edit(available_tags=keep, reason='All bugs-forum tags are for games')
        await load_tags()
        for g in game_lists()['released']:
            made, problems = await ensure_game_tags(clean_name(g['name']))
            if made or problems:
                print(clean_name(g['name']), '| made in:', made, *problems)
        forum = await client.fetch_channel(int(cfg.bugs_id))
        print('now', len(forum.available_tags), '/ 20:', [t.name for t in forum.available_tags])
    await finish(client)


asyncio.run(main())
