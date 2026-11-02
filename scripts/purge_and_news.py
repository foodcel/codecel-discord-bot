"""Empties #future-games and the test channel, shows the two announcements in the test channel (no pings), and posts the testing board again.
Run on the VM:  python scripts/purge_and_news.py --yes"""
import asyncio
import sys

import discord

from _boot import boot, finish

from bot.botnews import as_card, testing_news_devs_embeds, testing_news_testers_embeds
from bot.ctx import fetch_channel
from bot.env import cfg
from bot.games import refresh_testing_board

DEV_ROLE, TESTER_ROLE = 1562719404473458778, 1562726451797565521


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not purging. Pass --yes.')
        return await finish(client)
    for cid in ((cfg.test_id,) if '--news-only' in sys.argv else (cfg.future_games_id, cfg.test_id)):
        ch = await fetch_channel(cid)
        n = len(await ch.purge(limit=None, bulk=True, reason='Cleared on request'))
        print('purged', ch.name, n)
    ch = await fetch_channel(cfg.test_id)
    none = discord.AllowedMentions.none()
    for role, build in ((DEV_ROLE, testing_news_devs_embeds), (TESTER_ROLE, testing_news_testers_embeds)):
        view, files = as_card(build()[0], ping=f'<@&{role}>')
        await ch.send(view=view, files=files, allowed_mentions=none)
    if '--news-only' not in sys.argv:
        await refresh_testing_board()
    print('done')
    await finish(client)


asyncio.run(main())
