"""What players read in their own report: small cards in the community look (docs/DESIGN.md). One clear title, one or two short lines,
and a small hint saying what to do next. The person is pinged right above the card when they need to act.
Each function returns (view, files) for thread.send(view=..., files=...)."""
import discord
from discord import ui

from bot.core.ctx import thread_link
from bot.features.bugs.nums import label

NL = chr(10)


def _card(title, lines=(), hint=None, ping=None):
    parts = [ui.TextDisplay(f'### {title}')]
    body = NL.join(x for x in lines if x)
    if body:
        parts.append(ui.TextDisplay(body))
    if hint:
        parts.append(ui.TextDisplay(f'-# {hint}'))
    view = ui.LayoutView()
    if ping:
        view.add_item(ui.TextDisplay(ping))
    view.add_item(ui.Container(*parts))
    return view, []


def _who(user_id):
    return f'<@{user_id}>' if user_id else None


def needs_info(user_id, missing, kind='bug', multiple=False, personal=False):
    """A few things are missing: a short checklist of exactly what to send."""
    items = [f'• {m[:1].upper()}{m[1:]}' for m in missing[:5]] or ['• A bit more detail about what happened' if kind == 'bug' else '• A bit more detail about your idea']
    extra = []
    if multiple:
        extra.append('⚠️ One bug per post, please: post the others separately.')
    if personal:
        extra.append('⚠️ Your screenshot may show personal info: please hide it.')
    return _card('❓ Almost there: please add', items + ([''] + extra if extra else []), 'Reply in this post. I check it again when you do.', ping=_who(user_id))


def logged(bug, low_info=False, dev_report=False, was_asked=False):
    """The report is on the developer's board."""
    if dev_report:
        return _card(f'✅ Logged · {label(bug)}', ['On your board.'])
    if bug.get('kind') == 'suggestion':
        line = 'Sent to the developer. Others can vote on it here.'
    else:
        line = 'Sent to the developer.' + (' Thanks for the details!' if was_asked else ' Thanks for reporting!')
    if low_info:
        line += ' Some details are missing, so a developer may ask you here.'
    return _card(f'✅ Logged · {label(bug)}', [line], 'You get a ping here when it is fixed.' if bug.get('kind') != 'suggestion' else None)


def duplicate(user_id, dup, kind='bug'):
    """Somebody reported or suggested this already."""
    ref = f"{label(dup)} {dup['title']}" if dup['deleted'] else f"[{label(dup)} {dup['title']}]({thread_link(dup['thread_id'])})"
    if dup['status'] == 'fixed':
        line = f"{'Added' if kind == 'suggestion' else 'Fixed'} already: {ref}, <t:{(dup['fixed_at'] or 0) // 1000}:D>."
        hint = None
    else:
        line = f'Same as {ref}.'
        hint = 'Vote on that one instead. This post closes in 24 hours.' if kind == 'suggestion' else 'Add anything new there. This post closes in 24 hours.'
    return _card('🔁 Already ' + ('suggested' if kind == 'suggestion' else 'reported'), [line], hint, ping=_who(user_id))


def troll_closed(kind='bug'):
    return _card('⛔ Closed', [f"Fake or abusive {'posts' if kind == 'suggestion' else 'reports'} lead to strikes."])


def now_a_bug(user_id, bug, bugs_channel):
    return _card(f'🐛 Moved to bug reports · {label(bug)}', ["That's something broken, not a suggestion, so it goes to the developer as a bug."],
                 f'Next time, post bugs in <#{bugs_channel}>.', ping=_who(user_id))


NOTES = {
    'investigating': ('🔎 Looking into it', 'A developer is checking this.'),
    'fixing': ('🛠️ Fix on the way', 'A developer is working on a fix.'),
    'not_a_bug': ('🚫 Not a bug', 'This is how the game is meant to work. Ideas go in the suggestions forum.'),
    'duplicate': ('🔁 Duplicate', 'This was reported already. Follow the original report.'),
    'declined': ('❌ Declined', "The developers decided not to add this. Thanks for the idea! This post closes in 24 hours."),
}
NOTES_SUGGESTION = {'duplicate': ('🔁 Duplicate', 'This was suggested already. Vote on the original post.')}


def status_note(status, kind='bug'):
    found = (NOTES_SUGGESTION if kind == 'suggestion' else {}).get(status) or NOTES.get(status)
    return _card(found[0], [found[1]]) if found else None


def fixed(user_ids, bug, update_url=None):
    """Fixed (in a released update), or a suggestion added: the reporter and the people who 👀'd it are pinged."""
    ping = ' '.join(f'<@{u}>' for u in user_ids)
    if bug.get('kind') == 'suggestion':
        return _card(f"✅ Added · {label(bug)} {bug['title']}", ['Thanks for the idea!'], 'This post closes in 24 hours.', ping=ping)
    lines = [f'It is in the new update: {update_url}' if update_url else 'Thanks for reporting!']
    return _card(f"✅ Fixed · {label(bug)} {bug['title']}", lines, 'Still broken? Reply here within 24 hours and it reopens.', ping=ping)


def reopened(bug):
    return _card(f'🔁 Reopened · {label(bug)}', ['Back with the developer.'])


def files_more(n, total):
    return f'📎 More files · {n} of {total}'


ALLOW_NONE = discord.AllowedMentions.none()
