"""The private bug page: one bug at a time, with prev/next, status buttons (only for people who may change them),
a note button and transcripts."""
import re
from datetime import datetime, timezone

import discord

from bot.features.bugs.nums import label
from bot.features.games.bounty import owners_for
from bot.discord_ui.components import FormModal, button, link_button, make_view
from bot.core.ctx import ctx, fetch_channel, thread_link
from bot.core.db import bug_by_id
from bot.features.bugs.devboard import board_components, open_bugs_for
from bot.features.bugs.fixes import apply_status
from bot.features.bugs.media import live_media
from bot.core.perms import can_manage
from bot.features.bugs.tags import applied_ids, device_tags, tag_name
from bot.discord_ui.ui import E, FILLER, FILLER_SHORT, SEVERITY, STATUS, ZW, columns, describe, flat, head, plain


def list_for(key, game):
    return [b for b in open_bugs_for(key) if game == 'all' or (b['game_tag_id'] or 'none') == game]


async def bug_embeds(bug):
    thread = await fetch_channel(bug['thread_id'])
    media = await live_media(thread, bug) if thread else {'text': '', 'images': [], 'videos': []}
    try:
        reporter = await ctx.client.fetch_user(int(bug['reporter_id']))
    except Exception:
        reporter = None
    device_names = [t['name'] for t in device_tags()]
    if bug.get('device'):
        devices = [bug['device']]
    elif thread:
        devices = [n for n in (tag_name(i) for i in applied_ids(thread)) if n in device_names]
    else:
        devices = []
    url = thread_link(bug['thread_id'])
    quote = f"\n\n> {re.sub(r'\n+', '\n> ', media['text'])[:700]}" if media['text'] else ''
    embed = flat()
    embed.url = url
    suggestion = bug.get('kind') == 'suggestion'
    embed.title = head('💡' if suggestion else E['open'], f"{label(bug)} · {bug['game_name'] or 'Unknown game'}")
    embed.set_footer(text=f"{'Suggestion' if suggestion else 'Bug'} {label(bug)} · {'posted' if suggestion else 'reported'}")
    embed.timestamp = datetime.fromtimestamp(bug['created_at'] / 1000, timezone.utc)
    describe(embed, f"### {bug['title']}\n{bug['summary'] or ''}{quote}"[:3900], FILLER_SHORT if media['images'] else FILLER)
    if suggestion:
        status_text = {'new': f"{E['new']} New", 'fixed': f"{E['fixed']} Added", 'declined': '❌ Declined'}.get(bug['status']) or STATUS.get(bug['status'], bug['status'])
        columns(embed, [
            {'name': head(E['status'], 'Status'), 'lines': [status_text, ZW]},
            {'name': head('🙏', 'Votes'), 'lines': [str(bug['votes']), ZW]},
            {'name': head(E['game'], 'Game'), 'lines': [bug['game_name'] or 'Not given', ZW]},
        ], '')
    else:
        columns(embed, [
            {'name': head(E['status'], 'Status'), 'lines': [STATUS.get(bug['status'], bug['status']), ZW]},
            {'name': head(E['severity'], 'Severity'), 'lines': [SEVERITY.get(bug['severity']) or '?', ZW]},
            {'name': head(E['device'], 'Device'), 'lines': [', '.join(devices) or 'Not given', ZW]},
        ], '')  # no rule lines on this page
    if bug.get('low_info'):
        plain(embed, head('⚠️', 'Low info'), 'The player did not give enough details after 3 questions. Look into it yourself, or talk to them in the post.')
    if reporter:
        embed.set_author(name=reporter.display_name, icon_url=reporter.display_avatar.url)
    if media['videos']:
        plain(embed, head(E['video'], 'Videos & media'), '\n'.join(f"[{v['label']}]({v['url']})" for v in media['videos'][:6]))
    embeds = [embed]
    if media['images']:
        embed.set_image(url=media['images'][0])
        for img in media['images'][1:]:
            extra = flat()
            extra.url = url
            extra.set_image(url=img)
            embeds.append(extra)
    return embeds


async def render_view(member, key, game, bug_id):
    """The private page. Returns {'content', 'embeds', 'view'} for send / edit calls."""
    lst = list_for(key, game)
    if not lst:
        return {'content': f"No more open {'suggestions' if key.startswith('S') else 'bugs'} here 🎉", 'embeds': [], 'view': None}
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
    return {'content': f"{'Suggestion' if bug['kind'] == 'suggestion' else 'Bug'} {idx + 1} of {len(lst)}", 'embeds': await bug_embeds(bug), 'view': make_view(rows)}


async def open_game(i, key, game):
    """Game picker on the board message."""
    await i.response.defer(ephemeral=True, thinking=True)
    try:
        await i.message.edit(view=board_components(key))  # resets the picker so the same game can be picked again
    except Exception:
        pass
    lst = list_for(key, game)
    if not lst:
        return await i.edit_original_response(content=f"No open {'suggestions' if key.startswith('S') else 'bugs'} for that game.")
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
