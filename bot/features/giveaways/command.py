"""The /giveaway slash command."""
import re
from bot.features.invites import invites
from bot.discord_ui.components import NO_MENTIONS
from bot.core.db import all_
from bot.features.giveaways.rules import MAX_WINNERS, can_run, parse_duration
from bot.features.giveaways.draw import _g, cancel, end, reroll, valid_pool
from bot.features.giveaways.draft import new_draft, payload
from bot.features.giveaways.stats import stats_card


# ---- the slash command ----
def _pick(value):
    m = re.search(r'\d+', str(value or ''))
    return int(m[0]) if m else None


async def autocomplete(i, fvalue):
    q = str(fvalue or '').lower()
    rows = all_("SELECT id,title,status FROM giveaways WHERE status!='cancelled' ORDER BY id DESC LIMIT 40")
    return [{'name': f"#{r['id']} {r['title']} · {r['status']}"[:100], 'value': str(r['id'])} for r in rows if q in f"{r['id']} {r['title']}".lower()][:25]


async def command_giveaway(i, sub, opts):
    if not can_run(i.user):
        return await i.response.send_message('Only admins and the Giveaway Manager role can run giveaways.', ephemeral=True)
    if sub == 'new':
        seconds = parse_duration(opts.get('duration'))
        if seconds < 60:
            return await i.response.send_message('How long? Write it like `3d`, `12h` or `1d 6h`.', ephemeral=True)
        await i.response.defer(ephemeral=True)
        pid = new_draft(i.user.id, i.channel_id, str(opts['prize']).strip()[:40], min(seconds, 60 * 86400), min(int(opts.get('winners') or 1), MAX_WINNERS))
        return await i.edit_original_response(**payload(pid))
    if sub == 'list':
        await i.response.defer(ephemeral=True)
        rows = all_("SELECT * FROM giveaways WHERE status IN ('running','ended') ORDER BY id DESC LIMIT 10")
        lines = [f"#{r['id']} · **{r['title']}** · {r['status']} · <#{r['channel_id']}> · {len(valid_pool(_g(r['id']))) if r['status'] == 'running' else (_g(r['id'])['result'] or {}).get('eligible', 0)} entered" + (f" · ends <t:{r['ends_at'] // 1000}:f>" if r['status'] == 'running' else '') for r in rows]
        return await i.edit_original_response(content='\n'.join(lines) or 'No giveaways yet.', allowed_mentions=NO_MENTIONS)
    gid = _pick(opts.get('giveaway'))
    if not gid or not _g(gid):
        return await i.response.send_message('Pick a giveaway from the list.', ephemeral=True)
    if sub == 'stats':
        await i.response.defer(ephemeral=True)
        view, files, ids = stats_card(_g(gid))
        return await i.edit_original_response(view=view, attachments=files, allowed_mentions=invites.names_for(ids))
    await i.response.defer(ephemeral=True)
    if sub == 'end':
        text = await end(gid, by=i.user.id)
    elif sub == 'cancel':
        text = await cancel(gid)
    else:
        text = await reroll(gid, opts.get('place'), opts.get('user'))
    await i.edit_original_response(content=text or 'That giveaway is not running.')
