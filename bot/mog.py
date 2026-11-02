"""/mog: Codecel posts one of the GIFs in assets/mog at random and pings Robin and Redwing Helper. Admins only.
And when Redwing Helper talks about Codecel or pings it, Codecel answers with one of them (maybe_reply)."""
import random
import time
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


COOLDOWN = 30   # seconds between two automatic replies, so two bots can never keep each other going
_last = [0.0]


def about_me(m, me_id):
    """The message pings this bot or says its name (in the text or in an embed)."""
    if me_id in {u.id for u in m.mentions}:
        return True
    text = [m.content or '']
    for e in m.embeds:
        text += [e.title or '', e.description or ''] + [f'{f.name} {f.value}' for f in e.fields]
    return 'codecel' in ' '.join(text).lower()


async def reply_with_gif(m):
    """Replies to message m with a random GIF (the reply pings its author)."""
    gif = pick()
    if not gif:
        return None
    return await m.reply(file=discord.File(gif), allowed_mentions=discord.AllowedMentions(replied_user=True, everyone=False, roles=False, users=False))


async def maybe_reply(m, me_id):
    """Redwing Helper (or its webhook) mentions Codecel anywhere but the library channel: Codecel answers with a GIF. True when it did."""
    from .cards import in_library_channel, is_rival
    if not m.guild or in_library_channel(m.channel.id) or not is_rival(m) or not about_me(m, me_id):
        return False
    if time.monotonic() - _last[0] < COOLDOWN:
        return False
    _last[0] = time.monotonic()
    await reply_with_gif(m)
    return True

