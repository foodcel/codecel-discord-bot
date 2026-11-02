"""Holds a live new-game card's game out of the library until the card's 3 days are over, and redraws the card with the cropped picture:
python scripts/fix_card.py "Jump King". Run on the VM."""
import asyncio
import json
import sys

import discord

from _boot import boot, finish

from bot.cards import _cards_conf, library_config, new_game_card, refresh_library
from bot.ctx import fetch_channel
from bot.db import kv_set, one
from bot.games import key


async def main():
    client = await boot(claims=False)
    k = key(sys.argv[1])
    ch = await fetch_channel(library_config()['channel'])
    cards = _cards_conf()
    row = one("SELECT * FROM game_status WHERE key=? AND status='released'", k)
    for c in cards:
        if c['key'] == k:
            c['hold'] = True
            msg = await ch.fetch_message(int(c['msg']))
            top = msg.components[0].children[0] if msg.components and getattr(msg.components[0], 'children', None) else None
            ping = getattr(top, 'content', None) if top is not None and getattr(top, 'content', '').startswith(('@', '<@&')) else None
            view, files = new_game_card(row, ping)
            await msg.edit(view=view, attachments=files, allowed_mentions=discord.AllowedMentions.none())
            print('card redrawn', c['msg'], 'ping line:', ping)
    kv_set('library_cards', json.dumps(cards))
    await refresh_library()
    print('held out of the library:', [c['key'] for c in cards if c.get('hold')])
    await finish(client)


asyncio.run(main())
