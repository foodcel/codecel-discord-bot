"""Prints how the bounty-board embeds start (to find stray empty lines). Run on the VM."""
import asyncio

from _boot import boot, finish

from bot.features.games import board


async def main():
    client = await boot()
    top, unreleased, released = await board.build_embeds()
    for e in (top, unreleased, released):
        print('TITLE', repr(e.title), '| DESC', repr(e.description))
        for f in e.fields[:2]:
            print('   FIELD', repr(f.name), 'inline' if f.inline else 'block', repr(f.value[:80]))
    await finish(client)


asyncio.run(main())
