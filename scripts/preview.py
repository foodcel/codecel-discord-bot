"""Usage: python scripts/preview.py [all|bug|board|announcement|rules|messages|transcript|...]
Logs in as the bot (a second session, safe while the bot runs) and posts previews to TEST_CHANNEL_ID."""
import asyncio
import sys

from _boot import boot, finish

from bot.previews import post_previews


async def main():
    client = await boot()
    n = await post_previews(sys.argv[1] if len(sys.argv) > 1 else 'all')
    print(f'posted {n} preview message(s)')
    await finish(client)


asyncio.run(main())
