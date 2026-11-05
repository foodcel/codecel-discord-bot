"""Redraws the bounty board, every dev board and the tester roster (the posts that are cards now). Run on the VM."""
import asyncio

from _boot import boot, finish

from bot.features.games import board
from bot.features.bugs import devboard
from bot.features.testers import testers


async def main():
    client = await boot()
    await board.refresh_board()
    print('bounty board done')
    await devboard.refresh_all_boards()
    print('dev boards done')
    await testers.refresh_roster()
    print('roster done')
    await finish(client)


asyncio.run(main())
