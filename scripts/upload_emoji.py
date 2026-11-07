"""Uploads every GIF in assets/emoji as a server emoji (named like the file) and shows them in the test channel: python scripts/upload_emoji.py --yes. Run on the VM."""
import asyncio
import sys
from pathlib import Path

import discord
from _boot import boot, finish

from bot.core.ctx import ctx, fetch_channel
from bot.core.env import cfg

GIF = Path(__file__).resolve().parent.parent / 'assets' / 'emoji' / 'vibecoding.gif'  # the folder with every emoji GIF


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not running. Pass --yes.')
        return await finish(client)
    shown = []
    have = {e.name: e for e in await (await client.fetch_guild(int(ctx.guild.id))).fetch_emojis()}  # fetched: the small client has no emoji cache, so a cached check made duplicates
    for gif in sorted(GIF.parent.glob('*.gif')):
        emoji = have.get(gif.stem)
        if not emoji:
            emoji = await ctx.guild.create_custom_emoji(name=gif.stem, image=gif.read_bytes(), reason='Codecel emoji pack')
        shown.append(f'{emoji} `:{gif.stem}:`')
    print('emoji', len(shown), 'of', ctx.guild.emoji_limit, 'slots per kind')
    ch = await fetch_channel(cfg.test_id)
    await ch.send('**Emoji pack** (not posted anywhere else)' + chr(10) + chr(10).join(shown), allowed_mentions=discord.AllowedMentions.none())
    await finish(client)


asyncio.run(main())
