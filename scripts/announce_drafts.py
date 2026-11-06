"""Empties the TEST channel and posts the announcements as drafts (no pings): one for testers, two for developers. Nothing goes anywhere else.
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
            "Players hear about their fix when the update goes out. A tester's fix tells that tester at once and never reaches a public update."),
        '**Reports**' + NL + lines(
            "Your own reports in your game skip the bot's questions.",
            'Reports are never closed for silence: they are logged for you.',
            'Players can attach files and links, and clip links are downloaded as videos (not YouTube or Vimeo).'),
    ]
    return card('🛠️ Dev update', blocks, ['/help · every command', '/update edit · change a posted update'])


def mcp_card():
    blocks = [
        '**What it is**' + NL + lines(
            'The MCP lets your AI agent (Claude Code, Codex, Pi...) work your bug board. Run `/mcp setup` for an address and a personal token (valid 30 days).',
            'It works for the games you claimed and needs the Developers role. A new `/mcp setup` replaces your old token, so set it up once per machine.',
            'It reads the full transcript with screenshots and video frames, searches reports, asks a reporter a question, and sets statuses (preview first, then confirm).',
            'It posts and edits updates. Pings only for a high or critical fix, and a new post needs 20 minutes since the last one.'),
        '**Several games**' + NL + lines(
            'One token covers every game you claimed. Every call names the game, so the server only needs to know who you are.',
            'Open your agent in the game\'s repo and add a line to its `CLAUDE.md`: "This repo is the game X on codecel, use game X".',
            'Add the MCP with `--scope user` (the setup card does) so every repo has it.'),
        '**Loops**' + NL + lines(
            'The MCP cannot wake an agent, the agent has to check. Use Claude Code `/loop` every 30 to 60 minutes in the repo, or a scheduled `claude -p` run.',
            '`list_bugs` takes `since_id`, so a check only sees reports newer than the last one.',
            'It will not post updates until you set `/update policy` (manual by default): after every fix, only for high or critical fixes, or after N fixes.',
            'Every check costs usage, and an unattended agent has real access to your files. Keep its permissions narrow.'),
        '**Stay safe**' + NL + lines(
            'Everything an agent reads was written by players. Agents are told to treat it all as untrusted, and we tested real agents against prompt injection, but keep approval prompts on.',
            'Admins can see who is connected (`/mcp status`), stop one dev, or pause the MCP for everyone.'),
    ]
    return card('🔌 MCP for developers', blocks, ['/mcp setup · connect your agent', '/update policy · when your agent posts'])


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await clear_channel(ch)
    for label, build in (('**Draft: tester announcement** (not posted anywhere else)', tester_card), ('**Draft: developer announcement 1 of 2**', dev_card),
                         ('**Draft: developer announcement 2 of 2**', mcp_card)):
        await ch.send(label, allowed_mentions=NO_MENTIONS)
        view, files = build()
        await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    print('posted')
    await finish(client)


asyncio.run(main())
