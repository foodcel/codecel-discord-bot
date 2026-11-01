"""Posts the release announcements for devs and for testers in the test channel (nothing pings).   python scripts/preview_news.py"""
import asyncio

import discord

from _boot import boot, finish

from bot.botnews import release_news_devs_embeds, release_news_testers_embeds
from bot.ctx import fetch_channel
from bot.env import cfg


async def main():
    client = await boot(claims=False)
    ch = await fetch_channel(cfg.test_id)
    none = discord.AllowedMentions.none()
    await ch.send(content='🧪 **Preview · announcement for devs**', embeds=release_news_devs_embeds(), allowed_mentions=none)
    await ch.send(content='🧪 **Preview · announcement for testers**', embeds=release_news_testers_embeds(), allowed_mentions=none)
    await finish(client)


asyncio.run(main())
