"""Saves the current #games library banner (the gif at the top of the Redwing Helper library message) to assets/games-banner.gif."""
import asyncio
import urllib.request
from pathlib import Path

from _boot import boot, finish

from bot.ctx import fetch_channel


async def main():
    client = await boot(claims=False)
    ch = await fetch_channel(1562940878685872149)
    msg = await ch.fetch_message(1565926079355691129)
    url = None
    for c in [c.to_dict() for c in msg.components]:
        for x in c.get('components', []):
            if x.get('type') == 12:
                url = x['items'][0]['media']['url']
    print('banner url found:', bool(url))
    out = Path(__file__).resolve().parent.parent / 'assets' / 'games-banner.gif'
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'codecel-bot'}), timeout=30).read())
    print('saved', out.stat().st_size, 'bytes')
    await finish(client)


asyncio.run(main())
