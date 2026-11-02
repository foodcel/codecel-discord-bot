"""/mog: Codecel posts one of the GIFs in assets/mog at random and pings Robin and Redwing Helper. Admins only."""
import random
from pathlib import Path

import discord

FOLDER = Path(__file__).resolve().parent.parent / 'assets' / 'mog'
PING = (941724517481463888, 1565900080894967809)  # Robin, Redwing Helper


def pick():
    files = sorted(FOLDER.glob('*.gif'))
    return random.choice(files) if files else None


async def command_mog(i):
    """An admin ran /mog: one random GIF from the folder, pinging only the two on the list."""
    gif = pick()
    if not gif:
        return await i.response.send_message('There are no GIFs in the mog folder.', ephemeral=True)
    await i.response.defer()  # the file is big: answer first, then send it
    await i.followup.send(content=' '.join(f'<@{u}>' for u in PING), file=discord.File(gif),
                          allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=u) for u in PING], everyone=False, roles=False))
