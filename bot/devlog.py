"""The dev log: everything a dev does with the bot (commands, buttons, forms, typed status changes, and refused attempts too) is
written to the dev-logs channel, so it can be checked later when something looks wrong.

Slash commands, buttons and forms are recorded in one place, around the interaction handler: the reply the dev got is captured and
shown as the result. Status changes are recorded where they are applied, whichever way they were typed or clicked."""
import asyncio
import contextvars
import re
from datetime import datetime, timezone

import discord

from .ctx import fetch_channel
from .env import cfg
from .perms import level
from .ui import describe, flat, head

_capture = contextvars.ContextVar('devlog_capture', default=None)

# What a refusal looks like in the replies, to mark the entry with ⛔.
_REFUSED = re.compile(r"^(Only |You do not|You cannot|You can't|Pick |Give |The (link|icon|percent)|That (game|bug|report|post)|I do not|"
                      r"Unknown|Nothing|There's no|No games|Someone|Skipped|This (draft|command)|The \w+ must)", re.I)


def _note(text):
    c = _capture.get()
    if c is not None and isinstance(text, str) and text:
        c.append(text)


def install():
    """Lets the replies of a handler be captured (only while an interaction is being recorded)."""
    send_message, edit_message = discord.InteractionResponse.send_message, discord.InteractionResponse.edit_message
    edit_original, webhook_send = discord.Interaction.edit_original_response, discord.Webhook.send

    async def _send_message(self, content=None, *a, **k):
        _note(content)
        return await send_message(self, content, *a, **k)

    async def _edit_message(self, **k):
        _note(k.get('content'))
        return await edit_message(self, **k)

    async def _edit_original(self, **k):
        _note(k.get('content'))
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
        e = flat()
        e.title = head('📋' if ok else '⛔', _cut(title, 230))
        who = f'<@{user.id}>' + (f' in <#{where}>' if where else '')
        lines = [who]
        if details:
            lines.append(_cut(details, 900))
        if result:
            lines.append(f'**Result** · {_cut(result, 500)}')
        describe(e, '\n'.join(lines))
        e.timestamp = datetime.now(timezone.utc)
        e.set_footer(text=f'{user} · {user.id} · {level(user) if hasattr(user, "guild_permissions") else "?"}')
        await ch.send(embeds=[e], allowed_mentions=discord.AllowedMentions.none())
    except Exception as ex:
        print('devlog', repr(ex))


def _option(name, v):
    from . import board
    from .tags import tag_name
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
    """(title, details) for an interaction worth logging, or None for reading around (browsing, transcripts, autocomplete)."""
    from .db import bug_by_id, get_pending
    from .interactions import get_options
    t = i.type
    if t == discord.InteractionType.application_command:
        name = i.data['name']
        if name == 'bug':  # a tester's report, not a dev action
            return None
        sub, opts, _ = get_options(i)
        details = '\n'.join(f'**{k}** · {_option(k, v)}' for k, v in opts.items() if not isinstance(v, dict))
        return f'/{name}' + (f' {sub}' if sub else ''), details
    parts = (i.data.get('custom_id') or '').split(':')
    kind = parts[0]
    if t == discord.InteractionType.component:
        if kind == 'ann' and len(parts) > 2:
            p = get_pending(int(parts[2]))
            game = _option('game', p['tagId']) if p else '?'
            return f'Announcement · {parts[1]}', f'**game** · {game}'
        if kind == 'strike' and len(parts) > 2:
            return f'Strike · {parts[1]}', f'**strike log** · #{parts[2]}'
        if kind == 'exp' and len(parts) > 2:
            b = bug_by_id(int(parts[1]))
            return f'Exploit card · {parts[2]}', f"**report** · #{parts[1]}" + (f" {b['title']}" if b else '')
        return None
    if t == discord.InteractionType.modal_submit:
        from .components import modal_fields
        f = modal_fields(i)
        if kind == 'upd':
            return 'Update posted as draft', f"**game** · {_option('game', parts[1])}\n**updates** · {_cut(f.get('updates', ''), 300)}"
        if kind == 'annedit':
            return 'Announcement edited', f"**version** · {f.get('version') or '-'}\n**updates** · {_cut(f.get('updates', ''), 300)}"
        if kind == 'note':
            b = bug_by_id(int(parts[1]))
            return 'Note on a bug', f"**bug** · #{parts[1]}" + (f" {b['title']}" if b else '') + f"\n**note** · {_cut(f.get('note', ''), 400)}"
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
    title, details = d
    result = ' / '.join(c.replace('\n', ' ') for c in captured[:3]) if captured else None
    ok = error is None and not (result and _REFUSED.match(captured[0]))
    if error is not None:
        result = f'Error: {error!r}'
    asyncio.ensure_future(post(i.user, title, details, result, ok, getattr(i, 'channel_id', None)))


def log_status(member, bug_id, status, bug, outcome, ok, via):
    """A status change (or a refused attempt), however it was made."""
    if not cfg.devlog_id:
        return
    what = f"#{bug_id}" + (f" · {bug['game_name'] or 'Unknown game'} · {_cut(bug['title'], 80)}" if bug else '')
    kind = (bug or {}).get('kind') or 'bug'
    words = {'fixed': 'ADDED' if kind == 'suggestion' else 'FIXED'}
    title = f"Status · {words.get(status, status.upper().replace('_', ' '))}"
    asyncio.ensure_future(post(member, title, f'**{kind}** · {what}\n**via** · {via}', outcome, ok))
