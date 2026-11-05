"""The card look for the posts that are still embeds: any embed becomes a card with the title and a date button on the right, a line under the header,
the body, a line above the footer and the commands in small text. Columns become one line per row, with the blank line between devs kept. A post with side-by-side columns (the bug page, the fix log) stays an embed.
Used for the mockups first; a post only switches when its code builds a card instead of an embed."""
import re

import discord
from discord import ui

from .botnews import code_chip, date_button
from .pngs import fit, width_strip, with_strip

NL = chr(10)
ZWS = '​ㅤ   ⠀'  # the invisible characters the embeds use as spacers
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
        if out:  # the table was cut here between two devs: a blank line keeps them apart
            out.append('')
        if any(heads):
            out.append('**' + '  ·  '.join(h for h in heads if h) + '**')
        out += _row_lines(cols)
    return NL.join(out)


def _tidy(value):
    """A field's text without the empty lines at its end."""
    lines = str(value).split(NL)
    while lines and _blank(lines[-1]):
        lines.pop()
    return NL.join(lines)


def clone_rows(view):
    """The buttons and dropdowns of a classic view as rows for a card."""
    rows = []
    for c in view.children if view is not None else []:
        if isinstance(c, discord.ui.Select):
            item = ui.Select(custom_id=c.custom_id, placeholder=c.placeholder, min_values=c.min_values, max_values=c.max_values,
                             options=[discord.SelectOption(label=o.label, value=o.value, description=o.description, default=o.default, emoji=o.emoji) for o in c.options])
        elif c.url:
            item = ui.Button(style=discord.ButtonStyle.link, label=c.label, url=c.url, emoji=c.emoji, disabled=c.disabled)
        else:
            item = ui.Button(custom_id=c.custom_id, label=c.label, style=c.style, emoji=c.emoji, disabled=c.disabled)
        rows.append((getattr(c, 'row', None), item))
    out, last = [], object()
    for row, item in rows:  # items that were on the same row stay together
        if out and row is not None and row == last and not isinstance(item, ui.Select) and not isinstance(out[-1].children[0], ui.Select):
            out[-1].add_item(item)
        else:
            out.append(ui.ActionRow(item))
        last = row
    return out


async def edit_card(msg, embed, fallback_view=None, **opts):
    """Edits a message that is an embed into a card, in place. If Discord refuses, the embed is edited as it was."""
    below = opts.pop('below', None)
    allowed = opts.pop('allowed', None)  # people the message may mention without pinging them (their names then show for everyone)
    try:
        view, files = card_from_embed(embed, below=below, **opts)
        await msg.edit(content=None, embeds=[], view=view, attachments=files, allowed_mentions=allowed or discord.AllowedMentions.none())
    except discord.HTTPException as e:
        print('card edit failed, keeping the embed', repr(e)[:150])
        await msg.edit(embeds=[embed], view=fallback_view)


def card_from_embed(e, when=None, ping=None, inline_desc=False, plain_count=False, below=None, first_sub=None):
    """(view, files) for an embed shown as a card. A thumbnail on the embed goes to the right of the title, else the date does.
    inline_desc: the first line of the description (the counts) moves into the title; plain_count drops the emoji in front of it;
    first_sub: [(old, new)] changes to that line. below: components (rows) shown under the card, like a picker."""
    strip_ = width_strip()
    title, desc = e.title or '', _tidy((e.description or '').strip(' ' + ZWS + NL))
    if inline_desc and desc:
        first, _, desc = desc.partition(NL)
        first = re.sub(r'[*]', '', first).strip()
        for old, new in first_sub or []:
            first = first.replace(old, new)
        if plain_count:
            first = re.sub(r'^[^A-Za-z0-9]+', '', first)
        title = f'{title} · {first}'
        desc = _tidy(desc.strip(' ' + ZWS + NL))
    accessory = ui.Thumbnail(e.thumbnail.url) if e.thumbnail and e.thumbnail.url else (date_button(when) if len(title) <= 44 else None)
    items = []
    if title:
        items.append(ui.Section(f'### {title}', accessory=accessory) if accessory else ui.TextDisplay(f'### {title}'))
        items.append(ui.Separator(visible=True, spacing=SMALL))
    if desc:
        items.append(ui.TextDisplay(desc[:3900]))
    fields, i, buf = list(e.fields), 0, None

    def flush():
        nonlocal buf
        if buf:
            header, vals = buf
            if header:  # a heading, then its entries; a list of people gets a blank line under the heading and between the people
                sep = '\n\n' if vals and vals[0].startswith('<@') else '\n'
                text = header + sep + '\n\n'.join(vals)
            else:
                text = '\n\n'.join(vals)
            items.append(ui.TextDisplay(text[:3900]))
            buf = None

    while i < len(fields):
        f = fields[i]
        if f.inline:
            flush()
            group = []
            while i < len(fields) and fields[i].inline:
                group.append(fields[i])
                i += 1
            text = _table(group)
            if text.strip():
                items.append(ui.TextDisplay(text[:3900]))
            continue
        i += 1
        value = _tidy(f.value)
        if not _blank(f.name):
            flush()
            buf = (f'**{f.name.rstrip(":")}**', [value])
        elif not _blank(value):
            buf = (buf[0], buf[1] + [value]) if buf else (None, [value])
    flush()
    if e.footer and e.footer.text:
        items += [ui.Separator(visible=True, spacing=SMALL), ui.TextDisplay(NL.join('-# ' + code_chip(x) for x in e.footer.text.split(NL)))]
    view = ui.LayoutView()
    if ping:
        view.add_item(ui.TextDisplay(ping))
    items = fit(items, keep_tail=2 if e.footer and e.footer.text else 0, extra_parts=(1 if ping else 0) + sum(1 + len(r.children) for r in below or []))
    items, strip_ = with_strip(items)  # the strip keeps every card the same width
    view.add_item(ui.Container(*items))
    for row in below or []:  # a picker or buttons sit under the card, outside it
        view.add_item(row)
    return view, [strip_]
