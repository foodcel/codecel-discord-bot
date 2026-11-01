"""Redraws the library messages now (edits them in place). Run on the VM, where the real database lives."""
import asyncio

from _boot import boot, finish

from bot.cards import refresh_library


async def main():
    client = await boot()
    await refresh_library(force=True)
    print('library refreshed')
    await finish(client)


asyncio.run(main())
