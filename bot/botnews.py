"""The launch announcements (for the staff channel and for the testers). Built here so the preview and the real post are identical."""
import os

from .env import cfg
from .ui import E, ZW, columns, describe, flat, head, section, spacer


def bot_news_embeds():
    """The launch announcement, as ONE embed. Channel names are real channel links."""
    helper_id = os.environ.get('BOT_HELPER_ID') or ''  # optional: a bot this bot will move to (adds a PS line)
    owner_id = os.environ.get('OWNER_ID') or ''         # optional: who devs report bot bugs to
    bugs = f'<#{cfg.bugs_id}>'
    board = f'<#{cfg.dev_forum_id}>'
    modlog = f'<#{cfg.modlog_id}>'
    e = flat()
    e.title = head(E['update'], 'New · the bug bot')
    e.set_footer(text='Set your pings with /pings. Everything runs from your board.')
    describe(e, f'Reports in {bugs} are now checked, tagged and sent to the dev who owns the game. Owners come from the bounty-board.')
    section(e, head('😊', 'Your board'),
            f'Every dev has a post in {board} with their open bugs. Pick a game in the dropdown to scroll through its bugs one by one, with screenshots, videos and status buttons. A new bug gives you a quick ping.')
    section(e, head(E['fixed'], 'Fixing bugs'),
            'Press **Fixed**, or type `12 fixed` or `1-5 fixed`. The reporter and everyone who reacted 👀 are pinged, and the post is deleted after 24 hours. A reply of "still broken" reopens it. Also: investigating, fixing, not a bug, duplicate.')
    section(e, head(E['lock'], 'Exploit reports'),
            f'These are removed from {bugs} at once and appear in your board as a **HIGH PRIORITY** card. The reporter gets a message that it was received, and another when you mark it fixed.')
    section(e, head('📋', 'Transcripts'),
            'Per bug or per game: a zip with the conversation, screenshots, full videos and a few frames. Drop it into your AI agent.')
    section(e, head(E['log'], 'Fix log'),
            f'A pinned post in {board} with fixed and open counts for every game, each fix, and its transcript.')
    section(e, head(E['update'], 'Updates'),
            'After 3 fixes the bot drafts an update with the bug fixes. Post, Edit or Later. `/update` adds your own lines, and the bot rewrites them into clean patch notes.')
    section(e, head(E['warn'], 'Trolls'),
            f"Warning, 1-day mute, kick, 7-day ban, permanent ban. Kicks and bans wait for a dev's Confirm in {modlog}.")
    spacer(e)  # an empty line between the sections above and the commands
    columns(e, [
        {'name': head('⌨️', 'Commands'), 'lines': [
            '`/pings` · choose your pings', '`/update` · post an update', '`/config set` · game link, icon, channel',
            "`/strikes` · a user's strikes", '`/pardon` · remove a strike']},
        {'name': head(E['user'], 'Who can do what'), 'lines': [
            '**Devs** · act on their own games', '**Any dev** · unclaimed games', '**Jr devs** · read only', '**Admins** · everything']},
    ], '─' * 28)
    ps = [x for x in (helper_id and f'PS this bot will be moved to <@{helper_id}>', owner_id and f'Report any bugs to <@{owner_id}>') if x]
    if ps:
        e.add_field(name=ZW, value='\n'.join(ps), inline=False)
    return [e]


def tester_news_embeds():
    """The announcement for the tester announcements channel: how to use /bug. One embed."""
    testing = f'<#{cfg.testing_id}>'
    e = flat()
    e.title = head(E['update'], 'New · report bugs with /bug')
    e.set_footer(text='Only testers can use /bug, and only in the testing channel.')
    describe(e, f'You can now send bugs straight to the developers from {testing}. Your report goes to the dev who owns the game, with your screenshots and videos.')
    section(e, head('🧪', 'How to report'),
            f'1. Go to {testing} and type `/bug`\n2. Pick the game\n3. Attach up to **10 screenshots** and **5 videos** if you have them\n4. Fill in the form and send it')
    section(e, head(E['note'], 'The form'),
            'A short title, what happened, the steps to reproduce, what should happen (optional) and your device or build (optional). The clearer the steps, the faster it gets fixed.')
    section(e, head('🧵', 'After you send it'),
            'The bot opens a thread in the testing channel, and the developer replies there. You get a ping in that thread when it is fixed. The thread is deleted 24 hours later. If it is still broken, reply in the thread and it reopens.')
    section(e, head(E['video'], 'Big files'),
            'Files too big for Discord show up as download links on your report. Post them in your thread instead.')
    section(e, head(E['lock'], 'Found an exploit?'),
            'If a bug lets players cheat or crash servers, do not post the details. Message a developer directly.')
    return [e]


def board_news_embeds():
    """The announcement for the bounty board that now runs from this bot. One embed."""
    owner_id = os.environ.get('OWNER_ID') or ''
    board = f'<#{cfg.bounty_id}>'
    e = flat()
    e.title = head(E['update'], 'New · the bounty board')
    e.set_footer(text='Claims, progress and releases update the board by themselves.')
    describe(e, f'The bounty board in {board} now runs from this bot, with a new look. Every claim moved over, nothing was lost.')
    section(e, head('🏆', 'Top suggestions'),
            'The 25 best-voted games nobody has claimed yet, ranked by votes in the suggestions forum. It updates as votes come in.')
    section(e, head('🛠️', 'Unreleased games'),
            'Every claimed game under its dev, with how far it is and whether the dev is working on it right now.')
    section(e, head('✅', 'Released games'),
            'Games that are out, with a link to play them.')
    spacer(e)  # an empty line between the sections above and the commands
    columns(e, [
        {'name': head('⌨️', 'Commands'), 'lines': [
            '`/claim` · take a game, add its Steam page with `link:`', '`/unclaim` · drop a game you claimed',
            '`/progress` · how far it is, and if you are on it', '`/release` · the game is out, add its Roblox link',
            '`/unrelease` · move a game back', '`/gamelink` · change a game\'s link']},
        {'name': head(E['user'], 'Who can do what'), 'lines': [
            '**Devs** · only their own games', '**Admins** · everything, plus `/assign`, `/exclude` and `/include`']},
    ], '─' * 28)
    ps = ['Credits to <@1134858072989376644> for the original bounty board', owner_id and f'Report any bugs to <@{owner_id}>']
    e.add_field(name=ZW, value='\n'.join(x for x in ps if x), inline=False)
    return [e]
