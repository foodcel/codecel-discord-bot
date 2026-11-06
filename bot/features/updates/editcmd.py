"""/update edit (change a posted update) and /update settings (when the dev's AI agent posts, merging, pings)."""
import re

from bot.core.perms import can_manage
from bot.discord_ui.card import notice
from bot.discord_ui.components import FormModal
from bot.features.bugs.tags import tag_name
from bot.features.games.bounty import owners_for
from bot.features.updates import edit
from bot.mcp import writes


def lines_of(text):
    return [line for line in (re.sub(r'^[\s•*\-–]+', '', x).strip() for x in (text or '').split(chr(10))) if line]


def _field(id_, label, style, value='', required=False):
    mx = 3000 if style == 'paragraph' else 40
    return {'id': id_, 'label': label, 'style': style, 'required': required, 'max': mx, 'value': (value or '')[:mx]}


def _mine(member, tag_id):
    return can_manage(member, owners_for(tag_id, tag_name(tag_id) or ''))


def choices_for(member, current):
    """Autocomplete: the latest updates of the games this person manages, as (label, update id)."""
    from bot.features.bugs.tags import game_tags
    tags = [t['id'] for t in game_tags() if _mine(member, t['id'])]
    out = []
    for r in edit.recent(tags, 25):
        f, c, n, _ = edit.lines(r)
        first = (f or c or n or [''])[0]
        label = f"{r['game_name']} · {len(f) + len(c) + len(n)} lines · {first}"[:100]
        if current.lower() in label.lower():
            out.append((label, str(r['id'])))
    return out[:25]


async def command_edit(i, opts):
    row = edit.by_id(opts.get('update') or 0) if str(opts.get('update') or '').isdigit() else None
    if not row:
        return await i.response.send_message(view=notice('Pick an update from the list as you type.')[0], ephemeral=True)
    if not _mine(i.user, row['tag_id']):
        return await i.response.send_message(view=notice('Only the dev who owns this game can edit its updates.')[0], ephemeral=True)
    f, c, n, v = edit.lines(row)
    await i.response.send_modal(FormModal(f"updedit:{row['id']}", 'Edit the update', [
        _field('bugfixes', 'Bug fixes (one per line)', 'paragraph', chr(10).join(f)),
        _field('changes', 'Changes (one per line)', 'paragraph', chr(10).join(c)),
        _field('new', "What's new (one per line)", 'paragraph', chr(10).join(n)),
        _field('version', 'Version (optional)', 'short', v),
    ]))


async def modal_edit(i, id_, fields):
    row = edit.by_id(id_)
    if not row or not _mine(i.user, row['tag_id']):
        return await i.response.send_message(view=notice('That update is not yours to edit.')[0], ephemeral=True)
    await i.response.defer(ephemeral=True)
    ok, msg = await edit.edit_posted(row, lines_of(fields.get('bugfixes')), lines_of(fields.get('changes')), lines_of(fields.get('new')), (fields.get('version') or '').strip())
    if ok:
        from bot.discord_ui import devlog
        await devlog.update_step(int(row['id']) + 1000000, i.user, row['game_name'], 'Edited a posted update.', final='Posted (edited)')
    await i.edit_original_response(view=notice(('✅ **Edited**  ·  ' if ok else '⚠️ **Not edited**  ·  ') + msg)[0])


async def command_settings(i, opts):
    tag_id = opts.get('game')
    if not tag_name(tag_id) or not _mine(i.user, tag_id):
        return await i.response.send_message(view=notice('Pick one of your games.')[0], ephemeral=True)
    changed = any(opts.get(k) not in (None, '') for k in ('mode', 'count', 'merge', 'ping'))
    text = writes.set_settings([(tag_id, tag_name(tag_id))], tag_name(tag_id), opts.get('mode'), opts.get('count'), opts.get('merge'), opts.get('ping'))
    await i.response.send_message(view=notice(('✅ **Saved**  ·  ' if changed else '⚙️ **Update settings**  ·  ') + text)[0], ephemeral=True)
