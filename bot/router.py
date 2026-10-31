"""Messages typed in dev boards and bug posts: dev commands ("12 fixed"), jr-dev cleanup, reporters answering."""
import asyncio

import discord

from .ctx import get_member
from .db import bug_by_thread, kv_set, run
from .env import cfg
from .fixes import apply_status
from .intake import handle_bug_message
from .parse import parse_command
from .perms import level


async def _member_of(msg):
    return msg.author if isinstance(msg.author, discord.Member) else await get_member(msg.author.id)


async def _delete_later(m, seconds):
    await asyncio.sleep(seconds)
    try:
        await m.delete()
    except Exception:
        pass


async def handle_dev(msg):
    member = await _member_of(msg)
    lvl = level(member)
    if lvl == 'jr':
        try:
            await msg.delete()
        except Exception:
            pass
        try:
            n = await msg.channel.send(f"<@{msg.author.id}> Jr developers can't write in the dev board.")
            asyncio.ensure_future(_delete_later(n, 6))
        except Exception:
            pass
        return
    if lvl not in ('admin', 'dev'):
        return
    cmd = parse_command(msg.content)
    if not cmd or not cmd['ids']:
        return
    done, skipped = await apply_status(cmd['ids'], cmd['status'], member)
    try:
        await msg.add_reaction('✅' if done else '❌')
    except Exception:
        pass
    if skipped:
        try:
            await msg.reply(f"Skipped: {', '.join(skipped)}", allowed_mentions=discord.AllowedMentions(replied_user=False))
        except Exception:
            pass


async def handle_bug_thread(msg):
    bug = bug_by_thread(msg.channel.id)
    if bug:
        run('UPDATE bugs SET last_msg_id=? WHERE id=?', str(msg.id), bug['id'])
    if msg.author.bot:
        return
    member = await _member_of(msg)
    if level(member) in ('admin', 'dev'):
        cmd = parse_command(msg.content)
        if cmd:
            ids = cmd['ids'] if cmd['ids'] else ([bug['id']] if bug else [])
            if ids:
                done, _ = await apply_status(ids, cmd['status'], member)
                if done:
                    try:
                        await msg.add_reaction('✅')
                    except Exception:
                        pass
                    return
    handle_bug_message(msg)


async def handle_message(msg):
    if not msg.guild or not isinstance(msg.channel, discord.Thread):
        return
    ch = msg.channel
    parent = str(ch.parent_id)
    if parent == cfg.dev_forum_id:
        kv_set(f'devlast:{ch.id}', msg.id)
        if msg.author.bot:
            return
        return await handle_dev(msg)
    if parent == cfg.bugs_id or (cfg.testing_id and parent == cfg.testing_id):
        return await handle_bug_thread(msg)
