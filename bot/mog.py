"""/mog: Codecel posts one of the GIFs or pictures in assets/mog at random and pings Robin and Redwing Helper. Admins only.
And when Redwing Helper talks about Codecel or pings it, Codecel answers with one of them (maybe_reply)."""
import random
from pathlib import Path

import discord

from .env import cfg

FOLDER = Path(__file__).resolve().parent.parent / 'assets' / 'mog'
PING = tuple(int(u) for u in cfg.mog_ping)  # Robin, Redwing Helper (MOG_PING_USER_IDS in .env)


def pick():
    files = sorted(p for p in FOLDER.iterdir() if p.suffix.lower() in ('.gif', '.png'))
    return random.choice(files) if files else None


async def command_mog(i):
    """An admin ran /mog: one random GIF from the folder, pinging only the two on the list."""
    gif = pick()
    if not gif:
        return await i.response.send_message('There are no GIFs in the mog folder.', ephemeral=True)
    await i.response.defer()  # the file is big: answer first, then send it
    await i.followup.send(content=' '.join(f'<@{u}>' for u in PING), file=discord.File(gif),
                          allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=u) for u in PING], everyone=False, roles=False))


def about_me(m, me_id):
    """The message pings this bot, says its name (in the text or in an embed), or is a reply to one of this bot's messages."""
    if me_id in {u.id for u in m.mentions}:
        return True
    ref = getattr(getattr(m, 'reference', None), 'resolved', None)
    if ref is not None and getattr(getattr(ref, 'author', None), 'id', None) == me_id:
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


_last = {}  # channel id -> when the last GIF answer went out (at most one every 10 seconds per channel)


async def maybe_reply(m, me_id):
    """Redwing Helper (or its webhook) mentions Codecel or answers it anywhere but the library channel: Codecel answers with a GIF, every time."""
    from .cards import in_library_channel, is_rival
    if not m.guild or in_library_channel(m.channel.id) or not is_rival(m):
        return False
    hit = about_me(m, me_id)
    if not hit:
        return False
    import time
    if time.time() - _last.get(m.channel.id, 0) < 10:
        return True  # answered here a few seconds ago: two bots must not loop
    _last[m.channel.id] = time.time()
    await reply_with_gif(m)
    return True


async def app_mog(i):
    """Right click a message, Apps, Mog: Codecel replies to that message with a random GIF. Admins only."""
    from .ctx import fetch_channel
    from .perms import level
    if level(i.user) != 'admin':
        return await i.response.send_message('Only admins can use this.', ephemeral=True)
    await i.response.defer(ephemeral=True)
    ch = await fetch_channel(i.channel_id)
    target = await ch.fetch_message(int(i.data['target_id']))
    await reply_with_gif(target)
    await i.followup.send('Done.', ephemeral=True)
