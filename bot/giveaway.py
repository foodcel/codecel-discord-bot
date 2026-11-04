"""/giveaway: customizable giveaways. An admin (or someone with the Giveaway Manager role) runs /giveaway new, gets a preview card with buttons
(prizes and time, rules, required roles, ping) and presses Start. People enter with a button. When the time is up the bot draws the winners.
What a giveaway can have:
  - a prize per place ("1: 2k Robux + Nitro", "2-5: 2k Robux"), or one prize for N winners
  - required roles (any / all), blacklisted roles, a minimum time in the server, bonus entries for roles (Booster +2, Donator +3...)
  - a minimum number of invites (invites that count = the person is still here and has the Verified role, see invites.py)
  - every invite as one more entry (with an optional cap)
  - a claim window: winners press Claim in time or their place is drawn again
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
from .botnews import code_chip
from .components import NO_MENTIONS, FormModal
from .ctx import ctx, fetch_channel
from .db import add_timer, all_, cancel_timers, create_pending, db, del_pending, get_pending, now, one, run, set_pending
from .env import cfg
from .perms import level
from .pngs import with_strip

NL = chr(10)
SMALL = discord.SeparatorSpacing.small
MAX_WINNERS = 50
MAX_ROUNDS = 3  # a place whose winner never claims is drawn again this many times
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


def parse_prizes(text, winners):
    """([prizes of place 1, place 2...], error). Lines like "1: 2k Robux + Nitro" or "2-5: 2k Robux"; a line with no place is the prize of every winner."""
    places, loose = {}, []
    for line in str(text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^#?(\d+)(?:st|nd|rd|th)?(?:\s*[-–]\s*#?(\d+)(?:st|nd|rd|th)?)?(?:\s*[:=]\s*|\s+[-–]\s+)(.+)$', line, re.I)
        prizes = lambda s: [p.strip() for p in re.split(r'\s*\+\s*|\s*&\s*', s) if p.strip()]
        if m:
            for k in range(int(m[1]), int(m[2] or m[1]) + 1):
                places[k] = prizes(m[3])
        else:
            loose.append(prizes(line))
    if places:
        top = max(places)
        if top > MAX_WINNERS:
            return [], f'At most {MAX_WINNERS} winners.'
        missing = [k for k in range(1, top + 1) if k not in places]
        if missing:
            return [], f"Place {ordinal(missing[0])} has no prize. Write a line for every place, like `1: 2k Robux` or `2-5: 2k Robux`."
        return [places[k] for k in range(1, top + 1)], None
    if not loose:
        return [], 'Write the prizes: `1: 2k Robux + Nitro` per place, or one line for a prize every winner gets.'
    n = max(1, min(MAX_WINNERS, winners or 1))
    return [[p for line in loose for p in line] for _ in range(n)], None


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


# ---- who may enter, and how many entries they get ----
def eligible(member, c):
    """(True, '') or (False, the reason in plain words)."""
    if not member:
        return False, 'You are not in the server.'
    if not _has(member, cfg.verified_role):
        return False, 'You need the **Verified** role to enter. Verify first.'
    bad = [r for r in c['blacklist'] if _has(member, r)]
    if bad:
        return False, 'Your role is not allowed in this giveaway.'
    if c['req_roles']:
        have = [r for r in c['req_roles'] if _has(member, r)]
        if (c['req_mode'] == 'all' and len(have) != len(c['req_roles'])) or (c['req_mode'] != 'all' and not have):
            need = ' and '.join(_role(r) for r in c['req_roles']) if c['req_mode'] == 'all' else ' or '.join(_role(r) for r in c['req_roles'])
            return False, f'This giveaway is for {need}.'
    if c['min_days'] and member.joined_at and (datetime.now(timezone.utc) - member.joined_at).days < c['min_days']:
        return False, f"You need to be in the server for **{c['min_days']}** days to enter."
    if c['min_invites']:
        have = invites.qualified(member.id)
        if have < c['min_invites']:
            return False, f"You need **{c['min_invites']}** invites to enter and you have **{have}**. Only people who are still here and verified count. See `/invites stats`."
    return True, ''


def entries_for(member, c):
    """(total entries, base, from roles, from invites)."""
    roles = sum(n for rid, n in c['bonus'].items() if _has(member, rid))
    inv = 0
    if c['invite_entries']:
        q = invites.qualified(member.id)
        inv = min(q, c['invite_cap']) if c['invite_cap'] else q
    return 1 + roles + inv, 1, roles, inv


# ---- the card ----
def prize_tree(prizes):
    groups = []
    for k, p in enumerate(prizes, 1):
        if groups and groups[-1][1] == p:
            groups[-1][0].append(k)
        else:
            groups.append(([k], p))
    medals = {1: '🥇', 2: '🥈', 3: '🥉'}
    rows = []
    for n, (places, p) in enumerate(groups):
        label = ordinal(places[0]) if len(places) == 1 else f'{ordinal(places[0])}–{ordinal(places[-1])}'
        rows.append(f"{'└─' if n == len(groups) - 1 else '├─'} {medals.get(places[0], '🎁') if len(places) == 1 else '🎁'} **{label}** · {' + '.join(p)}")
    return rows


def rule_lines(c):
    rows = ['✅ Have the **Verified** role']
    if c['req_roles']:
        rows.append(f"🎭 Have {(' and ' if c['req_mode'] == 'all' else ' or ').join(_role(r) for r in c['req_roles'])}")
    if c['min_invites']:
        rows.append(f"📨 At least **{c['min_invites']}** invites (still here and verified)")
    if c['min_days']:
        rows.append(f"🕓 In the server for **{c['min_days']}+** days")
    if c['blacklist']:
        rows.append(f"🚫 Not for {' '.join(_role(r) for r in c['blacklist'])}")
    for rid, n in c['bonus'].items():
        rows.append(f'⭐ {_role(rid)} · **+{n}** entries')
    if c['invite_entries']:
        rows.append('➕ Every invite is **one more entry**' + (f" (up to {c['invite_cap']})" if c['invite_cap'] else ''))
    if c['claim_hours']:
        rows.append(f"⏳ Winners claim within **{c['claim_hours']}h**")
    return [f"{'└─' if k == len(rows) - 1 else '├─'} {r}" for k, r in enumerate(rows)]


def _end_button(ends_ms):
    d = datetime.fromtimestamp(ends_ms / 1000, timezone.utc).strftime('%b %d').replace(' 0', ' ')
    return ui.Button(style=discord.ButtonStyle.secondary, label=f'Ends {d}', disabled=True, custom_id='date')


def host_name(host_id):
    m = ctx.guild.get_member(int(host_id)) if ctx.guild else None
    return m.display_name if m else 'a host'


def winner_lines(res, c):
    medals = {1: '🥇', 2: '🥈', 3: '🥉'}
    mark = {'claimed': '✅', 'pending': '⏳' if c['claim_hours'] else '🎉', 'forfeit': '❌'}
    rows = []
    for k, w in enumerate(res['winners']):
        m = ctx.guild.get_member(int(w['user']))
        rows.append(f"{'└─' if k == len(res['winners']) - 1 else '├─'} {medals.get(w['place'], '🎁')} **{ordinal(w['place'])}** · **{m.display_name if m else 'a former member'}** {mark.get(w['state'], '')} · {' + '.join(w['prizes'])}")
    return rows or ['Nobody could win: no one who entered still qualified.']


def card_items(g, gid=None, status='running', count=0):
    """The giveaway as a card: (Container, files). status running | ended | draft."""
    c = g['config']
    ends = g['ends_at']
    items = [ui.Section(f"### 🎁 {g['title']}", accessory=_end_button(ends)), ui.Separator(visible=True, spacing=SMALL)]
    if status == 'ended':
        res = g['result']
        items.append(ui.TextDisplay(f"**Winners**{NL}" + NL.join(winner_lines(res, c))))
        items.append(ui.TextDisplay(f"-# Hosted by {host_name(g['host_id'])} · {count} entered · {res['entries']} entries counted{NL}-# Fair draw · seed `{res['seeds'][0]}`"))
    else:
        items.append(ui.TextDisplay(f"**Prizes**{NL}" + NL.join(prize_tree(c['prizes']))))
        items.append(ui.TextDisplay(f"**How to enter**{NL}" + NL.join(rule_lines(c))))
        items.append(ui.TextDisplay(f"-# Hosted by {host_name(g['host_id'])} · ends <t:{ends // 1000}:f> · **{count}** entered"))
    items.append(ui.Separator(visible=True, spacing=SMALL))
    foot = ['/invites stats · your invites and what counts'] if (c['min_invites'] or c['invite_entries']) else []
    foot += ['Press Enter below to join'] if status == 'running' else []
    items.append(ui.TextDisplay(NL.join('-# ' + code_chip(x) for x in foot) or '-# 🎁 Giveaway'))
    if status == 'running' and gid:
        items.append(ui.ActionRow(ui.Button(custom_id=f'gw:enter:{gid}', label='Enter', style=discord.ButtonStyle.success, emoji='🎉')))
    if status == 'ended' and gid and c['claim_hours'] and any(w['state'] == 'pending' for w in g['result']['winners']):
        items.append(ui.ActionRow(ui.Button(custom_id=f'gw:claim:{gid}', label='Claim prize', style=discord.ButtonStyle.primary, emoji='🏆')))
    items, strip = with_strip(items)
    return ui.Container(*items), [strip]


def container(g, gid=None, status='running', count=0, ping=None):
    """The same card as a message: (view, files). The ping, when there is one, sits right above it."""
    card, files = card_items(g, gid, status, count)
    view = ui.LayoutView()
    if ping:
        view.add_item(ui.TextDisplay(ping))
    view.add_item(card)
    return view, files


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
    if msg:
        view, files = container(g, gid, g['status'] if g['status'] == 'ended' else 'running', _count(gid))
        await msg.edit(view=view, attachments=files, allowed_mentions=NO_MENTIONS)


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
async def enter(i, gid):
    g = _g(gid)
    if not g or g['status'] != 'running':
        return await i.response.send_message('This giveaway is over.', ephemeral=True)
    c = g['config']
    ok, why = eligible(i.user, c)
    if not ok:
        return await i.response.send_message(why, ephemeral=True)
    total, _, roles, inv = entries_for(i.user, c)
    detail = ' (1' + (f' + {roles} from roles' if roles else '') + (f' + {inv} from invites' if inv else '') + ')' if total > 1 else ''
    if one('SELECT 1 FROM giveaway_entries WHERE gid=? AND user_id=?', gid, str(i.user.id)):
        view = ui.LayoutView()
        view.add_item(ui.TextDisplay(f"You are already in with **{total}** {'entry' if total == 1 else 'entries'}{detail}."))
        view.add_item(ui.ActionRow(ui.Button(custom_id=f'gw:leave:{gid}', label='Leave giveaway', style=discord.ButtonStyle.danger)))
        return await i.response.send_message(view=view, ephemeral=True)
    run('INSERT OR IGNORE INTO giveaway_entries(gid,user_id,at) VALUES(?,?,?)', gid, str(i.user.id), now())
    schedule_redraw(gid)
    await i.response.send_message(f"🎉 You are in with **{total}** {'entry' if total == 1 else 'entries'}{detail}. Good luck! It is checked again when the giveaway ends.", ephemeral=True)


async def leave(i, gid):
    run('DELETE FROM giveaway_entries WHERE gid=? AND user_id=?', gid, str(i.user.id))
    schedule_redraw(gid)
    await i.response.edit_message(view=text_view('You left the giveaway.'))


# ---- the draw ----
async def _pool(g):
    """[(user id, entries)] of everyone who entered and still qualifies right now."""
    out = []
    for r in all_('SELECT user_id FROM giveaway_entries WHERE gid=? ORDER BY user_id', g['id']):
        m = ctx.guild.get_member(int(r['user_id']))
        ok, _ = eligible(m, g['config'])
        if ok:
            out.append((r['user_id'], entries_for(m, g['config'])[0]))
    return out


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


async def _log(g, text):
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
    await _log(g, f"🎁 Giveaway **{g['title']}** (#{gid}) ended{f' by <@{by}>' if by else ''}: {len(g['result']['winners'])} winner(s) from {g['result']['eligible']} who qualified ({g['result']['entries']} entries). Seed `{g['result']['seeds'][0]}`.")
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
    for w in late:
        w['state'] = 'forfeit'
    again = [w for w in late if w.get('round', 0) < MAX_ROUNDS]
    for w in late:
        res['history'].append(w['user'])
        res['winners'].remove(w)
    before = {w['place'] for w in res['winners']}
    await _fill(g, [w['place'] for w in again], max(w.get('round', 0) for w in again) + 1 if again else 0)
    _save(g)
    await redraw(gid)
    new = [w for w in res['winners'] if w['place'] not in before]
    await _announce(g, new, '🎉 A place was drawn again:')


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
    await _log(g, f"🎁 Giveaway **{g['title']}** (#{gid}) rerolled {len(drop)} place(s). Seed `{res['seeds'][-1]}`.")
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
    try:
        host = ctx.guild.get_member(int(g['host_id']))
        await host.send(f"🏆 **{i.user.display_name}** claimed {ordinal(mine[0]['place'])} place in **{g['title']}**: {' + '.join(mine[0]['prizes'])}.")
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
def new_draft(user_id, channel_id, title, seconds, winners):
    return create_pending({'kind': 'giveaway', 'user': str(user_id), 'channel': str(channel_id), 'title': title, 'seconds': seconds,
                           'winners': winners or 1, 'prize_text': '', 'prizes': [], 'req_roles': [], 'req_mode': 'any', 'blacklist': [], 'bonus': {},
                           'min_invites': 0, 'invite_entries': False, 'invite_cap': 0, 'min_days': 0, 'claim_hours': 0, 'ping': 'none'})


def _config(d):
    return {k: d[k] for k in ('prizes', 'req_roles', 'req_mode', 'blacklist', 'bonus', 'min_invites', 'invite_entries', 'invite_cap', 'min_days', 'claim_hours', 'ping')}


def payload(pid):
    d = get_pending(pid)
    problems = []
    if not d['prizes']:
        problems.append('no prizes yet (press **Prizes & time**)')
    head = (f"### 🧪 PREVIEW · GIVEAWAY{NL}-# Nothing is posted yet. Check it, change what you want, then press Start. "
            f"It posts in <#{d['channel']}> and lasts **{fmt_duration(d['seconds'])}**." + (f"{NL}⚠️ Still missing: {', '.join(problems)}." if problems else ''))
    view = ui.LayoutView()
    view.add_item(ui.TextDisplay(head))
    g = {'title': d['title'], 'config': _config(d), 'ends_at': now() + d['seconds'] * 1000, 'host_id': d['user']}
    if d['prizes']:
        card, files = card_items(g, None, 'draft', 0)
        view.add_item(card)
    else:
        files = []
    view.add_item(ui.Separator())
    view.add_item(ui.ActionRow(
        ui.Button(custom_id=f"gw:start:{pid}", label='Start', style=discord.ButtonStyle.success, emoji='✅', disabled=bool(problems)),
        ui.Button(custom_id=f'gw:edit:{pid}', label='Prizes & time', style=discord.ButtonStyle.primary, emoji='🎁'),
        ui.Button(custom_id=f'gw:rules:{pid}', label='Rules', style=discord.ButtonStyle.primary, emoji='⚙️'),
        ui.Button(custom_id=f'gw:cancel:{pid}', label='Cancel', style=discord.ButtonStyle.danger)))
    roles = [r for r in (ctx.guild.get_role(int(x)) for x in d['req_roles']) if r]
    view.add_item(ui.ActionRow(ui.RoleSelect(custom_id=f'gw:roles:{pid}', placeholder='Required roles (leave empty for everyone verified)', min_values=0, max_values=5, default_values=roles)))
    view.add_item(ui.ActionRow(
        ui.Button(custom_id=f'gw:mode:{pid}', label=f"Required roles: {'all of them' if d['req_mode'] == 'all' else 'any one of them'}", style=discord.ButtonStyle.secondary, emoji='🎭'),
        ui.Button(custom_id=f'gw:inv:{pid}', label=f"Invites as entries: {'on' if d['invite_entries'] else 'off'}", style=discord.ButtonStyle.secondary, emoji='➕')))
    view.add_item(ui.ActionRow(ui.Select(custom_id=f'gw:ping:{pid}', placeholder='Who gets pinged', options=[
        discord.SelectOption(label=n, value=k, description=desc, default=k == d['ping']) for k, n, desc in PINGS])))
    return {'view': view, 'attachments': files, 'allowed_mentions': NO_MENTIONS}


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
    d = await _guard(i, ident)
    if not d:
        return
    if not can_run(i.user):
        return await i.response.send_message('Only admins and the Giveaway Manager role can run giveaways.', ephemeral=True)
    pid = ident
    if action == 'cancel':
        del_pending(pid)
        return await i.response.edit_message(view=text_view('🗑️ **CANCELLED**\nNothing was posted.'), attachments=[])
    if action == 'edit':
        bonus = '\n'.join(f"{ctx.guild.get_role(int(r)).name}: {n}" for r, n in d['bonus'].items() if ctx.guild.get_role(int(r)))
        return await i.response.send_modal(FormModal(f'gwp:{pid}', 'Prizes & time', [
            _spec('title', 'Title', d['title'], required=True),
            _spec('prizes', 'Prizes (1: 2k Robux + Nitro / 2-5: 2k Robux)', d['prize_text'], 'paragraph', 800, '1: 2k Robux + Nitro\n2-5: 2k Robux'),
            _spec('duration', 'How long (3d, 12h, 1d 6h)', fmt_duration(d['seconds']), required=True),
            _spec('winners', 'Winners (only if every winner gets the same)', d['winners'] if not d['prize_text'].count(':') else '', mx=3),
            _spec('bonus', 'Bonus entries for roles (Booster: 2)', bonus, 'paragraph', 400, 'Booster: 2\nDonator: 3')]))
    if action == 'rules':
        black = ', '.join(ctx.guild.get_role(int(r)).name for r in d['blacklist'] if ctx.guild.get_role(int(r)))
        inv = (str(d['invite_cap']) if d['invite_cap'] else 'yes') if d['invite_entries'] else 'no'
        return await i.response.send_modal(FormModal(f'gwr:{pid}', 'Rules', [
            _spec('min_invites', 'Minimum invites to enter (0 = none)', d['min_invites'], mx=4),
            _spec('invite_entries', 'Every invite = 1 more entry? no / yes / a cap', inv, mx=6),
            _spec('min_days', 'Minimum days in the server (0 = none)', d['min_days'], mx=4),
            _spec('claim_hours', 'Winners must claim within hours (0 = no claim)', d['claim_hours'], mx=4),
            _spec('blacklist', 'Roles that cannot enter (names, comma)', black, mx=200)]))
    if action == 'mode':
        d['req_mode'] = 'any' if d['req_mode'] == 'all' else 'all'
    elif action == 'inv':
        d['invite_entries'] = not d['invite_entries']
    elif action == 'roles':
        d['req_roles'] = [str(v) for v in (i.data.get('values') or [])]
    elif action == 'ping':
        d['ping'] = (i.data.get('values') or ['none'])[0]
    elif action == 'start':
        return await start(i, pid, d)
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
        winners = num('winners', MAX_WINNERS) or d['winners']
        prizes, err = parse_prizes(f.get('prizes'), winners)
        if err and f.get('prizes'):
            return await i.response.send_message(err, ephemeral=True)
        bonus, bad = parse_bonus(f.get('bonus'))
        if bad:
            return await i.response.send_message('I could not read these bonus lines: ' + '; '.join(f'`{b}`' for b in bad[:4]) + '. Write them like `Booster: 2` with the exact role name.', ephemeral=True)
        d.update(title=f.get('title')[:100] or d['title'], seconds=min(seconds, 60 * 86400), prize_text=f.get('prizes', ''), prizes=prizes if f.get('prizes') else d['prizes'],
                 winners=winners, bonus=bonus)
    else:
        ids, unknown = find_roles(f.get('blacklist'))
        if unknown:
            return await i.response.send_message('I do not know these roles: ' + ', '.join(f'`{u}`' for u in unknown[:5]), ephemeral=True)
        inv = f.get('invite_entries', 'no').lower()
        d.update(min_invites=num('min_invites', 1000), min_days=num('min_days', 3650), claim_hours=num('claim_hours', 720), blacklist=ids,
                 invite_entries=inv not in ('', 'no', 'n', 'off', '0', 'false'), invite_cap=int(inv) if inv.isdigit() else 0)
    set_pending(pid, d)
    await i.response.edit_message(**payload(pid)) if i.message else await i.response.send_message('Saved.', ephemeral=True)


async def start(i, pid, d):
    ch = await fetch_channel(d['channel'])
    if not ch:
        return await i.response.send_message('I cannot find that channel any more.', ephemeral=True)
    await i.response.defer()
    ends = now() + d['seconds'] * 1000
    c = _config(d)
    gid = run('INSERT INTO giveaways(channel_id,message_id,host_id,title,config,status,ends_at,created_at) VALUES(?,?,?,?,?,?,?,?)',
              str(ch.id), '0', d['user'], d['title'], json.dumps(c), 'running', ends, now()).lastrowid
    g = _g(gid)
    ping = {'giveaways': f'<@&{cfg.giveaways_role}>', 'everyone': '@everyone'}.get(d['ping'])
    view, files = container(g, gid, 'running', 0, ping)
    allowed = discord.AllowedMentions(everyone=d['ping'] == 'everyone', roles=[discord.Object(id=int(cfg.giveaways_role))] if d['ping'] == 'giveaways' else False, users=False)
    sent = await ch.send(view=view, files=files, allowed_mentions=allowed)
    run('UPDATE giveaways SET message_id=? WHERE id=?', str(sent.id), gid)
    add_timer('gw_end', gid, ends)
    del_pending(pid)
    await _log(g, f"🎁 Giveaway **{g['title']}** (#{gid}) started by <@{d['user']}> in <#{ch.id}>: {sent.jump_url}")
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
        ch = i.channel
        if opts.get('channel'):
            ch = await fetch_channel(opts['channel'])
        pid = new_draft(i.user.id, ch.id, str(opts['title'])[:100], min(seconds, 60 * 86400), min(int(opts.get('winners') or 1), MAX_WINNERS))
        await i.response.defer(ephemeral=True)
        return await i.edit_original_response(**payload(pid))
    if sub == 'list':
        rows = all_("SELECT * FROM giveaways WHERE status IN ('running','ended') ORDER BY id DESC LIMIT 10")
        lines = [f"#{r['id']} · **{r['title']}** · {r['status']} · <#{r['channel_id']}> · {_count(r['id'])} entered" + (f" · ends <t:{r['ends_at'] // 1000}:R>" if r['status'] == 'running' else '') for r in rows]
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
