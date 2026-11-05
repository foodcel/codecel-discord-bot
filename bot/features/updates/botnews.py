"""The announcements for devs and testers, all in one look: a short title, sections whose lines branch like the /help tree, and the commands
in the footer, one per line. Every branch is kept short enough to stay on one line, so nothing wraps back under the tree.
Built here so the preview and the real post are identical."""

import discord
from discord import ui

from bot.core.env import cfg
from bot.discord_ui.pngs import width_strip, with_strip
from bot.discord_ui.ui import E, ZW, flat, head, section, gap

GAMES_CHANNEL = cfg.games_channel_id  # #games
DEV_CHAT = cfg.dev_chat_id            # #developer-chat
MAX_LINE = 56                        # characters a branch may take before it wraps (a channel link counts as 16)


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
    e.set_image(url='attachment://width.png')  # a 1400 px transparent strip, sent with the embed (see strip()): every announcement is the same width
    return e


def strip():
    """The file the announcements' picture points to. A new one for every message sent."""
    return width_strip()


def bot_news_embeds():
    """The launch announcement for devs: the bug bot."""
    board, bugs, modlog = f'<#{cfg.dev_forum_id}>', f'<#{cfg.bugs_id}>', f'<#{cfg.modlog_id}>'
    return [make('New · the bug bot', [
        ('😊', 'Your board', [
            ('Board', f'your post in {board}'),
            ('Dropdown', 'pick a game, browse its bugs'),
            ('Pings', 'a quick ping per new bug'),
            ('Transcripts', 'a zip for your AI agent')]),
        (E['fixed'], 'Fixing bugs', [
            ('Fixed', 'press it, or type `12 fixed`'),
            ('Several', '`1-5 fixed` does a range'),
            ('Reopen', '"still broken" reopens it'),
            ('Exploits', f'hidden from {bugs} at once')]),
        ('🤖', 'Automatic', [
            ('Fix log', 'pinned: counts and each fix'),
            ('Updates', 'after 3 fixes, a draft to post'),
            ('Trolls', f'warn, mute, kick, ban: see {modlog}')])],
        ['/pings · choose your pings', '/update · post an update', '/config set · game link, icon, channel', "/strikes · a user's strikes", '/pardon · remove a strike'])]


def tester_news_embeds():
    """For testers: how to report with /bug."""
    testing = f'<#{cfg.testing_id}>'
    return [make('New · report bugs with /bug', [
        ('🧪', 'How to report', [
            ('1', f'type `/bug` in {testing}'),
            ('2', 'pick the game'),
            ('3', 'add up to 10 screenshots, 5 videos'),
            ('4', 'fill in the form and send it')]),
        ('🧵', 'After you send it', [
            ('Post', f'it becomes a post in <#{cfg.tester_forum_id}>'),
            ('Fixed', 'you are pinged when it is fixed'),
            ('Reopen', 'still broken? reply in the post'),
            ('Exploit', 'report it like any other bug')])],
        ['/bug · report a bug in the testing channel', '/help · the commands you can use'])]


def board_news_embeds():
    """For devs: the bounty board that runs from this bot."""
    e = make('New · the bounty board', [
        ('🏆', 'The board', [
            ('Top suggestions', 'best-voted, not claimed yet'),
            ('Unreleased', "each dev's games: progress or 🧪"),
            ('Released', 'games that are out, with a link')])],
        ['/claim · take a game, add its Steam page with link:', '/unclaim · drop a game you claimed', '/progress · how far it is, if you are on it, testing:on',
         '/release new · the game is out', '/unrelease · move a game back', "/gamelink · change a game's link"])
    e.add_field(name=ZW, value='Credits to <@1134858072989376644> for the original bounty board', inline=False)
    return [e]


def suggestion_news_embeds():
    """For devs: the suggestion boards."""
    suggestions, board = f'<#{cfg.suggestions_id}>', f'<#{cfg.dev_suggestions_id}>'
    return [make('New · suggestion boards', [
        ('💡', 'Your board', [
            ('Board', f'your post in {board}'),
            ('Ranked', 'by 🙏 votes, a dropdown per game'),
            ('Pings', 'a quick ping per new suggestion')]),
        (E['fixed'], 'Handling them', [
            ('Added', 'press it, or type `12 added`'),
            ('Declined', 'press it, or type `7 declined`'),
            ('Bugs', f'a bug from {suggestions} moves to your bugs'),
            ('Duplicates', 'point to the first post')])],
        ['12 added · the idea is in the game', '7 declined · we are not adding it', '3 duplicate · already suggested', '1-5 added · several at once'])]


def roster_news_testers_embeds():
    """For testers: the tester roster."""
    where = f'<#{cfg.tester_info_id}>' if cfg.tester_info_id else 'the tester-information channel'
    return [make('New · the tester roster', [
        ('👤', 'Your profile', [
            ('Profile', '`/tester profile` makes you active'),
            ('Fill in', 'devices, recording tool, free time'),
            ('List', f'everyone is in {where}')]),
        ('🟢', 'The marks', [
            ('🟢', 'open to every dev'), ('🟡', 'waiting for a reply'), ('🔒', "only tests one dev's games"), ('💤', 'on a break: tell an admin')])],
        ['/tester profile · fill in your profile'])]


def roster_news_devs_embeds():
    """For devs: the tester roster."""
    where = f'<#{cfg.tester_info_id}>' if cfg.tester_info_id else 'the tester-information channel'
    return [make('New · the tester roster', [
        ('🔍', 'Find a tester', [
            ('List', f'everyone is in {where}'),
            ('Find', '`/tester find device:Xbox`')]),
        ('🔒', 'Who to ask', [
            ('🔒', "only tests one dev's games: do not ask"),
            ('💤', 'on a break: do not ask'),
            ('🟡', 'new, waiting for their profile')])],
        ['/tester find device: · find a tester', '/tester add · add a tester (admins)', '/tester status · change a mark (admins)'])]


def testing_news_devs_embeds():
    """The announcement for devs about testing and previews."""
    return [make('New · testing and previews', [
        ('🧪', 'Testing', [
            ('Board', f'🧪 on the board and in <#{cfg.future_games_id}>'),
            ('Forum', f'testers report in <#{cfg.tester_forum_id}>'),
            ('Released games', 'can be in testing too')]),
        ('🚀', 'Releasing', [
            ('Preview', 'every `/release` shows it first'),
            ('Description', 'a line under your game'),
            ('Library', 'new games join after 3 days')]),
        ('🤖', 'Automatic', [
            ('Offline', 'taken-down games are marked offline'),
            ('Pings', f'you are pinged in <#{DEV_CHAT}>'),
            ('Updates', '`/update` drafts look like the post')])],
        ['/progress testing:on · put your game in testing', '/progress testing:off · testing is over', '/release new · preview, then post',
         '/release edit description: · the line under your game', '/help · every command you can use'])]


def testing_news_testers_embeds():
    """The announcement for testers about the testers forum."""
    return [make('New · testers forum', [
        ('🏷️', 'Reports', [
            ('Forum', f'testing channel reports: <#{cfg.tester_forum_id}>'),
            ('Tags', 'each report is tagged with the game'),
            ('Games', f'only games in testing: <#{cfg.future_games_id}>')]),
        ('🔍', 'Bug hunting', [
            ('!bug <game>', 'reply to a message'),
            ('Anywhere', f'a post in <#{cfg.bugs_id}>'),
            ('Testing channel', 'a post in the testers forum'),
            ('Limit', '5 false posts and you lose it')])],
        ['/bug · report a bug in the testing channel', '!bug <game> · reply to a message to report it', '/help · the commands you can use'],
        emoji='🧪')]


def tester_guide_embeds():
    """The pinned "get started" post of the testers forum."""
    return [make('Get started · testing', [
        ('🧪', 'Report a bug', [
            ('1', f'type `/bug` in <#{cfg.testing_id}>'),
            ('2', 'pick the game'),
            ('3', 'add screenshots and videos'),
            ('4', 'fill in the form and send it')]),
        ('🔍', 'Or reply to a message', [
            ('!bug <game>', 'reply to a message, anywhere'),
            ('Anywhere', 'a post in the public bugs forum'),
            ('Testing channel', 'a post in this forum'),
            ('Limit', '5 false posts and you lose it')]),
        ('📌', 'This forum', [
            ('Posts', 'one per bug, tagged with the game'),
            ('Dev', 'replies in your post, and pings you when fixed'),
            ('Games', f'only games in testing: <#{cfg.future_games_id}>')]),
        ('✨', 'A good report', [
            ('Title', 'short and clear'),
            ('Steps', 'how to make it happen again'),
            ('Proof', 'a screenshot or a video')])],
        ['/bug · report a bug in the testing channel', '!bug <game> · reply to a message to report it', '/help · the commands you can use'],
        emoji='👋')]


def code_chip(line):
    """"/cmd · text" becomes "`/cmd` · text": the command in a grey box."""
    first, sep, rest = line.partition(' · ')
    return f'`{first}` · {rest}' if sep and first[:1] in '/!' else line


def date_button(when=None):
    """The date as a greyed-out button: the only thing Discord puts on the right of a title."""
    d = (when or __import__('datetime').datetime.now()).strftime('%b %d, %Y').replace(' 0', ' ')
    return ui.Button(style=discord.ButtonStyle.secondary, label=d, disabled=True, custom_id='date')


def as_card(e, ping=None):
    """An announcement embed as a card: (view, files). The ping above the card, the title with the date on the right, a line under the header and one above the commands."""
    strip_ = width_strip()
    items = [ui.Section(f'### {e.title}', accessory=date_button()), ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)]
    for f in e.fields:
        items.append(ui.TextDisplay(f'**{f.name.rstrip(":")}**\n{f.value}') if f.name.strip(' \u200b') else ui.TextDisplay(f.value))
    if e.footer and e.footer.text:
        items += [ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                  ui.TextDisplay('\n'.join('-# ' + code_chip(x) for x in e.footer.text.split('\n')))]
    view = ui.LayoutView()
    if ping:  # the ping sits right above the card, outside it
        view.add_item(ui.TextDisplay(ping))
    items, strip_ = with_strip(items)  # the strip keeps every card the same width
    view.add_item(ui.Container(*items))
    return view, [strip_]
