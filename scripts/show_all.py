"""Shows every announcement and card in its current look in the test channel (nothing pings). Clears the channel first.   python scripts/show_all.py --yes"""
import asyncio
import sys

import discord

from _boot import boot, finish

from bot import botnews as n
from bot.cards import new_game_card, released_row_for, update_card
from bot.ctx import fetch_channel
from bot.db import bug_by_id, one
from bot.env import cfg
from bot.testerboard import board_view, card_view
from bot.tester import tester_report_embed

NONE = discord.AllowedMentions.none()
DEV, TESTER = '<@&1562719404473458778>', '<@&1562726451797565521>'
ANNOUNCEMENTS = [
    ('The bug bot (devs)', n.bot_news_embeds, DEV), ('The bounty board (devs)', n.board_news_embeds, DEV),
    ('Suggestion boards (devs)', n.suggestion_news_embeds, DEV), ('The tester roster (devs)', n.roster_news_devs_embeds, DEV),
    ('Game library and releases (devs)', n.release_news_devs_embeds, DEV), ('Testing and previews (devs)', n.testing_news_devs_embeds, DEV),
    ('Report bugs with /bug (testers)', n.tester_news_embeds, TESTER), ('The tester roster (testers)', n.roster_news_testers_embeds, TESTER),
    ('For testers', n.release_news_testers_embeds, TESTER), ('Testers forum (testers)', n.testing_news_testers_embeds, TESTER),
]


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await ch.purge(limit=None, bulk=True, reason='Showing the new looks')

    async def show(label, **kw):
        await ch.send(f'**{label}**', allowed_mentions=NONE)
        await ch.send(allowed_mentions=NONE, **kw)

    for label, build, role in ANNOUNCEMENTS:
        view, files = n.as_card(build()[0], ping=role)
        await show(f'Announcement · {label}', view=view, files=files)
    view, files = board_view()
    await show('Tester board', view=view, files=files)
    view, files, _ = card_view({'key': 'peggle', 'name': 'Peggle', 'owners': ['941724517481463888']})
    await show('Needs-testers card (lives a day)', view=view, files=files)
    game = {'name': 'Peggle', 'link': 'https://www.roblox.com'}
    view, files = update_card(game, released_row_for('Peggle'), ['The ball no longer sticks to the left peg', 'The score saves after every level'],
                              ['Fever buckets are a little wider'], ['A second map: Harbor'], 'v17', '<@&1564115717542903828>', poster='941724517481463888')
    await show('Update card', view=view, files=files)
    row = released_row_for('Peggle')
    view, files = new_game_card(row, '@everyone')
    await show('New-game card', view=view, files=files)
    bug = bug_by_id(124) or {'id': 124, 'game_name': 'Sonic Dimensions', 'title': 'Homing Dash appears blacked out', 'summary': '', 'severity': 'medium', 'created_at': 0}
    form = {'device': 'iPhone 17 Pro', 'what': "When first opening Tails' shop, Homing Dash is not seen and usually blacked out.", 'steps': '1. Find Tails\n2. Open his menu',
            'expected': 'Homing Dash is visible in the shop.'}
    await show('Bug report card (quote bar, device chip)', embeds=[tester_report_embed(bug, form, 941724517481463888)])
    print('done')
    await finish(client)


asyncio.run(main())
