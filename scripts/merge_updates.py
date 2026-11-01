"""Merges several update announcements of one game that were posted close together (before merging existed) into the first one:
all their lines go into that embed, the later posts are deleted, and the saved announcement rows follow. Prints what it would do without --yes.
    python scripts/merge_updates.py --channel=<id> --title=<GAME NAME> [--hours=12] [--yes]"""
import asyncio
import json
import sys

import discord

from _boot import boot, finish



def arg(name, default=None):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return default


def lines_of(embed, marker):
    for f in embed.fields:
        if marker in f.name.upper():
            return [ln.strip()[1:].strip() for ln in f.value.split('\n') if ln.strip().startswith('•')]
    return []


async def main():
    client = await boot(claims=False)
    ch = await client.fetch_channel(int(arg('channel')))
    hours = float(arg('hours', '12'))
    posts = []
    async for m in ch.history(limit=200, oldest_first=True):
        if m.author.id == client.user.id and m.embeds and (m.embeds[0].title or '').upper() == arg('title').upper():
            posts.append(m)
    for m in posts:
        e = m.embeds[0]
        print(m.id, m.created_at.strftime('%Y-%m-%d %H:%M'), 'fixes:', lines_of(e, 'BUG FIXES'), 'updates:', lines_of(e, 'UPDATES'), 'reactions:', [(str(r.emoji), r.count) for r in m.reactions])
    # the group: the first post and every later one within the window of the first
    if not posts:
        return await finish(client)
    first = posts[0]
    group = [m for m in posts if (m.created_at - first.created_at).total_seconds() <= hours * 3600]
    print('group', [m.id for m in group])
    if len(group) < 2 or '--yes' not in sys.argv:
        return await finish(client)
    fixes, updates = [], []
    for m in group:
        for ln in lines_of(m.embeds[0], 'BUG FIXES'):
            if ln not in fixes:
                fixes.append(ln)
        for ln in lines_of(m.embeds[0], 'UPDATES'):
            if ln not in updates:
                updates.append(ln)
    # an update line that only says what was fixed is a bug fix (the Updates column should not repeat the Bug fixes)
    for ln in [x for x in updates if x.lower().startswith('fixed')]:
        updates.remove(ln)
        if ln not in fixes:
            fixes.append(ln)
    # the first embed keeps its look (title, date, footer); only its Bug fixes lines change
    e = discord.Embed.from_dict(first.embeds[0].to_dict())
    fix = next(f for f in e.fields if 'BUG FIXES' in f.name.upper())
    NL = chr(10)
    rule = fix.value.split(NL)[0]
    e.clear_fields()
    e.add_field(name=fix.name, value=rule + NL + NL.join('• ' + x for x in fixes), inline=False)
    if updates:
        up = next(f for f in first.embeds[0].fields if 'UPDATES' in f.name.upper())
        e.add_field(name=up.name, value=up.value.split(NL)[0] + NL + NL.join('• ' + x for x in updates), inline=False)
    embeds = [e]
    await first.edit(embeds=embeds, allowed_mentions=discord.AllowedMentions.none())
    print('edited', first.id)
    for m in group[1:]:
        await m.delete()
        print('deleted', m.id)
    print(json.dumps({'message_id': str(first.id), 'channel_id': str(ch.id), 'bugfixes': fixes, 'updates': updates}))
    await finish(client)


asyncio.run(main())
