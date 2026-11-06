"""Posts the handoff doc (docs/HANDOFF-REDWING-HELPER.md) in staff chat as a card, pinging Redwing Helper: python scripts/post_handoff.py --yes. Run on the VM."""
import asyncio
import sys
from pathlib import Path

import discord
from _boot import boot, finish

from bot.core.ctx import fetch_channel
from bot.discord_ui.card import card

STAFF_CHAT = '1563043690732068975'
HELPER = 1565900080894967809
DOC = Path(__file__).resolve().parent.parent / 'docs' / 'HANDOFF-REDWING-HELPER.md'
NAME = 'codecel-handoff.md'


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(STAFF_CHAT)
    nl = chr(10)
    blocks = ['What Codecel does and touches: its commands, the channels it posts in or manages, and what runs by itself. The full list is attached.',
              nl.join(['• Codecel owns **#🎮・games**: it deletes other bots\' messages and webhooks there, so do not post in it.',
                       '• If you ping or mention Codecel, it answers with a GIF.',
                       '• Its commands are hidden by role, so players only see the player ones.'])]
    view, files = card('📘 Codecel handoff', blocks, ['Questions about Codecel: ask in this chat'], right=None, ping=f'<@{HELPER}>',
                       files=[discord.File(str(DOC), filename=NAME)], media={'files': [NAME]})
    msg = await ch.send(view=view, files=files, allowed_mentions=discord.AllowedMentions(users=[discord.Object(HELPER)]))
    print('posted', msg.jump_url)
    await finish(client)


asyncio.run(main())
