"""A transparent PNG made in code (no picture library needed): a strip that is very wide and 2 pixels tall.
Put at the top of a message in a media gallery, it makes the message as wide as Discord allows, so every message looks the same width."""
import io
import struct
import zlib

import discord


def _chunk(kind, data):
    body = kind + data
    return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xFFFFFFFF)


def _png(width, height, rgba=(0, 0, 0, 0)):
    rows = b''.join(b'\x00' + bytes(rgba) * width for _ in range(height))  # filter byte, then the pixels (transparent unless a colour is given)
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + _chunk(b'IDAT', zlib.compress(rows)) + _chunk(b'IEND', b''))


STRIP = _png(1400, 2)
LINE = _png(1400, 2, (255, 255, 255, 38))  # the same strip as a faint line: it widens the card and is the line above the footer


def width_strip():
    """A new file each time (a File can be sent once). Its gallery goes first in the message."""
    return discord.File(io.BytesIO(STRIP), filename='width.png')


def line_strip():
    return discord.File(io.BytesIO(LINE), filename='line.png')


def with_strip(items):
    """(items with the width strip put in, the strip file). The strip keeps every card the same width. It replaces the last divider line of the card:
    it is a faint line itself, so the card is wide and has its footer line with no dead space of its own. A card without a divider gets the
    invisible strip in front of its last button row."""
    from discord import ui
    items = list(items)
    for k in range(len(items) - 1, -1, -1):
        if isinstance(items[k], ui.Separator):
            strip = line_strip()
            items[k] = ui.MediaGallery(discord.MediaGalleryItem(strip))
            return items, strip
    strip = width_strip()
    gallery = ui.MediaGallery(discord.MediaGalleryItem(strip))
    k = next((k for k in range(len(items) - 1, -1, -1) if isinstance(items[k], ui.ActionRow)), len(items))
    items.insert(k, gallery)
    return items, strip


TEXT_LIMIT = 3800   # Discord allows 4000 characters of text per message (all text parts together); some room is kept
PART_LIMIT = 38     # and 40 components per message (every nested part counts)


def _text_of(item):
    from discord import ui
    if isinstance(item, ui.TextDisplay):
        return item.content
    if isinstance(item, ui.Section):
        return ''.join(c.content for c in item.children if isinstance(c, ui.TextDisplay))
    return ''


def _parts(item):
    from discord import ui
    if isinstance(item, ui.Section):
        return 1 + len(item.children) + 1
    if isinstance(item, (ui.ActionRow, ui.Container)):
        return 1 + sum(_parts(c) for c in item.children)
    return 1


def fit(items, keep_tail=2, extra_parts=0):
    """The card's items, shortened when it would break a limit. keep_tail: how many items at the end are the footer (always kept).
    extra_parts: components outside the card (the ping text, a picker below) that count too."""
    from discord import ui
    items = list(items)
    head, tail = items[:2], items[len(items) - keep_tail:] if keep_tail else []
    body = items[2:len(items) - keep_tail] if keep_tail else items[2:]
    dropped = 0

    def total():
        whole = head + body + tail
        return sum(len(_text_of(x)) for x in whole) + 40, 1 + sum(_parts(x) for x in whole) + extra_parts + (1 if dropped else 0)

    while body and (total()[0] > TEXT_LIMIT or total()[1] > PART_LIMIT):
        body.pop()
        dropped += 1
    if dropped:
        body.append(ui.TextDisplay(f'-# …and {dropped} more not shown'))
    over = total()[0] - TEXT_LIMIT
    if over > 0:  # one very long text: cut it
        for k in range(len(body) - 1, -1, -1):
            if isinstance(body[k], ui.TextDisplay) and len(body[k].content) > over + 20:
                body[k] = ui.TextDisplay(body[k].content[:len(body[k].content) - over - 2] + '…')
                break
    return head + body + tail
