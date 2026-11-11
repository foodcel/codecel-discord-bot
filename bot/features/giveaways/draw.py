"""A posted giveaway: entering and leaving, redrawing the card, the seeded draw, the end, claims, rerolls and cancelling."""
import asyncio
import json
import random
import secrets
import discord
from discord import ui
from bot.features.giveaways import boosts
from bot.discord_ui.components import NO_MENTIONS
from bot.core.ctx import ctx, fetch_channel
from bot.core.db import add_timer, all_, cancel_timers, db, now, one, run
from bot.core.env import cfg
from bot.features.giveaways.rules import MAX_ROUNDS, NL, eligible, entries_for, hosts_of, ordinal, short_of
from bot.features.giveaways.card import banner_for, container, names_only, text_view


db.executescript("""
CREATE TABLE IF NOT EXISTS giveaways(
  id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT, message_id TEXT, host_id TEXT, title TEXT, config TEXT,
  status TEXT NOT NULL DEFAULT 'running', ends_at INTEGER, created_at INTEGER, result TEXT);
CREATE TABLE IF NOT EXISTS giveaway_entries(gid INTEGER NOT NULL, user_id TEXT NOT NULL, at INTEGER, PRIMARY KEY(gid, user_id));
""")


# ---- stored giveaways ----
def _g(gid):
    r = one('SELECT * FROM giveaways WHERE id=?', gid)
    if not r:
        return None
    r['config'] = json.loads(r['config'])
    r['result'] = json.loads(r['result']) if r['result'] else None
    return r


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
    if g['status'] not in ('running', 'ended'):
        return  # cancelled: the card says so and stays that way
    msg = await _message(g)
    if not msg:
        return
    boosts.refresh_soon()
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
        lines = [f"**{headline}**"] + [f"{'+' if n > 0 else '−'}{abs(n)} · {what}" for what, n in rows] + ['', "-# It is checked again when the giveaway ends."]
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
    boosts.refresh_soon()
    g = _g(gid)
    if not g or g['status'] != 'running' or now() >= g['ends_at']:
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
    boosts.refresh_soon()
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
    g = _g(gid)
    if not g or g['status'] != 'running':
        return await i.response.edit_message(view=text_view('This giveaway is over, so nothing changed.'))
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
    pool = [(u, w) for u, w in valid_pool(g) if u not in taken]
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
        until = now() + c['claim_hours'] * 3600000
        g['result']['claim_until'] = until
        _save(g)
        cancel_timers('gw_claim', g['id'])
        add_timer('gw_claim', g['id'], until)


async def _log(text):
    if cfg.devlog_id:
        try:
            await (await fetch_channel(cfg.devlog_id)).send(text, allowed_mentions=NO_MENTIONS)
        except Exception:
            pass


async def end(gid, by=None):
    """Draws the winners. Returns text for the person who ended it early, None when there was nothing to end."""
    if run("UPDATE giveaways SET status='drawing' WHERE id=? AND status='running'", gid).rowcount != 1:
        return None  # not running, or another end is drawing it right now
    g = _g(gid)
    try:
        try:
            await boosts.refresh(force=True)  # the draw uses today's boost numbers
        except Exception as e:
            print('giveaway boosts', repr(e)[:120])  # the numbers from before are used
        g['status'] = 'ended'
        pool = valid_pool(g)
        g['result'] = {'winners': [], 'history': [], 'seeds': [], 'eligible': len(pool), 'entries': sum(w for _, w in pool)}
        await _fill(g, list(range(1, len(g['config']['prizes']) + 1)), 0)
        _save(g)
    except Exception:
        run("UPDATE giveaways SET status='running' WHERE id=? AND status='drawing'", gid)
        raise
    cancel_timers('gw_end', gid)
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
    if now() < res.get('claim_until', 0) - 60000:
        return  # a newer claim window is still open (this timer is an old one)
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


async def reroll(gid, place=None, user=None):
    g = _g(gid)
    if not g or g['status'] != 'ended' or not g['result']:
        return 'That giveaway has not ended yet.'
    res = g['result']
    if user:  # a host picked this person: they are replaced even if they already claimed
        if place:
            return 'Pick a place or a winner, not both.'
        drop = [w for w in res['winners'] if str(w['user']) == str(user)]
        if not drop:
            return f'<@{user}> is not a winner of this giveaway.'
    else:
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
