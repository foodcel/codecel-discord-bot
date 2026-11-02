"""Lists the bot's posts in the dev and tester announcement channels (id, title, date). Run on the VM."""
import asyncio

from _boot import boot, finish

from bot.ctx import fetch_channel

CHANNELS = {'devs': 1565961892264939531, 'testers': 1565825094801170492}


async def main():
    client = await boot(claims=False)
    for name, cid in CHANNELS.items():
        ch = await fetch_channel(cid)
        print('==', name, ch.name)
        async for m in ch.history(limit=100, oldest_first=True):
            title = m.embeds[0].title if m.embeds else (m.content or '')[:50]
            print(m.id, m.author.name, 'BOT' if m.author.bot else 'HUMAN', m.created_at.strftime('%m-%d %H:%M'), '|', (title or '')[:70].replace('\n', ' '))
    await finish(client)


asyncio.run(main())
