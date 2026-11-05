"""Posts (or redraws) the board of games in testing in #future-games. Run on the VM."""
import asyncio

from _boot import boot, finish

from bot.features.games.games import refresh_testing_board


async def main():
    client = await boot()
    await refresh_testing_board()
    print('testing board ready')
    await finish(client)


asyncio.run(main())
