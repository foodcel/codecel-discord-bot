"""Posts example cards (library, new game, update) in the test channel with made-up data. Nothing pings. Wipes nothing.
    python scripts/preview_cards.py [library|newgame|update|all]"""
import asyncio
import sys

import discord

from _boot import boot, finish

from bot.cards import library_pages, new_game_card, update_card
from bot.ctx import fetch_channel
from bot.env import cfg

HERO = 'https://tr.rbxcdn.com/180DAY-269f8f0a9d59069aa1f233be982fb4d3/768/432/Image/Png/noFilter'
OWNER = str(cfg.owner_id) if getattr(cfg, 'owner_id', None) else '945836832548089886'
SAMPLE = [
    ('Peggle', 'https://www.roblox.com/games/116662126806806/', 'Peggle Deluxe', 'PopCap Games', 'Thunderball Deluxe'),
    ('UNDERTALE', 'https://www.roblox.com/games/111794123776630/', 'Undertale', 'Toby Fox', 'Underground Game'),
    ('SUPERHOT', 'https://www.roblox.com/games/112455482363444/', 'SUPERHOT', 'SUPERHOT Team', None),
    ('Clustertruck', 'https://www.roblox.com/games/116853736743085/', 'Clustertruck', 'Landfall Games', None),
    ('Simpsons', 'https://www.roblox.com/games/100868275775327/', 'The Simpsons: Hit & Run', 'Radical Entertainment', 'The Simpsons Run & Hit'),
    ('Gang Beasts', 'https://www.roblox.com/games/139444303460818/', 'Gang Beasts', 'Boneloaf', 'FUNNY BEASTS'),
    ('Vyra Station', 'https://www.roblox.com/games/121947039198148/', 'Vyra Station', None, None),
    ('x_blocks', 'https://www.roblox.com/games/108938568298960/', 'X-Blocks 360', None, None),
]


def rows():
    return [{'name': n, 'title': orig, 'link': link, 'roblox_name': rb, 'studio': studio, 'owners': OWNER, 'hero_url': HERO, 'icon_url': HERO}
            for n, link, orig, studio, rb in SAMPLE]


async def main():
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    client = await boot(claims=False)
    ch = await fetch_channel(cfg.test_id)
    none = discord.AllowedMentions.none()
    if what in ('library', 'all'):
        for view, files in library_pages(rows()):
            await ch.send(view=view, files=files, allowed_mentions=none)
    if what in ('newgame', 'all'):
        view, files = new_game_card(rows()[0])
        await ch.send(view=view, files=files, allowed_mentions=none)
    if what in ('update', 'all'):
        game = {'name': 'Peggle', 'link': rows()[0]['link']}
        view, files = update_card(game, rows()[0], [
            'Free Ball Bucket: balls that drop into the outer edges now count as caught.',
            'Stage 4-1 (The Amoeban) now has all 105 of its pegs.',
        ], ['Coin flip: a total miss now shows the original spinning coin.'], ['Restart notices: you get a popup before the servers restart.'], 'v16', cfg.updates_role)
        await ch.send(view=view, files=files, allowed_mentions=none)
    await finish(client)


asyncio.run(main())
