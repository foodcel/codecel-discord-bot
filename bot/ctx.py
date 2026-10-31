"""Shared state and small Discord helpers."""
import asyncio

import discord

from .env import cfg


class Ctx:
    client: discord.Client = None
    guild: discord.Guild = None


ctx = Ctx()


async def sleep(ms):
    await asyncio.sleep(ms / 1000)


async def fetch_channel(id_):
    """Channel or thread by id (cache first, then the API). None when missing or unreachable."""
    if not id_:
        return None
    try:
        ch = ctx.client.get_channel(int(id_))
        return ch or await ctx.client.fetch_channel(int(id_))
    except Exception:
        return None


def thread_link(id_):
    return f'https://discord.com/channels/{cfg.guild_id}/{id_}'


async def modlog(**kwargs):
    ch = await fetch_channel(cfg.modlog_id)
    if not ch:
        return None
    try:
        return await ch.send(**kwargs)
    except Exception as e:
        print('modlog send failed:', e)
        return None


async def dm(user_id, content):
    try:
        user = await ctx.client.fetch_user(int(user_id))
        await user.send(content)
        return True
    except Exception:
        return False


async def get_member(id_):
    try:
        return ctx.guild.get_member(int(id_)) or await ctx.guild.fetch_member(int(id_))
    except Exception:
        return None


async def remove_thread_notice(thread):
    """A thread started inside a text channel leaves a "<bot> started a thread: ..." line behind, even after the thread is
    deleted. Call this before deleting the thread so that line goes away with it. Forum posts have no such line."""
    parent = thread.parent
    if parent is None or parent.type in (discord.ChannelType.forum, discord.ChannelType.media):
        return
    try:
        async for m in parent.history(limit=50, around=discord.Object(id=thread.id)):
            if m.type == discord.MessageType.thread_created and m.reference and m.reference.channel_id == thread.id:
                await m.delete()
                break
    except Exception:
        pass
