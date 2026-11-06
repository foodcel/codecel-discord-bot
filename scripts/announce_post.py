"""Posts the announcements for real: the two developer cards in the dev announcements channel (the first pings @Developers) and the tester card in the tester
announcements channel (pings @Tester). Run only after the owner said where and whether to ping.
    python scripts/announce_post.py --yes        run on the VM"""
import asyncio
import sys

import discord
from _boot import boot, finish
from announce_drafts import DEV, MCP, TESTER, build

from bot.core.ctx import fetch_channel
from bot.core.env import cfg

DEV_CHANNEL = '1565961892264939531'      # #annoucements in the dev category
TESTER_CHANNEL = '1565825094801170492'   # #announcements in the tester category


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    dev_ch, tester_ch = await fetch_channel(DEV_CHANNEL), await fetch_channel(TESTER_CHANNEL)
    dev_ping, tester_ping = f'<@&{cfg.dev_role}>', f'<@&{cfg.tester_ping_role}>'
    v, f = build('🛠️ Dev update', DEV, ['/help · every command', '/update edit · change a posted update'], ping=dev_ping)
    m1 = await dev_ch.send(view=v, files=f, allowed_mentions=discord.AllowedMentions(roles=[discord.Object(int(cfg.dev_role))]))
    v, f = build('🔌 MCP for developers', MCP, ['/mcp setup · connect your agent', '/update settings · when your agent posts'])
    m2 = await dev_ch.send(view=v, files=f, allowed_mentions=discord.AllowedMentions.none())
    v, f = build('🧪 Tester update', TESTER, ['/bug · report a bug', '/tester profile · your details'], ping=tester_ping)
    m3 = await tester_ch.send(view=v, files=f, allowed_mentions=discord.AllowedMentions(roles=[discord.Object(int(cfg.tester_ping_role))]))
    print('posted', m1.jump_url, m2.jump_url, m3.jump_url)
    await finish(client)


asyncio.run(main())
