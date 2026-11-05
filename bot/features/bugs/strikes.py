"""The troll strike ladder: warning, 1-day mute, kick, 7-day ban, permanent ban. Kicks and bans need a dev to confirm."""
from datetime import datetime, timedelta, timezone

import discord
from discord import ui

from bot.discord_ui.card import card, row
from bot.discord_ui.components import NO_MENTIONS, allowed, button
from bot.core.ctx import ctx, dm, get_member, modlog, thread_link
from bot.core.db import add_timer, now, one, run
from bot.core.env import cfg
from bot.core.perms import is_staff
from bot.discord_ui.ui import E, EM, sentence

DAY = 86400000
STEPS = ['warn', 'timeout', 'kick', 'ban7', 'permban']
LABEL = {
    'warn': 'a warning', 'timeout': 'a 1-day mute', 'kick': 'a kick',
    'ban7': 'a 7-day ban', 'permban': 'a permanent ban',
}

LADDER_TEXT = '\n'.join([
    '1️⃣ **Warning**',
    '2️⃣ **1-day mute**',
    '3️⃣ **Kick**',
    '4️⃣ **7-day ban**',
    '5️⃣ **Permanent ban**',
])

ACTION = {'warn': 'Warning', 'timeout': '1-day mute', 'kick': 'Kick', 'ban7': '7-day ban', 'permban': 'Permanent ban'}
NL = chr(10)


def rules_card():
    """The bug report rules (/botrules), as a card: (view, files)."""
    return card(f"{E['log']} Bug report rules", [
        'Honest reports are always welcome, even short or incomplete ones. The bot just asks for more details.',
        f"**{E['warn']} Strikes are only for**{NL}Fake reports, spam, abuse, or insulting the developers.",
        f"**🚦 The ladder**{NL}Each strike moves one step up:{NL}{LADDER_TEXT}",
        f"**{E['lock']} Kicks and bans**{NL}A developer confirms every kick and ban before it happens."])


def strike_card(user_id, count, step, reason, bug_id=None, pending=False, log_id=None, result=None):
    """The #mod-log card for one strike: (view, files). pending: a kick or ban waiting for a developer (with the Confirm and Dismiss buttons);
    result: what happened after a button was pressed."""
    found = one('SELECT thread_id FROM bugs WHERE id=?', bug_id) if bug_id else None
    post = found['thread_id'] if found else None
    status = result or (f"{E['warn']} **NEEDS CONFIRMATION**" if pending else f"{E['fixed']} **APPLIED**")
    facts = NL.join([row('User', f'<@{user_id}>'), row('Strike', str(count)), row('Action', ACTION[step])])
    reason_block = f"**{E['note']} Reason**{NL}{sentence(reason)}" + (f"{NL}[Open post]({thread_link(post)})" if post else '')
    inside = [ui.ActionRow(button(f'strike:confirm:{log_id}', f'Confirm {ACTION[step].lower()}', discord.ButtonStyle.danger),
                           button(f'strike:dismiss:{log_id}', 'Dismiss', discord.ButtonStyle.secondary))] if pending and log_id else []
    return card(f"{E['warn']} Strike {count}", [status, facts, reason_block], ping=f'<@&{cfg.dev_role}>' if pending and not result else None, inside=inside)


def step_for(count):
    return STEPS[min(count, len(STEPS)) - 1]


def moderatable(member):
    """Can the bot mute this member? (it has the permission and the member is below the bot's top role)"""
    me = member.guild.me
    return bool(me and me.guild_permissions.moderate_members and member.id != member.guild.owner_id
                and member.top_role < me.top_role)


async def strike_user(user_id, reason, bug_id=None):
    member = await get_member(user_id)
    if not member:
        return
    if is_staff(member):
        await modlog(content=f"{E['warn']} **SKIPPED**{EM}·{EM}<@{user_id}> is staff ({reason}).", allowed_mentions=NO_MENTIONS)
        return
    run('INSERT OR IGNORE INTO strikes(user_id,count,updated_at) VALUES(?,0,?)', user_id, now())
    run('UPDATE strikes SET count=count+1, updated_at=? WHERE user_id=?', now(), user_id)
    count = one('SELECT count FROM strikes WHERE user_id=?', user_id)['count']
    step = step_for(count)
    heavy = step in ('kick', 'ban7', 'permban')
    log_id = run('INSERT INTO strike_log(user_id,step,reason,bug_id,at,state) VALUES(?,?,?,?,?,?)',
                 user_id, step, reason, bug_id, now(), 'pending' if heavy else 'done').lastrowid

    if not heavy:
        await dm(user_id, f"{E['warn']} **STRIKE {count}**{EM}·{EM}{ctx.guild.name}\n{reason}\nThis is {LABEL[step]}. The next steps are:\n{LADDER_TEXT}")
        if step == 'timeout' and moderatable(member):
            try:
                await member.timeout(timedelta(milliseconds=DAY), reason=f'Bug-report trolling: {reason}')
            except Exception as e:
                print('timeout', e)
        view, files = strike_card(user_id, count, step, reason, bug_id, False)
        await modlog(view=view, files=files, allowed_mentions=NO_MENTIONS)
        return
    view, files = strike_card(user_id, count, step, reason, bug_id, True, log_id)
    await modlog(view=view, files=files, allowed_mentions=allowed(roles=[cfg.dev_role]))


async def resolve_strike(log_id, confirm, by_user):
    row = one('SELECT * FROM strike_log WHERE id=?', log_id)
    if not row or row['state'] != 'pending':
        return 'Already handled.'
    if not confirm:
        run("UPDATE strike_log SET state='dismissed' WHERE id=?", log_id)
        run('UPDATE strikes SET count=MAX(count-1,0) WHERE user_id=?', row['user_id'])
        return f'Dismissed by <@{by_user}>. Strike removed.'
    g = ctx.guild
    note = f"{E['warn']} **{ACTION[row['step']].upper()}**{EM}·{EM}{g.name}\nRepeated trolling in bug reports: {row['reason']}"
    await dm(row['user_id'], note)
    target = discord.Object(id=int(row['user_id']))
    try:
        if row['step'] == 'kick':
            await g.kick(target, reason=f"Bug-report trolling: {row['reason']}")
        elif row['step'] == 'ban7':
            await g.ban(target, reason=f"7-day ban, bug-report trolling: {row['reason']}")
            add_timer('unban', row['user_id'], now() + 7 * DAY)
        else:
            await g.ban(target, reason=f"Permanent ban, bug-report trolling: {row['reason']}")
    except Exception as e:
        return f'Confirmed by <@{by_user}> but the action failed: {e}. Press Confirm again to retry.'
    run("UPDATE strike_log SET state='done' WHERE id=?", log_id)
    return f"Confirmed by <@{by_user}>. {LABEL[row['step']]} applied."


async def pardon(user_id):
    run('UPDATE strikes SET count=MAX(count-1,0) WHERE user_id=?', user_id)
    m = await get_member(user_id)
    if m and m.timed_out_until and m.timed_out_until > datetime.now(timezone.utc):
        try:
            await m.timeout(None, reason='Pardoned')
        except Exception:
            pass
    r = one('SELECT count FROM strikes WHERE user_id=?', user_id)
    return r['count'] if r else 0


def strike_info(user_id):
    r = one('SELECT count FROM strikes WHERE user_id=?', user_id)
    from bot.core.db import all_
    log = all_('SELECT * FROM strike_log WHERE user_id=? ORDER BY id DESC LIMIT 5', user_id)
    return {'count': r['count'] if r else 0, 'log': log}
