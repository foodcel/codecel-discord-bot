"""The launch announcements (for the staff channel and for the testers). Built here so the preview and the real post are identical."""
import os

from .env import cfg
from .ui import E, ZW, columns, describe, flat, head, section, gap


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
    gap(e)  # one empty line between the sections above and the commands
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
    e.set_footer(text='Testers send reports here with /bug. Everyone else can use /bug too, in the commands channel.')
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
            'Report it here like any other bug, with all the details. Testers can read each other\'s reports, so others can reproduce it. '
            'Nothing is hidden or deleted, and you do not need to message a developer.')
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
    gap(e)  # one empty line between the sections above and the commands
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


def suggestion_news_embeds():
    """The announcement for the suggestion boards. One embed."""
    owner_id = os.environ.get('OWNER_ID') or ''
    suggestions = f'<#{cfg.suggestions_id}>'
    board = f'<#{cfg.dev_suggestions_id}>'
    bugs = f'<#{cfg.bugs_id}>'
    e = flat()
    e.title = head(E['update'], 'New · suggestion boards')
    e.set_footer(text='The 🙏 votes show devs what players want most.')
    describe(e, f'Posts in {suggestions} are now handled like bug reports: checked, tagged with their game and sent to the dev who owns it.')
    section(e, head('💡', 'Your suggestion board'),
            f'Every dev has a post in {board} with their open suggestions, ranked by 🙏 votes: the most wanted at the top, the least at the bottom. Pick a game in the dropdown to browse them one by one, in the same order. A new suggestion gives you a quick ping.')
    section(e, head(E['fixed'], 'Added or declined'),
            'Press **Added** or **Declined**, or type `12 added` or `7 declined`. The player is pinged and the post is deleted after 24 hours. Added suggestions go into the update announcements next to the bug fixes.')
    section(e, head(E['update'], 'Bugs posted there'),
            f'If a post is really a bug, the bot turns it into a bug on the owner\'s bug board and tells the player to use {bugs} next time.')
    section(e, head(E['duplicate'], 'Duplicates and missing info'),
            'The same idea posted twice points to the first one. A vague post gets a short question, and is closed after 3 days without an answer.')
    gap(e)  # one empty line between the sections above and the commands
    columns(e, [
        {'name': head('⌨️', 'Commands'), 'lines': [
            '`12 added` · the idea is in the game', '`7 declined` · we are not adding it', '`3 duplicate` · already suggested',
            '`1-5 added` · several at once']},
        {'name': head(E['user'], 'Who can do what'), 'lines': [
            '**Devs** · suggestions for their own games', '**Jr devs** · read only', '**Admins** · everything']},
    ], '─' * 28)
    if owner_id:
        e.add_field(name=ZW, value=f'Report any bugs to <@{owner_id}>', inline=False)
    return [e]


def roster_news_testers_embeds():
    """The announcement of the tester roster for the testers. One embed."""
    where = f'<#{cfg.tester_info_id}>' if cfg.tester_info_id else 'the tester-information channel'
    e = flat()
    e.title = head(E['update'], 'New · the tester roster')
    e.set_footer(text='Fill in your profile to show up as active.')
    describe(e, f'The tester list in {where} is now run by the bot. Everyone on it is shown with what they test on and when they are free.')
    section(e, head('👤', 'Your profile'),
            'Type `/tester profile` and fill in what you test on, how you record, when you are free and what you are best for. A complete profile moves you from 🟡 waiting to 🟢 active.')
    section(e, head('🟢', 'What the marks mean'),
            '🟢 open to every dev · 🟡 waiting for a reply · 🔒 only tests one dev\'s games · 💤 on a break.')
    section(e, head('📝', 'Your reports'), 'The roster shows how many bugs each tester has reported with `/bug`.')
    section(e, head('💤', 'Need a break?'), 'Tell an admin and you are put on a break, so devs do not ask you to test until you are back.')
    return [e]


def roster_news_devs_embeds():
    """The announcement of the tester roster for the devs. One embed."""
    owner_id = os.environ.get('OWNER_ID') or ''
    where = f'<#{cfg.tester_info_id}>' if cfg.tester_info_id else 'the tester-information channel'
    e = flat()
    e.title = head(E['update'], 'New · the tester roster')
    e.set_footer(text='The roster updates by itself.')
    describe(e, f'Need a tester? The list in {where} now shows every tester with their devices, recording tool and when they are free.')
    section(e, head('🔍', 'Find a tester'), '`/tester find device:Xbox` lists the testers who are open for testing on that device.')
    section(e, head('🔒', 'Private and on a break'),
            'Some testers only test one dev\'s games (🔒 private) and some are on a break (💤). They are never offered to other devs, so please do not ask them to test your game.')
    section(e, head('🟡', 'New testers'), 'A new tester starts as waiting until they fill in `/tester profile`. Do not count on them yet.')
    section(e, head(E['user'], 'Admins'),
            '`/tester add`, `remove`, `status` and `edit` manage the list. The bot gives and removes the Tester role by itself.')
    if owner_id:
        e.add_field(name=ZW, value=f'Report any bugs to <@{owner_id}>', inline=False)
    return [e]


GAMES_CHANNEL = 1562940878685872149  # #games


def release_news_devs_embeds():
    """The announcement for devs: the game library, /release, update cards, new info on logged bugs. One embed."""
    owner_id = os.environ.get('OWNER_ID') or ''
    games = f'<#{GAMES_CHANNEL}>'
    e = flat()
    e.title = head(E['update'], 'New · game library and releases')
    e.set_footer(text='Type /help to see every command you can use.')
    describe(e, f'The game library in {games} is rebuilt, and putting a game out is now one command.')
    section(e, head('🎮', 'Game library'),
            f'Every released game is its own card in {games}: its cover, a **Play now** button, the original studio and who ported it. The console hubs sit on top.')
    section(e, head('🚀', 'Releasing a game'),
            'Run `/release new`, pick your game and paste its Roblox link. The bot fetches the name, creator and picture, credits you, takes the studio from the Steam page, makes the game\'s tags in bugs and improvements, and posts a new-game card for 3 days. '
            'You choose who it pings: **@everyone**, **@Updates** or **@Releases**, or nobody. You can add your own picture, studio or original name.')
    section(e, head('🔇', 'Quietly, and fixing mistakes'),
            '`/release quiet` adds a game with no card and no ping. `/release edit` fixes a title, link, picture, studio or original name of a released game.')
    section(e, head('🛡️', 'Limits'),
            'A 5 minute wait between releases, 2 pings per dev and 6 per server per day, and one card per game. Pictures are checked for nudity and gore before anything pings, and a flagged picture is removed.')
    section(e, head(E['update'], 'Update cards'),
            'Updates now come as a card: the title, **Fixes**, **Changes** and **New**, the game\'s cover, a **Play now** button and who posted it.')
    section(e, head('📎', 'New info on a logged bug'),
            'Anything a player adds after **LOGGED** (words, logs, videos) is added to the report and marked with a 📎. You get a quiet **NEW INFO** ping, at most every 10 minutes per bug. `/pings bugs:off` turns it off.')
    section(e, head('❓', 'Learn /help'),
            'Type `/help`. It opens on your highest role page (admin, dev, tester, everyone) and explains every command you can use, with **Previous** and **Next** to flip through the pages. Start there when you are not sure what a command does.')
    section(e, head('🔍', 'Bug hunting'),
            'Reply to a message with `!bug` or `!improve` (and the game) and it becomes a post in the bugs or improvements forum for the player who wrote it. Five false posts and an admin takes the command away.')
    section(e, head('🏷️', 'Posts and tags'),
            'Older posts now have their number and a LOGGED reply. The bugs forum tags are only games now: statuses live on your board.')
    gap(e)
    columns(e, [
        {'name': head('⌨️', 'Commands'), 'lines': [
            '`/release new` · the game is out', '`/release quiet` · add it without announcing', '`/release edit` · fix a released game',
            '`/help` · the commands you can use', '`!bug` or `!improve` · bug hunting: reply to a message']},
        {'name': head(E['user'], 'Who can do what'), 'lines': [
            '**Devs** · only their own games', '**Admins** · everything']},
    ], '─' * 28)
    if owner_id:
        e.add_field(name=ZW, value=f'Report any bugs to <@{owner_id}>', inline=False)
    return [e]


def release_news_testers_embeds():
    """The announcement for testers. One embed."""
    owner_id = os.environ.get('OWNER_ID') or ''
    games = f'<#{GAMES_CHANNEL}>'
    e = flat()
    e.title = head(E['update'], 'New · for testers')
    e.set_footer(text='Type /help to see the commands you can use.')
    describe(e, 'A few things got easier when you test.')
    section(e, head('🔍', 'Bug hunting'),
            f'Reply to any message with `!bug` and the game, like `!bug Peggle`, and it becomes a post in <#{cfg.bugs_id}> in the name of the player who wrote it, with its text and files. `!improve` does the same for ideas in <#{cfg.suggestions_id}>.\n'
            f'**Limit:** if 5 of your posts turn out false, you lose the command and an admin will ask what you meant.')
    section(e, head('📎', 'Add more later'),
            'Once a report says **LOGGED**, anything you add to it (words, logs, videos) is added to the report and marked with a 📎. The dev is told.')
    section(e, head('🔢', 'Numbers'),
            'Every report now has its number in the title, like **#38**, and a LOGGED reply.')
    section(e, head('🎮', 'New games'),
            f'Every released game is in {games} with a **Play now** button, and a new game gets its own card for 3 days.')
    section(e, head('❓', 'Help'),
            '`/help` shows the commands you can use, one page per role.')
    if owner_id:
        e.add_field(name=ZW, value=f'Report any bugs to <@{owner_id}>', inline=False)
    return [e]



def testing_news_devs_embeds():
    """The announcement for devs: everything new since the last one, short. One embed."""
    owner_id = os.environ.get('OWNER_ID') or ''
    e = flat()
    e.title = head(E['update'], 'New · testing and previews')
    e.set_footer(text='Type /help to see every command you can use.')
    section(e, head('🧪', 'Testing'),
            f'`/progress testing:on` shows **🧪 testing** on the board and lists your game in <#{cfg.future_games_id}>. Works for released games too.')
    section(e, head('🏷️', 'Testers forum'),
            f'Testers report in <#{cfg.tester_forum_id}>. The game gets its tag when testing starts, and reports reach your board.')
    section(e, head('👀', 'Previews'),
            '`/release new`, `quiet` and `edit` show a preview first. **Post**, **Edit details** or **Cancel**.')
    section(e, head('💬', 'Description'),
            '`description:` adds a line under your game, like "Multiplayer + VC". `-` removes it.')
    section(e, head('📚', 'Library'),
            'A new game is a card for 3 days, then joins the library. Pictures are cropped to one shape, and there is no picture check.')
    section(e, head('🔴', 'Offline'),
            f'The bot checks Roblox every 5 minutes, marks a taken-down game offline and pings you in <#1565918318664093766>.')
    section(e, head(E['update'], 'Updates'),
            '`/update` drafts now look exactly like the posted card.')
    if owner_id:
        e.add_field(name=ZW, value=f'Report any bugs to <@{owner_id}>', inline=False)
    return [e]


def testing_news_testers_embeds():
    """The announcement for testers, short. One embed."""
    owner_id = os.environ.get('OWNER_ID') or ''
    e = flat()
    e.title = head('🧪', 'New · testers forum')
    e.set_footer(text='Type /help to see the commands you can use.')
    section(e, head('🏷️', 'Reports'),
            f'`/bug` and `!bug` in <#{cfg.testing_id}> now post in <#{cfg.tester_forum_id}>, tagged with the game.')
    section(e, head('🎮', 'Games'),
            f'Only games **in testing** (and released ones) are listed. See them in <#{cfg.future_games_id}>.')
    section(e, head('🔍', '!bug'),
            'Reply to a message with `!bug <game>`, in the testing channel only. 5 false posts and you lose it.')
    if owner_id:
        e.add_field(name=ZW, value=f'Report any bugs to <@{owner_id}>', inline=False)
    return [e]
