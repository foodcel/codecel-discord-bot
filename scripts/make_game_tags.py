"""Makes the tag of each named game in the bugs and improvements forums when it is missing (the same thing /release new does).
    python scripts/make_game_tags.py Peggle Deltarune"""
import asyncio
import sys

from _boot import boot, finish

from bot.features.bugs.tags import ensure_game_tags


async def main():
    client = await boot(claims=False)
    for name in sys.argv[1:]:
        made, problems = await ensure_game_tags(name)
        print(name, '| made in:', made or 'nothing', '|', *problems)
    await finish(client)


asyncio.run(main())
