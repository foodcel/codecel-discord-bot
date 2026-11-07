"""Uploads every GIF in assets/emoji as an APPLICATION emoji (owned by the bot, usable anywhere, also in its status): python scripts/upload_app_emoji.py --yes"""
import asyncio
import sys
from pathlib import Path

from _boot import boot, finish

DIR = Path(__file__).resolve().parent.parent / 'assets' / 'emoji'


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not running. Pass --yes.')
        return await finish(client)
    have = {e.name: e for e in await client.fetch_application_emojis()}
    for gif in sorted(DIR.glob('*.gif')):
        e = have.get(gif.stem) or await client.create_application_emoji(name=gif.stem, image=gif.read_bytes())
        print(e.name, e.id, e.animated)
    await finish(client)


asyncio.run(main())
