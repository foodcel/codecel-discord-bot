"""Messages typed in dev boards and bug posts: jr-dev cleanup, dev commands inside a post ("fixed"), reporters answering."""
import asyncio

import discord

from bot.core.ctx import get_member
from bot.discord_ui import devlog
from bot.core.db import bug_by_thread, kv_set, run
from bot.core.env import cfg
from bot.features.bugs.fixes import apply_status
from bot.features.bugs.intake import handle_bug_message
from bot.features.bugs.parse import parse_command
from bot.features.bugs import nums
from bot.core.perms import level
from bot.features.bugs.suggest import handle_suggestion_message


async def _member_of(msg):
    return msg.author if isinstance(msg.author, discord.Member) else await get_member(msg.author.id)


async def _delete_later(m, seconds):
    await asyncio.sleep(seconds)
    try:
        await m.delete()
    except Exception:
        pass


async def handle_dev(msg, kind='bug'):
    """A message in a dev board: only jr devs are stopped (they may not write there). Nothing typed there is a command."""
    member = await _member_of(msg)
    lvl = level(member)
    if lvl == 'jr':
        asyncio.ensure_future(devlog.post(msg.author, 'Jr dev wrote in a dev board', f'**message** · {msg.content[:300]}', 'Message deleted', False, msg.channel.id))
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


async def handle_bug_thread(msg):
    bug = bug_by_thread(msg.channel.id)
    if bug:
        run('UPDATE bugs SET last_msg_id=? WHERE id=?', str(msg.id), bug['id'])
    if msg.author.bot:
        return
    member = await _member_of(msg)
    if level(member) in ('admin', 'dev'):
        cmd = parse_command(msg.content)
        if cmd and cmd['ids'] and bug:  # the numbers belong to this post's game
            r = nums.resolve(cmd, bug['kind'], here=bug)
            cmd = None if (r['unknown_game'] or not r['ids']) else {**cmd, 'ids': r['ids']}  # numbers that fit no report are not a command
        if cmd:
            ids = cmd['ids'] if cmd['ids'] else ([bug['id']] if bug else [])
            if ids:
                done, _ = await apply_status(ids, cmd['status'], member, via='typed in the post')
                if done:
                    try:
                        await msg.add_reaction('✅')
                    except Exception:
                        pass
                    return
    handle_bug_message(msg)


async def handle_suggestion_thread(msg):
    bug = bug_by_thread(msg.channel.id)
    if not bug:
        return
    if bug['kind'] == 'bug':  # a suggestion that turned out to be a bug: it is handled like any bug post
        return await handle_bug_thread(msg)
    run('UPDATE bugs SET last_msg_id=? WHERE id=?', str(msg.id), bug['id'])
    if msg.author.bot:
        return
    member = await _member_of(msg)
    if level(member) in ('admin', 'dev'):
        cmd = parse_command(msg.content)
        if cmd and cmd['ids']:
            r = nums.resolve(cmd, bug['kind'], here=bug)
            cmd = None if (r['unknown_game'] or not r['ids']) else {**cmd, 'ids': r['ids']}
        if cmd:
            done, _ = await apply_status(cmd['ids'] or [bug['id']], cmd['status'], member, 'suggestion', via='typed in the post')
            if done:
                try:
                    await msg.add_reaction('✅')
                except Exception:
                    pass
                return
    handle_suggestion_message(msg)


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
    if cfg.dev_suggestions_id and parent == cfg.dev_suggestions_id:
        kv_set(f'devlast:{ch.id}', msg.id)
        if msg.author.bot:
            return
        return await handle_dev(msg, 'suggestion')
    if cfg.suggestions_id and parent == cfg.suggestions_id:
        return await handle_suggestion_thread(msg)
    if parent == cfg.bugs_id or parent in (cfg.testing_id, cfg.tester_forum_id):  # the bugs forum, and the testers' reports (the testing channel and the testers forum)
        return await handle_bug_thread(msg)
