"""The preview an admin sees after /giveaway new: its buttons, forms and the Start that posts it."""
import json
import re
import discord
from discord import ui
from bot.discord_ui.components import NO_MENTIONS, FormModal
from bot.core.ctx import ctx, fetch_channel
from bot.core.db import add_timer, create_pending, del_pending, get_pending, now, run, set_pending
from bot.core.perms import level
from bot.features.giveaways.rules import MAX_WINNERS, NL, can_run, find_roles, fmt_duration, parse_bonus, parse_duration, parse_prizes, prize_text_of, split_prize
from bot.features.giveaways.card import PINGS, banner_for, card_items, container, names_only, ping_text, text_view
from bot.features.giveaways.draw import _g, _log, claim, enter, leave, mine


# ---- the preview draft ----
FIELDS = ('prizes', 'req_roles', 'req_mode', 'blacklist', 'bonus', 'min_invites', 'invite_entries', 'invite_cap', 'min_days', 'claim_hours', 'ping', 'bonus_best',
          'hosts', 'banner', 'bypass_roles', 'per_boost')


def new_draft(user_id, channel_id, prize, seconds, winners):
    return create_pending({'kind': 'giveaway', 'user': str(user_id), 'channel': str(channel_id), 'title': f'{prize} giveaway'[:100], 'seconds': seconds,
                           'prizes': split_prize(prize, winners), 'req_roles': [], 'req_mode': 'any', 'blacklist': [], 'bonus': {},
                           'min_invites': 0, 'invite_entries': False, 'invite_cap': 0, 'min_days': 0, 'claim_hours': 0, 'ping': 'none', 'bonus_best': False, 'bypass_roles': [], 'per_boost': 0,
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
    free = [r for r in (ctx.guild.get_role(int(x)) for x in d.get('bypass_roles') or []) if r]
    view.add_item(ui.ActionRow(ui.RoleSelect(custom_id=f'gw:bypass:{pid}', placeholder='Always allowed in, not shown on the card (optional)', min_values=0, max_values=5, default_values=free)))
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
        bonus = NL.join(([f"each boost: {d['per_boost']}"] if d.get('per_boost') else []) + [f"{ctx.guild.get_role(int(r)).name}: {n}" for r, n in d['bonus'].items() if ctx.guild.get_role(int(r))])
        return await i.response.send_modal(FormModal(f'gwp:{pid}', 'Prizes & time', [
            _spec('title', 'Name (shown in the winner messages)', d['title'], required=True),
            _spec('prizes', 'Prizes per place', prize_text_of(d['prizes']), 'paragraph', 800, '1: 2K Robux + Nitro\n2-5: 2K Robux'),
            _spec('duration', 'How long (3d, 12h, 1d 6h)', fmt_duration(d['seconds']), required=True),
            _spec('winners', 'Winners (splits the banner prize again)', len(d['prizes']), mx=3),
            _spec('bonus', 'Bonus entries (Donator: 3 / each boost: 3)', bonus, 'paragraph', 400, 'Donator: 3\neach boost: 3')]))
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
    elif action == 'bypass':
        d['bypass_roles'] = values
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
        per, rest = 0, []
        for line in str(f.get('bonus') or '').splitlines():
            m = re.match(r'^\s*(?:each|per|every)\s+(?:server\s+)?boosts?\s*[:=x+]?\s*\+?(\d+)\s*$', line, re.I)
            if m:
                per = min(int(m[1]), 100)
            else:
                rest.append(line)
        bonus, bad = parse_bonus(NL.join(rest))
        if bad:
            return await i.response.send_message('I could not read these bonus lines: ' + '; '.join(f'`{b}`' for b in bad[:4]) + '. Write them like `Booster: 2` with the exact role name.', ephemeral=True)
        d.update(title=f.get('title')[:100] or d['title'], seconds=min(seconds, 60 * 86400), prizes=prizes, bonus=bonus, per_boost=per)
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


_starting = set()  # drafts being posted: a double click must not post (and ping) twice


async def start(i, pid, d):
    ch = await fetch_channel(d['channel'])
    if not ch:
        return await i.response.send_message('I cannot find that channel any more.', ephemeral=True)
    if pid in _starting:
        return await i.response.send_message('It is being posted already.', ephemeral=True)
    _starting.add(pid)
    try:
        await _start(i, pid, d, ch)
    finally:
        _starting.discard(pid)


async def _start(i, pid, d, ch):
    await i.response.defer()
    ends = now() + d['seconds'] * 1000
    gid = run('INSERT INTO giveaways(channel_id,message_id,host_id,title,config,status,ends_at,created_at) VALUES(?,?,?,?,?,?,?,?)',
              str(ch.id), '0', d['user'], d['title'], json.dumps({**_config(d), 'v': 2}), 'running', ends, now()).lastrowid
    g = _g(gid)
    # one send with the ping and the hosts allowed: the ping (if any) goes out now, the hosts are told they host. Later edits keep the same mentions (names_only), so nobody is pinged again.
    try:
        sent = await ch.send(view=container(g, gid, 'running', 0), files=[banner_for(g)], allowed_mentions=names_only(g))
    except Exception:
        run('DELETE FROM giveaways WHERE id=?', gid)  # nothing half-made is left behind; the draft stays so it can be tried again
        raise
    run('UPDATE giveaways SET message_id=? WHERE id=?', str(sent.id), gid)
    add_timer('gw_end', gid, ends)
    del_pending(pid)
    await _log(f"🎁 Giveaway **{g['title']}** (#{gid}) started by <@{d['user']}> in <#{ch.id}>: {sent.jump_url}")
    await i.edit_original_response(view=text_view(f'✅ **STARTED**{NL}{sent.jump_url}'), attachments=[])
