"""The one way to build a post: a card (Discord's components), never an embed. See docs/DESIGN.md.
card() gives the developer look: the title with the date (or a picture) on the right, a line, the body, a line, the small footer with command chips,
buttons inside the card, and pickers under it. Every card is kept inside Discord's limits (pngs.fit) and as wide as the others (pngs.with_strip).
words() reads the text back out of any message (a card, an old embed or plain text), for the code that reads posts (report intake, transcripts)."""
import discord
from discord import ui

from bot.discord_ui.pngs import fit, with_strip
from bot.features.updates.botnews import code_chip, date_button

NL = chr(10)
SMALL = discord.SeparatorSpacing.small


def row(label, value):
    """One 'column' line of a card: **Label** · value (cards have no side-by-side columns)."""
    return f'**{label}** · {value}'


def media_items(media):
    """The attached files of a report as card parts, each kind under its own heading. media: {'images': [names], 'videos': [names], 'files': [names]}
    (names of files uploaded with the message)."""
    out = []
    media = media or {}
    if media.get('images'):
        out += [ui.TextDisplay('**📷 Screenshots**'), ui.MediaGallery(*[discord.MediaGalleryItem(f'attachment://{n}') for n in media['images'][:10]])]
    if media.get('videos'):
        out += [ui.TextDisplay('**🎬 Videos**'), ui.MediaGallery(*[discord.MediaGalleryItem(f'attachment://{n}') for n in media['videos'][:10]])]
    if media.get('files'):
        out += [ui.TextDisplay('**📎 Files**')] + [ui.File(f'attachment://{n}') for n in media['files'][:5]]
    return out


def links_in(*texts):
    """The web links written in some text, once each, in order (a card shows no link previews, so they are listed)."""
    import re
    seen = []
    for t in texts:
        for u in re.findall(r'https?://[^\s<>()\[\]"]+', str(t or '')):
            u = u.rstrip('.,;:!?')
            if u not in seen:
                seen.append(u)
    return seen[:8]


def card(title, blocks=(), footer=(), right='date', ping=None, image=None, inside=(), below=(), files=(), when=None, gallery=(), media=None):
    """(view, files).
    title: the header text. right: 'date' (the date button), a picture URL (a thumbnail), or None.
    blocks: the body, one text part each (empty ones are skipped). footer: small lines; a 'cmd · text' line that starts with / or ! becomes a chip.
    image: the file name of an attached picture shown big in the card. gallery: picture URLs shown together (up to 10). inside: ActionRows inside the card, at the bottom. below: rows under the card.
    files: the discord.File list that goes with the message (attachments the card points at). ping: a mention right above the card."""
    if right == 'date':
        head = ui.Section(f'### {title}', accessory=date_button(when))
    elif isinstance(right, str) and right.startswith('http'):
        head = ui.Section(f'### {title}', accessory=ui.Thumbnail(right))
    else:
        head = ui.TextDisplay(f'### {title}')
    items = [head, ui.Separator(visible=True, spacing=SMALL)]
    items += [ui.TextDisplay(b[:3900]) for b in blocks if b and str(b).strip()]
    if image:
        items.append(ui.MediaGallery(discord.MediaGalleryItem(f'attachment://{image}')))
    if gallery:
        items.append(ui.MediaGallery(*[discord.MediaGalleryItem(u) for u in list(gallery)[:10]]))
    tail = 0
    if footer:
        items += [ui.Separator(visible=True, spacing=SMALL), ui.TextDisplay(NL.join('-# ' + code_chip(x) for x in footer))]
        tail = 2
    items += list(inside)
    shown = media_items(media)
    outside = (1 if ping else 0) + sum(1 + len(r.children) for r in below) + len(shown)
    items = fit(items, keep_tail=tail + len(inside), extra_parts=outside)
    at = len(items) - tail - len(inside)
    items[at:at] = shown  # the files sit after the text and before the footer, and are never cut off
    items, strip = with_strip(items)
    view = ui.LayoutView(timeout=None)
    if ping:
        view.add_item(ui.TextDisplay(ping))
    view.add_item(ui.Container(*items))
    for r in below:
        view.add_item(r)
    return view, [strip, *files]


def buttons(*items):
    """An ActionRow of buttons for inside or under a card."""
    return ui.ActionRow(*items)


def _walk(comps, out):
    for c in comps or []:
        if isinstance(c, discord.components.TextDisplay):
            out.append(c.content)
        _walk(getattr(c, 'children', None) or getattr(c, 'components', None), out)


def words(m):
    """Every word of a message: its text, an old embed's title, description and fields, and a card's text parts."""
    out = [m.content or '']
    for e in m.embeds:
        out += [e.title or '', e.description or ''] + [f'{f.name}: {f.value}' for f in e.fields]
    _walk(m.components, out)
    return NL.join(p.strip() for p in out if p and p.strip())


_OLD = None


def notice(text, ping=None):
    """A short message as a small card: (view, files). '{emoji} **LABEL** · text' becomes a bold title ('Saved') with the text under it; any other
    sentence is shown as plain text in a card. A leading mention is kept above the card."""
    global _OLD
    import re
    if _OLD is None:
        _OLD = re.compile(r'^\s*(?P<ping>(?:<@[&!]?\d+>\s*)*)(?P<emoji>[^\s*]+)\s+\*\*(?P<label>[^*\n]+)\*\*[\s\u2003\u2002]*(?:\u00b7)?[\s\u2003\u2002]*(?P<rest>.*)$', re.S)
    text = str(text).replace('\u2003', ' ').replace('\u2002', ' ')
    m = _OLD.match(text)
    parts = []
    if m:
        ping = ping or (m['ping'].strip() or None)
        label = m['label'].strip()
        parts.append(ui.TextDisplay(f"### {m['emoji']} {label[:1].upper()}{label[1:].lower()}"))
        if m['rest'].strip():
            parts.append(ui.TextDisplay(m['rest'].strip()[:3900]))
    else:
        parts.append(ui.TextDisplay(text.strip()[:3900]))
    view = ui.LayoutView()
    if ping:
        view.add_item(ui.TextDisplay(ping))
    view.add_item(ui.Container(*parts))
    return view, []


def stamp(ms):
    """A real date for a card line (Discord shows it in each reader's own time)."""
    return f'<t:{int(ms) // 1000}:f>'


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
