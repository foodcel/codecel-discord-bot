"""Posts the new-game card of one released game in #games, silent (no ping): python scripts/post_card.py "Jump King". Run on the VM."""
import asyncio
import sys

from _boot import boot, finish

from bot.cards import post_new_game_card
from bot.db import one, run
from bot.db import now
from bot.games import key


async def main():
    client = await boot()
    row = one("SELECT * FROM game_status WHERE key=? AND status='released'", key(sys.argv[1]))
    if not row:
        print('not released:', sys.argv[1])
    else:
        sent = await post_new_game_card(row, 'none')
        run('UPDATE game_status SET card_at=? WHERE key=?', now(), row['key'])
        print('card:', row['name'], sent.id if sent else None, '| everyone:', getattr(sent, 'mention_everyone', None))
    await finish(client)


asyncio.run(main())
