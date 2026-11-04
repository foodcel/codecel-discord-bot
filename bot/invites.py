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
    head = f"## 📨 {'Your' if mine else member.display_name + chr(39) + 's'} invites" + (f"{NL}-# rank **#{rank}**" if rank else '')
    body = [f"### {s['score']} {'invite counts' if s['score'] == 1 else 'invites count'}{NL}-# people {'you' if mine else 'they'} brought who are still here and verified",
            NL.join([f"🕓 **{s['unverified']}** joined but are not verified yet",
                     f"🚪 **{s['left']}** left the server",
                     f"👥 **{s['joined']}** joined with {who} invites",
                     f"🔗 **{s['uses']}** uses of {who} invites, all time"])]
    return _card(head, body, ['/invites top · the leaderboard'])


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def top_card(viewer_id=None, rows=None, mine=None, total=None):
    """The leaderboard. rows: [(name, counting, joined)] best first; by default the real ones. mine: the viewer's rank."""
    if rows is None:
        board = leaderboard()
        rows = [(ctx.guild.get_member(int(u)).display_name if ctx.guild.get_member(int(u)) else 'a former member', b['score'], b['joined']) for u, b in board]
        mine = next((k + 1 for k, (u, _) in enumerate(board) if u == str(viewer_id)), None)
        total = sum(b['score'] for _, b in board)
    lines = []
    for k, (name, score, joined) in enumerate(rows[:10]):
        lines += [f'### {name} · {score}', f'-# 1st place · {joined} joined with their invites'] if k == 0 else [f'**{_ord(k + 1)}** · {name} · {score}']
    head = f"## 🏆 Top inviters{NL}-# {total} invites counting" if total else '## 🏆 Top inviters'
    body = [NL.join(lines) or 'Nobody has a counting invite yet. Invite a friend: they count once they verify.']
    if mine:
        body.append(f'You are **{_ord(mine)}**' + (f" · {rows[mine - 1][1]} counting" if mine <= len(rows) else ''))
    return _card(head, body, ['/invites stats · your own numbers'])


async def command_invites(i, sub, opts):
    await i.response.defer(ephemeral=(sub != 'top'))
    if sub == 'top':
        view, files = top_card(i.user.id)
    else:
        target = ctx.guild.get_member(int(opts['user'])) if opts.get('user') else i.user
        if not target or target.bot:
            return await i.edit_original_response(content='I can only show invites for a person in the server.')
        view, files = stats_card(target, mine=target.id == i.user.id)
    await i.edit_original_response(view=view, attachments=files, allowed_mentions=NO_MENTIONS)
