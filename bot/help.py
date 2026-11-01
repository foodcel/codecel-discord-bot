"""/help: the commands the person can use, one page per role (highest role first), with Previous and Next buttons.
The descriptions come from the command definitions (bot/commands.py), so they never go stale."""
import discord

from .commands import BOARD_COMMANDS, COMMANDS
from .components import button, make_view
from .env import cfg
from .perms import level
from .ui import EM, flat, head

# what each page lists: command names as the definitions have them ('tester find' = the find subcommand), or (text, description) for typed ones
PAGES = {
    'admin': ('🔑', 'Admin', 'Only admins can use these.', [
        'assign', 'exclude', 'include', 'bounty-board', 'games', 'tester add', 'tester remove', 'tester status', 'tester edit', 'tester post',
        'strikes', 'pardon', 'botrules', 'preview']),
    'dev': ('🛠️', 'Dev', 'For devs, on the games they own.', [
        'claim', 'unclaim', 'release new', 'release quiet', 'release edit', 'unrelease', 'gamelink', 'progress', 'update', 'config', 'pings', 'tester find',
        ('12 fixed', 'Type this in your bug board to mark a bug: fixed, investigating, fixing, declined…'),
        ('1-5 fixed', 'The same for a range of bugs'),
        ('7 added', 'Mark a suggestion as added (or declined)'),
        ('!bug / !improve', 'Reply to a message with this to report it as a bug or an improvement')]),
    'tester': ('🧪', 'Tester', 'For testers.', [
        'tester profile', 'tester find',
        ('/bug', 'In the testing channel: report a bug as a thread'),
        ('!bug', 'Reply to a message with this to report it')]),
    'everyone': ('🌍', 'Everyone', 'For everyone, in the bug and suggestion forums.', ['bug', 'improvement', 'help']),
}
ORDER = ['admin', 'dev', 'tester', 'everyone']
# commands that are not in the definitions
EXTRA = {'help': 'Show the commands you can use'}


def descriptions():
    out = dict(EXTRA)
    for c in COMMANDS + BOARD_COMMANDS:
        out[c['name']] = c['description']
        for o in c.get('options') or []:
            if o.get('type') == 1:
                out[f"{c['name']} {o['name']}"] = o['description']
    return out


def roles_of(member):
    """The pages this person gets, highest first."""
    lv = level(member)
    tester = any(str(r.id) in cfg.tester_roles for r in getattr(member, 'roles', []))
    have = {'admin': lv == 'admin', 'dev': lv in ('admin', 'dev', 'jr'), 'tester': tester or lv == 'admin', 'everyone': True}
    return [r for r in ORDER if have[r]]


def page_embed(role, n, total, member):
    emoji, label, intro, entries = PAGES[role]
    desc = descriptions()
    if role == 'dev' and level(member) == 'jr':
        intro = 'You are a jr dev: you can look, but only full devs can use these.'
    lines = [f'-# {intro}', '']
    for item in entries:
        text, what = item if isinstance(item, tuple) else (f'/{item}', desc.get(item, ''))
        lines.append(f'**{text}**{EM}·{EM}{what}' if what else f'**{text}**')
    e = flat()
    e.title = head(emoji, f'Help · {label}')
    e.description = '\n'.join(lines)
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
