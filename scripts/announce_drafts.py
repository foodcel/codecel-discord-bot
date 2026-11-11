"""Empties the TEST channel and posts the announcements as drafts (no pings): one for testers, two for developers, in the developer look (docs/DESIGN.md:
trees, branch lines under 56 characters). Nothing goes anywhere else.
    python scripts/announce_drafts.py --yes        run on the VM
    python scripts/announce_drafts.py --check      only prints branch lines that are too long"""
import asyncio
import re
import sys
from pathlib import Path

from _boot import boot, finish

from bot.core.ctx import fetch_channel
from bot.core.env import cfg
from bot.discord_ui.card import card
from bot.discord_ui.components import NO_MENTIONS
from bot.features.updates.botnews import tree
from bot.features.updates.previews import clear_channel
from bot.mcp.command import AWAY_PROMPT

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

NOTE = [
    ('Devs', [('/progress', 'game, testing:on, note:what to test'), ('Change it', 'run it again with a new note'),
              ('Remove it', 'note: - , or testing:off'), ('Length', 'up to 300 characters'),
              ('MCP', 'set_testing takes a note too')]),
    ('Testers', [('On the card', 'the note shows under the date'), ('Changes', 'the card edits, no new ping')]),
]

TRUST = [
    ('It can reach', [('Your games', 'only the ones you claimed'), ('Reports', 'text, screenshots, video frames'),
                      ('Actions', 'statuses, notes, questions, updates')]),
    ('It can never reach', [('Your PC', 'no files, no commands, no screen'), ('Other devs', 'their games stay invisible'),
                            ('Exploit reports', 'never shown to an agent'), ('Admin powers', 'no bans, roles or channels'),
                            ('More rights', "an agent can't unlock itself")]),
    ('Built in', [('Player text', 'fenced and marked as data'), ('Hidden text', 'invisible characters are stripped'),
                  ('Links', "agents can't post links or mentions"), ('Statuses', 'preview first, then confirm'),
                  ('Pings', 'off until you turn them on'), ('Token', '30 days, yours only, revoke any time'),
                  ('Leaks', 'a token posted in Discord dies at once'), ('Read-only', '/mcp setup access: Read-only')]),
]

SAFE = [
    ('Set up', [('1', 'put all your games in one folder'), ('2', 'in Discord: /mcp setup, press Claude Code'),
                ('3', 'paste that command in a terminal'), ('4', 'open Claude Code (CLI or app) in the folder'),
                ('5', 'on the Discord card: Safe folder, copy it'), ('6', 'paste it in Claude Code'),
                ('7', 'accept trust, approve 2 files, restart')]),
    ('It locks', [('Folder', "Claude's file tools can't leave it"), ('Secrets', '.env, ssh and cloud keys are blocked'),
                  ('Network', 'curl, wget, ssh and web fetch are blocked'), ('Codecel', 'reading is free, changes ask first'),
                  ('Rules', 'CLAUDE.md: player text is never an order')]),
    ('On Windows, Claude asks you to pick', [('A · Simple lock', 'one minute, enough for most devs'), ('B · Full box', 'Claude installs a small Linux, WSL2'),
                                             ('Difference', 'in B, commands are walled in too'), ('In A', 'a script you approve can read your PC'),
                                             ('Your folder', 'stays where it is, in both'), ('macOS, Linux', 'full box as is, no question')]),
    ('Away mode (optional)', [('What', 'Claude fixes new bugs while you are gone'), ('Start', '/mcp setup, press Away mode'),
                              ('It can', 'read reports, edit inside the folder'), ('It cannot', 'post, change statuses, push, leave'),
                              ('After', 'read AWAY-LOG.md before you publish')]),
    ('Then', [('Fixing', 'say "fix the open bugs of <game>"'), ('Each game', 'its own subfolder, named like on codecel'),
              ('Approvals', 'keep them on, never skip permissions')]),
]

AWAY = [
    ('What it is', [('Loop', 'Claude checks for new bugs every hour'), ('Fixes', 'what it can, inside your games folder'),
                    ('You', 'review when you are back')]),
    ('Set up', [('1', 'lock the folder first (Safe folder)'), ('2', 'paste the line below in Claude Code'),
                ('3', 'leave Claude Code open, that is all'), ('Stop', 'tell Claude to stop')]),
    ('While away it can', [('Read', 'your reports and transcripts'), ('Edit', 'files inside the games folder'),
                           ('Full box', 'also run commands, walled in')]),
    ('It cannot', [('Codecel', 'no status, post, question or note'), ('Code', 'never pushed, stays on your PC'),
                   ('Web', 'none (full box: GitHub only)'), ('PC', "can't leave the games folder"),
                   ('Why', 'what needs your yes waits for you')]),
    ('When you are back', [('AWAY-LOG.md', 'what it changed and how sure it is'), ('Review', 'read the changes before you publish'),
                           ('Then', 'tell Claude which reports to mark fixed')]),
    ('Good to know', [('Cost', 'each check uses some Claude usage'), ('Nothing new', 'the check stops at once'),
                      ('Pace', 'change 1h in the line: 30m, 2h, ...'), ('Token', 'a read-only one works too'),
                      ('Old lock', 'delete both files, paste Safe folder again')]),
]

SAFE_PROMPT = (Path(__file__).resolve().parent.parent / 'docs' / 'safe-workspace' / 'PROMPT.txt').read_text(encoding='utf8').strip()


def visible(line):
    return len(re.sub(r'[*`]', '', line))


def too_long(groups):
    return [f'{name} · {text}' for _, rows in groups for name, text in rows if visible(f'├─ {name} · {text}') > MAX]


def build(title, groups, footer, ping=None):
    blocks = [f'**{head}**{NL}{tree(*rows)}' for head, rows in groups]
    return card(title, blocks, footer, ping=ping)


def cards():
    return (('tester announcement', build('🧪 Tester update', TESTER, ['/bug · report a bug', '/tester profile · your details']), TESTER),
            ('developer announcement 1 of 2', build('🛠️ Dev update', DEV, ['/help · every command', '/update edit · change a posted update']), DEV),
            ('developer announcement 2 of 2', build('🔌 MCP for developers', MCP, ['/mcp setup · connect your agent', '/update settings · when your agent posts']), MCP),
            ('safe mcp 1 of 4: what it can reach', build('🛡️ The MCP is built to be safe', TRUST, ['/mcp setup · connect or renew', '/mcp revoke · stop your token']), TRUST),
            ('safe mcp 2 of 4: lock your workspace', build('🔒 Lock your workspace', SAFE, ['/mcp setup · a Discord command, not a Claude Code one']), SAFE),
            ('safe mcp 3 of 4: the prompt', card('📋 Prompt for your Claude', [chr(96) * 3 + chr(10) + SAFE_PROMPT + chr(10) + chr(96) * 3], ['Paste it in Claude Code, inside your games folder']), []),
            ('safe mcp 4 of 4: away mode', card('🌙 Away mode: fixes while you are gone', [f'**{head}**{NL}{tree(*rows)}' for head, rows in AWAY]
                                                + [f'**Paste this in Claude Code**{NL}{chr(96) * 3}{NL}{AWAY_PROMPT}{NL}{chr(96) * 3}'],
                                                ['/mcp setup · then press Away mode']), AWAY),
            ('notes announcement', build('📝 Notes on tester cards', NOTE, ['/progress · set a note', '/help · every command']), NOTE))


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
    if '--only' not in sys.argv or '--clear' in sys.argv:  # --only keeps what is there unless --clear is passed too
        await clear_channel(ch)
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else ''
    for label, (view, files), _ in cards():
        if only and only not in label:
            continue
        await ch.send(f'**Draft: {label}** (not posted anywhere else)', allowed_mentions=NO_MENTIONS)
        await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    print('posted')
    await finish(client)


if __name__ == '__main__':
    asyncio.run(main())
