"""Shows the giveaway look in the test channel: the preview draft (its buttons work, Start posts in the test channel), a finished giveaway card, and the invite cards.
Posts nothing anywhere else and pings nobody.   python scripts/show_giveaway.py --yes"""
import asyncio
import sys

from _boot import boot, finish

from bot import giveaway as gw
from bot import invites
from bot.components import NO_MENTIONS
from bot.ctx import ctx, fetch_channel
from bot.db import now
from bot.env import cfg


async def main():
    client = await boot(members=True, claims=False)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    owner = ctx.guild.get_member(ctx.guild.owner_id)
    await invites.load()

    # 1. the preview draft, filled in like the example
    pid = gw.new_draft(owner.id, ch.id, '10k Robux giveaway', 3 * 86400, 5)
    d = gw.get_pending(pid)
    prizes, _ = gw.parse_prizes('1: 2k Robux + Nitro\n2: 2k Robux + Nitro\n3-5: 2k Robux', 5)
    booster = next((r for r in ctx.guild.roles if r.name == 'Server Boost+'), None)
    donator = next((r for r in ctx.guild.roles if r.name == 'Donator'), None)
    d.update(prize_text='1: 2k Robux + Nitro\n2: 2k Robux + Nitro\n3-5: 2k Robux', prizes=prizes, invite_entries=True, invite_cap=10, min_invites=3, claim_hours=24,
             min_days=3, bonus={str(r.id): n for r, n in ((booster, 2), (donator, 3)) if r}, ping='none')
    gw.set_pending(pid, d)
    await ch.send('**Giveaway preview** · every button works; Start posts it in this channel (no ping)', allowed_mentions=NO_MENTIONS)
    p = gw.payload(pid)
    await ch.send(view=p['view'], files=p['attachments'], allowed_mentions=NO_MENTIONS)

    # 2. a finished giveaway (a static example, no buttons)
    me = owner.id
    res = {'seeds': ['9f3a1c7be20d44aa'], 'history': [], 'eligible': 212, 'entries': 640,
           'winners': [{'place': k, 'user': str(me), 'prizes': prizes[k - 1], 'state': st, 'round': 0}
                       for k, st in ((1, 'claimed'), (2, 'pending'), (3, 'pending'), (4, 'forfeit'), (5, 'pending'))]}
    g = {'title': '10k Robux giveaway', 'config': gw._config(d), 'ends_at': now(), 'host_id': str(me), 'result': res}
    view, files = gw.container(g, None, 'ended', 187)
    await ch.send('**A finished giveaway (example)**', allowed_mentions=NO_MENTIONS)
    await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)

    # 3. the invite cards
    view, files = invites.stats_card(owner)
    await ch.send('**/invites stats**', allowed_mentions=NO_MENTIONS)
    await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    view, files = invites.top_card(owner.id)
    await ch.send('**/invites top** (empty until people join: the tracker only knows joins from now on)', allowed_mentions=NO_MENTIONS)
    await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    print('done')
    await finish(client)


asyncio.run(main())
