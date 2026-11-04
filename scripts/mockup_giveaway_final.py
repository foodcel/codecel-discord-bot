"""Clears the test channel and shows the giveaway as it is now: the running card, the /giveaway new preview (live buttons), the ended card, what only you see
after pressing Enter or My entries, and the two /invites cards (no banner). Pings nobody.   python scripts/mockup_giveaway_final.py --yes"""
import asyncio
import sys

from discord import ui

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
    await ch.purge(limit=None, bulk=True, reason='Giveaway mockups')
    owner = ctx.guild.get_member(ctx.guild.owner_id)
    role = lambda name: next((str(r.id) for r in ctx.guild.roles if r.name == name), None)
    prizes, _ = gw.parse_prizes('1-2: 2K Robux + Nitro\n3-5: 2K Robux', 1)
    config = {'prizes': prizes, 'req_roles': [], 'req_mode': 'any', 'blacklist': [], 'bonus': {r: n for r, n in ((role('Server Boost+'), 2), (role('Donator'), 3)) if r},
              'min_invites': 2, 'invite_entries': True, 'invite_cap': 10, 'min_days': 3, 'claim_hours': 24, 'ping': 'none',
              'hosts': [str(owner.id)], 'banner': {'headline': '10K Robux'}}
    g = {'id': 0, 'title': '10K Robux giveaway', 'config': config, 'ends_at': now() + 3 * 86400000, 'host_id': str(owner.id), 'status': 'running'}
    send = lambda text: ch.send(text, allowed_mentions=NO_MENTIONS)

    await send('**1 · The giveaway** · Enter giveaway and My entries under it (a mockup: the buttons only say so here)')
    await ch.send(view=gw.container(g, None, 'draft', 187), files=[gw.banner_for(g)], allowed_mentions=NO_MENTIONS)

    await send('**2 · What only you see after pressing Enter giveaway** (a mockup of that private message)')
    lines = ['**You are in with 6 entries**', '+1 · for entering', f"+2 · <@&{role('Server Boost+')}>" if role('Server Boost+') else '+2 · Booster',
             '+3 · your invites (3 count, up to 10)', '', '-# It is checked again when the giveaway ends.']
    view = ui.LayoutView()
    view.add_item(ui.TextDisplay('\n'.join(lines)))
    view.add_item(ui.ActionRow(ui.Button(custom_id='mock:leave', label='Leave giveaway', style=gw.discord.ButtonStyle.danger)))
    await ch.send(view=view, allowed_mentions=NO_MENTIONS)

    await send('**3 · What only you see after pressing My entries** when you have not entered yet')
    view = ui.LayoutView()
    view.add_item(ui.TextDisplay('You have not entered yet. You would get **4 entries**.'))
    view.add_item(ui.ActionRow(ui.Button(custom_id='mock:enter', label='Enter giveaway', style=gw.discord.ButtonStyle.success, emoji='🎉')))
    await ch.send(view=view, allowed_mentions=NO_MENTIONS)

    await send('**4 · /giveaway new preview** · live: every button works, Start posts it here with no ping')
    pid = gw.new_draft(owner.id, ch.id, '10K Robux', 3 * 86400, 5)
    d = gw.get_pending(pid)
    d.update(prizes=prizes, bonus=config['bonus'], min_invites=2, invite_entries=True, invite_cap=10, min_days=3, claim_hours=24)
    gw.set_pending(pid, d)
    p = gw.payload(pid)
    await ch.send(view=p['view'], files=p['attachments'], allowed_mentions=NO_MENTIONS)

    await send('**5 · A finished giveaway**')
    res = {'seeds': ['9f3a1c7be20d44aa'], 'history': [], 'eligible': 212, 'entries': 640,
           'winners': [{'place': k, 'user': str(owner.id), 'prizes': prizes[k - 1], 'state': st, 'round': 0}
                       for k, st in ((1, 'claimed'), (2, 'pending'), (3, 'pending'), (4, 'pending'), (5, 'pending'))]}
    ended = {**g, 'status': 'ended', 'result': res}
    await ch.send(view=gw.container(ended, None, 'ended', 187), files=[gw.banner_for(ended, ended=True)], allowed_mentions=NO_MENTIONS)

    await invites.load()
    sample = [('Robin', 24, 31), ('Asher', 19, 22), ('Kasoku', 15, 18), ('Crab', 12, 14), ('Eggdog', 9, 12), ('Santo', 8, 9), ('tim', 6, 8), ('Itel dev', 5, 5), ('ice cube', 3, 4), ('yo', 2, 3)]
    stats = {'score': 12, 'unverified': 3, 'left': 2, 'joined': 17, 'uses': 21}
    for label, (view, files) in (('**6 · /invites stats** · an example with real-looking numbers', invites.stats_card(owner, s=stats, rank=4)),
                                 ('**7 · /invites top** · an example (ten people, you are 14th)', invites.top_card(rows=sample + [('a', 2, 2)] * 3 + [(owner.display_name, 1, 1)], mine=14, total=105))):
        await send(label)
        await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    print('done')
    await finish(client)


asyncio.run(main())
