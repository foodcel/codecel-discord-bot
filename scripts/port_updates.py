"""Ports this bot's update embeds in a channel to the new card look (posted again, oldest first, no ping), then deletes every other message in the channel.
Everything deleted is first saved to data/backup-<channel>-<time>.json. Prints the plan without --yes. Run on the VM (the real database lives there).
    python scripts/port_updates.py --channel=<id> [--yes]"""
import asyncio
import json
import sys
import time
from pathlib import Path

import discord

from _boot import boot, finish

from bot.cards import released_row_for, update_card
from bot.ctx import fetch_channel
from bot.db import get_game, run
from bot.games import owner_ids
from bot.tags import find_game_tag


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


def lines_of(embed, marker):
    for f in embed.fields:
        if marker in f.name.upper():
            return [ln.strip()[1:].strip() for ln in f.value.split(chr(10)) if ln.strip().startswith('•')]
    return []


async def main():
    client = await boot(claims=False)
    ch = await fetch_channel(arg('channel'))
    msgs = [m async for m in ch.history(limit=500, oldest_first=True)]
    mine = [m for m in msgs if m.author.id == client.user.id and m.embeds and (lines_of(m.embeds[0], 'BUG FIXES') or lines_of(m.embeds[0], 'UPDATES'))]
    print(ch.name, '|', len(msgs), 'messages | to port:', [(m.id, m.embeds[0].title) for m in mine], '| to delete:', len(msgs) - len(mine))
    if '--yes' not in sys.argv:
        return await finish(client)
    out = Path(__file__).resolve().parent.parent / 'data' / f'backup-{ch.id}-{int(time.time())}.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps([{'id': m.id, 'author': str(m.author), 'at': m.created_at.isoformat(), 'content': m.content,
                                'embeds': [e.to_dict() for e in m.embeds], 'reactions': [(str(r.emoji), r.count) for r in m.reactions]} for m in msgs],
                              ensure_ascii=False, indent=1), encoding='utf8')
    print('backup saved:', out)
    keep = set()
    for m in mine:
        e = m.embeds[0]
        tag = find_game_tag(e.title)
        name = tag['name'] if tag else e.title.title()
        row = released_row_for(name)
        game = {'name': name, 'link': (get_game(tag['id']) or {}).get('link') if tag else None}
        owners = owner_ids(row) if row else []
        view, files = update_card(game, row, lines_of(e, 'BUG FIXES'), lines_of(e, 'UPDATES'), [], '', None, when=m.created_at, poster=owners[0] if owners else None)
        sent = await ch.send(view=view, files=files, allowed_mentions=discord.AllowedMentions.none())
        run('UPDATE announcements SET message_id=? WHERE message_id=?', str(sent.id), str(m.id))
        keep.add(sent.id)
        print('ported', name, '->', sent.id)
    doomed = [m for m in msgs]
    for i in range(0, len(doomed), 100):
        chunk = doomed[i:i + 100]
        try:
            if len(chunk) > 1:
                await ch.delete_messages(chunk)
            else:
                await chunk[0].delete()
        except Exception as e:
            print('bulk delete failed, one by one:', repr(e))
            for m in chunk:
                try:
                    await m.delete()
                except Exception:
                    pass
    print('deleted', len(doomed), '| left:', len([m async for m in ch.history(limit=50)]))
    await finish(client)


asyncio.run(main())
