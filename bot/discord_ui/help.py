"""/help: the commands the person can use, one page per role (highest role first), with Previous and Next buttons.
The commands come from the command definitions (bot/commands.py); the short texts below only make the lines easy to read, and a command
without one falls back to its definition, so a new command always shows up."""
import re

import discord
from discord import ui

from bot.discord_ui.card import card
from bot.discord_ui.commands import BOARD_COMMANDS, COMMANDS
from bot.discord_ui.components import button
from bot.core.env import cfg
from bot.core.perms import level
from bot.discord_ui.ui import EM

# role -> (emoji, label, intro, [(group emoji, group title, [command names or (text, description)])])
PAGES = {
    'admin': ('🔑', 'Admin', 'Only admins can use these. You can use every other page too.', [
        ('🎮', 'Games board', ['assign', 'exclude', 'include', 'bounty-board', 'games']),
        ('🧪', 'Testers', ['tester add', 'tester remove', 'tester status', 'tester edit', 'tester post']),
        ('🔎', 'Invites', ['invites check']),
        ('🎁', 'Giveaways', ['giveaway+']),
        ('🛡️', 'Moderation', ['strikes', 'pardon', 'botrules', 'preview'])]),
    'dev': ('🛠️', 'Dev', 'For devs, on the games they own.', [
        ('🎮', 'Your games', ['claim+', 'release+', 'progress', 'update']),
        ('⚙️', 'Settings', ['pings'])]),
    'tester': ('🧪', 'Tester', 'For testers.', [
        ('🧪', 'Testing', ['tester profile',
                          ('/bug', 'in the testing channel: report a bug as a thread')])]),
    'everyone': ('🌍', 'Everyone', 'For everyone, in the bug and improvement forums.', [
        ('🐛', 'Reporting', ['bug', 'suggest']),
        ('📨', 'Invites', ['invites link', 'invites stats', 'invites top']),
        ('❓', 'Help', ['help'])]),
}
ORDER = ['admin', 'dev', 'tester', 'everyone']
# every page that may report a message (testers and devs): bug hunting
HUNTING = ('🔍', 'Bug hunting', [('!bug', 'reply to a message to post it in the bugs forum'),
                                  ('!suggest', 'the same for an idea in the improvements forum')])

SHORT = {
    'claim': 'take a game, change its link, or drop it', 'release': 'your game is out, or fix it', 'giveaway': 'run a giveaway',
    'assign': 'give a game to a dev, even if someone holds it', 'exclude': 'take a post off the bounty board', 'include': 'put an excluded post back',
    'bounty-board': 'set up the bounty board in a channel', 'games': 'post or refresh the games board',
    'tester add': 'add a tester to the roster', 'tester remove': 'take a tester off the roster', 'tester status': 'active, waiting, private or on a break',
    'tester edit': "change a tester's details", 'tester post': 'post the tester guide and roster', 'strikes': "show a user's troll strikes",
    'mog': 'Codecel posts a mog GIF and pings Robin and Redwing Helper',
    'pardon': 'remove a strike (and give back bug hunting)', 'botrules': 'post the bug report rules here', 'preview': 'post the finished embeds in the test channel',
    'claim new': 'take a game (add its Steam page with link:)', 'claim edit': 'change the link to the original game', 'claim drop': 'drop a game you claimed', 'release new': 'paste its Roblox link',
    'release quiet': 'add it without announcing it', 'release edit': 'fix a released game', 'release undo': 'move it back to unreleased',
    'progress': 'how far a game is, or put it in testing', 'update': 'draft and post an update',
    'pings': 'choose when the bot pings you', 'tester profile': 'fill in or change your tester profile',
    'giveaway new': 'start a giveaway (opens a preview first)', 'giveaway end': 'end one now and draw', 'giveaway reroll': 'draw a new winner',
    'giveaway cancel': 'cancel a running giveaway', 'giveaway stats': 'how many new members it brought', 'giveaway list': 'the latest giveaways',
    'invites stats': 'your invites and how many count', 'invites link': 'your own invite link, tracked for you', 'invites check': "a member's invite links, who they invited, who is verified", 'invites top': 'the invite leaderboard',
    'bug': 'report a bug with a short form (files and links optional)', 'suggest': 'suggest an improvement with a short form', 'help': 'this list',
}


def descriptions():
    out = {}
    for c in COMMANDS + BOARD_COMMANDS:
        out[c['name']] = c.get('description', '')  # the right-click Mog app has none
        for o in c.get('options') or []:
            if o.get('type') == 1:
                out[f"{c['name']} {o['name']}"] = o['description']
    return out


def _clean(text):
    """A definition's description made short: no 'Admin:' and no '(admins only)'."""
    text = re.sub(r'^Admin:\s*', '', text or '')
    text = re.sub(r'\s*\((?:admins?(?: only)?)\)\s*$', '', text)
    return text[:1].lower() + text[1:] if text else text


def roles_of(member):
    """The pages this person gets, highest first."""
    lv = level(member)
    tester = any(str(r.id) in cfg.tester_roles for r in getattr(member, 'roles', []))
    have = {'admin': lv == 'admin', 'dev': lv in ('admin', 'dev', 'jr'), 'tester': tester or lv == 'admin', 'everyone': True}
    return [r for r in ORDER if have[r]]


def _subs(name):
    """The sub-commands of a command, from its definition."""
    for c in COMMANDS + BOARD_COMMANDS:
        if c['name'] == name:
            return [o['name'] for o in c.get('options') or [] if o.get('type') == 1]
    return []


def _tree(entries, desc):
    """One line per command; an entry like 'claim+' lists its sub-commands as bullets under it (a blank line keeps the groups apart)."""
    lines = []
    for n, item in enumerate(entries):
        many = isinstance(item, str) and item.endswith('+')
        item = item[:-1] if many else item
        text, what = item if isinstance(item, tuple) else (f'/{item}', SHORT.get(item) or _clean(desc.get(item, '')))
        lines.append(f"**{text}**{EM}·{EM}{what}" if what else f'**{text}**')
        if many:
            for sname in _subs(item):
                lines.append(f"•{EM}`{sname}`{EM}{SHORT.get(f'{item} {sname}') or _clean(desc.get(f'{item} {sname}', ''))}")
            if n < len(entries) - 1:
                lines.append('')
    return chr(10).join(lines)


def page_card(role, n, total, member):
    """One page of /help as a card: (view, files). Previous / Next sit under it."""
    emoji, label, intro, groups = PAGES[role]
    if role == 'dev' and level(member) == 'jr':
        intro = 'You are a jr dev: you can look, but only full devs can use these.'
    groups = list(groups)
    if role in ('dev', 'tester'):  # devs and testers can report a message
        groups.append(HUNTING)
    desc = descriptions()
    blocks = [f'-# {intro}'] + [f"**{g_emoji} {title}**{chr(10)}{_tree(entries, desc)}" for g_emoji, title, entries in groups]
    below = [ui.ActionRow(button(f'help:{n - 1}', 'Previous', discord.ButtonStyle.secondary, disabled=n == 0),
                          button(f'help:{n + 1}', 'Next', discord.ButtonStyle.primary, disabled=n >= total - 1))] if total > 1 else []
    return card(f'{emoji} Help · {label}', blocks, [f'Page {n + 1} of {total} · {label}'], below=below)


def _page(member, n):
    roles = roles_of(member)
    n = max(0, min(int(n), len(roles) - 1))
    return page_card(roles[n], n, len(roles), member)


async def command_help(i):
    view, files = _page(i.user, 0)
    await i.response.send_message(view=view, files=files, ephemeral=True)


async def button_help(i, n):
    view, files = _page(i.user, n)
    await i.response.edit_message(content=None, embeds=[], view=view, attachments=files)
