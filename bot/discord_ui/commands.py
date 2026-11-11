"""The slash command definitions, in the raw form Discord expects."""

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


def _evidence_options():
    """Up to 10 files and a links box on /bug and /suggest. Anything more goes in as replies in the post, which have no limit."""
    files = [option(ATTACHMENT, 'file' if n == 1 else f'file_{n}', 'A screenshot or video (optional)' if n == 1 else 'Another file (optional)') for n in range(1, 11)]
    return files + [option(STRING, 'links', 'Clip or video links, separated by spaces (optional)', max_length=400)]


def _bug_command():
    opts = [option(STRING, 'game', 'Which game', required=True, autocomplete=True), *_evidence_options()]
    return command('bug', 'Report a bug: pick the game, add files or links if you have them, and fill in a short form', opts)


def _improvement_command():
    opts = [option(STRING, 'game', 'Which game', required=True, autocomplete=True), *_evidence_options()]
    return command('suggest', 'Suggest an improvement: pick the game, add files or links if you have them, and fill in a short form', opts)


FORUM, TEXT = 15, 0

SETUP_COMMAND = command('bounty-board', 'Rank a suggestions forum by votes in a dev channel, with claims (admins only)', [
    option(CHANNEL, 'channel', 'Dev channel for the three pinned messages. Running this again moves them.', required=True,
           channel_types=[TEXT]),
    option(CHANNEL, 'forum', 'The game suggestions forum', required=True, channel_types=[FORUM]),
    option(ROLE, 'role', 'Who can /claim games', required=True),
])

# Registered only once the board is set up with /bounty-board, so they never sit next to another bot's /claim before that.
BOARD_COMMANDS = [
    command('claim', 'Claim a game you are working on, change its link, or drop it', [
        sub('new', "Claim a game you're working on: a suggestion, or a custom game", [
            option(STRING, 'post', "Type to search the forum's posts, or pick \"Custom game\" for one that has no post", required=True,
                   autocomplete=True),
            option(STRING, 'link', 'Link to the original game (Steam page etc.), shown on the games board'),
        ]),
        sub('edit', 'Change the link to the original game of a game you claimed', [
            option(STRING, 'post', 'The game', required=True, autocomplete=True),
            option(STRING, 'link', 'Link to the original game (Steam page etc.)', required=True),
        ]),
        sub('drop', 'Drop a game you claimed: it goes back to Top suggestions', [option(STRING, 'post', 'The game', required=True, autocomplete=True)]),
    ]),
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

STATUS_CHOICES = [('🟢 Active (open to every dev)', 'active'), ('🟡 Waiting for a reply', 'pending'),
                  ('🔒 Private (one dev only)', 'private'), ('💤 On a break', 'inactive')]
ON_OFF = [('On', 'on'), ('Off', 'off')]
ONLINE = [('Online', 'online'), ('Offline for now', 'offline')]
RELEASE_PING = [('@everyone', 'everyone'), ('@Updates', 'updates'), ('@Releases', 'releases'), ('No ping', 'none')]

PREVIEW_CHOICES = [
    ('everything (clears the test channel)', 'all'), ('dev board', 'board'), ('bug page', 'bug'), ('update draft', 'announcement'),
    ('fix log', 'fixlog'), ('rules', 'rules'), ('mod cards', 'mod'), ('tester report', 'tester'), ('bounty board', 'games'),
]

COMMANDS = [
    command('update', 'Post a game update, change a posted one, or change how updates work', [
        sub('new', 'Draft and post an update with the bug fixes that are waiting', [option(STRING, 'game', 'Game', required=True, autocomplete=True)]),
        sub('edit', 'Change an update that was already posted', [option(STRING, 'update', 'Which update', required=True, autocomplete=True)]),
        sub('settings', 'How updates work for a game: when your agent posts, merging, pings', [
            option(STRING, 'game', 'Game', required=True, autocomplete=True),
            option(STRING, 'mode', 'When your AI agent may post updates', choices=[('Only when I say so (manual)', 'manual'), ('After every fixed report', 'every'),
                                                                                   ('When a high or critical fix is waiting', 'critical'), ('After a number of fixes', 'count')]),
            option(INTEGER, 'count', 'For "after a number of fixes": how many', min_value=1, max_value=50),
            option(INTEGER, 'merge', 'Fold updates posted this many hours apart into one card (0 = off, the default)', min_value=0, max_value=72),
            option(STRING, 'ping', 'May your AI agent ping when it posts? (off by default)', choices=[('On', 'on'), ('Off', 'off')]),
        ]),
    ]),
    _bug_command(),
    _improvement_command(),
    command('help', 'Show the commands you can use'),
    command('mcp', 'Connect your AI agent to the reports of your games', [
        sub('setup', 'Get the address and your personal token (shown only to you)', [
            option(STRING, 'access', 'What your agent may do (Full when left out)', choices=[('Full: read, change statuses, post updates', 'full'), ('Read-only: look, never change or post', 'read')])]),
        sub('revoke', 'Stop your token from working'),
        sub('status', 'Admin: who has a token, who is connected, when it last called'),
        sub('kick', 'Admin: stop a developer from using the MCP until you allow them again', [option(USER, 'user', 'The dev', required=True)]),
        sub('allow', 'Admin: let a stopped developer use the MCP again', [option(USER, 'user', 'The dev', required=True)]),
        sub('pause', 'Admin: switch the MCP off for everyone'),
        sub('resume', 'Admin: switch the MCP back on'),
    ]),
    command('mog', 'Admin: Codecel posts a mog GIF and pings Robin and Redwing Helper'),
    {'type': 3, 'name': 'Mog'},  # right click a message, Apps, Mog: Codecel replies to it with a GIF
    command('pings', 'Choose when the bot pings you', [
        option(STRING, 'bugs', 'Ping me when a new bug arrives on my games', choices=ON_OFF),
        option(STRING, 'exploits', 'Ping me for high-priority exploit reports', choices=ON_OFF),
    ]),
    command('strikes', "Show a user's troll strikes", [option(USER, 'user', 'User', required=True)]),
    command('pardon', 'Remove one strike from a user', [option(USER, 'user', 'User', required=True)]),
    command('preview', 'Admin: post the finished embeds in the test channel (everything wipes it first)',
            [option(STRING, 'what', 'Which preview', choices=PREVIEW_CHOICES)]),
    command('botrules', 'Post the bug report rules and strike ladder here'),
    command('release', 'Release one of your games, fix a released one, or move it back', [
        sub('new', 'Your game is out: paste its Roblox link', [
            option(STRING, 'game', 'Game', required=True, autocomplete=True),
            option(STRING, 'link', 'Roblox game link (a game that was released before keeps its old one if you leave this out)'),
            option(ATTACHMENT, 'image', 'Your own hero image (otherwise the one from Roblox)'),
            option(STRING, 'studio', 'Original studio (otherwise taken from the Steam page)'),
            option(STRING, 'original', 'Original game name (otherwise the name on the board)'),
            option(STRING, 'ping', 'Who the new-game card pings (default: everyone)', choices=RELEASE_PING),
            option(STRING, 'description', 'A short line shown under the game, e.g. Multiplayer + VC, or Only 1 map so far', max_length=140),
        ]),
        sub('quiet', 'Add a finished game to the library without announcing it (no card, no ping)', [
            option(STRING, 'game', 'Game', required=True, autocomplete=True),
            option(STRING, 'link', 'Roblox game link (a game that was released before keeps its old one if you leave this out)'),
            option(ATTACHMENT, 'image', 'Your own picture (otherwise the one from Roblox)'),
            option(STRING, 'studio', 'Original studio (otherwise taken from the Steam page)'),
            option(STRING, 'original', 'Original game name (otherwise the name on the board)'),
            option(STRING, 'description', 'A short line shown under the game, e.g. Multiplayer + VC, or Only 1 map so far', max_length=140),
        ]),
        sub('edit', 'Fix a released game', [
            option(STRING, 'game', 'Released game', required=True, autocomplete=True),
            option(STRING, 'title', 'The title to show'),
            option(STRING, 'link', 'Roblox game link'),
            option(ATTACHMENT, 'image', 'Your own hero image'),
            option(STRING, 'studio', 'Original studio'),
            option(STRING, 'original', 'Original game name'),
            option(STRING, 'online', 'Is the game up? Offline shows a grey Offline button instead of Play', choices=ONLINE),
            option(STRING, 'description', 'The short line under the game: change it, or a single - removes it', max_length=140),
        ]),
        sub('undo', 'Move a released game back to unreleased', [option(STRING, 'game', 'Released game', required=True, autocomplete=True)]),
    ]),
    command('progress', 'Say how far an unreleased game is, whether you are working on it, or that it is in testing', [
        option(STRING, 'game', 'Game', required=True, autocomplete=True),
        option(INTEGER, 'percent', 'How much of the game is done', min_value=0, max_value=100),
        option(BOOLEAN, 'working', 'Are you working on it right now? (yes / no)'),
        option(STRING, 'testing', 'Testing phase on or off. Testers can report a game in testing (released games too)', choices=[('On', 'on'), ('Off', 'off')]),
        option(STRING, 'link', 'The Roblox link testers play the test build with (shown as a Play button). A single - removes it'),
        option(STRING, 'note', 'A note for testers on the testing card (what to test, what you need). A single - removes it', max_length=300),
    ]),
    command('invites', 'Invites: your numbers and the leaderboard', [
        sub('stats', 'How many people you invited, how many are verified and count', [option(USER, 'user', 'Someone else (default: you)')]),
        sub('top', 'The invite leaderboard'),
        sub('link', 'Your personal invite link: everyone who joins with it and verifies counts for you'),
        sub('check', 'Admin: everything about one member: links, who they invited, who is verified', [option(USER, 'user', 'The member', required=True)]),
    ]),
    command('tester', 'The tester roster', [
        sub('add', 'Add a tester to the roster (admins)', [
            option(USER, 'user', 'The tester', required=True),
            option(STRING, 'status', 'Default: waiting for a reply', choices=STATUS_CHOICES),
            option(STRING, 'only_for', 'For a private tester: dev (any developer) or one dev whose games they test (default: you)', autocomplete=True),
            option(STRING, 'devices', 'What they test on', max_length=120),
            option(STRING, 'recording', 'How they record', max_length=120),
            option(STRING, 'availability', 'When they are free', max_length=120),
            option(STRING, 'best_for', 'What they are best for', max_length=120),
        ]),
        sub('remove', 'Take a tester off the roster and remove the Tester role (admins)', [option(USER, 'user', 'The tester', required=True)]),
        sub('status', 'Open to all devs, waiting, private (one dev only) or on a break (admins)', [
            option(USER, 'user', 'The tester', required=True),
            option(STRING, 'status', 'New status', required=True, choices=STATUS_CHOICES),
            option(STRING, 'only_for', 'Private only: dev (any developer) or one dev whose games they test (default: you)', autocomplete=True),
        ]),
        sub('edit', "Change a tester's details (admins)", [
            option(USER, 'user', 'The tester', required=True),
            option(STRING, 'devices', 'What they test on', max_length=120),
            option(STRING, 'recording', 'How they record', max_length=120),
            option(STRING, 'availability', 'When they are free', max_length=120),
            option(STRING, 'best_for', 'What they are best for', max_length=120),
        ]),
        sub('profile', 'Fill in or update your own tester profile'),
        sub('post', 'Post the tester guide and the roster in a channel; they update by themselves (admins)', [
            option(CHANNEL, 'channel', 'Default: this channel', channel_types=[GUILD_TEXT])]),
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
