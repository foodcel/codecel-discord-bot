"""Empties the TEST channel and posts the two announcements as drafts (no pings): one for testers, one for developers. Nothing goes anywhere else.
    python scripts/announce_drafts.py --yes        run on the VM"""
import asyncio
import sys

from _boot import boot, finish

from bot.core.ctx import fetch_channel
from bot.core.env import cfg
from bot.discord_ui.card import card
from bot.discord_ui.components import NO_MENTIONS
from bot.features.updates.previews import clear_channel

NL = chr(10)
B = '•' + chr(0x2003)


def lines(*items):
    return NL.join(B + x for x in items)


def tester_card():
    blocks = [
        '**Reporting is easier**' + NL + lines(
            '`/bug` takes up to 10 files and a links box. After that, reply in your post with as many files and links as you like.',
            'Clip links from Streamable, Medal, X and Imgur are downloaded and attached as real videos, so the developer always has the file.',
            'YouTube and Vimeo links do **not** download (YouTube blocks the bot, Vimeo wants a login). Upload the video instead.',
            'A file too big for the server limit: post a link.'),
        '**When your bug is fixed**' + NL + lines(
            'You are told in your post the moment the developer marks it fixed. Tester reports never go into a public update.',
            'A report that is missing details is never closed for silence: the developer still gets it.'),
        '**What changed around you**' + NL + lines(
            'The tester board lists the games in testing. Pick the ones you test, and use the Play test button to join.',
            '`/tester profile` is where you fill in your devices and when you are free. The roster no longer pings anyone.',
            '`/tester find` is gone: the board replaces it.'),
    ]
    return card('🧪 Tester update', blocks, ['/bug · report a bug', '/tester profile · your details'])


def dev_card():
    blocks = [
        '**Simpler commands**' + NL + lines(
            '`/claim` has `new`, `edit` and `drop`. `/release` has `undo`. `/update` has `new`, `edit` and `policy`.',
            '`/suggest` replaces `/improvement`, and `!suggest` replaces `!improve`.',
            'Gone: `/config`, `/gamelink`, `/unrelease`, `/unclaim`, `/tester find`, and typing `12 fixed` in a board. Use the status buttons on the bug page.',
            '`/help` shows every command with its subcommands.'),
        '**Updates**' + NL + lines(
            'Updates within 12 hours of each other can fold into one card. The lines the latest addition brought get a 🆕.',
            '`/update edit` changes an update you already posted.',
            'Players hear about their fix when the update goes out. A tester\'s fix tells that tester at once and never reaches a public update.'),
        '**Reports**' + NL + lines(
            'Your own reports in your game skip the bot\'s questions.',
            'Reports are never closed for silence: they are logged for you.',
            'Players can attach files and links, and clip links are downloaded as videos (not YouTube or Vimeo).'),
        '**The MCP: your AI agent works your board**' + NL + lines(
            '`/mcp setup` gives you an address and a personal token (valid 30 days). It works for the games you claimed, and only with the Developers role.',
            'The agent reads the full transcript with screenshots and video frames, searches reports, asks a reporter a question, and sets statuses (preview first, then confirm).',
            'It posts and edits updates for you. `/update policy` sets when it may post: only when you say so (default), after every fix, only for high or critical fixes, or after N fixes.',
            'Pings are only allowed for a high or critical fix, and a new post needs 20 minutes since the last one.'),
        '**Stay safe with it**' + NL + lines(
            'Everything an agent reads was written by players. Agents are told to treat it all as untrusted, and we tested it against prompt injection, but keep your agent\'s approval prompts on.',
            'Do not run it fully unattended with shell access on a folder you care about.',
            'Admins can see who is connected (`/mcp status`), stop one dev or pause it for everyone.'),
    ]
    return card('🛠️ Dev update', blocks, ['/mcp setup · connect your agent', '/update policy · when your agent posts', '/help · every command'])


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await clear_channel(ch)
    for label, build in (('**Draft: tester announcement** (not posted anywhere else)', tester_card), ('**Draft: developer announcement** (not posted anywhere else)', dev_card)):
        await ch.send(label, allowed_mentions=NO_MENTIONS)
        view, files = build()
        await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    print('posted')
    await finish(client)


asyncio.run(main())
