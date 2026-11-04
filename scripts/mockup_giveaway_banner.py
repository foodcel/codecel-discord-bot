"""Three giveaway looks with the Redwing banner, in the test channel. D1 has two columns in a card (text left, value in a grey pill on the right),
D2 is an embed with three real columns, D3 is a banner-first poster with chips. Pings nobody.   python scripts/mockup_giveaway_banner.py --yes"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import discord
from discord import ui

from _boot import boot, finish

from bot.banner import banner_file
from bot.components import NO_MENTIONS
from bot.ctx import fetch_channel
from bot.env import cfg
from bot.giveaway import _end_button

NL = chr(10)
SMALL = discord.SeparatorSpacing.small
ENDS = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())
RED = 0xD61820


def pill(text, n):
    """A grey, switched-off button: the only thing a card can put on the right of a line."""
    return ui.Button(style=discord.ButtonStyle.secondary, label=text[:80], disabled=True, custom_id=f'p{n}')


def row(left, right, n):
    return ui.Section(left, accessory=pill(right, n))


def card(items):
    view = ui.LayoutView()
    view.add_item(ui.Container(*items))
    return view


def enter_row():
    return ui.ActionRow(ui.Button(custom_id='mock:enter', label='Enter giveaway', style=discord.ButtonStyle.success, emoji='🎉'))


def d1():
    """D1 · Scoreboard: banner, then two columns. The line's name on the left, its value in a pill on the right."""
    file = banner_file('GIVEAWAY', 'Win Robux, Nitro and more', 'ENTER BELOW')
    items = [ui.MediaGallery(discord.MediaGalleryItem(file)),
             ui.Section(f'### 10k Robux giveaway{NL}-# Hosted by Eric · **187** entered', accessory=_end_button(ENDS * 1000)),
             ui.Separator(visible=True, spacing=SMALL),
             ui.TextDisplay('**Prizes**'),
             row('🥇 **1st and 2nd**', '2k Robux + Nitro', 1), row('🎁 **3rd to 5th**', '2k Robux each', 2),
             ui.TextDisplay('**To enter**'),
             row('✅ Verified', 'required', 3), row('📨 Invites', '3 or more', 4), row('🕓 In the server', '3+ days', 5),
             ui.TextDisplay('**More entries**'),
             row('⭐ Booster', '+2', 6), row('⭐ Donator', '+3', 7), row('➕ Every invite', '+1 (max 10)', 8),
             ui.Separator(visible=True, spacing=SMALL),
             ui.TextDisplay(f'-# ⏳ Winners claim within 24h · ends <t:{ENDS}:f>'),
             enter_row()]
    return {'view': card(items), 'files': [file]}


def d2():
    """D2 · Columns: a real embed. Three columns side by side, the banner closing it, the button under it."""
    file = banner_file('GIVEAWAY', 'Win Robux, Nitro and more', 'ENTER BELOW', filename='giveaway2.png')
    e = discord.Embed(title='🎁 10k Robux giveaway', color=RED, description=f'**5 winners** · ends <t:{ENDS}:f> · **187** entered')
    e.add_field(name='🏆 Prizes', value='🥇 **1st–2nd**\n2k Robux + Nitro\n\n🎁 **3rd–5th**\n2k Robux', inline=True)
    e.add_field(name='✅ To enter', value='Verified\n\n📨 3+ invites\n\n🕓 3+ days here', inline=True)
    e.add_field(name='⭐ Bonus entries', value='Booster **+2**\n\nDonator **+3**\n\nEach invite **+1**\n-# max 10', inline=True)
    e.set_footer(text='Hosted by Eric · Winners claim within 24h')
    e.set_image(url='attachment://giveaway2.png')
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(custom_id='mock:enter', label='Enter giveaway', style=discord.ButtonStyle.success, emoji='🎉'))
    return {'embed': e, 'file': file, 'view': view}


def d3():
    """D3 · Poster: the banner carries the prize, then one big facts line, short blocks and grey chips."""
    file = banner_file('10K ROBUX', '5 winners · ends Nov 8', 'ENTER BELOW', filename='giveaway3.png')
    items = [ui.MediaGallery(discord.MediaGalleryItem(file)),
             ui.TextDisplay(f'**5** winners  ·  **187** entered  ·  ends <t:{ENDS}:R>'),
             ui.Separator(visible=True, spacing=SMALL),
             ui.TextDisplay(NL.join(['🥇 **1st and 2nd** · 2k Robux + Nitro', '🎁 **3rd to 5th** · 2k Robux each'])),
             ui.TextDisplay(NL.join(['**Need**', '`verified` `3+ invites` `3+ days in server`'])),
             ui.TextDisplay(NL.join(['**Bonus entries**', '`Booster +2` `Donator +3` `each invite +1 (max 10)`'])),
             ui.Separator(visible=True, spacing=SMALL),
             ui.TextDisplay('-# Hosted by Eric · Winners claim within 24h'),
             enter_row()]
    return {'view': card(items), 'files': [file]}


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    for label, build in (('**D1 · Scoreboard** · banner, then two columns: the name left, its value in a grey pill right', d1),
                         ('**D2 · Columns** · a real embed with three side-by-side columns, the banner at the bottom', d2),
                         ('**D3 · Poster** · the banner carries the prize, then a facts line, short blocks and chips', d3)):
        kw = build()
        await ch.send(label, allowed_mentions=NO_MENTIONS)
        await ch.send(allowed_mentions=NO_MENTIONS, **kw)
    print('done')
    await finish(client)


asyncio.run(main())
