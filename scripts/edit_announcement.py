"""Rewrites an announcement this bot posted earlier, so it gets the current look (same text, same ping).
Usage: python scripts/edit_announcement.py --channel=<id> --message=<id> [--kind=bot|testers|board] --yes"""
import asyncio
import sys

from _boot import boot, finish

from bot.botnews import board_news_embeds, bot_news_embeds, tester_news_embeds


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


if '--yes' not in sys.argv or not (arg('channel') and arg('message')):
    print('Not editing. Pass --channel=<id> --message=<id> and --yes.')
    sys.exit(0)


async def main():
    client = await boot(claims=False)
    ch = await client.fetch_channel(int(arg('channel')))
    msg = await ch.fetch_message(int(arg('message')))
    embeds = {'testers': tester_news_embeds, 'board': board_news_embeds}.get(arg('kind'), bot_news_embeds)()
    await msg.edit(embeds=embeds)  # the content (the ping) stays; editing never pings again
    print('edited', msg.jump_url)
    await finish(client)


asyncio.run(main())
