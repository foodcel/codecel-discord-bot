"""Prints which dev owns each #bugs game tag, using the live bounty-board."""
import asyncio

from _boot import boot, finish

from bot.bounty import board_name_for, get_claims, owners_for
from bot.ctx import ctx
from bot.tags import game_tags


async def main():
    client = await boot(members=True)
    print(f'claims read: {len(get_claims())}')
    for t in game_tags():
        names = []
        for id_ in owners_for(t['id'], t['name']):
            try:
                names.append((ctx.guild.get_member(int(id_)) or await ctx.guild.fetch_member(int(id_))).display_name)
            except Exception:
                names.append(id_)
        print(f"{t['name']:<20} -> {', '.join(names) or 'UNCLAIMED'}   (board: {board_name_for(t['id'], t['name']) or '-'})")
    await finish(client)


asyncio.run(main())
