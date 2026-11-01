"""A transparent PNG made in code (no picture library needed): a strip that is very wide and 2 pixels tall.
Put at the top of a message in a media gallery, it makes the message as wide as Discord allows, so every message looks the same width."""
import io
import struct
import zlib

import discord


def _chunk(kind, data):
    body = kind + data
    return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xFFFFFFFF)


def _png(width, height):
    rows = b''.join(b'\x00' + b'\x00\x00\x00\x00' * width for _ in range(height))  # filter byte, then transparent pixels
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + _chunk(b'IDAT', zlib.compress(rows)) + _chunk(b'IEND', b''))


STRIP = _png(1400, 2)


def width_strip():
    """A new file each time (a File can be sent once). Its gallery goes first in the message."""
    return discord.File(io.BytesIO(STRIP), filename='width.png')
