"""The new giveaway card (D3 with its own banner) in the test channel, once per prize look: podium, prize pool, tiles. Built with the real card code.
Also the new /invites cards. Pings nobody.   python scripts/mockup_giveaway_prizes.py --yes"""
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
    role = lambda name: next((str(r.id) for r in ctx.guild.roles if r.name == name), None)
    prizes, _ = gw.parse_prizes('1-2: 2K Robux + Nitro\n3-5: 2K Robux', 1)
    config = {'prizes': prizes, 'req_roles': [], 'req_mode': 'any', 'blacklist': [], 'bonus': {r: n for r, n in ((role('Server Boost+'), 2), (role('Donator'), 3)) if r},
              'min_invites': 2, 'invite_entries': True, 'invite_cap': 10, 'min_days': 3, 'claim_hours': 24, 'ping': 'none',
              'hosts': [str(owner.id)], 'banner': {'headline': '10K Robux'}, 'prize_style': 'podium'}
    for style, label in (('podium', '**P1 · Podium** · first place as a heading, the others under it'),
                         ('pool', '**P2 · Prize pool** · the total in big letters, then every place'),
                         ('tiles', '**P3 · Tiles** · every place in its own quoted block')):
        g = {'title': '10K Robux giveaway', 'config': {**config, 'prize_style': style}, 'ends_at': now() + 3 * 86400000, 'host_id': str(owner.id)}
        await ch.send(label, allowed_mentions=NO_MENTIONS)
        await ch.send(view=gw.container(g, None, 'draft', 187), files=[gw.banner_for(g)], allowed_mentions=NO_MENTIONS)
    await invites.load()
    for label, (view, files) in (('**/invites stats** · the community look', invites.stats_card(owner)), ('**/invites top** · the community look', invites.top_card(owner.id))):
        await ch.send(label, allowed_mentions=NO_MENTIONS)
        await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    print('done')
    await finish(client)


asyncio.run(main())
