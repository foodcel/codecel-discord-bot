"""/giveaway stats: how many new members a giveaway brought."""
from bot.features.invites import invites
from bot.core.ctx import ctx
from bot.core.db import all_, now
from bot.core.env import cfg
from bot.features.giveaways.rules import NL, _has
from bot.features.giveaways.draw import valid_pool


# ---- what a giveaway brought ----
def stats_card(g):
    """(view, files, ids mentioned). The new members since the giveaway started (the invite tracker's joins), where they came from, and who of them entered.
    The tracker only knows joins since it started, and cannot tell who joined because of the giveaway: these are all new members in the same hours."""
    gid, t0 = g['id'], g['created_at']
    t1 = min(now(), g['ends_at']) if g['status'] == 'ended' else now()
    rows = all_('SELECT * FROM invite_joins WHERE joined_at>=? AND joined_at<=? ORDER BY joined_at', t0, t1)
    entered = {r['user_id'] for r in all_('SELECT user_id FROM giveaway_entries WHERE gid=?', gid)}
    members = {r['user_id']: ctx.guild.get_member(int(r['user_id'])) for r in rows}
    here = [r for r in rows if members[r['user_id']]]
    verified = [r for r in here if _has(members[r['user_id']], cfg.verified_role)]
    by_person = {}
    for r in rows:
        if r['inviter_id']:
            by_person[r['inviter_id']] = by_person.get(r['inviter_id'], 0) + 1
    top = sorted(by_person.items(), key=lambda x: -x[1])[:5]
    hours = max(1, (t1 - t0) // 3600000)
    first = (all_('SELECT MIN(joined_at) m FROM invite_joins') or [{}])[0].get('m')
    before = None
    if first and first <= t0 - (t1 - t0):  # the tracker was already running for a whole window before: a fair comparison
        before = len(all_('SELECT 1 FROM invite_joins WHERE joined_at>=? AND joined_at<?', t0 - (t1 - t0), t0))
    valid = len(valid_pool(g)) if g['status'] == 'running' else (g['result'] or {}).get('eligible', 0)
    head = f"## 📊 Giveaway stats{NL}-# {g['title']} · <t:{t0 // 1000}:f> to {'now' if g['status'] != 'ended' else f'<t:{t1 // 1000}:f>'} · {hours}h"
    body = [NL.join([f"**New members** · {len(rows)}",
                     f"├─ ✅ **{len(verified)}** still here and verified",
                     f"├─ 🕓 **{len(here) - len(verified)}** here, not verified yet",
                     f"└─ 🚪 **{len(rows) - len(here)}** already left"]),
            NL.join(["**Where they came from**",
                     f"├─ 🔗 **{sum(by_person.values())}** through a member's link, from **{len(by_person)}** people",
                     f"└─ 🌐 **{len(rows) - sum(by_person.values())}** through the vanity link or a link that is gone (nobody to credit)"]),
            NL.join(["**The giveaway**",
                     f"├─ 🎟️ **{len(entered)}** pressed Enter · **{valid}** qualify",
                     f"├─ 👥 **{sum(1 for u in by_person if u in entered)}** of the **{len(by_person)}** inviters entered",
                     f"└─ 🙋 **{sum(1 for r in rows if r['user_id'] in entered)}** new members entered"])]
    if top:
        body.append(NL.join(['**Most new members through their link**'] + [f"{'└─' if k == len(top) - 1 else '├─'} <@{u}> · {n}" for k, (u, n) in enumerate(top)]))
    if before is not None:
        body.append(f"**Before it**{NL}{before} new members in the {hours}h before it started, so {len(rows)} during it.")
    body.append(f"-# Tracking started <t:{first // 1000}:f>. These are all new members in the same hours: Discord cannot say who joined because of the giveaway." if first else '-# Tracking has not seen a join yet.')
    view, files = invites._card(head, body, ['/invites check · look at one member'])
    return view, files, [u for u, _ in top]
