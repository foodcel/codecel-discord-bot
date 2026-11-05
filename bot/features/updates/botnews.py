"""The announcements for devs and testers, all in one look: a short title, sections whose lines branch like the /help tree, and the commands
in the footer, one per line. Every branch is kept short enough to stay on one line, so nothing wraps back under the tree.
Built here so the preview and the real post are identical."""

import discord
from discord import ui

from bot.core.env import cfg
from bot.discord_ui.pngs import width_strip

GAMES_CHANNEL = cfg.games_channel_id  # #games
DEV_CHAT = cfg.dev_chat_id            # #developer-chat
MAX_LINE = 56                        # characters a branch may take before it wraps (a channel link counts as 16)


def tree(*rows):
    """(name, text) pairs as branches: ├─ **name** · text, the last one └─."""
    last = len(rows) - 1
    return '\n'.join(f"{'└─' if n == last else '├─'} **{name}** · {text}" for n, (name, text) in enumerate(rows))


def strip():
    """The file the announcements' picture points to. A new one for every message sent."""
    return width_strip()


def code_chip(line):
    """"/cmd · text" becomes "`/cmd` · text": the command in a grey box."""
    first, sep, rest = line.partition(' · ')
    return f'`{first}` · {rest}' if sep and first[:1] in '/!' else line


def date_button(when=None):
    """The date as a greyed-out button: the only thing Discord puts on the right of a title."""
    d = (when or __import__('datetime').datetime.now()).strftime('%b %d, %Y').replace(' 0', ' ')
    return ui.Button(style=discord.ButtonStyle.secondary, label=d, disabled=True, custom_id='date')


