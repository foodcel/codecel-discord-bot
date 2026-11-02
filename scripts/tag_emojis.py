"""Gives the Deltarune and Jump King tags of the bugs forum their emoji, and puts the Fixed tag on fixed bugs that still have a post. Run on the VM."""
import asyncio

import discord

from _boot import boot, finish

from bot.db import all_
from bot.env import cfg
from bot.tags import _status_tag, set_tags

EMOJI = {'Deltarune': '♠️', 'Jump King': '👑'}


async def main():
    client = await boot(claims=False)
    forum = await client.fetch_channel(int(cfg.bugs_id))
    tags, changed = [], False
    for t in forum.available_tags:
        want = EMOJI.get(t.name)
        if want and not (t.emoji and t.emoji.name == want):
            new = discord.ForumTag(name=t.name, emoji=discord.PartialEmoji(name=want), moderated=t.moderated)
            new.id = t.id
            t, changed = new, True
        tags.append(t)
    if changed:
        await forum.edit(available_tags=tags, reason='Game emojis')
    print('emojis', 'set' if changed else 'already there')
    n = 0
    for b in all_("SELECT * FROM bugs WHERE status='fixed' AND deleted=0 AND kind='bug' AND thread_id IS NOT NULL AND thread_id != '0'"):
        try:
            thread = await client.fetch_channel(int(b['thread_id']))
        except Exception:
            continue
        if str(thread.parent_id) == str(cfg.bugs_id):
            await set_tags(thread, status='fixed')
            n += 1
    print('Fixed tag put on', n, 'posts')
    await finish(client)


asyncio.run(main())
