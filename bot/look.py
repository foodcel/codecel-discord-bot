"""The card look for the posts that are still embeds: any embed becomes a card with the title and a date button on the right, a line under the header,
the body, a line above the footer and the commands in small text. Columns become one line per row, with the blank line between devs kept. A post with side-by-side columns (the bug page, the fix log) stays an embed.
Used for the mockups first; a post only switches when its code builds a card instead of an embed."""
import re

import discord
from discord import ui

from .botnews import code_chip, date_button
from .pngs import width_strip

NL = chr(10)
ZWS = '​'
RULE = re.compile(r'^[\s​_─―‾-]+$')  # a line that is only a rule
SMALL = discord.SeparatorSpacing.small


def _blank(s):
    return not str(s).strip(' ' + ZWS)


def _cells(value):
    """The lines of a column, kept in place (an empty one is a gap), without the rule line under the heading."""
    lines = str(value).split(NL)
    if lines and RULE.match(lines[0]):
        lines = lines[1:]
    return ['' if _blank(ln) else ln for ln in lines]


def _plain(s):
    return re.sub(r'\s+', ' ', re.sub(r'[*`_]', '', str(s))).strip()


def _row_lines(cols):
    """Rows for columns of a list: the cells side by side, an all-empty row stays as a blank line (the gap between two devs)."""
    out = []
    for k in range(max(len(c) for c in cols)):
        parts = [c[k] for c in cols if k < len(c) and c[k]]
        out.append(' · '.join(parts))
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return out


def _table(group):
    """Consecutive inline fields (columns), three to a row like Discord lays them out; the empty fillers are dropped after that."""
    out = []
    for i in range(0, len(group), 3):
        part = [f for f in group[i:i + 3] if not (_blank(f.name) and _blank(f.value))]
        if not part:
            continue
        cols = [_cells(f.value) for f in part]
        heads = [f.name.strip(' ' + ZWS) for f in part]
        if any(heads):
            out.append('**' + '  ·  '.join(h for h in heads if h) + '**')
        out += _row_lines(cols)
    return NL.join(out)


def _spaced(value):
    """A long list of people: one blank line before each next person (a line that starts with a mention)."""
    out = []
    for ln in str(value).split(NL):
        if ln.startswith('<@') and out and out[-1].strip(' ' + ZWS):
            out.append('')
        out.append(ln)
    return NL.join(out)


def card_from_embed(e, when=None, ping=None, inline_desc=False, plain_count=False):
    """(view, files) for an embed shown as a card. A thumbnail on the embed goes to the right of the title, else the date does.
    inline_desc: the first line of the description (the counts) moves into the title; plain_count drops the emoji in front of it."""
    strip_ = width_strip()
    title, desc = e.title or '', (e.description or '').strip(' ' + ZWS + NL)
    if inline_desc and desc:
        first, _, desc = desc.partition(NL)
        first = re.sub(r'[*]', '', first).strip()
        if plain_count:
            first = re.sub(r'^[^A-Za-z0-9]+', '', first)
        title = f'{title} · {first}'
        desc = desc.strip(' ' + ZWS + NL)
    accessory = ui.Thumbnail(e.thumbnail.url) if e.thumbnail and e.thumbnail.url else (date_button(when) if len(title) <= 44 else None)
    items = []
    if title:
        items.append(ui.Section(f'### {title}', accessory=accessory) if accessory else ui.TextDisplay(f'### {title}'))
        items.append(ui.Separator(visible=True, spacing=SMALL))
    if desc:
        items.append(ui.TextDisplay(desc[:3900]))
    fields, i = list(e.fields), 0
    while i < len(fields):
        f = fields[i]
        if f.inline:
            group = []
            while i < len(fields) and fields[i].inline:
                group.append(fields[i])
                i += 1
            text = _table(group)
            if text.strip():
                items.append(ui.TextDisplay(text[:3900]))
            continue
        i += 1
        if not _blank(f.name):
            items.append(ui.TextDisplay(f'**{f.name.rstrip(":")}**{NL}{_spaced(f.value)}'[:3900]))
        elif not _blank(f.value):
            items.append(ui.TextDisplay(_spaced(f.value)[:3900]))
    if e.footer and e.footer.text:
        items += [ui.Separator(visible=True, spacing=SMALL), ui.TextDisplay(NL.join('-# ' + code_chip(x) for x in e.footer.text.split(NL)))]
    view = ui.LayoutView()
    view.add_item(ui.MediaGallery(discord.MediaGalleryItem(strip_)))
    if ping:
        view.add_item(ui.TextDisplay(ping))
    view.add_item(ui.Container(*items))
    return view, [strip_]
