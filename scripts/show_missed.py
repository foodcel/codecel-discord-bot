"""Shows the posts that are still embeds in the new card look, in the test channel (nothing pings), and three looks for the dev bug board.
Clears the channel first.   python scripts/show_missed.py --yes"""
import asyncio
import re
import sys

import discord
from discord import ui

from _boot import boot, finish

from bot import board, botnews, devboard, fixlog, guides, help as helpmod, strikes, testers
from bot.bugview import bug_embeds
from bot.ctx import ctx, fetch_channel
from bot.db import all_
from bot.env import cfg
from bot.look import card_from_embed
from bot.nums import label
from bot.pngs import width_strip
from bot.ui import STATUS

NONE = discord.AllowedMentions.none()
NL = chr(10)
ASHER = '510246875870396438'
SMALL = discord.SeparatorSpacing.small


def dev_board():
    """Your bug board, grouped by game: a tree under each game, the counts in the header."""
    bugs = devboard.open_bugs_for(ASHER)
    n = lambda s: len([b for b in bugs if b['status'] == s])
    title = f"### 😊 Your bug board · 🐛 {n('new')} open · 🔎 {n('investigating')} investigating · 🛠️ {n('fixing')} fixing"
    foot = '-# Pick a game below to browse its bugs. Type `sonic 3 fixed` or `sonic 1-5 fixed` here.'
    cut = lambda s, k: s if len(s) <= k else s[:k - 1] + '…'
    by = {}
    for b in bugs:
        by.setdefault(b['game_name'] or 'Unknown game', []).append(b)
    blocks = []
    for game, lst in by.items():
        lines = [f"{'└─' if k == len(lst) - 1 else '├─'} **{label(b)}** · {cut(b['title'], 30)} · {STATUS.get(b['status'], b['status'])}" for k, b in enumerate(lst)]
        blocks.append(f'**🎮 {game}** · {len(lst)}{NL}' + NL.join(lines))
    return title, (NL + NL).join(blocks), foot


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await ch.purge(limit=None, bulk=True, reason='Showing the new looks')
    me = ctx.guild.me

    async def show(label_, embed, **kw):
        view, files = card_from_embed(embed, **kw)
        await ch.send(f'**{label_}**', allowed_mentions=NONE)
        await ch.send(view=view, files=files, allowed_mentions=NONE)

    top, unreleased, released = await board.build_embeds()
    top.description = (top.description or '').replace(' open suggestions', ' open', 1)
    await show('Bounty board · top suggestions', top, inline_desc=True)
    await show('Bounty board · unreleased games', unreleased, inline_desc=True, plain_count=True)
    await show('Bounty board · released games', released, inline_desc=True, plain_count=True)
    await show('/help · admin page', helpmod.page_embed('admin', 0, 4, me))
    await show('/help · dev page', helpmod.page_embed('dev', 1, 4, me))
    title, body, foot = dev_board()
    strip_ = width_strip()
    view = ui.LayoutView()
    view.add_item(ui.MediaGallery(discord.MediaGalleryItem(strip_)))
    view.add_item(ui.Container(ui.TextDisplay(title), ui.Separator(visible=True, spacing=SMALL), ui.TextDisplay(body), ui.Separator(visible=True, spacing=SMALL), ui.TextDisplay(foot)))
    await ch.send('**Dev board · your bug board**', allowed_mentions=NONE)
    await ch.send(view=view, files=[strip_], allowed_mentions=NONE)
    bug = all_("SELECT * FROM bugs WHERE kind='bug' AND deleted=0 AND thread_id IS NOT NULL ORDER BY id DESC LIMIT 1")
    if bug:
        e = (await bug_embeds(bug[0]))[0]
        await ch.send('**Dev board · one bug page** (stays an embed: it has side-by-side columns)', embeds=[e], allowed_mentions=NONE)
    await ch.send('**Fix log** (stays an embed: it has side-by-side columns)', embeds=[fixlog.log_embed()], allowed_mentions=NONE)
    await show('Strike card (mod log)', strikes.strike_embed(int(ASHER), 2, 'timeout', 'Spam in the bugs forum'))
    await show('Bot rules', strikes.rules_embed())
    await show('Tester roster', testers.roster_embed(), inline_desc=True)
    await show('Tester roster guide', testers.guide_embed())
    await show('Bugs channel guide', guides.bugs_guide_embed())
    await show('Suggestions channel guide', guides.suggestions_guide_embed())
    await show('Games channel guide', guides.games_guide_embed())
    await show('Testers forum · get started', botnews.tester_guide_embeds()[0])
    print('done')
    await finish(client)


asyncio.run(main())
