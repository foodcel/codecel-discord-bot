"""Uploads assets/emoji/vibecoding.gif as the server emoji :vibecoding: and shows it in the test channel: python scripts/upload_emoji.py --yes. Run on the VM."""
import asyncio
import sys
from pathlib import Path

import discord
from _boot import boot, finish

from bot.core.ctx import ctx, fetch_channel
from bot.core.env import cfg

GIF = Path(__file__).resolve().parent.parent / 'assets' / 'emoji' / 'vibecoding.gif'


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not running. Pass --yes.')
        return await finish(client)
    emoji = discord.utils.get(ctx.guild.emojis, name='vibecoding')
    if not emoji:
        emoji = await ctx.guild.create_custom_emoji(name='vibecoding', image=GIF.read_bytes(), reason='Codecel status emoji')
    print('emoji', emoji.id, 'animated', emoji.animated)
    ch = await fetch_channel(cfg.test_id)
    await ch.send(f'**Emoji preview** {emoji} vibecoding...', allowed_mentions=discord.AllowedMentions.none())
    await finish(client)


asyncio.run(main())
