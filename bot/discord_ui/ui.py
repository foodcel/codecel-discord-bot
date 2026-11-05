"""Shared words and symbols for every card: the emoji per meaning (E), the status and severity labels, spacing characters, and small text helpers.
The cards themselves are built in bot/discord_ui/card.py."""
import re

EN = ' '    # en space
EM = ' '    # em space
ZW = '​'    # zero width space

# Sets the width of every embed: 17 + 17 filler characters plus an en and a thin space reach the widest an embed can get.
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


def sentence(s):
    """Mod cards: text ends with a period."""
    s = ('' if s is None else str(s)).strip()
    return s if re.search(r'[.!?]$', s) else f'{s}.'


def lkey(s):
    """Sort key close to JavaScript's localeCompare: case-insensitive, accents ignored, punctuation before digits before letters."""
    import unicodedata
    s = unicodedata.normalize('NFKD', '' if s is None else str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ([(0 if not c.isalnum() else (1 if c.isdigit() else 2), c.casefold()) for c in s], s.swapcase())


