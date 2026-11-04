"""The invite tracker: who invited every member who joins, and how many of their invites really count.
Discord does not say which invite a new member used, so the bot keeps a copy of every invite's use count and, when someone joins, looks for the one that went up.
It only knows joins from the moment it runs (invites used before that show as "uses" but cannot be checked). An invite counts for the score when the
person it brought is still in the server AND has the Verified role, checked at the moment the number is needed.
It is a feature of its own: giveaways can read the number (invites.qualified), but nothing here depends on them.
/invites stats [user] shows one person's numbers, /invites top the leaderboard."""
import asyncio

import discord
from discord import ui

from .botnews import code_chip
from .components import NO_MENTIONS
from .ctx import ctx
from .db import all_, db, now, run
from .env import cfg
from .pngs import with_strip

NL = chr(10)
SMALL = discord.SeparatorSpacing.small

db.executescript("""
CREATE TABLE IF NOT EXISTS invite_joins(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, inviter_id TEXT, code TEXT, joined_at INTEGER NOT NULL, left_at INTEGER);
CREATE INDEX IF NOT EXISTS invite_joins_inviter ON invite_joins(inviter_id);
CREATE INDEX IF NOT EXISTS invite_joins_user ON invite_joins(user_id);
""")

_cache = {}  # code -> {'uses', 'max', 'inviter'}
_lock = asyncio.Lock()


async def _snapshot():
    return {i.code: {'uses': i.uses or 0, 'max': i.max_uses or 0, 'inviter': str(i.inviter.id) if i.inviter else None}
            for i in await ctx.guild.invites()}


async def load():
    """The copy of every invite's uses, taken at start-up and kept up to date by the join event."""
    try:
        async with _lock:
            _cache.clear()
            _cache.update(await _snapshot())
        print(f'invite tracker: {len(_cache)} invites')
    except Exception as e:
        print('invite tracker could not load', repr(e)[:150])


async def on_invite_create(invite):
    _cache[invite.code] = {'uses': invite.uses or 0, 'max': invite.max_uses or 0, 'inviter': str(invite.inviter.id) if invite.inviter else None}


async def on_member_join(member):
    if member.bot or not ctx.guild or member.guild.id != ctx.guild.id:
        return
    async with _lock:
        code = inviter = None
        try:
            fresh = await _snapshot()
        except Exception as e:
            print('invite tracker: could not read the invites', repr(e)[:120])
            fresh = None
        if fresh is not None:
            for c, v in fresh.items():  # the invite whose use count went up
                if v['uses'] > (_cache.get(c) or {}).get('uses', 0):
                    code, inviter = c, v['inviter']
                    break
            if not code:  # an invite that is gone now: its last use was this join
                for c, old in _cache.items():
                    if c not in fresh and old['max'] and old['uses'] + 1 >= old['max']:
                        code, inviter = c, old['inviter']
                        break
            _cache.clear()
            _cache.update(fresh)
        run('INSERT INTO invite_joins(user_id,inviter_id,code,joined_at) VALUES(?,?,?,?)', str(member.id), inviter, code, now())


async def on_member_remove(member):
    run('UPDATE invite_joins SET left_at=? WHERE user_id=? AND left_at IS NULL', now(), str(member.id))


def _verified(m):
    return any(str(r.id) == str(cfg.verified_role) for r in m.roles)


def _bucket(rows):
    """{'joined', 'verified', 'unverified', 'left'} for the people one inviter brought (each person once, their latest join)."""
    latest = {}
    for r in rows:
        latest[r['user_id']] = r
    out = {'joined': len(latest), 'verified': 0, 'unverified': 0, 'left': 0}
    for uid in latest:
        m = ctx.guild.get_member(int(uid))
        out['left' if not m else 'verified' if _verified(m) else 'unverified'] += 1
    return out


def stats(user_id):
    """One person's numbers. `score` is what counts for giveaways: people still here with the Verified role."""
    rows = all_('SELECT user_id FROM invite_joins WHERE inviter_id=? ORDER BY joined_at', str(user_id))
    b = _bucket(rows)
    b['uses'] = sum(v['uses'] for v in _cache.values() if v['inviter'] == str(user_id))  # Discord's own count of their live invites
    b['score'] = b['verified']
    return b


def qualified(user_id):
    """The invites that count right now (a giveaway reads this for its invite rules)."""
    return stats(user_id)['score']


def leaderboard():
    """[(user id, stats)] best first, only people with at least one counting invite."""
    by = {}
    for r in all_('SELECT user_id, inviter_id FROM invite_joins WHERE inviter_id IS NOT NULL ORDER BY joined_at'):
        by.setdefault(r['inviter_id'], []).append(r)
    rows = []
    for inviter, rs in by.items():
        b = _bucket(rs)
        b['score'] = b['verified']
        if b['score']:
            rows.append((inviter, b))
    return sorted(rows, key=lambda x: (-x[1]['score'], -x[1]['joined']))


def _card(head, body, footer):
    """The community look without a banner: the heading, ONE line under it, the body in blocks with only a gap between them (no lines), ONE line above the footer,
    the command chips at the bottom. The faint footer line also keeps the card as wide as the others."""
    items = [ui.TextDisplay(head), ui.Separator(visible=True, spacing=SMALL)]
    for k, b in enumerate(body):
        if k:
            items.append(ui.Separator(visible=False, spacing=SMALL))
        items.append(ui.TextDisplay(b))
    items += [ui.Separator(visible=True, spacing=SMALL), ui.TextDisplay(NL.join('-# ' + code_chip(x) for x in footer))]
    items, strip = with_strip(items)
    view = ui.LayoutView()
    view.add_item(ui.Container(*items))
    return view, [strip]


def stats_card(member, mine=True, s=None, rank=None):
    s = s or stats(member.id)
    rank = rank or next((k + 1 for k, (u, _) in enumerate(leaderboard()) if u == str(member.id)), None)
    who = 'your' if mine else 'their'
    head = f"## 📨 {'Your' if mine else f'<@{member.id}>' + chr(39) + 's'} invites" + (f"{NL}-# rank **#{rank}**" if rank else '')
    body = [f"### {s['score']} {'invite counts' if s['score'] == 1 else 'invites count'}{NL}-# people {'you' if mine else 'they'} brought who are still here and verified",
            NL.join([f"🕓 **{s['unverified']}** joined but are not verified yet",
                     f"🚪 **{s['left']}** left the server",
                     f"👥 **{s['joined']}** joined with {who} invites",
                     f"🔗 **{s['uses']}** uses of {who} invites, all time"])]
    return _card(head, body, ['/invites top · the leaderboard'])


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def top_card(viewer_id=None, rows=None, mine=None, total=None):
    """(view, files, ids of the people mentioned). rows: [(user id, counting, joined)] best first; by default the real ones. mine: the viewer's rank."""
    if rows is None:
        board = leaderboard()
        rows = [(u, b['score'], b['joined']) for u, b in board]
        mine = next((k + 1 for k, (u, _) in enumerate(board) if u == str(viewer_id)), None)
        total = sum(b['score'] for _, b in board)
    who = lambda u: f'<@{u}>' if ctx.guild.get_member(int(u)) else 'a former member'
    lines = []
    for k, (u, score, joined) in enumerate(rows[:10]):
        lines += [f'### {who(u)} · {score}', f'-# 1st place · {joined} joined with their invites'] if k == 0 else [f'**{_ord(k + 1)}** · {who(u)} · {score}']
    head = f"## 🏆 Top inviters{NL}-# {total} invites counting" if total else '## 🏆 Top inviters'
    body = [NL.join(lines) or 'Nobody has a counting invite yet. Invite a friend: they count once they verify.']
    if mine:
        body.append(f'You are **{_ord(mine)}**' + (f" · {rows[mine - 1][1]} counting" if mine <= len(rows) else ''))
    view, files = _card(head, body, ['/invites stats · your own numbers'])
    return view, files, [str(u) for u, _, _ in rows[:10]]


def names_for(ids):
    """The mentions in a card are shown as names in every app, and nobody is pinged: the message is sent silent and only these users are allowed."""
    return discord.AllowedMentions(users=[discord.Object(id=int(u)) for u in ids], roles=False, everyone=False, replied_user=False)


async def command_invites(i, sub, opts):
    if sub == 'top':
        view, files, ids = top_card(i.user.id)
        return await i.response.send_message(view=view, files=files, ephemeral=True, allowed_mentions=names_for(ids))  # only the person who ran it sees it
    target = ctx.guild.get_member(int(opts['user'])) if opts.get('user') else i.user
    if not target or target.bot:
        return await i.response.send_message('I can only show invites for a person in the server.', ephemeral=True)
    view, files = stats_card(target, mine=target.id == i.user.id)
    await i.response.send_message(view=view, files=files, ephemeral=True, allowed_mentions=names_for([target.id]))


# ---- /invite check: everything about one member's invites, for admins ----
def _ts(ms):
    return f'<t:{int(ms) // 1000}:d>'


async def check_card(member):
    """(view, files, ids mentioned). The admin's look at one member: their live links, the people tracked as invited by them and what each is now,
    how many uses cannot be checked, and who invited this member."""
    uid = str(member.id)
    live = [i for i in await ctx.guild.invites() if i.inviter and str(i.inviter.id) == uid]
    rows = all_('SELECT user_id, code, joined_at, left_at FROM invite_joins WHERE inviter_id=? ORDER BY joined_at', uid)
    latest = {}
    for r in rows:
        latest[r['user_id']] = r
    people = []
    for u, r in latest.items():
        m = ctx.guild.get_member(int(u))
        people.append(('left' if not m else 'verified' if _verified(m) else 'unverified', u, r))
    order = {'verified': 0, 'unverified': 1, 'left': 2}
    people.sort(key=lambda p: (order[p[0]], -p[2]['joined_at']))
    count = {k: sum(1 for p in people if p[0] == k) for k in order}
    uses = sum(i.uses or 0 for i in live)
    on_live = sum(1 for r in rows if r['code'] in {i.code for i in live})
    first = (all_('SELECT MIN(joined_at) first FROM invite_joins') or [{}])[0].get('first')
    me = ctx.guild.get_member(member.id)
    head = f'## 🔎 Invite check{NL}-# <@{member.id}> · joined {_ts(member.joined_at.timestamp() * 1000) if member.joined_at else "?"} · account made {_ts(member.created_at.timestamp() * 1000)}' \
           f"{NL}-# {'✅ verified' if me and _verified(me) else '🕓 not verified'}"
    summary = NL.join([f"├─ ✅ **{count['verified']}** count: still here and verified",
                       f"├─ 🕓 **{count['unverified']}** here but not verified",
                       f"├─ 🚪 **{count['left']}** left the server",
                       f"├─ 👥 **{len(people)}** people tracked as invited by them",
                       f"└─ 🔗 **{uses}** uses on their live links"])
    gap = max(0, uses - on_live)
    note = f"-# {gap} use{'s' if gap != 1 else ''} on their links were not tracked (before tracking started, or by someone who is not in the list): they cannot be checked." if gap else None
    links = []
    for k, i in enumerate(sorted(live, key=lambda i: -(i.uses or 0))[:6]):
        limit = f"/{i.max_uses}" if i.max_uses else ''
        exp = f" · expires {_ts(i.expires_at.timestamp() * 1000)}" if i.expires_at else ''
        links.append(f"{'└─' if k == min(len(live), 6) - 1 else '├─'} `discord.gg/{i.code}` · **{i.uses or 0}{limit}** uses{' · <#' + str(i.channel.id) + '>' if i.channel else ''} · made {_ts(i.created_at.timestamp() * 1000) if i.created_at else '?'}{exp}")
    links_block = '**Their invite links**' + NL + (NL.join(links) if links else 'None right now. Links that expired or were deleted cannot be listed, and their uses cannot be checked.')
    icon = {'verified': '✅', 'unverified': '🕓', 'left': '🚪'}
    people_lines = []
    for k, (state, u, r) in enumerate(people[:12]):
        people_lines.append(f"{'└─' if k == min(len(people), 12) - 1 else '├─'} {icon[state]} <@{u}> · joined {_ts(r['joined_at'])} · `{r['code'] or 'vanity or unknown'}`")
    people_block = '**People they invited** (since tracking started)' + NL + (NL.join(people_lines) if people_lines else 'Nobody tracked yet.') \
        + (f'{NL}-# and {len(people) - 12} more' if len(people) > 12 else '')
    mine = all_('SELECT inviter_id, code, joined_at FROM invite_joins WHERE user_id=? ORDER BY joined_at DESC LIMIT 1', uid)
    if mine:
        r = mine[0]
        by = f"<@{r['inviter_id']}> with `{r['code']}`" if r['inviter_id'] else 'the vanity link (discord.gg/redwing) or a link that no longer exists'
        invited_by = f"**Invited by**{NL}{_ts(r['joined_at'])} · {by}"
    else:
        invited_by = f'**Invited by**{NL}Not tracked: they joined before tracking started.'
    body = [summary + (NL + note if note else ''), links_block, people_block, invited_by]
    foot = [f"Tracking since {_ts(first)}" if first else 'Tracking has not seen a join yet']
    view, files = _card(head, body, foot)
    ids = [member.id] + [u for _, u, _ in people[:12]] + [r['inviter_id'] for r in mine if r['inviter_id']]
    return view, files, ids


async def command_invite_check(i, opts):
    target = ctx.guild.get_member(int(opts['user']))
    if not target:
        return await i.response.send_message('That person is not in the server.', ephemeral=True)
    await i.response.defer(ephemeral=True)
    view, files, ids = await check_card(target)
    await i.edit_original_response(view=view, attachments=files, allowed_mentions=names_for(ids))
