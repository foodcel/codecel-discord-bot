"""Edits announcements this bot posted earlier that show an Updates column repeating the Bug fixes: they keep only the Bug fixes, laid out
like a fresh announcement of only bug fixes. Reactions and the date stay. Prints what it would do without --yes.
    python scripts/trim_updates.py --channel=<id> --title=<GAME NAME> [--yes]"""
import asyncio
import sys

import discord

from _boot import boot, finish

from bot.ui import WIDE_RULE


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


async def main():
    client = await boot(claims=False)
    ch = await client.fetch_channel(int(arg('channel')))
    async for m in ch.history(limit=100, oldest_first=True):
        if m.author.id != client.user.id or not m.embeds or (m.embeds[0].title or '').upper() != arg('title').upper():
            continue
        e = discord.Embed.from_dict(m.embeds[0].to_dict())
        names = [f.name for f in e.fields]
        has_updates = any('UPDATES' in n.upper() for n in names)
        print(m.id, m.created_at.strftime('%Y-%m-%d %H:%M'), '| fields:', [n.strip() for n in names], '| will trim' if has_updates else '| left alone')
        if not has_updates or '--yes' not in sys.argv:
            continue
        fix = next(f for f in e.fields if 'BUG FIXES' in f.name.upper())
        lines = [ln for ln in fix.value.split('\n') if ln.strip().startswith('•')]
        e.clear_fields()
        e.add_field(name=fix.name, value=f"{WIDE_RULE}\n" + '\n'.join(lines), inline=False)
        await m.edit(embeds=[e])
        print('  edited')
    await finish(client)


asyncio.run(main())
