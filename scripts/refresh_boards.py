"""Redraws every dev bug board now (bugs move to the dev who owns the game). Run on the VM, where the real database is."""
import asyncio

from _boot import boot, finish

from bot.features.bugs.devboard import refresh_all_boards


async def main():
    client = await boot()
    await refresh_all_boards()
    print('boards refreshed')
    await finish(client)


asyncio.run(main())
