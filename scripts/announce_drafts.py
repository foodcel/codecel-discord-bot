"""Empties the TEST channel and posts the announcements as drafts (no pings): one for testers, two for developers, in the developer look (docs/DESIGN.md:
trees, branch lines under 56 characters). Nothing goes anywhere else.
    python scripts/announce_drafts.py --yes        run on the VM
    python scripts/announce_drafts.py --check      only prints branch lines that are too long"""
import asyncio
import re
import sys

from _boot import boot, finish

from bot.core.ctx import fetch_channel
from bot.core.env import cfg
from bot.discord_ui.card import card
from bot.discord_ui.components import NO_MENTIONS
from bot.features.updates.botnews import tree
from bot.features.updates.previews import clear_channel

NL = chr(10)
MAX = 56

TESTER = [
    ('Reporting', [('/bug', 'up to 10 files and a links box'), ('Replies', 'add as many files and links as you like'),
                   ('Clips', 'Streamable, Medal, X, Imgur become videos'), ('YouTube, Vimeo', 'do not download: upload the file'),
                   ('Too big?', 'post a link')]),
    ('Fixes', [('Fixed', 'you are told in your post at once'), ('Silence', 'a report is never closed for it'),
               ('Updates', 'tester reports stay out of public ones')]),
    ('Around you', [('Board', 'pick games to test, Play test button'), ('/tester profile', 'your devices and free times'),
                    ('Roster', 'no longer pings anyone'), ('/tester find', 'gone, the board replaces it')]),
]

DEV = [
    ('Commands', [('/claim', 'new, edit, drop'), ('/release', 'new, quiet, edit, undo'), ('/update', 'new, edit, settings'),
                  ('/suggest', 'replaces /improvement and !improve'), ('Removed', '/config, /gamelink, /unrelease, /unclaim'),
                  ('Removed', '/tester find, typing 12 fixed in a board'), ('Status', 'use the buttons on the bug page')]),
    ('Updates', [('Merging', 'off by default, set the hours in settings'), ('🆕', 'marks what a merge added'),
                 ('/update edit', 'change a posted update'), ('/update settings', 'agent posting, merging, pings'), ('Players', 'hear of their fix when it posts'),
                 ('Testers', 'told at once, never in public updates')]),
    ('Reports', [('Your own', "skip the bot's questions"), ('Silence', 'logged for you, never closed'),
                 ('Clips', 'links become videos, not YouTube/Vimeo')]),
]

MCP = [
    ('Connect', [('/mcp setup', 'address and token, valid 30 days'), ('Who', 'devs, for the games they claimed'),
                 ('New setup', 'replaces your old token'), ('Repos', 'one setup works in all your game repos')]),
    ('It can', [('Read', 'transcript, screenshots, video frames'), ('Search', 'related and duplicate reports'),
                ('Ask', 'a question to the reporter'), ('Mark reports', 'fixed, duplicate, not a bug'),
                ('Updates', 'post and edit, per /update settings')]),
    ('Several games', [('Token', 'one covers every game you claimed'), ('Repo', "open the agent in the game's repo"),
                       ('CLAUDE.md', '"This repo is game X on codecel"')]),
    ('Loops', [('Wake-up', "the MCP can't, the agent must check"), ('How', 'Claude Code /loop, or a scheduled claude -p'),
               ('since_id', 'a check sees only newer reports'), ('Updates', 'none until /update settings allows it'),
               ('Cost', 'every check uses usage: narrow access')]),
    ('Safety', [('Untrusted', 'player text is data, agents know it'), ('Approvals', 'keep them on, no unattended shell'),
                ('Pings', 'off unless you turn them on'), ('Admins', '/mcp status, kick, pause')]),
]


def visible(line):
    return len(re.sub(r'[*`]', '', line))


def too_long(groups):
    return [f'{name} · {text}' for _, rows in groups for name, text in rows if visible(f'├─ {name} · {text}') > MAX]


def build(title, groups, footer):
    blocks = [f'**{head}**{NL}{tree(*rows)}' for head, rows in groups]
    return card(title, [NL.join(blocks[:1])] + blocks[1:], footer)


def cards():
    return (('tester announcement', build('🧪 Tester update', TESTER, ['/bug · report a bug', '/tester profile · your details']), TESTER),
            ('developer announcement 1 of 2', build('🛠️ Dev update', DEV, ['/help · every command', '/update edit · change a posted update']), DEV),
            ('developer announcement 2 of 2', build('🔌 MCP for developers', MCP, ['/mcp setup · connect your agent', '/update settings · when your agent posts']), MCP))


async def main():
    if '--check' in sys.argv:
        for label, _, groups in cards():
            print(label, too_long(groups) or 'ok')
        return
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await clear_channel(ch)
    for label, (view, files), _ in cards():
        await ch.send(f'**Draft: {label}** (not posted anywhere else)', allowed_mentions=NO_MENTIONS)
        await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    print('posted')
    await finish(client)


asyncio.run(main())
