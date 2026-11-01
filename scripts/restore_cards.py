"""Puts the new-game cards of Deltarune and Peggle back in #games, silent (no ping). They leave 3 days after the game was released. Run on the VM."""
import asyncio

import discord

from _boot import boot, finish

from bot.cards import library_config, new_game_card
from bot.ctx import fetch_channel
from bot.db import add_timer, one, run
from bot.games import key

DAY = 86400000
CARDS = (('YOU SHOULD MAKE DELTARUNE PLEASE', 1793511748084 + 3 * DAY), ('Peggle', 1793479248980 + 3 * DAY))


async def main():
    client = await boot()
    ch = await fetch_channel(library_config()['channel'])
    for name, leave_at in CARDS:
        row = one("SELECT * FROM game_status WHERE key=? AND status='released'", key(name))
        view, files = new_game_card(row, None)
        sent = await ch.send(view=view, files=files, allowed_mentions=discord.AllowedMentions.none())
        add_timer('delete_card', f'{ch.id}:{sent.id}', leave_at)
        run('UPDATE game_status SET card_at=? WHERE key=?', 1, key(name))
        print('card back:', row['name'], sent.id, '| everyone:', sent.mention_everyone, '| roles:', [r.id for r in sent.role_mentions])
    await finish(client)


asyncio.run(main())
