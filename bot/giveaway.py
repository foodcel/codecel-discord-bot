"""/giveaway: customizable giveaways, in the community look (docs/DESIGN.md, "Community"): a banner made for each giveaway, short lines, real role pings.
An admin (or someone with the Giveaway Manager role) runs /giveaway new with only what the banner needs (the prize, how long, how many winners).
That opens a preview with buttons: prizes and time, rules, banner (draw it again with other words), hosts, required roles, ping, channel.
Nothing posts until Start. People enter with a button. When the time is up the bot draws the winners.
What a giveaway can have:
  - a prize per place ("1: 2K Robux + Nitro", "2-5: 2K Robux"); by default the prize is split over the winners (10K Robux, 5 winners = 2K each), shown as a podium
  - required roles (any / all), blacklisted roles, a minimum time in the server, bonus entries for roles (Booster +2, Donator +3...)
  - a minimum number of invites (invites that count = the person is still here and has the Verified role, see invites.py)
  - every invite as one more entry (with an optional cap)
  - a claim window: winners press Claim in time or their place is drawn again
  - hosts: whoever the admin picks, not only the person who ran the command
Everything is checked again when the giveaway ends, so someone who left, lost the role or got un-verified is skipped.
The draw is seeded (the seed is shown), so it can be re-run to prove it was fair."""
import asyncio
import json
import random
import re
import secrets
from datetime import datetime, timezone

import discord
from discord import ui

from . import invites
from .banner import banner_file
from .botnews import code_chip
from .components import NO_MENTIONS, FormModal
from .ctx import ctx, fetch_channel
from .db import add_timer, all_, cancel_timers, create_pending, db, del_pending, get_pending, now, one, run, set_pending
from .env import cfg
from .perms import level

NL = chr(10)
SMALL = discord.SeparatorSpacing.small
MAX_WINNERS = 50
MAX_ROUNDS = 3  # a place whose winner never claims is drawn again this many times
BANNER = 'giveaway.png'
PINGS = [('none', 'No ping', 'The card appears silently'), ('giveaways', '@Giveaways', 'Only people who want giveaways'), ('everyone', '@everyone', 'Everyone in the server')]
db.executescript("""
CREATE TABLE IF NOT EXISTS giveaways(
  id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT, message_id TEXT, host_id TEXT, title TEXT, config TEXT,
  status TEXT NOT NULL DEFAULT 'running', ends_at INTEGER, created_at INTEGER, result TEXT);
CREATE TABLE IF NOT EXISTS giveaway_entries(gid INTEGER NOT NULL, user_id TEXT NOT NULL, at INTEGER, PRIMARY KEY(gid, user_id));
""")


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
    if c['req_roles']:
        have = [r for r in c['req_roles'] if _has(member, r)]
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
    if c.get('bonus_best') and held:  # the bonuses do not stack: only the highest one counts
        held = [max(held, key=lambda h: h[1])]
    rows += [(_role(rid), n) for rid, n in held]
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


# ---- the card (community look: banner, short lines, real pings, no trees, no code blocks, no medal emojis) ----
def place_label(places, long=True):
    a, b = places[0], places[-1]
    if a == b:
        return f'{ordinal(a)} place' if long else ordinal(a)
    if b == a + 1:
        return f'{ordinal(a)} and {ordinal(b)} place' if long else f'{ordinal(a)}–{ordinal(b)}'
    return f'{ordinal(a)} to {ordinal(b)} place' if long else f'{ordinal(a)}–{ordinal(b)}'


def prize_block(prizes):
    """The podium: the first prize as a heading, the others in bold under it, each with its place in small letters."""
    lines = []
    for k, (pl, p) in enumerate(groups(prizes)):
        lines.append(f"{'### ' if k == 0 else '**'}{' + '.join(p)}{'' if k == 0 else '**'}")
        lines.append(f'-# {place_label(pl)}')
    return NL.join(lines)


def required_block(c):
    rows = [f'✅ {_role(cfg.verified_role)}']
    if c['req_roles']:
        rows.append('🎭 ' + (' and ' if c['req_mode'] == 'all' else ' or ').join(_role(r) for r in c['req_roles']))
    if c['min_invites']:
        rows.append(f"📨 **{c['min_invites']}** invite{'s' if c['min_invites'] != 1 else ''} for your first entry")
    if c['min_days']:
        rows.append(f"🕓 **{c['min_days']}+** days in the server")
    if c['blacklist']:
        rows.append('🚫 Not for ' + ' '.join(_role(r) for r in c['blacklist']))
    return '**Required**' + NL + NL.join(rows)


def bonus_block(c):
    rows = [f"⭐ {_role(r)} **+{n}** {'entry' if n == 1 else 'entries'}" for r, n in c['bonus'].items()]
    if c['invite_entries']:
        rows.append('➕ **+1** entry for every invite' + (f" · max **{c['invite_cap']}** entries in total" if c['invite_cap'] else ''))
    if rows and c.get('bonus_best') and len(c['bonus']) > 1:
        rows.append('-# Role bonuses do not stack: only your highest counts')
    return '**Bonus entries**' + NL + NL.join(rows) if rows else None


def winners_block(res, c):
    mark = {'claimed': ' ✅', 'pending': ' ⏳' if c['claim_hours'] else ''}
    rows = [f"**{ordinal(w['place'])}** · <@{w['user']}> · {' + '.join(w['prizes'])}{mark.get(w['state'], '')}" for w in res['winners']]
    return '**Winners**' + NL + (NL.join(rows) or 'Nobody could win: no one who entered still qualified.')


def banner_for(g, ended=False):
    """The banner file of a giveaway: its own words, or the prize with the winners and the end date. Drawn in code, no model is used."""
    c, b = g['config'], g['config'].get('banner') or {}
    n = len(c['prizes'])
    day = datetime.fromtimestamp(g['ends_at'] / 1000, timezone.utc).strftime('%b %d').replace(' 0', ' ')
    sub = b.get('sub') or f"{n} {'winner' if n == 1 else 'winners'} · ends {day}"
    if ended:
        return banner_file(b.get('headline') or g['title'], 'Winners below', 'GIVEAWAY ENDED', filename=BANNER)
    return banner_file(b.get('headline') or g['title'], sub, b.get('pill') or 'ENTER BELOW', filename=BANNER)


def card_items(g, gid=None, status='running', count=0):
    """The giveaway as a card (a Container). status running | ended | draft. The banner is the message's attachment BANNER.
    A draft (the preview, a mockup) has the same buttons, switched to "only a mockup" ids."""
    c = g['config']
    n, ends = len(c['prizes']), g['ends_at'] // 1000
    when = f'ended <t:{ends}:f>' if status == 'ended' else f'ends <t:{ends}:f>'
    items = [ui.MediaGallery(discord.MediaGalleryItem(f'attachment://{BANNER}')),
             ui.TextDisplay(f"**{n}** {'winner' if n == 1 else 'winners'}  ·  **{count}** entered  ·  {when}"),
             ui.Separator(visible=True, spacing=SMALL)]
    if status == 'ended':
        items.append(ui.TextDisplay(winners_block(g['result'], c)))
    else:
        items.append(ui.TextDisplay(prize_block(c['prizes'])))
        items.append(ui.TextDisplay(required_block(c)))
        if bonus := bonus_block(c):
            items.append(ui.TextDisplay(bonus))
    items.append(ui.Separator(visible=True, spacing=SMALL))
    foot = [f"-# Hosted by: {' '.join(f'<@{h}>' for h in hosts_of(g))}"]
    if c['claim_hours']:
        foot.append(f"-# Winners claim within {c['claim_hours']}h")
    if status == 'ended':
        foot.append(f"-# Fair draw · seed `{g['result']['seeds'][0]}` · {g['result']['entries']} entries counted")
    elif c['min_invites'] or c['invite_entries']:
        foot.append('-# ' + code_chip('/invites stats · see how many of your invites count'))
    items.append(ui.TextDisplay(NL.join(foot)))
    if status in ('running', 'draft'):
        enter, mine = (f'gw:enter:{gid}', f'gw:mine:{gid}') if gid else ('mock:enter', 'mock:mine')
        items.append(ui.ActionRow(ui.Button(custom_id=enter, label='Enter giveaway', style=discord.ButtonStyle.success, emoji='🎉'),
                                  ui.Button(custom_id=mine, label='My entries', style=discord.ButtonStyle.secondary, emoji='🎟️')))
    if status == 'ended' and gid and c['claim_hours'] and any(w['state'] == 'pending' for w in g['result']['winners']):
        items.append(ui.ActionRow(ui.Button(custom_id=f'gw:claim:{gid}', label='Claim prize', style=discord.ButtonStyle.primary, emoji='🏆')))
    return ui.Container(*items)


def ping_text(c):
    return {'giveaways': f'<@&{cfg.giveaways_role}>', 'everyone': '@everyone'}.get(c.get('ping'))


def container(g, gid=None, status='running', count=0):
    """The card as a message view. The ping, when there is one, sits right above the card, outside it."""
    view = ui.LayoutView()
    if p := ping_text(g['config']):
        view.add_item(ui.TextDisplay(p))
    view.add_item(card_items(g, gid, status, count))
    return view


def names_only(g):
    """The mentions an edit may carry. An edit must keep the card's ping allowed (@everyone or the role), or Discord strips the mention from the message and
    nobody who comes later sees it as a ping. Hosts are allowed so their names show. A giveaway posted before this rule (no 'v': 2) keeps users only:
    allowing its ping now would add the mention again and ping the server a second time."""
    c = g['config']
    ping = c.get('ping') if c.get('v') == 2 else None
    return discord.AllowedMentions(everyone=ping == 'everyone', roles=[discord.Object(id=int(cfg.giveaways_role))] if ping == 'giveaways' else False,
                                   users=[discord.Object(id=int(h)) for h in hosts_of(g)], replied_user=False)


def text_view(text):
    view = ui.LayoutView()
    view.add_item(ui.TextDisplay(text[:3900]))
    return view


# ---- stored giveaways ----
def _g(gid):
    r = one('SELECT * FROM giveaways WHERE id=?', gid)
    if not r:
        return None
    r['config'] = json.loads(r['config'])
    r['result'] = json.loads(r['result']) if r['result'] else None
    return r


def _count(gid):
    return one('SELECT COUNT(*) AS n FROM giveaway_entries WHERE gid=?', gid)['n']


async def _message(g):
    ch = await fetch_channel(g['channel_id'])
    try:
        return await ch.fetch_message(int(g['message_id'])) if ch else None
    except Exception:
        return None


async def redraw(gid):
    g = _g(gid)
    if not g:
        return
    msg = await _message(g)
    if not msg:
        return
    status = 'ended' if g['status'] == 'ended' else 'running'
    # the banner is uploaded again with every edit: a card that points at attachment://giveaway.png needs the file in the same request
    count = g['result']['eligible'] if status == 'ended' and g['result'] else len(valid_pool(g))  # "entered" counts the people who have at least one entry, not everyone who pressed Enter
    await msg.edit(view=container(g, gid, status, count), attachments=[banner_for(g, ended=status == 'ended')], allowed_mentions=names_only(g))


_pending_redraw = set()


def schedule_redraw(gid):
    """The entry count on the card, refreshed a few seconds after the last entry (many people enter at once)."""
    if gid in _pending_redraw:
        return
    _pending_redraw.add(gid)

    async def go():
        await asyncio.sleep(8)
        _pending_redraw.discard(gid)
        try:
            await redraw(gid)
        except Exception as e:
            print('giveaway redraw', repr(e)[:120])

    asyncio.ensure_future(go())


# ---- entering ----
def _need_line(member, c):
    short = short_of(member, c)
    return f"You get your first entry at **{short[0]}** invites. **{short[1]}** count so far. Invites count if the person is still here and verified; invites from before tracking count too. See `/invites stats`." if short else None


def _entries_view(g, member, headline):
    """What only you see: your entries and where each one comes from, with Leave while the giveaway runs."""
    total, rows = entries_for(member, g['config'])
    if total == 0:
        lines = [f'**{headline}**', _need_line(member, g['config']) or 'You have no entries.', '', '-# It is checked again when the giveaway ends.']
    else:
        lines = [f"**{headline}**"] + [f"{'+' if n > 0 else '−'}{abs(n)} · {what}" for what, n in rows] + ['', f"-# It is checked again when the giveaway ends."]
    ok, why = eligible(member, g['config'])
    if not ok:
        lines = [f'⚠️ You no longer qualify: {why}', '-# You will be skipped at the draw unless that changes.']
    view = ui.LayoutView()
    view.add_item(ui.TextDisplay(NL.join(lines)))
    if g['status'] == 'running':
        view.add_item(ui.ActionRow(ui.Button(custom_id=f"gw:leave:{g['id']}", label='Leave giveaway', style=discord.ButtonStyle.danger)))
    return view


def _entry_word(total):
    return f"{total} {'entry' if total == 1 else 'entries'}"


async def enter(i, gid):
    g = _g(gid)
    if not g or g['status'] != 'running':
        return await i.response.send_message('This giveaway is over.', ephemeral=True)
    ok, why = eligible(i.user, g['config'])
    if not ok:
        return await i.response.send_message(why, ephemeral=True)
    total = entries_for(i.user, g['config'])[0]
    joined = bool(one('SELECT 1 FROM giveaway_entries WHERE gid=? AND user_id=?', gid, str(i.user.id)))
    if not joined:
        run('INSERT OR IGNORE INTO giveaway_entries(gid,user_id,at) VALUES(?,?,?)', gid, str(i.user.id), now())
        schedule_redraw(gid)
    await i.response.send_message(view=_entries_view(g, i.user, f"{'You are in with' if not joined else 'You are already in with'} {_entry_word(total)}"), ephemeral=True)


async def mine(i, gid):
    """The My entries button: whether you are in, and how many entries you have."""
    g = _g(gid)
    if not g or g['status'] == 'cancelled':
        return await i.response.send_message('This giveaway is over.', ephemeral=True)
    if one('SELECT 1 FROM giveaway_entries WHERE gid=? AND user_id=?', gid, str(i.user.id)):
        total = entries_for(i.user, g['config'])[0]
        return await i.response.send_message(view=_entries_view(g, i.user, f'You have {_entry_word(total)}'), ephemeral=True)
    ok, why = eligible(i.user, g['config'])
    view = ui.LayoutView()
    if g['status'] != 'running':
        view.add_item(ui.TextDisplay('You did not enter this giveaway.'))
    elif ok:
        would = entries_for(i.user, g['config'])[0]
        view.add_item(ui.TextDisplay(f"You have not entered yet. You would get **{_entry_word(would)}**." + (f'{NL}{_need_line(i.user, g["config"])}' if not would else '')))
        view.add_item(ui.ActionRow(ui.Button(custom_id=f'gw:enter:{gid}', label='Enter giveaway', style=discord.ButtonStyle.success, emoji='🎉')))
    else:
        view.add_item(ui.TextDisplay(f'You have not entered, and you cannot yet: {why}'))
    await i.response.send_message(view=view, ephemeral=True)


async def leave(i, gid):
    run('DELETE FROM giveaway_entries WHERE gid=? AND user_id=?', gid, str(i.user.id))
    schedule_redraw(gid)
    await i.response.edit_message(view=text_view('You left the giveaway. Press Enter giveaway to join again.'))


# ---- the draw ----
def valid_pool(g):
    """[(user id, entries)] of everyone who entered, still qualifies and has at least one entry right now."""
    out = []
    for r in all_('SELECT user_id FROM giveaway_entries WHERE gid=? ORDER BY user_id', g['id']):
        m = ctx.guild.get_member(int(r['user_id']))
        ok, _ = eligible(m, g['config'])
        total = entries_for(m, g['config'])[0] if ok else 0
        if total > 0:  # below the invite minimum = 0 entries = not in the draw
            out.append((r['user_id'], total))
    return out


async def _pool(g):
    return valid_pool(g)


def draw(pool, n, rng):
    pool, out = list(pool), []
    while pool and len(out) < n:
        total = sum(w for _, w in pool)
        r, acc = rng.uniform(0, total), 0
        for k, (u, w) in enumerate(pool):
            acc += w
            if r <= acc or k == len(pool) - 1:
                out.append(u)
                pool.pop(k)
                break
    return out


async def _fill(g, places, rnd):
    """Draws a winner for each of these places (1-based), never someone who already won or was dropped."""
    res, c = g['result'], g['config']
    taken = {w['user'] for w in res['winners']} | set(res['history'])
    pool = [(u, w) for u, w in await _pool(g) if u not in taken]
    seed = secrets.token_hex(8)
    res['seeds'].append(seed)
    for place, uid in zip(places, draw(pool, len(places), random.Random(seed))):
        res['winners'].append({'place': place, 'user': uid, 'prizes': c['prizes'][place - 1], 'state': 'pending', 'round': rnd})
    res['winners'].sort(key=lambda w: w['place'])
    return res


def _save(g):
    run('UPDATE giveaways SET status=?, result=? WHERE id=?', g['status'], json.dumps(g['result']) if g['result'] else None, g['id'])


async def _announce(g, new_winners, header):
    """Pings the winners (this is the one real ping a giveaway sends), DMs them, and starts the claim clock."""
    ch = await fetch_channel(g['channel_id'])
    msg = await _message(g)
    c = g['config']
    ids = [w['user'] for w in new_winners]
    if ids and ch:
        claim = f" Press **Claim prize** on the giveaway within **{c['claim_hours']}h** or your place is drawn again." if c['claim_hours'] else ' A host will contact you.'
        await ch.send(f"{header} {' '.join(f'<@{u}>' for u in ids)}{NL}You won **{g['title']}**.{claim}",
                      reference=msg.to_reference(fail_if_not_exists=False) if msg else None,
                      allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=int(u)) for u in ids], roles=False, everyone=False))
    for w in new_winners:
        m = ctx.guild.get_member(int(w['user']))
        try:
            await m.send(f"🎉 You won **{g['title']}** in **{ctx.guild.name}**: {' + '.join(w['prizes'])}." + (f" Claim it within {c['claim_hours']}h: {msg.jump_url}" if c['claim_hours'] and msg else ''))
        except Exception:
            pass  # DMs closed: the ping in the channel is enough
    if c['claim_hours'] and ids:
        cancel_timers('gw_claim', g['id'])
        add_timer('gw_claim', g['id'], now() + c['claim_hours'] * 3600000)


async def _log(text):
    if cfg.devlog_id:
        try:
            await (await fetch_channel(cfg.devlog_id)).send(text, allowed_mentions=NO_MENTIONS)
        except Exception:
            pass


async def end(gid, by=None):
    """Draws the winners. Returns text for the person who ended it early, None when there was nothing to end."""
    g = _g(gid)
    if not g or g['status'] != 'running':
        return None
    cancel_timers('gw_end', gid)
    g['status'] = 'ended'
    pool = await _pool(g)
    g['result'] = {'winners': [], 'history': [], 'seeds': [], 'eligible': len(pool), 'entries': sum(w for _, w in pool)}
    await _fill(g, list(range(1, len(g['config']['prizes']) + 1)), 0)
    _save(g)
    await redraw(gid)
    await _announce(g, g['result']['winners'], '🎉 Congratulations')
    await _log(f"🎁 Giveaway **{g['title']}** (#{gid}) ended{f' by <@{by}>' if by else ''}: {len(g['result']['winners'])} winner(s) from {g['result']['eligible']} who qualified ({g['result']['entries']} entries). Seed `{g['result']['seeds'][0]}`.")
    return f"Ended. {len(g['result']['winners'])} winner(s) drawn."


async def claim_expired(gid):
    """The claim window closed: places nobody claimed are drawn again (up to MAX_ROUNDS times)."""
    g = _g(gid)
    if not g or g['status'] != 'ended' or not g['result']:
        return
    res = g['result']
    late = [w for w in res['winners'] if w['state'] == 'pending']
    if not late:
        return
    again = [w for w in late if w.get('round', 0) < MAX_ROUNDS]
    for w in late:
        res['history'].append(w['user'])
        res['winners'].remove(w)
    before = {w['place'] for w in res['winners']}
    await _fill(g, [w['place'] for w in again], max(w.get('round', 0) for w in again) + 1 if again else 0)
    _save(g)
    await redraw(gid)
    await _announce(g, [w for w in res['winners'] if w['place'] not in before], '🎉 A place was drawn again:')


async def reroll(gid, place=None):
    g = _g(gid)
    if not g or g['status'] != 'ended' or not g['result']:
        return 'That giveaway has not ended yet.'
    res = g['result']
    drop = [w for w in res['winners'] if w['state'] != 'claimed' and (place is None or w['place'] == place)]
    if place and not drop:
        return f'{ordinal(place)} place is already claimed or has no winner. Nothing to draw again.'
    if not drop:
        return 'Every winner already claimed.'
    for w in drop:
        res['history'].append(w['user'])
        res['winners'].remove(w)
    before = {w['place'] for w in res['winners']}
    await _fill(g, [w['place'] for w in drop], 1 + max(w.get('round', 0) for w in drop))
    _save(g)
    await redraw(gid)
    new = [w for w in res['winners'] if w['place'] not in before]
    await _announce(g, new, '🎉 New winner:')
    await _log(f"🎁 Giveaway **{g['title']}** (#{gid}) rerolled {len(drop)} place(s). Seed `{res['seeds'][-1]}`.")
    return f'Drew {len(new)} new winner(s).' if new else 'Nobody else qualifies, so those places stay empty.'


async def claim(i, gid):
    g = _g(gid)
    if not g or g['status'] != 'ended' or not g['result']:
        return await i.response.send_message('This giveaway is not open for claims.', ephemeral=True)
    mine = [w for w in g['result']['winners'] if w['user'] == str(i.user.id)]
    if not mine:
        return await i.response.send_message('You are not a winner of this giveaway.', ephemeral=True)
    if all(w['state'] == 'claimed' for w in mine):
        return await i.response.send_message('You already claimed it. A host will contact you.', ephemeral=True)
    for w in mine:
        w['state'] = 'claimed'
    _save(g)
    await i.response.send_message(f"🏆 Claimed: {' · '.join(' + '.join(w['prizes']) for w in mine)}. A host will contact you.", ephemeral=True)
    await redraw(gid)
    for h in hosts_of(g):
        try:
            await ctx.guild.get_member(int(h)).send(f"🏆 **{i.user.display_name}** claimed {ordinal(mine[0]['place'])} place in **{g['title']}**: {' + '.join(mine[0]['prizes'])}.")
        except Exception:
            pass


async def cancel(gid):
    g = _g(gid)
    if not g or g['status'] != 'running':
        return 'That giveaway is not running.'
    run("UPDATE giveaways SET status='cancelled' WHERE id=?", gid)
    cancel_timers('gw_end', gid)
    msg = await _message(g)
    if msg:
        await msg.edit(view=text_view(f"🚫 **CANCELLED**{NL}{g['title']}"), attachments=[], allowed_mentions=NO_MENTIONS)
    return 'Cancelled.'


# ---- the preview draft ----
FIELDS = ('prizes', 'req_roles', 'req_mode', 'blacklist', 'bonus', 'min_invites', 'invite_entries', 'invite_cap', 'min_days', 'claim_hours', 'ping', 'bonus_best',
          'hosts', 'banner')


def new_draft(user_id, channel_id, prize, seconds, winners):
    return create_pending({'kind': 'giveaway', 'user': str(user_id), 'channel': str(channel_id), 'title': f'{prize} giveaway'[:100], 'seconds': seconds,
                           'prizes': split_prize(prize, winners), 'req_roles': [], 'req_mode': 'any', 'blacklist': [], 'bonus': {},
                           'min_invites': 0, 'invite_entries': False, 'invite_cap': 0, 'min_days': 0, 'claim_hours': 0, 'ping': 'none', 'bonus_best': False,
                           'hosts': [str(user_id)], 'banner': {'headline': prize}})


def _config(d):
    return {k: d[k] for k in FIELDS if k in d}


def payload(pid):
    d = get_pending(pid)
    g = {'title': d['title'], 'config': _config(d), 'ends_at': now() + d['seconds'] * 1000, 'host_id': d['user']}
    view = ui.LayoutView()
    view.add_item(ui.TextDisplay(f"### 🧪 PREVIEW · GIVEAWAY{NL}-# Nothing is posted yet. Change what you want, then press Start. "
                                 f"It posts in <#{d['channel']}> and runs for **{fmt_duration(d['seconds'])}**."))
    if p := ping_text(g['config']):  # shown as text here; it only pings when Start is pressed
        view.add_item(ui.TextDisplay(p))
    view.add_item(card_items(g, None, 'draft', 0))
    view.add_item(ui.ActionRow(
        ui.Button(custom_id=f'gw:start:{pid}', label='Start', style=discord.ButtonStyle.success, emoji='✅'),
        ui.Button(custom_id=f'gw:edit:{pid}', label='Prizes & time', style=discord.ButtonStyle.primary, emoji='🎁'),
        ui.Button(custom_id=f'gw:rules:{pid}', label='Rules', style=discord.ButtonStyle.primary, emoji='⚙️'),
        ui.Button(custom_id=f'gw:banner:{pid}', label='Banner', style=discord.ButtonStyle.primary, emoji='🖼️'),
        ui.Button(custom_id=f'gw:cancel:{pid}', label='Cancel', style=discord.ButtonStyle.danger)))
    hosts = [m for m in (ctx.guild.get_member(int(h)) for h in d['hosts']) if m]
    view.add_item(ui.ActionRow(ui.UserSelect(custom_id=f'gw:hosts:{pid}', placeholder='Hosted by (pick up to 5)', min_values=1, max_values=5, default_values=hosts)))
    roles = [r for r in (ctx.guild.get_role(int(x)) for x in d['req_roles']) if r]
    view.add_item(ui.ActionRow(ui.RoleSelect(custom_id=f'gw:roles:{pid}', placeholder='Required roles (empty = everyone verified)', min_values=0, max_values=5, default_values=roles)))
    view.add_item(ui.ActionRow(
        ui.Button(custom_id=f'gw:mode:{pid}', label=f"Roles needed: {'all of them' if d['req_mode'] == 'all' else 'any one'}", style=discord.ButtonStyle.secondary, emoji='🎭'),
        ui.Button(custom_id=f'gw:inv:{pid}', label=f"Invites as entries: {'on' if d['invite_entries'] else 'off'}", style=discord.ButtonStyle.secondary, emoji='➕'),
        ui.Button(custom_id=f'gw:best:{pid}', label=f"Role bonuses: {'highest only' if d.get('bonus_best') else 'add up'}", style=discord.ButtonStyle.secondary, emoji='⭐')))
    view.add_item(ui.ActionRow(ui.Select(custom_id=f'gw:ping:{pid}', placeholder='Who gets pinged', options=[
        discord.SelectOption(label=n, value=k, description=desc, default=k == d['ping']) for k, n, desc in PINGS])))
    ch = ctx.guild.get_channel(int(d['channel']))
    view.add_item(ui.ActionRow(ui.ChannelSelect(custom_id=f'gw:channel:{pid}', placeholder='Where it posts', min_values=1, max_values=1,
                                                channel_types=[discord.ChannelType.text, discord.ChannelType.news], default_values=[ch] if ch else [])))
    return {'view': view, 'attachments': [banner_for(g)], 'allowed_mentions': NO_MENTIONS}


async def _guard(i, pid):
    d = get_pending(pid)
    if not d:
        await i.response.edit_message(view=text_view('This draft is gone.'), attachments=[])
        return None
    if str(i.user.id) != d['user'] and level(i.user) != 'admin':
        await i.response.send_message('This draft belongs to someone else.', ephemeral=True)
        return None
    return d


def _spec(id_, label, value='', style='short', mx=100, placeholder=None, required=False):
    return {'id': id_, 'label': label, 'style': style, 'required': required, 'max': mx, 'value': str(value or '')[:mx], 'placeholder': placeholder}


async def on_component(i, parts):
    """Every button and dropdown of a giveaway: gw:<action>:<draft or giveaway id>."""
    action, ident = parts[1], int(parts[2])
    if action == 'enter':
        return await enter(i, ident)
    if action == 'leave':
        return await leave(i, ident)
    if action == 'claim':
        return await claim(i, ident)
    if action == 'mine':
        return await mine(i, ident)
    if not can_run(i.user):
        return await i.response.send_message('Only admins and the Giveaway Manager role can run giveaways.', ephemeral=True)
    d = await _guard(i, ident)
    if not d:
        return
    pid, values = ident, [str(v) for v in (i.data.get('values') or [])]
    if action == 'cancel':
        del_pending(pid)
        return await i.response.edit_message(view=text_view('🗑️ **CANCELLED**\nNothing was posted.'), attachments=[])
    if action == 'edit':
        bonus = NL.join(f"{ctx.guild.get_role(int(r)).name}: {n}" for r, n in d['bonus'].items() if ctx.guild.get_role(int(r)))
        return await i.response.send_modal(FormModal(f'gwp:{pid}', 'Prizes & time', [
            _spec('title', 'Name (shown in the winner messages)', d['title'], required=True),
            _spec('prizes', 'Prizes per place', prize_text_of(d['prizes']), 'paragraph', 800, '1: 2K Robux + Nitro\n2-5: 2K Robux'),
            _spec('duration', 'How long (3d, 12h, 1d 6h)', fmt_duration(d['seconds']), required=True),
            _spec('winners', 'Winners (splits the banner prize again)', len(d['prizes']), mx=3),
            _spec('bonus', 'Bonus entries for roles (Booster: 2)', bonus, 'paragraph', 400, 'Booster: 2\nDonator: 3')]))
    if action == 'banner':
        b = d['banner']
        return await i.response.send_modal(FormModal(f'gwb:{pid}', 'Banner', [
            _spec('headline', 'Big text (the prize)', b.get('headline'), required=True, mx=40),
            _spec('sub', 'Small line (empty = winners and end date)', b.get('sub'), mx=60),
            _spec('pill', 'Text in the outlined pill', b.get('pill') or 'ENTER BELOW', mx=30)]))
    if action == 'rules':
        black = ', '.join(ctx.guild.get_role(int(r)).name for r in d['blacklist'] if ctx.guild.get_role(int(r)))
        inv = (str(d['invite_cap']) if d['invite_cap'] else 'yes') if d['invite_entries'] else 'no'
        return await i.response.send_modal(FormModal(f'gwr:{pid}', 'Rules', [
            _spec('min_invites', 'Minimum invites to enter (0 = none)', d['min_invites'], mx=4),
            _spec('invite_entries', 'Invites as entries? no/yes/max total entries', inv, mx=6),
            _spec('min_days', 'Minimum days in the server (0 = none)', d['min_days'], mx=4),
            _spec('claim_hours', 'Winners must claim within hours (0 = no claim)', d['claim_hours'], mx=4),
            _spec('blacklist', 'Roles that cannot enter (names, comma)', black, mx=200)]))
    if action == 'start':
        return await start(i, pid, d)
    if action == 'mode':
        d['req_mode'] = 'any' if d['req_mode'] == 'all' else 'all'
    elif action == 'inv':
        d['invite_entries'] = not d['invite_entries']
    elif action == 'best':
        d['bonus_best'] = not d.get('bonus_best')
    elif action == 'roles':
        d['req_roles'] = values
    elif action == 'hosts':
        d['hosts'] = values or d['hosts']
    elif action == 'channel':
        d['channel'] = values[0] if values else d['channel']
    elif action == 'ping':
        d['ping'] = values[0] if values else 'none'
    set_pending(pid, d)
    return await i.response.edit_message(**payload(pid))


async def on_modal(i, kind, pid, f):
    d = get_pending(pid)
    if not d:
        return await i.response.send_message('This draft is gone.', ephemeral=True)
    if str(i.user.id) != d['user'] and level(i.user) != 'admin':
        return await i.response.send_message('This draft belongs to someone else.', ephemeral=True)
    f = {k: (v or '').strip() for k, v in f.items()}
    num = lambda k, hi=100000: max(0, min(int(re.sub(r'\D', '', f.get(k, '')) or 0), hi))
    if kind == 'gwp':
        seconds = parse_duration(f.get('duration'))
        if seconds < 60:
            return await i.response.send_message('How long? Write it like `3d`, `12h` or `1d 6h` (at least 1 minute).', ephemeral=True)
        winners = num('winners', MAX_WINNERS) or len(d['prizes'])
        if f.get('prizes', '') == prize_text_of(d['prizes']) and winners != len(d['prizes']):  # only the winner count changed: split the banner prize again
            prizes = split_prize(d['banner'].get('headline') or d['title'], winners)
        else:
            prizes, err = parse_prizes(f.get('prizes'), winners)
            if err:
                return await i.response.send_message(err, ephemeral=True)
        bonus, bad = parse_bonus(f.get('bonus'))
        if bad:
            return await i.response.send_message('I could not read these bonus lines: ' + '; '.join(f'`{b}`' for b in bad[:4]) + '. Write them like `Booster: 2` with the exact role name.', ephemeral=True)
        d.update(title=f.get('title')[:100] or d['title'], seconds=min(seconds, 60 * 86400), prizes=prizes, bonus=bonus)
    elif kind == 'gwb':
        d['banner'] = {'headline': f.get('headline')[:40] or d['banner'].get('headline'), 'sub': f.get('sub')[:60], 'pill': f.get('pill')[:30] or 'ENTER BELOW'}
    else:
        ids, unknown = find_roles(f.get('blacklist'))
        if unknown:
            return await i.response.send_message('I do not know these roles: ' + ', '.join(f'`{u}`' for u in unknown[:5]), ephemeral=True)
        inv = f.get('invite_entries', 'no').lower()
        d.update(min_invites=num('min_invites', 1000), min_days=num('min_days', 3650), claim_hours=num('claim_hours', 720), blacklist=ids,
                 invite_entries=inv not in ('', 'no', 'n', 'off', '0', 'false'), invite_cap=int(inv) if inv.isdigit() else 0)
    set_pending(pid, d)
    await i.response.edit_message(**payload(pid))


async def start(i, pid, d):
    ch = await fetch_channel(d['channel'])
    if not ch:
        return await i.response.send_message('I cannot find that channel any more.', ephemeral=True)
    await i.response.defer()
    ends = now() + d['seconds'] * 1000
    gid = run('INSERT INTO giveaways(channel_id,message_id,host_id,title,config,status,ends_at,created_at) VALUES(?,?,?,?,?,?,?,?)',
              str(ch.id), '0', d['user'], d['title'], json.dumps({**_config(d), 'v': 2}), 'running', ends, now()).lastrowid
    g = _g(gid)
    # one send with the ping and the hosts allowed: the ping (if any) goes out now, the hosts are told they host. Later edits keep the same mentions (names_only), so nobody is pinged again.
    sent = await ch.send(view=container(g, gid, 'running', 0), files=[banner_for(g)], allowed_mentions=names_only(g))
    run('UPDATE giveaways SET message_id=? WHERE id=?', str(sent.id), gid)
    add_timer('gw_end', gid, ends)
    del_pending(pid)
    await _log(f"🎁 Giveaway **{g['title']}** (#{gid}) started by <@{d['user']}> in <#{ch.id}>: {sent.jump_url}")
    await i.edit_original_response(view=text_view(f'✅ **STARTED**{NL}{sent.jump_url}'), attachments=[])


# ---- the slash command ----
def _pick(value):
    m = re.search(r'\d+', str(value or ''))
    return int(m[0]) if m else None


async def autocomplete(i, fvalue):
    q = str(fvalue or '').lower()
    rows = all_("SELECT id,title,status FROM giveaways WHERE status!='cancelled' ORDER BY id DESC LIMIT 40")
    return [{'name': f"#{r['id']} {r['title']} · {r['status']}"[:100], 'value': str(r['id'])} for r in rows if q in f"{r['id']} {r['title']}".lower()][:25]


async def command_giveaway(i, sub, opts):
    if not can_run(i.user):
        return await i.response.send_message('Only admins and the Giveaway Manager role can run giveaways.', ephemeral=True)
    if sub == 'new':
        seconds = parse_duration(opts.get('duration'))
        if seconds < 60:
            return await i.response.send_message('How long? Write it like `3d`, `12h` or `1d 6h`.', ephemeral=True)
        await i.response.defer(ephemeral=True)
        pid = new_draft(i.user.id, i.channel_id, str(opts['prize']).strip()[:40], min(seconds, 60 * 86400), min(int(opts.get('winners') or 1), MAX_WINNERS))
        return await i.edit_original_response(**payload(pid))
    if sub == 'list':
        rows = all_("SELECT * FROM giveaways WHERE status IN ('running','ended') ORDER BY id DESC LIMIT 10")
        lines = [f"#{r['id']} · **{r['title']}** · {r['status']} · <#{r['channel_id']}> · {len(valid_pool(_g(r['id']))) if r['status'] == 'running' else (_g(r['id'])['result'] or {}).get('eligible', 0)} entered" + (f" · ends <t:{r['ends_at'] // 1000}:f>" if r['status'] == 'running' else '') for r in rows]
        return await i.response.send_message('\n'.join(lines) or 'No giveaways yet.', ephemeral=True, allowed_mentions=NO_MENTIONS)
    gid = _pick(opts.get('giveaway'))
    if not gid or not _g(gid):
        return await i.response.send_message('Pick a giveaway from the list.', ephemeral=True)
    await i.response.defer(ephemeral=True)
    if sub == 'end':
        text = await end(gid, by=i.user.id)
    elif sub == 'cancel':
        text = await cancel(gid)
    else:
        text = await reroll(gid, opts.get('place'))
    await i.edit_original_response(content=text or 'That giveaway is not running.')
