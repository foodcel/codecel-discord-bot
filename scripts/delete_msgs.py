"""Deletes known bot messages: python scripts/delete_msgs.py <channel id> <message id> ... Run on the VM (only messages the bot itself posted)."""
import asyncio
import sys

from _boot import boot, finish

from bot.ctx import fetch_channel


async def main():
    client = await boot(claims=False)
    ch = await fetch_channel(sys.argv[1])
    for mid in sys.argv[2:]:
        try:
            m = await ch.fetch_message(int(mid))
            if m.author.id == client.user.id:
                await m.delete()
                print('deleted', mid)
        except Exception as e:
            print(mid, repr(e))
    await finish(client)


asyncio.run(main())
