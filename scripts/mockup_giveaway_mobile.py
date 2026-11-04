"""Three phone-friendly looks for the giveaway card, in the test channel. No tree glyphs, short lines that wrap cleanly.   python scripts/mockup_giveaway_mobile.py --yes"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import discord
from discord import ui

from _boot import boot, finish

from bot.botnews import code_chip
from bot.components import NO_MENTIONS
from bot.ctx import fetch_channel
from bot.env import cfg
from bot.giveaway import _end_button
from bot.pngs import with_strip

NL = chr(10)
SMALL = discord.SeparatorSpacing.small
ENDS = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())


def shell(body, footer=None):
    """Header (title + end date), a line, the body, a line, small footer, and the Enter button."""
    items = [ui.Section('### 🎁 10k Robux giveaway', accessory=_end_button(ENDS * 1000)), ui.Separator(visible=True, spacing=SMALL)]
    items += [ui.TextDisplay(b) for b in body]
    items += [ui.Separator(visible=True, spacing=SMALL), ui.TextDisplay(footer or f'-# Hosted by Eric · ends <t:{ENDS}:f> · **187** entered'),
              ui.ActionRow(ui.Button(custom_id='mock:enter', label='Enter', style=discord.ButtonStyle.success, emoji='🎉'))]
    items, strip = with_strip(items)
    view = ui.LayoutView()
    view.add_item(ui.Container(*items))
    return view, [strip]


def design_a():
    """A · Flat: a bold heading per block, one short line per fact with an emoji. Nothing to wrap badly."""
    return shell([
        NL.join(['**Prizes**', '🥇 **1st** · 2k Robux + Nitro', '🥈 **2nd** · 2k Robux + Nitro', '🎁 **3rd to 5th** · 2k Robux each']),
        NL.join(['**To enter**', '✅ Be verified', '📨 Have 3+ invites', '🕓 Be here 3+ days']),
        NL.join(['**More entries**', '⭐ Booster **+2**', '⭐ Donator **+3**', '➕ Every invite **+1** (max 10)']),
        '-# ⏳ Winners claim within 24h',
    ])


def design_b():
    """B · Labels: a small grey label over each block, then plain sentences that wrap like normal text."""
    return shell([
        NL.join(['-# PRIZES', '**1st and 2nd** win 2k Robux + Nitro', '**3rd, 4th and 5th** win 2k Robux each']),
        NL.join(['-# TO ENTER', '✅ Verified · 📨 3+ invites · 🕓 3+ days in the server']),
        NL.join(['-# MORE ENTRIES', '⭐ Booster +2 · ⭐ Donator +3 · ➕ +1 for every invite (max 10)']),
        '-# ⏳ Winners have 24h to claim',
    ])


def design_c():
    """C · Chips: the place or rule in a grey code chip, the prize next to it. Reads like the command chips in the footers."""
    return shell([
        NL.join(['**5 winners**', '`1st–2nd` 2k Robux + Nitro', '`3rd–5th` 2k Robux']),
        NL.join(['**Need**', '`verified` `3+ invites` `3+ days`']),
        NL.join(['**Bonus entries**', '`Booster +2` `Donator +3` `invite +1 (max 10)`']),
        '-# ⏳ Claim within 24h',
    ])


async def main():
    client = await boot(claims=False)
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    for label, build in (('**A · Flat** · a bold heading per block, one short line per fact', design_a),
                         ('**B · Labels** · a small grey label per block, sentences that wrap normally', design_b),
                         ('**C · Chips** · rules and places as grey chips, like the command chips', design_c)):
        view, files = build()
        await ch.send(label, allowed_mentions=NO_MENTIONS)
        await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    print('done')
    await finish(client)


asyncio.run(main())
