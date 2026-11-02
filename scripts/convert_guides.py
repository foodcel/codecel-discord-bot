"""Turns the pinned guide posts the bot made in the forums (and the testers' Get started post) into cards, in place. A post Discord will not convert stays as it is.
Run on the VM:  python scripts/convert_guides.py --yes"""
import sys

import discord

from _boot import boot, finish

from bot.botnews import tester_guide_embeds
from bot.env import cfg
from bot.guides import bugs_guide_embed, games_guide_embed, suggestions_guide_embed
from bot.look import edit_card

GAMES_FORUM = '1562961976387174452'
BUILDERS = {'bugs': bugs_guide_embed, 'suggestions': suggestions_guide_embed, 'games': games_guide_embed, 'testers': lambda: tester_guide_embeds()[0]}


FORUM_GUIDE = {str(cfg.bugs_id): bugs_guide_embed, str(cfg.suggestions_id): suggestions_guide_embed, GAMES_FORUM: games_guide_embed,
               str(cfg.tester_forum_id): lambda: tester_guide_embeds()[0]}


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not editing. Pass --yes.')
        return await finish(client)
    titles = {}
    for k, b in BUILDERS.items():
        titles[b().title] = b
    for fid in (cfg.bugs_id, cfg.suggestions_id, GAMES_FORUM, cfg.tester_forum_id):
        forum = await client.fetch_channel(int(fid))
        threads = list(forum.threads)
        async for t in forum.archived_threads(limit=50):
            threads.append(t)
        for t in threads:
            if not t.flags.pinned:
                continue
            try:
                msg = await t.fetch_message(t.id)
            except Exception:
                continue
            if msg.author.id != client.user.id:
                continue
            # an embed is known by its title; a post that is a card already is known by its forum (one guide per forum)
            build = titles.get(msg.embeds[0].title) if msg.embeds else FORUM_GUIDE.get(str(fid))
            if not build:
                print('skipped (not one of the guides):', t.name)
                continue
            await edit_card(msg, build())
            print('converted', forum.name, '·', t.name)
    await finish(client)


import asyncio  # noqa: E402

asyncio.run(main())
