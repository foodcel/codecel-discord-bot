"""Three looks for the dev announcement, all in the bot's usual embed look with the commands in the footer, shown in the test channel (no pings).
Clears the channel first.   python scripts/mockup_news.py --yes"""
import asyncio
import sys

import discord

from _boot import boot, finish

from bot.ctx import fetch_channel
from bot.env import cfg
from bot.ui import E, describe, flat, gap, head, section

DEV_ROLE = 1562719404473458778
NONE = discord.AllowedMentions.none()
NL = chr(10)
FOOTER = NL.join([
    '/progress testing:on · put your game in testing',
    '/progress testing:off · testing is over',
    '/release new · preview, then post',
    '/release edit description: · the line under your game',
    '/help · every command you can use',
])
FUTURE, FORUM, GAMES, DEVCHAT = cfg.future_games_id, cfg.tester_forum_id, 1562940878685872149, 1565918318664093766


def mock_a():
    """A · Sections: the look the announcements had, each feature one short line under its heading."""
    e = flat()
    e.title = head(E['update'], 'New · testing and previews')
    section(e, head('🧪', 'Testing'), f'**🧪 testing** on the board, and your game is listed in <#{FUTURE}>. Released games too.')
    section(e, head('🏷️', 'Testers forum'), f'Testers report in <#{FORUM}>. The tag is made when testing starts.')
    section(e, head('👀', 'Previews'), '`/release new`, `quiet` and `edit` show a preview first: post, edit or cancel.')
    section(e, head('💬', 'Description'), 'A line under your game, like "Multiplayer + VC".')
    section(e, head('📚', 'Library'), f'A new game is a card in <#{GAMES}> for 3 days, then joins the library.')
    section(e, head('🔴', 'Offline'), f'Taken-down games are marked offline for you, and you are pinged in <#{DEVCHAT}>.')
    gap(e)
    e.set_footer(text=FOOTER)
    return {'content': f'<@&{DEV_ROLE}>', 'embeds': [e]}


def mock_b():
    """B · Tree: the same layout as /help, three groups with branches."""
    e = flat()
    e.title = head(E['update'], 'New · testing and previews')
    section(e, head('🧪', 'Testing'), NL.join([
        f'├─ **Board** · 🧪 on the board, listed in <#{FUTURE}>',
        f'├─ **Forum** · testers report in <#{FORUM}>',
        '└─ **Released games** · can be in testing too']))
    section(e, head('🚀', 'Releasing'), NL.join([
        '├─ **Preview** · `/release new`, `quiet` and `edit` show it first',
        '├─ **Description** · a line under your game',
        f'└─ **Library** · a card in <#{GAMES}> for 3 days, then in the library']))
    section(e, head('🤖', 'Automatic'), NL.join([
        f'├─ **Offline** · taken-down games are marked, you are pinged in <#{DEVCHAT}>',
        '└─ **Updates** · `/update` drafts look like the posted card']))
    gap(e)
    e.set_footer(text=FOOTER)
    return {'content': f'<@&{DEV_ROLE}>', 'embeds': [e]}


def mock_c():
    """C · Short: no headings, one line per feature in one block."""
    e = flat()
    e.title = head(E['update'], 'New · testing and previews')
    describe(e, NL.join([
        f'🧪 **Testing** · 🧪 on the board, listed in <#{FUTURE}>, released games too',
        f'🏷️ **Testers forum** · testers report in <#{FORUM}>',
        '👀 **Previews** · `/release new`, `quiet` and `edit` show it first',
        '💬 **Description** · a line under your game',
        f'📚 **Library** · a card in <#{GAMES}> for 3 days, then the library',
        f'🔴 **Offline** · taken-down games are marked, you are pinged in <#{DEVCHAT}>',
        '🧾 **Updates** · `/update` drafts look like the posted card']))
    gap(e)
    e.set_footer(text=FOOTER)
    return {'content': f'<@&{DEV_ROLE}>', 'embeds': [e]}


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await ch.purge(limit=None, bulk=True, reason='Mockups')
    for label, make in (('**A · Sections**', mock_a), ('**B · Tree (like /help)**', mock_b), ('**C · Short list**', mock_c)):
        await ch.send(label, allowed_mentions=NONE)
        await ch.send(allowed_mentions=NONE, **make())
    print('done')
    await finish(client)


asyncio.run(main())
