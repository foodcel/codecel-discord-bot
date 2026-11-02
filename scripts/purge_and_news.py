"""Empties #future-games and the test channel, shows the two announcements in the test channel (no pings), and posts the testing board again.
Run on the VM:  python scripts/purge_and_news.py --yes"""
import asyncio
import sys

import discord

from _boot import boot, finish

from bot.botnews import testing_news_devs_embeds, testing_news_testers_embeds
from bot.ctx import fetch_channel
from bot.env import cfg
from bot.games import refresh_testing_board

DEV_ROLE, TESTER_ROLE = 1562719404473458778, 1562726451797565521


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not purging. Pass --yes.')
        return await finish(client)
    for cid in (cfg.future_games_id, cfg.test_id):
        ch = await fetch_channel(cid)
        n = len(await ch.purge(limit=None, bulk=True, reason='Cleared on request'))
        print('purged', ch.name, n)
    ch = await fetch_channel(cfg.test_id)
    none = discord.AllowedMentions.none()
    await ch.send(content=f'<@&{DEV_ROLE}>', embeds=testing_news_devs_embeds(), allowed_mentions=none)
    await ch.send(content=f'<@&{TESTER_ROLE}>', embeds=testing_news_testers_embeds(), allowed_mentions=none)
    await refresh_testing_board()
    print('done')
    await finish(client)


asyncio.run(main())
