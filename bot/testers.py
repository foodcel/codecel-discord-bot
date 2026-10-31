"""The tester roster: who tests, on what, and when. Two embeds (the tester guide and the roster) are kept up to date by the bot.
A tester can be open to every dev (🟢), waiting for a reply (🟡), private (🔒, only tests one dev's games and is never offered to other
devs) or on a break (💤)."""
import asyncio
import json
import re

import discord

from .components import NO_MENTIONS, FormModal
from .ctx import ctx, fetch_channel
from .db import all_, kv_get, kv_set, one, run
from .env import cfg
from .perms import level
from .ui import E, ZW, describe, flat, gap, head, section

MARK = {'active': '🟢', 'pending': '🟡', 'private': '🔒', 'inactive': '💤'}
FIELDS = ('devices', 'recording', 'availability', 'best_for')
_refresh_task = None


# ---- data ----
def get(uid):
    return one('SELECT * FROM testers WHERE user_id=?', str(uid))


def everyone():
    order = {'active': 0, 'private': 1, 'pending': 2, 'inactive': 3}
    return sorted(all_('SELECT * FROM testers'), key=lambda r: (order.get(r['status'], 9), r['added_at'] or 0, r['user_id']))


def save(uid, **fields):
    if not get(uid):
        run("INSERT INTO testers(user_id,status,added_at) VALUES(?, 'pending', strftime('%s','now'))", str(uid))
    for k, v in fields.items():
        run(f'UPDATE testers SET {k}=? WHERE user_id=?', v, str(uid))
    return get(uid)


def report_counts():
    return {r['reporter_id']: r['n'] for r in all_("SELECT reporter_id, COUNT(*) n FROM bugs WHERE source='tester' GROUP BY reporter_id")}


# ---- the two embeds ----
def guide_embed():
    e = flat()
    e.title = head('🧪', 'Tester responsibilities')
    describe(e, 'All testers are expected to:\n\n' + '\n'.join([
        '✅ Test assigned games thoroughly',
        '✅ Report bugs and gameplay issues',
        '✅ Provide screenshots or recordings when possible',
        '✅ Communicate regularly with the development team',
        '✅ Remain active and complete assigned testing tasks',
        '✅ Be patient with difficult or unfinished games']))
    section(e, head(E['warn'], 'Important'),
            "We expect consistent effort, honesty and communication. If you're unavailable or unable to finish a test, please notify the developer(s).")
    where = f'<#{cfg.testing_id}>' if cfg.testing_id else 'the testing channel'
    section(e, head(E['open'], 'How to report bugs'),
            f'Type `/bug` in {where}. The form asks for:\n'
            '• **Game** · which game, the dev is pinged for you\n• **Issue** · what happened\n• **Steps** · how can we recreate it?\n'
            '• **Evidence** · screenshots or videos\n• **Device** · your platform\n• **Frequency** · how often it happens (say it in the description)')
    section(e, head('👤', 'Your profile'), 'Use `/tester profile` to tell the developers what you test on and when you are free.')
    gap(e)
    e.set_footer(text='Questions? Ask in this channel or message a developer.')
    return e


LABEL = {'active': 'Active', 'private': 'Private', 'pending': 'Waiting for a reply', 'inactive': 'On a break'}
COMMANDS_FOOTER = '\n'.join([
    '/tester profile · fill in or update your own details',
    '/tester find · devs: find testers open for a device',
])
WIDTH = chr(0x3164) * 24  # the width line: narrower than the other embeds, so it fits a phone


def _name(uid):
    m = ctx.guild.get_member(int(uid)) if ctx.guild else None
    return m.display_name if m else 'a dev'


def _block(r, reports):
    """One tester: the mention, then its details branching under it, one short line each (no columns, so a phone shows it whole)."""
    n = reports.get(r['user_id'], 0)
    lines = [f"<@{r['user_id']}>" + (f' · 📝 {n} report{"" if n == 1 else "s"}' if n else '')]
    if r['status'] == 'pending' and not r['devices']:
        kids = ['⏳ No response yet']
    elif r['status'] == 'inactive':
        kids = ['💤 On a break: not available for testing']
    else:
        kids = [f"🎮 {r['devices'] or '?'}  ·  🎥 {r['recording'] or '?'}", f"🕐 {r['availability'] or '?'}"]
        if r['best_for']:
            kids.append(f"⭐ {r['best_for']}")
        if r['status'] == 'private':
            kids.append(f"🔒 Only tests {_name(r['only_for'])}'s games" if r['only_for'] else '🔒 Only tests one dev\'s games')
    for k, kid in enumerate(kids):
        lines.append(f"{'└─' if k == len(kids) - 1 else '├─'} {kid}")
    return '\n'.join(lines)


def roster_embed(rows=None, reports=None):
    """The roster. `rows` and `reports` can be given to show an example."""
    rows = everyone() if rows is None else rows
    reports = report_counts() if reports is None else reports
    count = {st: sum(1 for r in rows if r['status'] == st) for st in MARK}
    e = flat()
    e.title = head('👥', 'Tester roster')
    parts = [f"{MARK[st]} **{n}** {label}" for st, label in (('active', 'active'), ('private', 'private'), ('pending', 'waiting for a reply'), ('inactive', 'on a break')) if (n := count[st])]
    describe(e, '  ·  '.join(parts) or 'Nobody on the roster yet.', WIDTH)
    used = 0
    for st in ('active', 'private', 'pending', 'inactive'):
        for k, r in enumerate([r for r in rows if r['status'] == st]):
            if used >= 24:
                break
            if k == 0 and used:
                gap(e)  # one empty line above each group name after the first
            # the first tester of a group carries the group's name, the others a blank line above them
            e.add_field(name=head(MARK[st], f'{LABEL[st]} · {count[st]}') if k == 0 else ZW, value=_block(r, reports)[:1024], inline=False)
            used += 1
    gap(e)
    e.set_footer(text=COMMANDS_FOOTER)
    return e


# ---- the posted messages ----
def _board():
    raw = kv_get('testerboard')
    return json.loads(raw) if raw else None


async def refresh_roster():
    b = _board()
    if not b:
        return
    ch = await fetch_channel(b['channelId'])
    if ch is None:
        return
    for key, embed in (('guide', guide_embed()), ('roster', roster_embed())):
        try:
            await ch.get_partial_message(int(b[key])).edit(embed=embed)
        except discord.NotFound:
            msg = await ch.send(embed=embed)
            b[key] = str(msg.id)
            kv_set('testerboard', json.dumps(b))
        except Exception as e:
            print('tester board', e)


def schedule_refresh():
    """Refreshes in a few seconds, once for a burst of changes."""
    global _refresh_task
    if _refresh_task and not _refresh_task.done():
        return

    async def go():
        global _refresh_task
        await asyncio.sleep(4)
        _refresh_task = None
        await refresh_roster()

    _refresh_task = asyncio.ensure_future(go())


async def post_board(ch):
    """Posts the guide and the roster in a channel and keeps them up to date from now on. The earlier copy is removed. In the
    tester-information channel the two old messages are replaced too. Returns how many old messages were removed."""
    await import_old()  # the old roster message is read before it is replaced
    old = _board()
    g = await ch.send(embed=guide_embed())
    r = await ch.send(embed=roster_embed())
    kv_set('testerboard', json.dumps({'channelId': str(ch.id), 'guide': str(g.id), 'roster': str(r.id)}))
    removed = 0
    if old and (old['channelId'], old['roster']) != (str(ch.id), str(r.id)):  # the earlier copy stops updating: remove it
        oc = await fetch_channel(old['channelId'])
        for k in ('guide', 'roster'):
            try:
                await oc.get_partial_message(int(old[k])).delete()
            except Exception:
                pass
    if cfg.tester_info_id and str(ch.id) == cfg.tester_info_id:
        async for m in ch.history(limit=50):
            if m.author.id != ctx.client.user.id and ('Total Testers' in m.content or 'TESTER RESPONSIBILITIES' in m.content):
                try:
                    await m.delete()
                    removed += 1
                except Exception:
                    pass
    return removed


# ---- taking over the old message ----
def parse_old_roster(text):
    out = []
    for m in re.finditer(r'(🟢|🟡)\s*(\d+)\.\s*<@!?(\d+)>\s*\n((?:\s*-\s*\*\*.+\n?)+)', text + '\n'):
        f = {k.strip().lower().replace(' ', '_'): v.strip() for k, v in re.findall(r'-\s*\*\*(.+?):\*\*\s*(.+)', m.group(4))}
        known = lambda k: None if f.get(k, 'Unknown').lower() == 'unknown' else f[k]  # noqa: E731
        avail = ' · '.join(x for x in (known('availability'), known('schedule'), f"short notice: {f['short_notice']}" if f.get('short_notice') else None) if x)
        done = m.group(1) == '🟢'
        out.append({'user_id': m.group(3), 'status': 'active' if done else 'pending', 'devices': known('devices'), 'recording': known('recording'),
                    'availability': avail or None, 'best_for': None if (f.get('best_for') or '').startswith('⏳') else known('best_for')})
    return out


async def import_old():
    """The first time only: the roster message in the tester-information channel becomes the list."""
    chan = cfg.tester_info_id
    if not chan or all_('SELECT 1 FROM testers LIMIT 1'):
        return 0
    ch = await fetch_channel(chan)
    if ch is None:
        return 0
    n = 0
    async for m in ch.history(limit=20):
        if 'Total Testers' in m.content:
            for r in parse_old_roster(m.content):
                save(r['user_id'], **{k: v for k, v in r.items() if k != 'user_id'})
                n += 1
            break
    return n


# ---- the Tester role ----
def _tester_role_ids():
    return [int(r) for r in cfg.tester_roles]


async def give_role(uid):
    roles = _tester_role_ids()
    m = ctx.guild.get_member(int(uid)) if roles else None
    if not m:
        return 'is not in the server'
    if any(r.id in roles for r in m.roles):
        return None
    try:
        await m.add_roles(discord.Object(id=roles[0]), reason='Added to the tester roster')
        return None
    except Exception as e:
        return f"could not get the Tester role ({e})"


async def take_roles(uid):
    roles = _tester_role_ids()
    m = ctx.guild.get_member(int(uid)) if roles else None
    if not m:
        return None
    mine = [discord.Object(id=r.id) for r in m.roles if r.id in roles]
    if not mine:
        return None
    try:
        await m.remove_roles(*mine, reason='Removed from the tester roster')
        return None
    except Exception as e:
        return f"could not remove the Tester role ({e})"


async def on_member_update(before, after):
    """Someone got the Tester role by hand: they join the roster as waiting. They lost it: they leave."""
    roles = set(_tester_role_ids())
    if not roles:
        return
    had = bool(roles & {r.id for r in before.roles})
    has = bool(roles & {r.id for r in after.roles})
    if has and not had and not get(after.id):
        save(after.id)
        schedule_refresh()
    elif had and not has and get(after.id):
        run('DELETE FROM testers WHERE user_id=?', str(after.id))
        schedule_refresh()


# ---- the commands ----
def _text(v, n=120):
    v = ' '.join(str(v or '').split())
    return v[:n] or None


async def command_tester(i, sub, opts):
    reply = i.response.send_message
    admin = level(i.user) == 'admin'
    if sub in ('add', 'remove', 'status', 'edit', 'post') and not admin:
        return await reply('Only admins can manage the tester roster.', ephemeral=True)
    if sub == 'profile':
        me = get(i.user.id)
        is_tester = any(str(r.id) in cfg.tester_roles for r in i.user.roles) or me or level(i.user) != 'none'
        if not is_tester:
            return await reply('This is for testers.', ephemeral=True)
        me = me or {}
        return await i.response.send_modal(FormModal('tp', 'Your tester profile', [
            {'id': 'devices', 'label': 'What do you test on?', 'style': 'short', 'required': True, 'max': 120, 'value': me.get('devices') or '', 'placeholder': 'e.g. PC, Mobile, Xbox'},
            {'id': 'recording', 'label': 'How do you record?', 'style': 'short', 'required': True, 'max': 120, 'value': me.get('recording') or '', 'placeholder': 'e.g. OBS, Medal, built-in'},
            {'id': 'availability', 'label': 'When are you free?', 'style': 'short', 'required': True, 'max': 120, 'value': me.get('availability') or '', 'placeholder': 'e.g. After 2 PM, 3 days a week, short notice ok'},
            {'id': 'best_for', 'label': 'What are you best for?', 'style': 'short', 'required': False, 'max': 120, 'value': me.get('best_for') or '', 'placeholder': 'e.g. PC, long playthroughs, urgent testing'},
        ]))
    if sub == 'find':
        if level(i.user) == 'none' and not any(str(r.id) in cfg.tester_roles for r in i.user.roles):
            return await reply('Only devs can look for testers.', ephemeral=True)
        q = str(opts.get('device') or '').lower()
        found = []
        for r in everyone():
            if r['status'] == 'active' or (r['status'] == 'private' and r['only_for'] == str(i.user.id)):
                if q in f"{r['devices'] or ''} {r['best_for'] or ''}".lower():
                    found.append(f"{MARK[r['status']]} <@{r['user_id']}> · 🎮 {r['devices'] or '?'} · 🕐 {r['availability'] or '?'}")
        return await reply('\n'.join(found)[:1900] or f'Nobody open for testing matches "{q}".', ephemeral=True, allowed_mentions=NO_MENTIONS)
    if sub == 'post':
        ch = await fetch_channel(opts.get('channel')) if opts.get('channel') else i.channel
        await i.response.defer(ephemeral=True, thinking=True)
        removed = await post_board(ch)
        return await i.edit_original_response(content=f'Posted in {ch.mention}. The roster updates by itself.' + (f' Replaced {removed} old message(s).' if removed else ''))
    uid = str(opts.get('user'))
    if sub == 'add':
        status = opts.get('status') or 'pending'
        if status == 'private' and not opts.get('only_for'):
            return await reply('A private tester needs `only_for`: the dev whose games they test.', ephemeral=True)
        row = save(uid, status=status, only_for=str(opts['only_for']) if opts.get('only_for') else None,
                   **{k: _text(opts.get(k)) for k in FIELDS if opts.get(k)})
        problem = await give_role(uid)
        note = f' (but {problem})' if problem else ''
        await refresh_roster()
        return await reply(f"Added <@{uid}> as {MARK[row['status']]} {row['status']}{note}.", ephemeral=True, allowed_mentions=NO_MENTIONS)
    if not get(uid):
        return await reply('That person is not on the roster. Add them with `/tester add`.', ephemeral=True)
    if sub == 'remove':
        run('DELETE FROM testers WHERE user_id=?', uid)
        problem = await take_roles(uid)
        await refresh_roster()
        return await reply(f"Removed <@{uid}> from the roster{f' (but {problem})' if problem else ' and took the Tester role'}.", ephemeral=True, allowed_mentions=NO_MENTIONS)
    if sub == 'status':
        status = opts['status']
        if status == 'private' and not opts.get('only_for'):
            return await reply('A private tester needs `only_for`: the dev whose games they test.', ephemeral=True)
        row = save(uid, status=status, only_for=str(opts['only_for']) if status == 'private' else None)
        await refresh_roster()
        extra = f" They only test <@{row['only_for']}>'s games and are never offered to other devs." if status == 'private' else \
            ' They are not offered to devs while they are on a break.' if status == 'inactive' else ''
        return await reply(f"<@{uid}> is now {MARK[status]} {status}.{extra}", ephemeral=True, allowed_mentions=NO_MENTIONS)
    if sub == 'edit':
        changes = {k: _text(opts.get(k)) for k in FIELDS if opts.get(k)}
        if not changes:
            return await reply('Nothing to change. Pass at least one field.', ephemeral=True)
        save(uid, **changes)
        await refresh_roster()
        return await reply(f"Updated <@{uid}>: {', '.join(changes)}.", ephemeral=True, allowed_mentions=NO_MENTIONS)


async def modal_profile(i, fields):
    uid = str(i.user.id)
    row = get(uid)
    vals = {k: _text(fields.get(k)) for k in FIELDS}
    save(uid, **vals)
    if (not row or row['status'] == 'pending') and vals['devices'] and vals['recording'] and vals['availability']:
        save(uid, status='active')  # a complete profile moves them from waiting to open
    await refresh_roster()
    return await i.response.send_message('Thanks! Your tester profile is saved.', ephemeral=True)
