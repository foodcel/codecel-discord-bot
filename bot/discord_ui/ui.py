"""One look for every embed the bot makes (same rules as the JavaScript version):
 - flat: the embed color matches Discord's dark embed background, so there is no colored stripe
 - heading: one emoji + bold UPPERCASE text, with a rule line under it
 - at most 3 columns across, one value per cell
 - every embed ends its description with an invisible line so they all stretch to the same width
 - one emoji per meaning (E below), the same words for the same event
"""
import re

import discord

EN = ' '    # en space
EM = ' '    # em space
THIN = ' '  # thin space
ZW = '​'    # zero width space
HF = 'ㅤ'    # hangul filler: an invisible character that is as wide as a letter

FLAT = 0x2b2d31
# Sets the width of every embed: 17 + 17 filler characters plus an en and a thin space reach the widest an embed can get.
FILLER = HF * 17 + EN + THIN + HF * 17
FILLER_SHORT = HF * 26   # embeds that carry a big image are narrower, so a shorter width line
RULE = '─' * 13          # under a column heading
WIDE_RULE = '─' * 34     # under a full-width heading
GAP = ';' + EN           # divider inside the summary line
SEP = EM + '·' + EM

E = {
    'fixed': '✅', 'open': '🐛', 'new': '🆕', 'investigating': '🔎', 'fixing': '🛠️', 'update': '📣',
    'duplicate': '🔁', 'notbug': 'ℹ️', 'warn': '⚠️', 'game': '🎮', 'user': '👤', 'date': '📅', 'log': '📜',
    'lock': '🔒', 'video': '🎥', 'status': '📌', 'severity': '⚡', 'device': '🎮', 'fix': '🔧', 'note': '📝',
}

STATUS = {
    'new': f"{E['new']} New", 'needs_info': '❓ Needs info', 'investigating': f"{E['investigating']} Investigating",
    'fixing': f"{E['fixing']} Fixing", 'fixed': f"{E['fixed']} Fixed", 'duplicate': f"{E['duplicate']} Duplicate",
    'not_a_bug': f"{E['notbug']} Not a bug",
}
SEVERITY = {'low': '🟢 Low', 'medium': '🟡 Medium', 'high': '🔴 High', 'critical': '⛔ Critical'}


def cut(x, n):
    x = '' if x is None else str(x)
    return x[:n - 1] + '…' if len(x) > n else x


def head(emoji, text):
    """The heading used for columns and fields, e.g. "🎮 GAME"."""
    return f'{emoji}{EN}{str(text).upper()}'


def flat():
    return discord.Embed(color=FLAT)


def describe(e, line, filler=FILLER):
    """Description = summary line + the invisible width line."""
    e.description = f'{line}\n{filler}'
    return e


def columns(e, cols, rule=RULE):
    """One inline field per column: heading, a rule (pass '' for none), then one line per row."""
    for c in cols:
        value = (f'{rule}\n' if rule else '') + ('\n'.join(c['lines']) or '—')
        e.add_field(name=c['name'], value=value[:1024], inline=True)
    return e


def plain(e, name, text):
    """A full-width field with no rule line."""
    return e.add_field(name=name, value=str(text)[:1024], inline=False)


def section(e, name, text):
    """A full-width field: heading, a wide rule, then text."""
    return e.add_field(name=name, value=f'{WIDE_RULE}\n{text}'[:1024], inline=False)


def sentence(s):
    """Mod cards: text ends with a period."""
    s = ('' if s is None else str(s)).strip()
    return s if re.search(r'[.!?]$', s) else f'{s}.'


def labeled(e, name, text):
    """Mod cards: no rule, heading ends with a colon."""
    return e.add_field(name=f'{name}:', value=str(text)[:1024], inline=False)


def spaced(e, name, text):
    """A full-width field with no rule and one blank line of space after it (used to separate sections)."""
    return e.add_field(name=name, value=f'{str(text)[:1000]}\n{ZW}', inline=False)


def lkey(s):
    """Sort key close to JavaScript's localeCompare: case-insensitive, accents ignored, punctuation before digits before letters."""
    import unicodedata
    s = unicodedata.normalize('NFKD', '' if s is None else str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ([(0 if not c.isalnum() else (1 if c.isdigit() else 2), c.casefold()) for c in s], s.swapcase())


def gap(e):
    """Exactly one empty line after what is already in the embed (a spacer field would be two lines tall)."""
    if e.fields:
        f = e.fields[-1]
        e.set_field_at(len(e.fields) - 1, name=f.name, value=f'{f.value}\n{ZW}', inline=f.inline)
    else:
        e.description = f'{e.description or ""}\n{ZW}'
    return e
