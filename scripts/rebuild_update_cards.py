"""Redraws the update cards of a channel in place from what was saved when they were posted (the lines, the poster, the date).
Run on the VM (the real database lives there).   python scripts/rebuild_update_cards.py --channel=<id>"""
import asyncio
import json
import sys

import discord

from _boot import boot, finish

from bot.cards import released_row_for, update_card
from bot.ctx import fetch_channel
from bot.db import all_, get_game
from bot.games import owner_ids


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


async def main():
    client = await boot(claims=False)
    ch = await fetch_channel(arg('channel'))
    for r in all_('SELECT * FROM announcements WHERE channel_id=? AND message_id IS NOT NULL AND payload IS NOT NULL ORDER BY id', str(ch.id)):
        try:
            msg = await ch.fetch_message(int(r['message_id']))
        except Exception:
            continue
        if msg.embeds:
            continue
        p = json.loads(r['payload'])
        g = get_game(r['tag_id']) or {'name': r['game_name']}
        game = {'name': g.get('name') or r['game_name'], 'link': g.get('link')}
        row = released_row_for(game['name'])
        poster = p.get('poster') or ((owner_ids(row) or [None])[0] if row else None)
        changes = p['changes'] if 'changes' in p else p.get('updates', [])
        view, files = update_card(game, row, p.get('bugfixes', []), changes, p.get('new', []), p.get('version', ''),
                                  f"<@&{p['ping_role']}>" if p.get('ping_role') else None, when=msg.created_at, poster=poster)
        await msg.edit(view=view, attachments=files, allowed_mentions=discord.AllowedMentions.none())
        print('rebuilt', game['name'], msg.id)
    await finish(client)


asyncio.run(main())
