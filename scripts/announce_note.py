"""Posts the tester-card notes announcement in the dev announcements channel, pinging @Developers. Run only after the owner said so.
    python scripts/announce_note.py --yes        run on the VM"""
import asyncio
import sys

import discord
from _boot import boot, finish
from announce_drafts import NOTE, build

from bot.core.ctx import fetch_channel
from bot.core.env import cfg

DEV_CHANNEL = '1565961892264939531'      # #annoucements in the dev category


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(DEV_CHANNEL)
    v, f = build('📝 Notes on tester cards', NOTE, ['/progress · set a note', '/help · every command'], ping=f'<@&{cfg.dev_role}>')
    m = await ch.send(view=v, files=f, allowed_mentions=discord.AllowedMentions(roles=[discord.Object(int(cfg.dev_role))]))
    print('posted', m.jump_url)
    await finish(client)


asyncio.run(main())
