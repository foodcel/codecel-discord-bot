"""The slash command definitions, in the raw form Discord expects."""
from .tester import ATTACH

SUB, STRING, INTEGER, BOOLEAN, USER, CHANNEL, ROLE, ATTACHMENT = 1, 3, 4, 5, 6, 7, 8, 11
GUILD_TEXT, GUILD_ANNOUNCEMENT = 0, 5


def option(type_, name, description, required=False, autocomplete=False, choices=None, **extra):
    o = {'type': type_, 'name': name, 'description': description}
    if type_ != SUB:
        o['required'] = bool(required)
    if autocomplete:
        o['autocomplete'] = True
    if choices:
        o['choices'] = [{'name': n, 'value': v} for n, v in choices]
    o.update(extra)
    return o


def command(name, description, options=None):
    return {'type': 1, 'name': name, 'description': description, 'options': options or []}


def sub(name, description, options=None):
    return option(SUB, name, description, options=options or [])


def _bug_command():
    opts = [option(STRING, 'game', 'Which game', required=True, autocomplete=True)]
    for k, name in enumerate(ATTACH['screenshots']):
        opts.append(option(ATTACHMENT, name, f'Screenshot {k + 1} (optional)'))
    for k, name in enumerate(ATTACH['videos']):
        opts.append(option(ATTACHMENT, name, f'Video {k + 1} (optional)'))
    return command('bug', 'Testers: report a bug straight to the developers', opts)


FORUM, TEXT = 15, 0

SETUP_COMMAND = command('bounty-board', 'Rank a suggestions forum by votes in a dev channel, with claims (admins only)', [
    option(CHANNEL, 'channel', 'Dev channel for the three pinned messages. Running this again moves them.', required=True,
           channel_types=[TEXT]),
    option(CHANNEL, 'forum', 'The game suggestions forum', required=True, channel_types=[FORUM]),
    option(ROLE, 'role', 'Who can /claim games', required=True),
])

# Registered only once the board is set up with /bounty-board, so they never sit next to another bot's /claim before that.
BOARD_COMMANDS = [
    command('claim', "Claim a game you're working on: a suggestion, or a custom game", [
        option(STRING, 'post', "Type to search the forum's posts, or pick \"Custom game\" for one that has no post", required=True,
               autocomplete=True),
        option(STRING, 'link', 'Link to the original game (Steam page etc.), shown on the games board'),
    ]),
    command('unclaim', 'Drop a game you claimed: it goes back to Top suggestions', [option(STRING, 'post', 'The game', required=True, autocomplete=True)]),
    command('assign', 'Give a game to a dev, taking it from whoever holds it (admins only)', [
        option(STRING, 'post', "Type to search the forum's posts, or pick \"Custom game\" for one that has no post", required=True,
               autocomplete=True),
        option(USER, 'dev', 'Who gets the game', required=True),
    ]),
    command('exclude', 'Remove a forum post from the bounty board and /claim (admins only)',
            [option(STRING, 'post', "The game's forum post", required=True, autocomplete=True)]),
    command('include', 'Put an excluded forum post back on the bounty board (admins only)',
            [option(STRING, 'post', "The game's forum post", required=True, autocomplete=True)]),
]
BOARD_NAMES = {c['name'] for c in BOARD_COMMANDS}

ON_OFF = [('On', 'on'), ('Off', 'off')]

PREVIEW_CHOICES = [
    ('everything (clears the test channel)', 'all'), ('dev board', 'board'), ('bug page', 'bug'),
    ('announcements', 'announcement'), ('fix log', 'fixlog'), ('rules', 'rules'),
    ('mod cards', 'mod'), ('bot messages', 'messages'), ('transcript', 'transcript'),
    ('launch announcement draft', 'botnews'), ('tester report', 'tester'), ('tester announcement draft', 'testernews'),
    ('games board', 'games'),
]

COMMANDS = [
    command('config', 'Set up a game for update announcements', [
        sub('set', 'Change announcement settings for a game', [
            option(STRING, 'game', 'Game', required=True, autocomplete=True),
            option(STRING, 'link', 'Link to the game'),
            option(STRING, 'icon', 'Icon image URL (auto-pulled from a Roblox link if empty)'),
            option(CHANNEL, 'channel', 'Announcement channel', channel_types=[GUILD_TEXT, GUILD_ANNOUNCEMENT]),
            option(ROLE, 'role', 'Role to ping on announcements'),
            option(INTEGER, 'threshold', 'Fixes before an announcement is offered', min_value=1, max_value=50),
            option(USER, 'owner', 'Admin only: force the owner of this game'),
            option(STRING, 'board', 'Admin only: the bounty-board name of this game', autocomplete=True),
        ]),
        sub('show', 'Show game settings', [option(STRING, 'game', 'Game', autocomplete=True)]),
    ]),
    command('update', 'Post a game update with its bug fixes', [option(STRING, 'game', 'Game', required=True, autocomplete=True)]),
    _bug_command(),
    command('pings', 'Choose when the bot pings you', [
        option(STRING, 'bugs', 'Ping me when a new bug arrives on my games', choices=ON_OFF),
        option(STRING, 'exploits', 'Ping me for high-priority exploit reports', choices=ON_OFF),
    ]),
    command('strikes', "Show a user's troll strikes", [option(USER, 'user', 'User', required=True)]),
    command('pardon', 'Remove one strike from a user', [option(USER, 'user', 'User', required=True)]),
    command('preview', 'Admin: post the finished embeds in the test channel (everything wipes it first)',
            [option(STRING, 'what', 'Which preview', choices=PREVIEW_CHOICES)]),
    command('botrules', 'Post the bug report rules and strike ladder here'),
    command('release', 'Mark one of your games as released', [
        option(STRING, 'game', 'Game', required=True, autocomplete=True),
        option(STRING, 'link', 'Link players use to play it (optional)'),
    ]),
    command('unrelease', 'Move a released game back to unreleased', [option(STRING, 'game', 'Game', required=True, autocomplete=True)]),
    command('gamelink', 'Set the link of an unreleased game (the site it is ported from, e.g. Steam)', [
        option(STRING, 'game', 'Game', required=True, autocomplete=True),
        option(STRING, 'link', 'Link to the original game', required=True),
    ]),
    command('progress', 'Say how far an unreleased game is, and whether you are working on it right now', [
        option(STRING, 'game', 'Game', required=True, autocomplete=True),
        option(INTEGER, 'percent', 'How much of the game is done', min_value=0, max_value=100),
        option(BOOLEAN, 'working', 'Are you working on it right now? (yes / no)'),
    ]),
    SETUP_COMMAND,
    command('games', 'Admin: the released / unreleased games board', [
        sub('post', 'Post the board in this channel (it updates by itself)'),
        sub('rename', 'Fix the name shown for a game', [
            option(STRING, 'game', 'Game', required=True, autocomplete=True),
            option(STRING, 'name', 'The correct name', required=True, max_length=40),
        ]),
    ]),
]
