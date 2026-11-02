"""The card look for the posts that are still embeds: any embed becomes a card with the title and a date button on the right, a line under the header,
the body, a line above the footer and the commands in small text. Columns become one line per row. Used for the mockups first; a post only switches
when its code builds a card instead of an embed."""
import re
from datetime import datetime

import discord
from discord import ui

from .botnews import code_chip, date_button
from .pngs import width_strip
from .ui import ZW

NL = chr(10)
RULE = re.compile(r'^[\s​_─―‾-]+$')  # a line that is only a rule
SMALL = discord.SeparatorSpacing.small


def _lines(value):
    return [ln for ln in str(value).split(NL) if ln.strip(' ​') and not RULE.match(ln)]


def _table(group):
    """Consecutive inline fields (columns) as one line per row: the headings, then the cells side by side."""
    real = [f for f in group if f.name.strip(' ​') or f.value.strip(' ​')]
    out = []
    for i in range(0, len(real), 3):
        cols = real[i:i + 3]
        heads = [f.name.strip(' ​') for f in cols if f.name.strip(' ​')]
        if heads:
            out.append('**' + '  ·  '.join(heads) + '**')
        cells = [_lines(f.value) for f in cols]
        for k in range(max(len(c) for c in cells)):
            out.append(' · '.join(c[k] for c in cells if k < len(c)))
    return NL.join(out)


def card_from_embed(e, when=None, ping=None):
    """(view, files) for an embed shown as a card. A thumbnail on the embed goes to the right of the title, else the date does."""
    strip_ = width_strip()
    accessory = ui.Thumbnail(e.thumbnail.url) if e.thumbnail and e.thumbnail.url else date_button(when)
    items = []
    if e.title:
        items += [ui.Section(f'### {e.title}', accessory=accessory), ui.Separator(visible=True, spacing=SMALL)]
    if e.description and e.description.strip(' ​'):
        items.append(ui.TextDisplay(e.description.strip()[:3900]))
    fields, i = list(e.fields), 0
    while i < len(fields):
        f = fields[i]
        if f.inline:
            group = []
            while i < len(fields) and fields[i].inline:
                group.append(fields[i])
                i += 1
            text = _table(group)
            if text:
                items.append(ui.TextDisplay(text[:3900]))
            continue
        i += 1
        if f.name.strip(' ​'):
            items.append(ui.TextDisplay(f'**{f.name.rstrip(":")}**{NL}{f.value}'[:3900]))
        elif f.value.strip(' ​'):
            items.append(ui.TextDisplay(f.value[:3900]))
    if e.footer and e.footer.text:
        items += [ui.Separator(visible=True, spacing=SMALL), ui.TextDisplay(NL.join('-# ' + code_chip(x) for x in e.footer.text.split(NL)))]
    view = ui.LayoutView()
    view.add_item(ui.MediaGallery(discord.MediaGalleryItem(strip_)))
    if ping:
        view.add_item(ui.TextDisplay(ping))
    view.add_item(ui.Container(*items))
    return view, [strip_]
