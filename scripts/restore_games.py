"""One-off (2026-11-01): removes the five Redwing Helper messages in #games (the user chose to keep this bot's library) and puts the Deltarune and
Peggle new-game cards back WITHOUT any ping. Only deletes messages written by the bot named "Redwing Helper". Run on the VM. Needs --yes."""
import asyncio
import sys

import discord

from _boot import boot, finish

from bot.cards import new_game_card
from bot.ctx import fetch_channel
from bot.db import add_timer, one, run
from bot.games import key

CHANNEL = 1562940878685872149  # #games
THEIRS = (1566568186382389371, 1566568190681550919, 1566568192267260016, 1566568194368344176, 1566568196335608010)
DAY = 86400000
# card -> when it should leave again (the original 3 days)
CARDS = (('YOU SHOULD MAKE DELTARUNE PLEASE', 1793511748084 + 3 * DAY), ('Peggle', 1793479248980 + 3 * DAY))


async def main():
    client = await boot()
    ch = await fetch_channel(CHANNEL)
    doomed = []
    for mid in THEIRS:
        m = await ch.fetch_message(mid)
        assert m.author.bot and 'Redwing Helper' in m.author.name, f'{mid} is not Redwing Helper'
        doomed.append(m)
    print('would delete:', [(m.id, m.author.name) for m in doomed])
    if '--yes' not in sys.argv:
        return await finish(client)
    for m in doomed:
        await m.delete()
    print('deleted', len(doomed))
    for name, leave_at in CARDS:
        row = one("SELECT * FROM game_status WHERE key=? AND status='released'", key(name))
        view, files = new_game_card(row, None)  # no ping text
        sent = await ch.send(view=view, files=files, allowed_mentions=discord.AllowedMentions.none())
        add_timer('delete_card', f'{ch.id}:{sent.id}', leave_at)
        run('UPDATE game_status SET card_at=? WHERE key=?', 1, key(name))
        print('card back, silent:', row['name'], sent.id, '| everyone:', sent.mention_everyone, '| roles:', [r.id for r in sent.role_mentions])
    await finish(client)


asyncio.run(main())
