"""Empties the test channel and shows every card the bot can send, built by the code as it is now (also before the bot is restarted):
the player replies, the report posts, the dev cards (/preview), /help, the tester roster and guide. Pings nobody.
    python scripts/show_all_cards.py --yes"""
import asyncio
import sys
import time

from _boot import boot, finish

from bot.core.ctx import ctx, fetch_channel
from bot.core.db import all_
from bot.core.env import cfg
from bot.discord_ui.components import NO_MENTIONS
from bot.features.bugs import replies
from bot.features.bugs.forms import _card as report_card
from bot.features.testers.testers import guide_embed, roster_embed
from bot.features.updates.previews import clear_channel, post_previews


async def main():
    client = await boot(members=True)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await clear_channel(ch)
    me = str(ctx.guild.owner_id)

    async def show(label, built):
        view, files = built
        await ch.send(label, allowed_mentions=NO_MENTIONS)
        await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)

    bug = dict(all_("SELECT * FROM bugs WHERE kind='bug' AND game_name IS NOT NULL ORDER BY id DESC LIMIT 1")[0])
    sug = dict(all_("SELECT * FROM bugs WHERE kind='suggestion' ORDER BY id DESC LIMIT 1")[0])
    dup = dict(bug, status='new', deleted=0)
    await ch.send('# 1 · What players read in their report', allowed_mentions=NO_MENTIONS)
    await show('**Missing details** (the bot asks)', replies.needs_info(me, ['Which device you play on', 'The steps to make it happen', 'A screenshot or video']))
    await show('**Logged** (the report is with the developer)', replies.logged(bug))
    await show('**Logged** · a suggestion', replies.logged(sug))
    await show('**Already reported**', replies.duplicate(me, dup))
    await show('**Moved to bug reports** (a suggestion that is a bug)', replies.now_a_bug(me, bug, cfg.bugs_id))
    for status in ('investigating', 'fixing', 'not_a_bug', 'declined'):
        await show(f'**Status · {status}** (a developer pressed it)', replies.status_note(status, 'suggestion' if status == 'declined' else 'bug'))
    await show('**Fixed** (when the update with the fix is posted)', replies.fixed([me], bug, 'https://discord.com/channels/1/2/3'))
    await show('**Reopened** (the player said it is still broken)', replies.reopened(bug))
    await show('**Closed · no reply** (after 3 days)', replies.stale_closed(me))
    await show('**Closed** (fake or abusive)', replies.troll_closed())

    await ch.send('# 2 · Posts made by /bug, /improvement and !bug', allowed_mentions=NO_MENTIONS)
    form = {'title': 'Car falls through the map', 'what': 'After the second checkpoint my car drops through the road', 'steps': '1. Start a race on Harbor\n2. Drive past checkpoint 2',
            'expected': 'The car stays on the road', 'device': 'PS5', 'why': ''}
    await show('**/bug post**', report_card('bug', me, bug['game_name'], form))
    await show('**/improvement post**', report_card('suggestion', me, bug['game_name'], {**form, 'title': 'Add a night mode', 'what': 'A darker map for night races', 'why': 'Easier on the eyes'}))
    await show('**!bug saved from a message**', report_card('bug', me, bug['game_name'], form, origin='https://discord.com/channels/1/2/3',
                                                          footer='Saved from a message by a tester · replies go in this post'))

    await ch.send('# 3 · Developer and admin cards', allowed_mentions=NO_MENTIONS)
    await post_previews('board')
    for k in ('bug', 'announcement', 'fixlog', 'rules', 'mod', 'tester', 'games'):
        await post_previews(k)
    from bot.discord_ui.help import page_card
    await show('**/help** · the admin page', page_card('admin', 0, 4, ctx.guild.get_member(int(me))))
    await show('**Tester responsibilities**', guide_embed())
    await show('**Tester roster**', roster_embed())
    print('done in', round(time.time()), 'posted')
    await finish(client)


asyncio.run(main())
