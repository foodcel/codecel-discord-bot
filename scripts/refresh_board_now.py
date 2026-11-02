"""Redraws the bounty-board's pinned messages now (after the layout changed). Run on the VM."""
import asyncio

from _boot import boot, finish

from bot import board
from bot.games import game_embeds, game_lists


async def main():
    client = await boot()
    lists = game_lists()
    print({k: len(v) for k, v in lists.items()})
    for e in await game_embeds():
        print(e.title, len(e.fields), 'fields')
    await board.refresh_board()
    print('board refreshed')
    await finish(client)


asyncio.run(main())
