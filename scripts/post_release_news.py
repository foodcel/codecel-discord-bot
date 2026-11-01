"""Posts the release announcements: devs (pinging the Developers role) and testers (pinging the Tester role). Posts only with --yes.
    python scripts/post_release_news.py --yes"""
import asyncio
import sys

import discord

from _boot import boot, finish

from bot.botnews import release_news_devs_embeds, release_news_testers_embeds
from bot.ctx import fetch_channel

DEV_CHANNEL, DEV_ROLE = 1565961892264939531, 1562719404473458778
TESTER_CHANNEL, TESTER_ROLE = 1565825094801170492, 1562726451797565521


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    for channel, role, embeds in ((DEV_CHANNEL, DEV_ROLE, release_news_devs_embeds()), (TESTER_CHANNEL, TESTER_ROLE, release_news_testers_embeds())):
        ch = await fetch_channel(channel)
        sent = await ch.send(content=f'<@&{role}>', embeds=embeds, allowed_mentions=discord.AllowedMentions(roles=[discord.Object(id=role)]))
        print(ch.name, '->', sent.jump_url, '| roles pinged:', [r.id for r in sent.role_mentions], '| everyone:', sent.mention_everyone)
    await finish(client)


asyncio.run(main())
