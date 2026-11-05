"""Checks the testers' forum end to end without telling any dev: makes the game's tag, makes a post with it, then deletes the post. Run on the VM."""
import asyncio
import sys

from _boot import boot, finish

from bot.core.ctx import fetch_channel
from bot.core.env import cfg
from bot.features.bugs.tags import ensure_tester_tag
from bot.features.bugs.tester import known_games, resolve_game


async def main():
    client = await boot()
    print('games a tester can pick:', known_games())
    for q in sys.argv[1:]:
        print('resolve', q, '->', resolve_game(q))
    name = resolve_game(sys.argv[1])[0]
    tag, problem = await ensure_tester_tag(name)
    print('tag', tag and (tag.id, tag.name), problem)
    forum = await fetch_channel(cfg.tester_forum_id)
    created = await forum.create_thread(name='check (deleted right away)', content='check', applied_tags=[tag] if tag else [])
    print('post made', created.thread.id, [t.name for t in created.thread.applied_tags])
    await created.thread.delete()
    print('post deleted')
    await finish(client)


asyncio.run(main())
