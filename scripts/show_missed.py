"""Shows the posts that are still embeds in the new card look, in the test channel (nothing pings). Clears the channel first.   python scripts/show_missed.py --yes"""
import asyncio
import sys

import discord

from _boot import boot, finish

from bot import board, botnews, devboard, fixlog, guides, help as helpmod, strikes, testers
from bot.bugview import bug_embeds
from bot.ctx import ctx, fetch_channel
from bot.db import all_
from bot.env import cfg
from bot.look import card_from_embed

NONE = discord.AllowedMentions.none()
ASHER = '510246875870396438'


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await ch.purge(limit=None, bulk=True, reason='Showing the new looks')
    me = ctx.guild.me

    async def show(label, embed):
        view, files = card_from_embed(embed)
        await ch.send(f'**{label}**', allowed_mentions=NONE)
        await ch.send(view=view, files=files, allowed_mentions=NONE)

    top, unreleased, released = await board.build_embeds()
    await show('Bounty board · top suggestions', top)
    await show('Bounty board · unreleased games', unreleased)
    await show('Bounty board · released games', released)
    await show('/help · admin page', helpmod.page_embed('admin', 0, 4, me))
    await show('/help · dev page', helpmod.page_embed('dev', 1, 4, me))
    await show('Dev board · your bug board', devboard.board_embed(ASHER))
    bug = all_("SELECT * FROM bugs WHERE kind='bug' AND deleted=0 AND thread_id IS NOT NULL ORDER BY id DESC LIMIT 1")
    if bug:
        for e in (await bug_embeds(bug[0]))[:1]:
            await show('Dev board · one bug page', e)
    await show('Fix log', fixlog.log_embed())
    await show('Strike card (mod log)', strikes.strike_embed(int(ASHER), 2, '1-day mute', 'Spam in the bugs forum'))
    await show('Bot rules', strikes.rules_embed())
    await show('Tester roster', testers.roster_embed())
    await show('Tester roster guide', testers.guide_embed())
    await show('Bugs channel guide', guides.bugs_guide_embed())
    await show('Suggestions channel guide', guides.suggestions_guide_embed())
    await show('Games channel guide', guides.games_guide_embed())
    await show('Testers forum · get started', botnews.tester_guide_embeds()[0])
    print('done')
    await finish(client)


asyncio.run(main())
