"""The private bug page: one bug at a time, with prev/next, status buttons (only for people who may change them),
a note button and transcripts."""
import re
from datetime import datetime, timezone

import discord
from discord import ui

from bot.discord_ui.card import card, row, stamp
from bot.features.bugs.intake import MAX_ASKS
from bot.features.bugs.nums import label
from bot.features.games.bounty import owners_for
from bot.discord_ui.components import FormModal, button, link_button
from bot.core.ctx import fetch_channel, thread_link
from bot.core.db import bug_by_id
from bot.features.bugs.devboard import board_components, open_bugs_for
from bot.features.bugs.fixes import apply_status
from bot.features.bugs.media import live_media
from bot.core.perms import can_manage
from bot.features.bugs.tags import applied_ids, device_tags, tag_name
from bot.discord_ui.ui import E, SEVERITY, STATUS


NL = chr(10)


def _text_page(text):
    """A one-line page (the bug page is a card, so its edits must stay cards)."""
    view = ui.LayoutView()
    view.add_item(ui.TextDisplay(text))
    return {'content': None, 'embeds': [], 'view': view, 'attachments': []}


def list_for(key, game):
    return [b for b in open_bugs_for(key) if game == 'all' or (b['game_tag_id'] or 'none') == game]


async def bug_embeds(bug, rows=(), counter=''):
    """The page of one report as a card: (view, files). rows: the button rows shown inside it. counter: 'Bug 2 of 5'."""
    thread = await fetch_channel(bug['thread_id'])
    media = await live_media(thread, bug) if thread else {'text': '', 'images': [], 'videos': []}
    device_names = [t['name'] for t in device_tags()]
    if bug.get('device'):
        devices = [bug['device']]
    elif thread:
        devices = [n for n in (tag_name(i) for i in applied_ids(thread)) if n in device_names]
    else:
        devices = []
    quote = f"> {re.sub(r'\n+', '\n> ', media['text'])[:700]}" if media['text'] else ''
    suggestion = bug.get('kind') == 'suggestion'
    if suggestion:
        status_text = {'new': f"{E['new']} New", 'fixed': f"{E['fixed']} Added", 'declined': '❌ Declined'}.get(bug['status']) or STATUS.get(bug['status'], bug['status'])
        facts = [row('Game', bug['game_name'] or 'Not given'), row('Status', status_text), row('Votes', str(bug['votes'])),
                 row('Posted by', f"<@{bug['reporter_id']}>")]
    else:
        facts = [row('Game', bug['game_name'] or 'Unknown game'), row('Status', STATUS.get(bug['status'], bug['status'])),
                 row('Severity', SEVERITY.get(bug['severity']) or '?'), row('Device', ', '.join(devices) or 'Not given'),
                 row('Reported by', f"<@{bug['reporter_id']}>")]
    blocks = [bug['summary'] or '', quote, NL.join(facts)]
    if bug.get('low_info'):
        blocks.append(f"**⚠️ Low info**{NL}The player did not give enough details after {MAX_ASKS} questions. Look into it yourself, or talk to them in the post.")
    if media['videos']:
        blocks.append(f"**{E['video']} Videos & media**{NL}" + NL.join(f"[{v['label']}]({v['url']})" for v in media['videos'][:6]))
    icon = '💡' if suggestion else E['open']
    foot = f"{counter} · " if counter else ''
    return card(f"{icon} {label(bug)} · {bug['title']}"[:200], blocks, [f"{foot}{'posted' if suggestion else 'reported'} {stamp(bug['created_at'])}"],
                gallery=media['images'], inside=rows, when=datetime.fromtimestamp(bug['created_at'] / 1000, timezone.utc))


async def render_view(member, key, game, bug_id):
    """The private page. Returns {'content', 'embeds', 'view'} for send / edit calls."""
    lst = list_for(key, game)
    if not lst:
        return _text_page(f"No more open {'suggestions' if key.startswith('S') else 'bugs'} here 🎉")
    idx = next((i for i, b in enumerate(lst) if b['id'] == bug_id), -1)
    if idx < 0:
        nxt = next((i for i, b in enumerate(lst) if b['id'] > bug_id), -1)
        idx = len(lst) - 1 if nxt < 0 else nxt
    bug = lst[idx]

    def cid(act, extra=''):
        return f"v:{act}:{key}:{game}:{bug['id']}{extra}"

    rows = [[
        button(cid('p'), '◀ Prev', discord.ButtonStyle.secondary, idx == 0),
        button('v:noop', f'{idx + 1} / {len(lst)}', discord.ButtonStyle.secondary, True),
        button(cid('n'), 'Next ▶', discord.ButtonStyle.secondary, idx == len(lst) - 1),
    ]]
    manage = can_manage(member, owners_for(bug['game_tag_id'], bug['game_name']))
    if manage and bug['kind'] == 'suggestion':
        rows.append([
            button(cid('st', ':fixed'), '✅ Added', discord.ButtonStyle.success),
            button(cid('st', ':declined'), '❌ Declined'),
            button(cid('st', ':duplicate'), f"{E['duplicate']} Duplicate"),
        ])
    elif manage:
        rows.append([
            button(cid('st', ':investigating'), '🔎 Investigating'),
            button(cid('st', ':fixing'), '🛠️ Fixing'),
            button(cid('st', ':fixed'), '✅ Fixed', discord.ButtonStyle.success),
            button(cid('st', ':not_a_bug'), f"{E['notbug']} Not a bug"),
            button(cid('st', ':duplicate'), f"{E['duplicate']} Duplicate"),
        ])
    tools = [button(f"tr:{bug['id']}", '📋 Transcript', discord.ButtonStyle.primary)]
    if manage:
        tools.append(button(cid('note'), '🎮 Set game / add note'))
    tools.append(link_button('Open post', thread_link(bug['thread_id'])))
    rows.append(tools)
    view, files = await bug_embeds(bug, [ui.ActionRow(*r) for r in rows if r], f"{'Suggestion' if bug['kind'] == 'suggestion' else 'Bug'} {idx + 1} of {len(lst)}")
    return {'content': None, 'embeds': [], 'view': view, 'attachments': files}


async def open_game(i, key, game):
    """Game picker on the board message."""
    await i.response.defer(ephemeral=True, thinking=True)
    try:
        await i.message.edit(view=board_components(key))  # resets the picker so the same game can be picked again
    except Exception:
        pass
    lst = list_for(key, game)
    if not lst:
        return await i.edit_original_response(**_text_page(f"No open {'suggestions' if key.startswith('S') else 'bugs'} for that game."))
    return await i.edit_original_response(**await render_view(i.user, key, game, lst[0]['id']))


async def handle_view(i):
    """Buttons inside the private page: v:<act>:<key>:<game>:<bugId>[:<status>]"""
    parts = i.data['custom_id'].split(':')
    act = parts[1]
    if act == 'noop':
        return await i.response.defer()
    key, game, bug_id = parts[2], parts[3], int(parts[4])
    status = parts[5] if len(parts) > 5 else None
    if act == 'note':  # a form must open before any deferral
        bug = bug_by_id(bug_id)
        if not bug or not can_manage(i.user, owners_for(bug['game_tag_id'], bug['game_name'])):
            return await i.response.send_message('You cannot change this bug.', ephemeral=True)
        return await i.response.send_modal(FormModal(f'note:{bug_id}', f'Note for bug {label(int(bug_id))}', [{
            'id': 'note', 'label': 'Tell the bot what this is', 'style': 'paragraph', 'required': True, 'max': 500,
            'placeholder': 'e.g. This is Vyra Station. Happens on PS5 only.'}]))
    await i.response.defer()
    if act in ('p', 'n'):
        lst = list_for(key, game)
        idx = max(0, next((k for k, b in enumerate(lst) if b['id'] == bug_id), -1))
        target = lst[min(len(lst) - 1, max(0, idx + (1 if act == 'n' else -1)))] if lst else None
        return await i.edit_original_response(**await render_view(i.user, key, game, target['id'] if target else bug_id))
    if act == 'st':
        done, skipped = await apply_status([bug_id], status, i.user, via='bug page')
        if not done:
            await i.followup.send(f"Could not change {label(int(bug_id))}: {skipped[0] if skipped else 'unknown'}", ephemeral=True)
        return await i.edit_original_response(**await render_view(i.user, key, game, bug_id))
