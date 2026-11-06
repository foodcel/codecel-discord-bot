"""The dev log: everything a dev does with the bot (commands, buttons, forms, typed status changes, and refused attempts too) is
written to the dev-logs channel, so it can be checked later when something looks wrong.

Slash commands, buttons and forms are recorded in one place, around the interaction handler: the reply the dev got is captured and
shown as the result. Status changes are recorded where they are applied, whichever way they were typed or clicked."""
import asyncio
import contextvars
import json
import re
from datetime import datetime, timezone

import discord

from bot.features.bugs.nums import label
from bot.core.ctx import fetch_channel
from bot.core.db import kv_del, kv_get, kv_set
from bot.core.env import cfg
from bot.core.perms import level
from bot.discord_ui.card import card

_capture = contextvars.ContextVar('devlog_capture', default=None)

# What a refusal looks like in the replies, to mark the entry with ⛔.
_REFUSED = re.compile(r"^(Only |You do not|You cannot|You can't|Pick |Give |The (link|icon|percent)|That (game|bug|report|post)|I do not|"
                      r"Unknown|Nothing|There's no|No games|Someone|Skipped|This (draft|command)|The \w+ must)", re.I)


def _note(text, view=None):
    """Keeps a reply for the log entry: its text, or the text of the card it sent."""
    c = _capture.get()
    if c is None:
        return
    if not (isinstance(text, str) and text) and view is not None and hasattr(view, 'walk_children'):
        text = ' · '.join(x.content for x in view.walk_children() if isinstance(x, discord.ui.TextDisplay))[:500]
    if isinstance(text, str) and text:
        c.append(text)


def install():
    """Lets the replies of a handler be captured (only while an interaction is being recorded)."""
    send_message, edit_message = discord.InteractionResponse.send_message, discord.InteractionResponse.edit_message
    edit_original, webhook_send = discord.Interaction.edit_original_response, discord.Webhook.send

    async def _send_message(self, content=None, *a, **k):
        _note(content, k.get('view'))
        return await send_message(self, content, *a, **k)

    async def _edit_message(self, **k):
        _note(k.get('content'), k.get('view'))
        return await edit_message(self, **k)

    async def _edit_original(self, **k):
        _note(k.get('content'), k.get('view'))
        return await edit_original(self, **k)

    async def _webhook_send(self, content=discord.utils.MISSING, *a, **k):
        _note(content if isinstance(content, str) else None)
        return await webhook_send(self, content, *a, **k)

    discord.InteractionResponse.send_message = _send_message
    discord.InteractionResponse.edit_message = _edit_message
    discord.Interaction.edit_original_response = _edit_original
    discord.Webhook.send = _webhook_send


def begin():
    cap = []
    return cap, _capture.set(cap)


def end(token):
    _capture.reset(token)


# Commands that only show something or open a draft: the log says so, so it never looks like something was changed.
READ_ONLY = {
    '/strikes': 'Looked up only: nothing changed',
    '/config show': 'Looked up only: nothing changed',
    '/preview': 'Posted previews in the test channel: nothing live changed',
    '/botrules': 'Posted the rules message',
}


def _cut(s, n):
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + '…'


async def post(user, title, details='', result=None, ok=True, where=None):
    """Writes one entry. `user` is the member or user who did it."""
    if not cfg.devlog_id:
        return
    try:
        ch = await fetch_channel(cfg.devlog_id)
        if ch is None:
            return
        who = f'<@{user.id}>' + (f' in <#{where}>' if where else '')
        lines = [who] + ([_cut(details, 900)] if details else []) + ([f'**Result** · {_cut(result, 500)}'] if result else [])
        view, files = card(f"{'📋' if ok else '⛔'} {_cut(title, 200)}", ['\n'.join(lines)],
                           [f'{user} · {user.id} · {level(user) if hasattr(user, "guild_permissions") else "?"} · <t:{int(datetime.now(timezone.utc).timestamp())}:T>'])
        await ch.send(view=view, files=files, allowed_mentions=discord.AllowedMentions.none())
    except Exception as ex:
        print('devlog', repr(ex))


def _option(name, v):
    from bot.features.games import board
    from bot.features.bugs.tags import tag_name
    if name in ('user', 'dev', 'owner'):
        return f'<@{v}>'
    if name in ('channel', 'forum'):
        return f'<#{v}>'
    if name == 'role':
        return f'<@&{v}>'
    if name == 'post':
        s = str(v)
        if s.startswith(board.CLAIM) and s[len(board.CLAIM):].isdigit():
            c = board.claim_by_id(int(s[len(board.CLAIM):]))
            return (board.claim_title(c) if c else None) or s
        if s.startswith(board.CUSTOM):
            return f'{s[len(board.CUSTOM):]} (custom game)'
        if s.isdigit():
            p = board.post_by_id(s)
            return p['title'] if p else s
        return s
    if name == 'game' and str(v).isdigit() and tag_name(v):
        return tag_name(v)
    return str(v)


def describe_interaction(i):
    """(title, details, fixed result or None) for an interaction worth logging, or None for reading around (browsing, transcripts, autocomplete)."""
    from bot.core.db import bug_by_id
    from bot.discord_ui.interactions import get_options
    t = i.type
    if t == discord.InteractionType.application_command:
        name = i.data['name']
        if name in ('bug', 'improvement', 'update'):  # a tester's report is not a dev action; /update has its own single entry (update_step)
            return None
        sub, opts, _ = get_options(i)
        from bot.features.games.games import clean_name
        proper = lambda k, v: clean_name(v) if k == 'game' and isinstance(v, str) and name in ('release', 'progress') else v  # the proper name, not the bounty-board post title
        details = '\n'.join(f'**{k}** · {_option(k, proper(k, v))}' for k, v in opts.items() if not isinstance(v, dict))
        title = f'/{name}' + (f' {sub}' if sub else '')
        return title, details, READ_ONLY.get(title)
    parts = (i.data.get('custom_id') or '').split(':')
    kind = parts[0]
    if t == discord.InteractionType.component:
        if kind == 'strike' and len(parts) > 2:
            return f'Strike · {parts[1]}', f'**strike log** · #{parts[2]}', None
        if kind == 'exp' and len(parts) > 2:
            b = bug_by_id(int(parts[1]))
            return f'Exploit card · {parts[2]}', f"**report** · #{parts[1]}" + (f" {b['title']}" if b else ''), None
        return None
    if t == discord.InteractionType.modal_submit:
        from bot.discord_ui.components import modal_fields
        f = modal_fields(i)
        if kind == 'note':
            b = bug_by_id(int(parts[1]))
            return 'Note on a bug', f"**bug** · #{parts[1]}" + (f" {b['title']}" if b else '') + f"\n**note** · {_cut(f.get('note', ''), 400)}", None
    return None


def record(i, captured, error=None):
    """Called after an interaction was handled: writes the entry if it was a dev action."""
    if not cfg.devlog_id:
        return
    try:
        d = describe_interaction(i)
    except Exception as e:
        print('devlog describe', repr(e))
        return
    if not d:
        return
    title, details, fixed = d
    result = fixed or (' / '.join(c.replace('\n', ' ') for c in captured[:3]) if captured else 'No reply: nothing changed')
    ok = error is None and not (captured and not fixed and _REFUSED.match(captured[0]))
    if error is not None:
        result = f'Error: {error!r}'
    asyncio.ensure_future(post(i.user, title, details, result, ok, getattr(i, 'channel_id', None)))


def log_status(member, bug_id, status, bug, outcome, ok, via):
    """A status change (or a refused attempt), however it was made."""
    if not cfg.devlog_id:
        return
    what = (label(bug) if bug else f"#{bug_id}") + (f" · {bug['game_name'] or 'Unknown game'} · {_cut(bug['title'], 80)}" if bug else '')
    kind = (bug or {}).get('kind') or 'bug'
    words = {'fixed': 'ADDED' if kind == 'suggestion' else 'FIXED'}
    title = f"Status · {words.get(status, status.upper().replace('_', ' '))}"
    asyncio.ensure_future(post(member, title, f'**{kind}** · {what}\n**via** · {via}', outcome, ok))


# ---- one entry per update draft ----
# Opening a draft, ticking, editing and posting are one story: they all go into the same log entry, which is edited as it goes
# and ends with the result (posted, or not posted).
_session_locks = {}


def _load_session(pid):
    raw = kv_get(f'devlog:upd:{pid}')
    return json.loads(raw) if raw else None


async def update_step(pid, user, game_name, text, final=None):
    """Adds a step to the log entry of update draft `pid` (made on the first step). `final` closes the entry with that result."""
    if not cfg.devlog_id:
        return
    lock = _session_locks.setdefault(pid, asyncio.Lock())
    async with lock:
        try:
            s = _load_session(pid) or {'mid': None, 'user': str(user.id), 'game': game_name, 'steps': []}
            s['steps'].append([int(datetime.now(timezone.utc).timestamp()), str(user.id), text])
            s['steps'] = s['steps'][-20:]
            if final:
                s['final'] = final
            posted = bool(final) and final.startswith(('Posted', 'Added'))
            title = f"{'📣' if posted else '📋'} " + _cut(f"/update · {s['game']}" + (' · NOT POSTED' if final and not posted else ''), 200)
            status = f'**Result** · {final}' if final else '**Status** · Draft open, nothing posted yet'
            lines = []
            for ts, uid, step in s['steps']:
                who = '' if uid == s['user'] else f' <@{uid}>'
                lines.append(f'<t:{ts}:T>{who} · {_cut(step, 250)}')
            view, files = card(title, [f"<@{s['user']}>\n{status}", '\n'.join(lines)], [f'{user} · {user.id} · draft #{pid}'])
            ch = await fetch_channel(cfg.devlog_id)
            if ch is None:
                return
            msg = None
            if s['mid']:
                try:
                    msg = await ch.fetch_message(int(s['mid']))
                except Exception:
                    msg = None
            if msg:
                await msg.edit(content=None, embeds=[], view=view, attachments=files)
            else:
                msg = await ch.send(view=view, files=files, allowed_mentions=discord.AllowedMentions.none())
                s['mid'] = str(msg.id)
            if final:
                kv_del(f'devlog:upd:{pid}')  # finished: the next action on a new draft starts a new entry
            else:
                kv_set(f'devlog:upd:{pid}', json.dumps(s))
        except Exception as ex:
            print('devlog update', repr(ex))
