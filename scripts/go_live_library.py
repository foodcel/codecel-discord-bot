"""Puts the game library live in #games: posts the new library, then deletes the two old Redwing Helper library messages (only those two ids,
and only if a bot wrote them), then posts the new-game card of the game named with --card (with its real ping). Run on the VM.
    python scripts/go_live_library.py --yes [--card=Peggle]"""
import asyncio
import json
import sys

from _boot import boot, finish

from bot.cards import post_new_game_card, refresh_library
from bot.ctx import fetch_channel
from bot.db import kv_set, one
from bot.games import key

CHANNEL = 1562940878685872149  # #games
OLD = (1565926079355691129, 1565926081796771862)  # the Redwing Helper library messages


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


async def main():
    client = await boot()
    ch = await fetch_channel(CHANNEL)
    old = []
    for mid in OLD:
        m = await ch.fetch_message(mid)
        assert m.author.bot, f'{mid} was not written by a bot'
        old.append(m)
    print('old messages:', [(m.id, str(m.author)) for m in old])
    if '--yes' not in sys.argv:
        return await finish(client)
    kv_set('library', json.dumps({'channel': str(ch.id), 'messages': [], 'digests': []}))
    await refresh_library(force=True)
    print('new library posted')
    for m in old:
        await m.delete()
    print('old library deleted')
    if arg('card'):
        row = one("SELECT * FROM game_status WHERE key=? AND status='released'", key(arg('card')))
        sent = await post_new_game_card(row)
        print('card posted:', sent.jump_url, '| mention_everyone:', sent.mention_everyone)
    await finish(client)


asyncio.run(main())
