"""/help: the commands the person can use, one page per role (highest role first), with Previous and Next buttons.
The commands come from the command definitions (bot/commands.py); the short texts below only make the lines easy to read, and a command
without one falls back to its definition, so a new command always shows up."""
import re

import discord

from .commands import BOARD_COMMANDS, COMMANDS
from .components import button, make_view
from .env import cfg
from .perms import level
from .ui import EM, flat, head, section

# role -> (emoji, label, intro, [(group emoji, group title, [command names or (text, description)])])
PAGES = {
    'admin': ('🔑', 'Admin', 'Only admins can use these. You can use every other page too.', [
        ('🎮', 'Games board', ['assign', 'exclude', 'include', 'bounty-board', 'games']),
        ('🧪', 'Testers', ['tester add', 'tester remove', 'tester status', 'tester edit', 'tester post']),
        ('🛡️', 'Moderation', ['strikes', 'pardon', 'botrules', 'preview']),
        ('😈', 'Fun', ['mog'])]),
    'dev': ('🛠️', 'Dev', 'For devs, on the games they own.', [
        ('🎮', 'Your games', ['claim', 'unclaim', 'release new', 'release quiet', 'release edit', 'unrelease', 'gamelink', 'progress']),
        ('📣', 'Updates and settings', ['update', 'config', 'pings', 'tester find']),
        ('⌨️', 'Typed in your board', [
            ('12 fixed', 'mark a bug fixed, investigating, duplicate…'),
            ('1-5 fixed', 'the same for a range of bugs'),
            ('7 added', 'mark an idea as added or declined')])]),
    'tester': ('🧪', 'Tester', 'For testers.', [
        ('🧪', 'Testing', ['tester profile',
                          ('/bug', 'in the testing channel: report a bug as a thread')])]),
    'everyone': ('🌍', 'Everyone', 'For everyone, in the bug and improvement forums.', [
        ('🐛', 'Reporting', ['bug', 'improvement']),
        ('❓', 'Help', ['help'])]),
}
ORDER = ['admin', 'dev', 'tester', 'everyone']
# every page that may report a message (testers and devs): bug hunting
HUNTING = ('🔍', 'Bug hunting', [('!bug', 'reply to a message to post it in the bugs forum'),
                                  ('!improve', 'the same for an idea in the improvements forum')])

SHORT = {
    'assign': 'give a game to a dev, even if someone holds it', 'exclude': 'take a post off the bounty board', 'include': 'put an excluded post back',
    'bounty-board': 'set up the bounty board in a channel', 'games': 'post or refresh the games board',
    'tester add': 'add a tester to the roster', 'tester remove': 'take a tester off the roster', 'tester status': 'active, waiting, private or on a break',
    'tester edit': "change a tester's details", 'tester post': 'post the tester guide and roster', 'strikes': "show a user's troll strikes",
    'mog': 'Codecel posts a mog GIF and pings Robin and Redwing Helper',
    'pardon': 'remove a strike (and give back bug hunting)', 'botrules': 'post the bug report rules here', 'preview': 'post the finished embeds in the test channel',
    'claim': 'take a game (add its Steam page with link:)', 'unclaim': 'drop a game you claimed', 'release new': 'your game is out: paste its Roblox link',
    'release quiet': 'add a finished game without announcing it', 'release edit': 'fix a released game', 'unrelease': 'move a game back to unreleased',
    'gamelink': "change a game's link", 'progress': 'say how far a game is', 'update': 'draft and post an update', 'config': "a game's channel, link and pings",
    'pings': 'choose when the bot pings you', 'tester find': 'find a tester for your game', 'tester profile': 'fill in or change your tester profile',
    'bug': 'report a bug with a short form', 'improvement': 'suggest an improvement with a short form', 'help': 'this list',
}


def descriptions():
    out = {}
    for c in COMMANDS + BOARD_COMMANDS:
        out[c['name']] = c['description']
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


def _tree(entries, desc):
    lines = []
    for n, item in enumerate(entries):
        text, what = item if isinstance(item, tuple) else (f'/{item}', SHORT.get(item) or _clean(desc.get(item, '')))
        lines.append(f"{'└─' if n == len(entries) - 1 else '├─'} **{text}**{EM}·{EM}{what}" if what else f'{"└─" if n == len(entries) - 1 else "├─"} **{text}**')
    return '\n'.join(lines)


def page_embed(role, n, total, member):
    emoji, label, intro, groups = PAGES[role]
    if role == 'dev' and level(member) == 'jr':
        intro = 'You are a jr dev: you can look, but only full devs can use these.'
    groups = list(groups)
    if role in ('dev', 'tester'):  # devs and testers can report a message
        groups.append(HUNTING)
    desc = descriptions()
    e = flat()
    e.title = head(emoji, f'Help · {label}')
    e.description = f'-# {intro}'
    for g_emoji, title, entries in groups:
        section(e, head(g_emoji, title), _tree(entries, desc))
    e.set_footer(text=f'Page {n + 1} of {total} · {label}')
    return e


def page_view(n, total):
    return make_view([[
        button(f'help:{n - 1}', 'Previous', discord.ButtonStyle.secondary, disabled=n == 0),
        button(f'help:{n + 1}', 'Next', discord.ButtonStyle.primary, disabled=n >= total - 1),
    ]]) if total > 1 else None


def _page(member, n):
    roles = roles_of(member)
    n = max(0, min(int(n), len(roles) - 1))
    return page_embed(roles[n], n, len(roles), member), page_view(n, len(roles))


async def command_help(i):
    e, view = _page(i.user, 0)
    await i.response.send_message(embeds=[e], view=view, ephemeral=True)


async def button_help(i, n):
    e, view = _page(i.user, n)
    await i.response.edit_message(embeds=[e], view=view)
