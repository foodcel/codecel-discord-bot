"""Posts the bug bot launch announcement.
Usage: python scripts/post_announcement.py --channel=<id> [--kind=bot|testers|board] [--ping | --role=<roleId>] --yes
--kind=testers posts the /bug announcement for testers. --role pings only that role.
ONLY run this after the user approved the text AND the channel. It refuses to run without --yes and --channel.
--ping adds an @everyone ping (only members who can see that channel are notified)."""
import asyncio
import sys

import discord

from _boot import boot, finish

from bot.botnews import board_news_embeds, bot_news_embeds, tester_news_embeds


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


channel_id = arg('channel')
if '--yes' not in sys.argv or not channel_id:
    print('Not posting. Pass --channel=<id> and --yes after the user approved the announcement and the channel.')
    sys.exit(0)


async def main():
    client = await boot(claims=False)
    ch = await client.fetch_channel(int(channel_id))
    ping = '--ping' in sys.argv
    role = arg('role')
    embeds = {'testers': tester_news_embeds, 'board': board_news_embeds}.get(arg('kind'), bot_news_embeds)()
    msg = await ch.send(
        content=f'<@&{role}>' if role else '@everyone' if ping else None, embeds=embeds,
        allowed_mentions=discord.AllowedMentions(everyone=ping, roles=[discord.Object(id=int(role))] if role else False, users=False))
    print('posted', msg.jump_url)
    await finish(client)


asyncio.run(main())
