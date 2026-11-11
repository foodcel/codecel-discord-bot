"""Posts the three safe-MCP cards for real in the dev announcements channel, with no ping. Run only after the owner said so.
    python scripts/announce_safe.py --yes        run on the VM"""
import asyncio
import sys

from _boot import boot, finish
from announce_drafts import cards

from bot.core.ctx import fetch_channel
from bot.discord_ui.components import NO_MENTIONS

DEV_CHANNEL = '1565961892264939531'      # #annoucements in the dev category


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(DEV_CHANNEL)
    for label, (view, files), _ in cards():
        if 'safe mcp' in label:
            m = await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
            print('posted', label, m.jump_url)
    await finish(client)


asyncio.run(main())
