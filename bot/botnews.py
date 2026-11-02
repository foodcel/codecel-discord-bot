"""The announcements for devs and testers, all in one look: a short title, sections whose lines branch like the /help tree, and the commands
in the footer, one per line. Built here so the preview and the real post are identical."""
from .env import cfg
from .ui import E, ZW, flat, head, section, gap

GAMES_CHANNEL = 1562940878685872149  # #games
DEV_CHAT = 1565918318664093766       # #developer-chat


def tree(*rows):
    """(name, text) pairs as branches: ├─ **name** · text, the last one └─."""
    last = len(rows) - 1
    return '\n'.join(f"{'└─' if n == last else '├─'} **{name}** · {text}" for n, (name, text) in enumerate(rows))


def make(title, groups, footer, emoji=None):
    """One embed: the title, a section per group (emoji, heading, rows) and the footer."""
    e = flat()
    e.title = head(emoji or E['update'], title)
    for icon, heading, rows in groups:
        section(e, head(icon, heading), tree(*rows))
    gap(e)
    e.set_footer(text='\n'.join(footer))
    return e


def bot_news_embeds():
    """The launch announcement for devs: the bug bot."""
    board, bugs, modlog = f'<#{cfg.dev_forum_id}>', f'<#{cfg.bugs_id}>', f'<#{cfg.modlog_id}>'
    return [make('New · the bug bot', [
        ('😊', 'Your board', [
            ('Board', f'a post in {board} with your open bugs, a dropdown per game and status buttons'),
            ('Pings', 'a quick ping for each new bug'),
            ('Transcripts', 'a zip per bug or game, ready for your AI agent')]),
        (E['fixed'], 'Fixing bugs', [
            ('Fixed', 'press the button, or type `12 fixed` or `1-5 fixed`. The reporter is pinged'),
            ('Reopen', 'a reply of "still broken" reopens it'),
            ('Exploits', f'removed from {bugs} at once and shown as **HIGH PRIORITY** on your board')]),
        ('🤖', 'Automatic', [
            ('Fix log', f'pinned in {board}: counts per game and each fix'),
            ('Updates', 'after 3 fixes the bot drafts an update: Post, Edit or Later'),
            ('Trolls', f'warning, 1-day mute, kick, 7-day ban, ban. Kicks and bans wait for Confirm in {modlog}')])],
        ['/pings · choose your pings', '/update · post an update', '/config set · game link, icon, channel', "/strikes · a user's strikes", '/pardon · remove a strike'])]


def tester_news_embeds():
    """For testers: how to report with /bug."""
    testing = f'<#{cfg.testing_id}>'
    return [make('New · report bugs with /bug', [
        ('🧪', 'How to report', [
            ('1', f'type `/bug` in {testing}'),
            ('2', 'pick the game, attach up to **10 screenshots** and **5 videos**'),
            ('3', 'fill in the form and send it')]),
        ('🧵', 'After you send it', [
            ('Post', f'it becomes a post in <#{cfg.tester_forum_id}> and the dev replies there'),
            ('Fixed', 'you are pinged when it is fixed'),
            ('Still broken', 'reply in the post and it reopens'),
            ('Exploit', 'report it like any other bug, with all the details')])],
        ['/bug · report a bug in the testing channel', '/help · the commands you can use'])]


def board_news_embeds():
    """For devs: the bounty board that runs from this bot."""
    e = make('New · the bounty board', [
        ('🏆', 'The board', [
            ('Top suggestions', 'the best-voted games nobody has claimed yet'),
            ('Unreleased', 'every claimed game under its dev: how far it is, or 🧪 testing'),
            ('Released', 'games that are out, with a link to play them')])],
        ['/claim · take a game, add its Steam page with link:', '/unclaim · drop a game you claimed', '/progress · how far it is, if you are on it, testing:on',
         '/release new · the game is out', '/unrelease · move a game back', "/gamelink · change a game's link"])
    e.add_field(name=ZW, value='Credits to <@1134858072989376644> for the original bounty board', inline=False)
    return [e]


def suggestion_news_embeds():
    """For devs: the suggestion boards."""
    suggestions, board = f'<#{cfg.suggestions_id}>', f'<#{cfg.dev_suggestions_id}>'
    return [make('New · suggestion boards', [
        ('💡', 'Your board', [
            ('Board', f'a post per dev in {board}, ranked by 🙏 votes, with a dropdown per game'),
            ('Pings', 'a quick ping for each new suggestion')]),
        (E['fixed'], 'Handling them', [
            ('Added or declined', 'press the button, or type `12 added` or `7 declined`. The player is pinged'),
            ('Bugs', f'a bug posted in {suggestions} becomes a bug on your board'),
            ('Duplicates', 'the same idea points to the first, and a vague post gets a question')])],
        ['12 added · the idea is in the game', '7 declined · we are not adding it', '3 duplicate · already suggested', '1-5 added · several at once'])]


def roster_news_testers_embeds():
    """For testers: the tester roster."""
    where = f'<#{cfg.tester_info_id}>' if cfg.tester_info_id else 'the tester-information channel'
    return [make('New · the tester roster', [
        ('👤', 'Your profile', [
            ('Profile', f'`/tester profile`: what you test on, how you record, when you are free. The list is in {where}'),
            ('Active', 'a complete profile moves you from 🟡 waiting to 🟢 active')]),
        ('🟢', 'The marks', [
            ('🟢', 'open to every dev'), ('🟡', 'waiting for a reply'), ('🔒', "only tests one dev's games"), ('💤', 'on a break: tell an admin')])],
        ['/tester profile · fill in your profile'])]


def roster_news_devs_embeds():
    """For devs: the tester roster."""
    where = f'<#{cfg.tester_info_id}>' if cfg.tester_info_id else 'the tester-information channel'
    return [make('New · the tester roster', [
        ('🔍', 'Find a tester', [
            ('List', f'{where} shows every tester with their devices, recording tool and free time'),
            ('Find', '`/tester find device:Xbox` lists the open testers for that device')]),
        ('🔒', 'Who to ask', [
            ('🔒 and 💤', 'private testers and testers on a break are never offered, so do not ask them'),
            ('🟡', 'a new tester waits until they fill in their profile')])],
        ['/tester find device: · find a tester', '/tester add · add a tester (admins)', '/tester status · change a mark (admins)'])]


def release_news_devs_embeds():
    """For devs: the game library and releasing a game."""
    games = f'<#{GAMES_CHANNEL}>'
    return [make('New · game library and releases', [
        ('🎮', 'Library', [
            ('Cards', f'every game is a card in {games}: cover, **Play now**, studio and who ported it'),
            ('Hubs', 'the console hubs sit on top')]),
        ('🚀', 'Releasing', [
            ('New', 'paste your Roblox link: name, creator and picture are filled in, and a new-game card runs for 3 days'),
            ('Ping', '@everyone, @Updates or @Releases, or nobody'),
            ('Quiet', 'add a game with no card and no ping'),
            ('Edit', "fix a released game's title, link, picture, studio or original name")]),
        ('🔧', 'More', [
            ('Updates', 'an update is a card with fixes, changes, new and the cover'),
            ('Logged', 'anything a player adds to a LOGGED bug is saved with a 📎'),
            ('Bug hunting', 'reply `!bug` or `!improve` to a message to report it')])],
        ['/release new · the game is out', '/release quiet · add it without announcing', '/release edit · fix a released game', '/help · the commands you can use'])]


def release_news_testers_embeds():
    """For testers: bug hunting, added info and the games."""
    games = f'<#{GAMES_CHANNEL}>'
    return [make('New · for testers', [
        ('🔍', 'Bug hunting', [
            ('!bug', f'reply to a message with `!bug <game>` in <#{cfg.testing_id}> and it becomes a report'),
            ('Limit', '5 false posts and you lose it')]),
        ('📎', 'Your reports', [
            ('Add more', 'after **LOGGED**, anything you add is saved with a 📎 and the dev is told'),
            ('Numbers', 'every report has its number, like **#38**')]),
        ('🎮', 'Games', [('Library', f'every released game is in {games} with **Play now**')])],
        ['!bug <game> · reply to a message to report it', '/help · the commands you can use'])]


def testing_news_devs_embeds():
    """The announcement for devs about testing and previews."""
    games = f'<#{GAMES_CHANNEL}>'
    return [make('New · testing and previews', [
        ('🧪', 'Testing', [
            ('Board', f'🧪 on the board, listed in <#{cfg.future_games_id}>'),
            ('Forum', f'testers report in <#{cfg.tester_forum_id}>'),
            ('Released games', 'can be in testing too')]),
        ('🚀', 'Releasing', [
            ('Preview', '`/release new`, `quiet` and `edit` show it first'),
            ('Description', 'a line under your game'),
            ('Library', f'a card in {games} for 3 days, then in the library')]),
        ('🤖', 'Automatic', [
            ('Offline', f'taken-down games are marked, you are pinged in <#{DEV_CHAT}>'),
            ('Updates', '`/update` drafts look like the posted card')])],
        ['/progress testing:on · put your game in testing', '/progress testing:off · testing is over', '/release new · preview, then post',
         '/release edit description: · the line under your game', '/help · every command you can use'])]


def testing_news_testers_embeds():
    """The announcement for testers about the testers forum."""
    return [make('New · testers forum', [
        ('🏷️', 'Reports', [
            ('Forum', f'`/bug` and `!bug` post in <#{cfg.tester_forum_id}>, tagged with the game'),
            ('Games', f'only games in testing (and released ones), listed in <#{cfg.future_games_id}>')]),
        ('🔍', 'Bug hunting', [
            ('!bug <game>', 'reply to a message, in the testing channel only'),
            ('Limit', '5 false posts and you lose it')])],
        ['/bug · report a bug in the testing channel', '!bug <game> · reply to a message to report it', '/help · the commands you can use'],
        emoji='🧪')]
