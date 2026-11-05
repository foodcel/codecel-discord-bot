"""Removes a game's new-game card from #games and moves the game back to unreleased: python scripts/take_back.py "Jump King". Run on the VM."""
import asyncio
import json
import sys

from _boot import boot, finish

from bot.features.games import board
from bot.features.games.cards import _cards_conf, library_config, refresh_library
from bot.core.ctx import fetch_channel
from bot.core.db import cancel_timers, kv_set, one, run
from bot.features.games.games import key, refresh_game_board


async def main():
    client = await boot()
    k = key(sys.argv[1])
    row = one('SELECT * FROM game_status WHERE key=?', k)
    ch = await fetch_channel(library_config()['channel'])
    cards = _cards_conf()
    for c in [c for c in cards if c['key'] == k]:
        cancel_timers('delete_card', f"{ch.id}:{c['msg']}")
        try:
            await (await ch.fetch_message(int(c['msg']))).delete()
            print('card deleted', c['msg'])
        except Exception as e:
            print('card', c['msg'], repr(e))
    kv_set('library_cards', json.dumps([c for c in cards if c['key'] != k]))
    run("UPDATE game_status SET status='unreleased', released_at=NULL, card_at=NULL WHERE key=?", k)
    if board.is_live():
        board.set_completed(row['name'], False)
        await board.reload_claims()
    await refresh_game_board()
    await refresh_library()
    print('unreleased:', row['name'])
    await finish(client)


asyncio.run(main())
