"""/attach: adds one more screenshot or video to a report. Used inside the report post; as often as needed, so a report has no file limit.
It works for everyone who may use slash commands, also when the server does not let them upload files in the forum (the bot uploads it for them)."""
import io

import discord

from bot.core.db import bug_by_id, bug_by_thread, update_bug
from bot.core.perms import level
from bot.discord_ui.card import card, notice
from bot.discord_ui.components import NO_MENTIONS
from bot.features.bugs.forms import safe
from bot.features.bugs.transcript import download, upload_limit

NL = chr(10)


async def command_attach(i, opts):
    thread = i.channel if isinstance(i.channel, discord.Thread) else None
    bug = bug_by_thread(thread.id) if thread else None
    if not bug:
        return await i.response.send_message(view=notice('Use `/attach` inside your report post, so I know which report the file is for.')[0], ephemeral=True)
    staff = level(i.user) in ('admin', 'dev', 'jr')
    if str(i.user.id) != bug['reporter_id'] and not staff:
        return await i.response.send_message(view=notice('Only the person who made this report can add files to it.')[0], ephemeral=True)
    a = opts['file']
    if a['size'] > upload_limit():
        return await i.response.send_message(view=notice(f"That file is too big ({round(a['size'] / 1048576)} MB). The limit is {round(upload_limit() / 1048576)} MB. Post a link instead.")[0], ephemeral=True)
    await i.response.defer(ephemeral=True)
    try:
        data = await download(a['url'])
    except Exception:
        return await i.edit_original_response(view=notice('I could not read that file. Try again.')[0])
    name = f"{int(i.id) % 10000}-{safe(a['filename'])}"
    kind = (a.get('content_type') or '')
    media = {'images' if kind.startswith('image/') else 'videos' if kind.startswith('video/') else 'files': [name]}
    note = (opts.get('note') or '').strip()
    view, files = card(f'📎 Added by {i.user.display_name}', [note] if note else [], right=None, media=media, files=[discord.File(io.BytesIO(data), filename=name)])
    sent = await thread.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    line = f"[{i.user.display_name}] attached {a['filename']}" + (f": {note}" if note else '')
    update_bug(bug['id'], {'body': ((bug.get('body') or '') + NL + line)[-3000:]})
    if not staff and bug['routed'] and bug['status'] in ('new', 'investigating', 'fixing') and not bug['deleted']:
        from bot.features.bugs.intake import add_info
        await add_info(bug_by_id(bug['id']), sent, by=i.user.display_name)
    await i.edit_original_response(view=notice('✅ **Added**' + chr(0x2003) + '·' + chr(0x2003) + f"{a['filename']} is in the post. Use `/attach` again for more.")[0])
