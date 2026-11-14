"""The pinned "Get started" post of the testers' bug forum, in the same look as the public bugs forum's "Report a bug" card.
    python scripts/tester_guide.py --test     a draft in the test channel (no pings)
    python scripts/tester_guide.py --yes      edits the pinned post in place, silently"""
import asyncio
import sys

from _boot import boot, finish

from bot.core.ctx import fetch_channel
from bot.core.env import cfg
from bot.discord_ui.card import card
from bot.discord_ui.components import NO_MENTIONS

NL = chr(10)
RULE = '─' * 34
PINNED = 1566680524733288490  # the "Get started" post in the testers' forum


def section(title, lines):
    return f'**{title}**{NL}{RULE}{NL}' + NL.join(lines)


def guide():
    testing, board = f'<#{cfg.testing_id}>', f'<#{cfg.future_games_id}>'
    return card('🧪 REPORT A BUG · TESTING', [
        f'The easiest way: type **`/bug`** in {testing}.{NL}The bot makes the post here for you and sends it to the right developer.',
        section('⌨️ HOW IT WORKS', [
            f'1. Type `/bug` in {testing}',
            '2. Pick the game, and add screenshots or videos if you have them',
            '3. Fill in the short form and send it',
            'Your post appears here, with the game in its title.']),
        section('🔍 REPORTING A MESSAGE?', [
            '• Reply to the message with **`!bug <game>`**',
            '• In the testing channel it becomes a post here',
            '• Anywhere else it becomes a post in the public bugs forum',
            '• 5 false reports and you lose it']),
        section('🤖 AFTER YOU SEND IT', [
            '• Your post gets a number, like **#12**',
            '• The developer replies in your post. **Reply there too.**',
            '• Fixed? You get a ping and the post is deleted after 24 hours. **Still broken?** Reply before then and it reopens.',
            f'• The fix is listed in the next tester update in {board}']),
        section('💡 GOOD TO KNOW', [
            f'• Only games in testing and released games. See {board}',
            '• One bug per report, and please do not ping developers',
            '• Clear steps and a screenshot or video get fixed faster',
            '• Hide personal information in screenshots']),
    ], ['Thank you for testing and helping improve every game.'])


async def main():
    client = await boot(claims=False)
    view, files = guide()
    if '--test' in sys.argv:
        ch = await fetch_channel(cfg.test_id)
        await ch.send('**Draft: testers forum, Get started** (not posted anywhere else)', allowed_mentions=NO_MENTIONS)
        m = await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
        print('draft', m.jump_url)
    elif '--yes' in sys.argv:
        t = await fetch_channel(PINNED)
        await t.get_partial_message(PINNED).edit(view=view, attachments=files, allowed_mentions=NO_MENTIONS)
        print('edited', t.jump_url)
    else:
        print('Pass --test or --yes.')
    await finish(client)


if __name__ == '__main__':
    asyncio.run(main())
