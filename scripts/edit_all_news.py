"""Rewrites every announcement this bot posted in the dev and tester announcement channels in the current look (same ping, nobody is pinged again).
Run on the VM:  python scripts/edit_all_news.py --yes"""
import asyncio
import sys

from _boot import boot, finish

from bot import botnews as n

DEVS, TESTERS = 1565961892264939531, 1565825094801170492
POSTS = [
    (DEVS, 1565976993957158973, n.bot_news_embeds), (DEVS, 1566045632060334262, n.board_news_embeds),
    (DEVS, 1566057077431083215, n.suggestion_news_embeds), (DEVS, 1566164080023044239, n.roster_news_devs_embeds),
    (DEVS, 1566414001368338563, n.release_news_devs_embeds),
    (TESTERS, 1565993946704912460, n.tester_news_embeds), (TESTERS, 1566164064906907839, n.roster_news_testers_embeds),
    (TESTERS, 1566414002332901479, n.release_news_testers_embeds),
]


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not editing. Pass --yes.')
        return await finish(client)
    for channel, message, build in POSTS:
        ch = await client.fetch_channel(channel)
        msg = await ch.fetch_message(message)
        await msg.edit(embeds=build())  # the content (the ping) stays; editing never pings again
        print('edited', build.__name__, msg.jump_url)
    await finish(client)


asyncio.run(main())
