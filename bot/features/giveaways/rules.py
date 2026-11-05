"""Giveaway rules: prizes and durations parsed from what admins type, who may enter, and how many entries someone gets."""
import re
from datetime import datetime, timezone
import discord
from bot.features.giveaways import boosts
from bot.features.invites import invites
from bot.core.ctx import ctx
from bot.core.env import cfg
from bot.core.perms import level


NL = chr(10)


SMALL = discord.SeparatorSpacing.small


MAX_WINNERS = 50


MAX_ROUNDS = 3  # a place whose winner never claims is drawn again this many times


# ---- helpers ----
def can_run(m):
    return level(m) == 'admin' or bool(cfg.giveaway_role and any(str(r.id) == str(cfg.giveaway_role) for r in m.roles))


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


UNITS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}


def parse_duration(text):
    """'3d 12h' -> seconds (0 when it says nothing)."""
    return sum(int(n) * UNITS[u] for n, u in re.findall(r'(\d+)\s*([smhdw])', str(text or '').lower()))


def fmt_duration(s):
    out = []
    for unit, size in (('d', 86400), ('h', 3600), ('m', 60)):
        if s >= size:
            out.append(f'{s // size}{unit}')
            s %= size
    return ' '.join(out) or '0m'


AMOUNT = re.compile(r'^\s*([\d,]+(?:\.\d+)?)\s*([kKmM]?)\s+(.+?)\s*$')


def _amount(text):
    """(number, what) for "2K Robux" / "2,000 Robux", else None."""
    m = AMOUNT.match(str(text or ''))
    if not m:
        return None
    return float(m[1].replace(',', '')) * {'': 1, 'k': 1e3, 'm': 1e6}[m[2].lower()], m[3]


def fmt_amount(n, what):
    if n >= 1e6 and n % 1e5 == 0:
        s = f'{n / 1e6:g}M'
    elif n >= 1e3 and n % 100 == 0:
        s = f'{n / 1e3:g}K'
    else:
        s = f'{int(n):,}'
    return f'{s} {what}'


def split_prize(prize, n):
    """The prize of every place when one prize is shared: 10K Robux over 5 winners is 2K Robux each; something that is not an amount goes to everyone."""
    a = _amount(prize)
    each = fmt_amount(a[0] // n, a[1]) if a and n > 1 else prize
    return [[each] for _ in range(n)]


PLACE = re.compile(r'^#?(\d+)(?:st|nd|rd|th)?(?:\s*(?:[-–—]|to)\s*#?(\d+)(?:st|nd|rd|th)?)?(\s*[:=]\s*|\s+[-–—]\s+|\s+)(.+)$', re.I)


def _tidy(prize):
    """'2k robux' typed in lower case becomes '2K Robux'; anything with capitals is left as written."""
    return prize.title() if prize == prize.lower() else prize


def parse_prizes(text, winners):
    """([prizes of place 1, place 2...], error). Lines like "1: 2K Robux + Nitro", "2-5: 2K Robux" or "3-5 2K Robux" (dash or en dash, colon optional after a range).
    A line with no place is the prize of every winner. A line it cannot read is an error, never dropped quietly."""
    places, loose, bad = {}, [], []
    prizes = lambda s: [_tidy(p.strip()) for p in re.split(r'\s*\+\s*|\s*&\s*', s) if p.strip()]
    for line in str(text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        m = PLACE.match(line)
        if m and (m[2] or m[3].strip()):  # a place needs a colon or dash, unless it is a range ("3-5 2K Robux")
            lo, hi = int(m[1]), int(m[2] or m[1])
            if hi < lo or hi > MAX_WINNERS:
                return [], f'At most {MAX_WINNERS} winners, and a range goes up (`2-5`).'
            for k in range(lo, hi + 1):
                places[k] = prizes(m[4])
        else:
            loose.append(prizes(line))
            bad.append(line)
    if places:
        if bad:
            return [], f"I could not read this line: `{bad[0]}`. Write it like `3-5: 2K Robux` (the places, then the prize)."
        top = max(places)
        missing = [k for k in range(1, top + 1) if k not in places]
        if missing:
            return [], f"Place {ordinal(missing[0])} has no prize. Write a line for every place, like `1: 2K Robux` or `2-5: 2K Robux`."
        return [places[k] for k in range(1, top + 1)], None
    if not loose:
        return [], 'Write the prizes: `1: 2K Robux + Nitro` per place, or one line for a prize every winner gets.'
    n = max(1, min(MAX_WINNERS, winners or 1))
    return [[p for line in loose for p in line] for _ in range(n)], None


def groups(prizes):
    """[(places, prize)] with places next to each other that win the same thing put together."""
    out = []
    for k, p in enumerate(prizes, 1):
        if out and out[-1][1] == p:
            out[-1][0].append(k)
        else:
            out.append(([k], p))
    return out


def prize_text_of(prizes):
    """The prizes written back the way the form takes them: '1-2: 2K Robux + Nitro'."""
    return NL.join(f"{pl[0]}{f'-{pl[-1]}' if len(pl) > 1 else ''}: {' + '.join(p)}" for pl, p in groups(prizes))


def find_roles(text):
    """([role ids], [names that matched nothing]) from role names, mentions or ids split by commas or lines."""
    ids, unknown = [], []
    for tok in re.split(r'[,\n]', str(text or '')):
        tok = tok.strip().lstrip('@')
        if not tok:
            continue
        digits = re.fullmatch(r'<@&(\d+)>|(\d{15,})', tok)
        role = ctx.guild.get_role(int(digits[1] or digits[2])) if digits else None
        if not role:
            low = tok.casefold()
            exact = [r for r in ctx.guild.roles if r.name.casefold() == low]
            part = [r for r in ctx.guild.roles if low in r.name.casefold() and not r.is_default()]
            role = exact[0] if exact else (part[0] if len(part) == 1 else None)
        if role and not role.is_default():
            ids.append(str(role.id))
        else:
            unknown.append(tok)
    return list(dict.fromkeys(ids)), unknown


def parse_bonus(text):
    """({role id: extra entries}, [lines that did not work]). Lines like "Booster: 2"."""
    out, bad = {}, []
    for line in str(text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^(.*?)[\s:=x+]*?(\d+)\s*$', line, re.I)
        ids, _ = find_roles(m[1].strip(' :=x+')) if m and m[1].strip(' :=x+') else ([], [])
        if m and len(ids) == 1 and int(m[2]) > 0:
            out[ids[0]] = min(int(m[2]), 100)
        else:
            bad.append(line)
    return out, bad


def _role(rid):
    return f'<@&{rid}>'


def _has(member, rid):
    return any(str(r.id) == str(rid) for r in member.roles)


LEVEL = re.compile(r'^level\s*(\d+)$', re.I)


def _level_of(role):
    m = LEVEL.match(role.name.strip()) if role else None
    return int(m[1]) if m else None


def _has_or_higher(member, rid):
    """A required role. A level role ("Level 3") is also met by any higher level role ("Level 5", "Level 10"...), so the level bot only has to give the
    lowest one and nobody above it is shut out."""
    if _has(member, rid):
        return True
    need = _level_of(ctx.guild.get_role(int(rid)))
    return need is not None and any((_level_of(r) or -1) >= need for r in member.roles)


def hosts_of(g):
    return g['config'].get('hosts') or [g['host_id']]


# ---- who may enter, and how many entries they get ----
def eligible(member, c):
    """(True, '') or (False, the reason in plain words)."""
    if not member:
        return False, 'You are not in the server.'
    if not _has(member, cfg.verified_role):
        return False, 'You need the **Verified** role to enter. Verify first.'
    if any(_has(member, r) for r in c['blacklist']):
        return False, 'Your role is not allowed in this giveaway.'
    if any(_has(member, r) for r in c.get('bypass_roles') or []):  # always allowed in (boosters...): the role and time requirements do not apply, and the card does not list them
        return True, ''
    if c['req_roles']:
        have = [r for r in c['req_roles'] if _has_or_higher(member, r)]
        if (c['req_mode'] == 'all' and len(have) != len(c['req_roles'])) or (c['req_mode'] != 'all' and not have):
            need = (' and ' if c['req_mode'] == 'all' else ' or ').join(_role(r) for r in c['req_roles'])
            return False, f'This giveaway is for {need}.'
    if c['min_days'] and member.joined_at and (datetime.now(timezone.utc) - member.joined_at).days < c['min_days']:
        return False, f"You need to be in the server for **{c['min_days']}** days to enter."
    return True, ''


def short_of(member, c):
    """(invites needed, invites that count) while the person is below the invite minimum, else None."""
    if not c['min_invites']:
        return None
    have = invites.qualified(member.id)
    return (c['min_invites'], have) if have < c['min_invites'] else None


def entries_for(member, c):
    """(total entries, [(what it is for, how many)]). With an invite minimum anyone may enter but has 0 entries until the minimum is reached; then one for
    entering, the bonus roles, and (if on) one more for every invite past the minimum."""
    if short_of(member, c):
        return 0, []
    rows = [('for entering', 1)]
    held = [(rid, n) for rid, n in c['bonus'].items() if _has(member, rid)]
    if c.get('bonus_best') and held:  # level bonuses do not stack (only the highest counts); other role bonuses, like boosting, add on top
        lv = [h for h in held if _level_of(ctx.guild.get_role(int(h[0]))) is not None]
        rest = [h for h in held if h not in lv]
        held = rest + ([max(lv, key=lambda h: h[1])] if lv else [])
        if not lv and len(rest) > 1 and not any(_level_of(ctx.guild.get_role(int(r))) is not None for r in c['bonus']):
            held = [max(rest, key=lambda h: h[1])]  # no level roles in this giveaway: the setting means highest only for all of them
    rows += [(_role(rid), n) for rid, n in held]
    n = boosts.count(member) if c.get('per_boost') else 0  # every server boost they gave (read from the boosters channel), only while they still hold the Server Booster role
    if n:
        rows.append((f"{n} server boost{'s' if n != 1 else ''}", c['per_boost'] * n))
    if c['invite_entries']:
        q = invites.qualified(member.id)
        inv = q - c['min_invites']
        if inv > 0:
            rows.append((f"your invites past {c['min_invites']} ({q} count)" if c['min_invites'] else f'your invites ({q} count)', inv))
    total = sum(n for _, n in rows)
    cap = c['invite_cap']  # the most entries one person can have in total, so nobody wins on invites alone
    if cap and total > cap:
        rows.append((f'capped at {cap} entries in total', cap - total))
        total = cap
    return total, rows
