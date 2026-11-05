"""Builds every card the bot can make now and checks it serialises (no Discord calls). Run on the VM."""
import asyncio

from _boot import boot, finish

from bot.features.bugs import devboard
from bot.discord_ui import help as helpmod
from bot.core.ctx import ctx
from bot.discord_ui.look import card_from_embed, clone_rows


async def main():
    client = await boot()
    me = ctx.guild.me
    for n in range(4):
        e, view = helpmod._page(me, n)
        card, files = card_from_embed(e, below=clone_rows(view))
        print('help page', n, len(card.to_components()), 'parts')
    keys = ['unclaimed', 'Sunclaimed'] + [r['k'][len('devthread:'):] for r in __import__('bot.db', fromlist=['kv_keys']).kv_keys('devthread:')]
    for k in keys:
        v, f = devboard.board_card(k)
        print('board', k, 'ok', len(v.to_components()))
    await finish(client)


asyncio.run(main())
