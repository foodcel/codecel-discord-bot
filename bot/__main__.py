"""Starts the bot: python -m bot"""
import asyncio
import traceback

import discord

from . import board
from .bounty import refresh_claims
from .catchup import catchup
from .commands_sync import register_commands
from .ctx import ctx, sleep
from .db import kv_get, kv_set, run
from .devboard import clear_bug_messages, refresh_all_boards, schedule_boards
from .env import cfg
from .fixlog import backfill_snapshots
from .intake import intake_thread
from .interactions import handle_interaction
from .router import handle_message
from . import devlog, suggest
from .tags import ensure_suggest_tags, load_tags
from .timers import run_timers

devlog.install()
intents = discord.Intents.none()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
intents.members = True
intents.guild_reactions = True
client = discord.Client(intents=intents)
ctx.client = client

_claim_task = None
_started = False


def schedule_claims():
    """Re-read the bounty-board 3 seconds after it changed (many edits arrive in a burst)."""
    global _claim_task
    if _claim_task and not _claim_task.done():
        _claim_task.cancel()

    async def go():
        await asyncio.sleep(3)
        try:
            if await refresh_claims():
                schedule_boards()
        except Exception:
            pass

    _claim_task = asyncio.ensure_future(go())


async def timer_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await run_timers()
        except Exception:
            traceback.print_exc()


@client.event
async def on_ready():
    global _started
    if _started:
        return  # reconnects fire on_ready again
    _started = True
    ctx.guild = client.get_guild(int(cfg.guild_id)) or await client.fetch_guild(int(cfg.guild_id))
    print(f'Logged in as {client.user}')
    await load_tags()
    await ensure_suggest_tags()
    await register_commands()
    if board.is_live():  # this bot runs the bounty board: read the forum again before anything uses the claims
        try:
            await board.sync_forum()
        except Exception:
            print('bounty board sync failed')
            traceback.print_exc()
    await refresh_claims()
    try:
        await catchup()
    except Exception:
        print('catchup failed')
        traceback.print_exc()
    if not kv_get('board_v3'):  # one-time: remove the per-bug messages the old layout posted
        try:
            await clear_bug_messages()
        except Exception:
            print('clear failed')
            traceback.print_exc()
        kv_set('board_v3', '1')
    if not kv_get('threshold_3'):  # announcement offers now start at 3 fixes
        run('UPDATE games SET threshold=3 WHERE threshold=5')
        kv_set('threshold_3', '1')
    try:
        await backfill_snapshots()  # transcripts for bugs fixed before the log existed
    except Exception:
        traceback.print_exc()
    try:
        await refresh_all_boards()  # claims may have changed while offline (also creates/refreshes the fix log post)
    except Exception:
        traceback.print_exc()
    asyncio.ensure_future(timer_loop())
    asyncio.ensure_future(board.sync_loop())
    print('Ready. Catch-up finished.')


@client.event
async def on_thread_create(thread):
    board.on_thread_create(thread)
    if cfg.suggestions_id and str(thread.parent_id) == cfg.suggestions_id and ctx.guild:
        await sleep(1500)
        try:
            await suggest.intake_suggestion(thread)
        except Exception:
            traceback.print_exc()
        return
    if str(thread.parent_id) != cfg.bugs_id or not ctx.guild:
        return
    await sleep(1500)
    try:
        await intake_thread(thread)
    except Exception:
        traceback.print_exc()


@client.event
async def on_message(m):
    if str(m.channel.id) == cfg.bounty_id and not board.is_live():
        return schedule_claims()
    try:
        await handle_message(m)
    except Exception:
        traceback.print_exc()


@client.event
async def on_raw_message_edit(payload):
    if str(payload.channel_id) == cfg.bounty_id and not board.is_live():
        schedule_claims()


@client.event
async def on_raw_reaction_add(p):
    await board.on_vote_change(p.channel_id, p.message_id)
    await suggest.on_vote_change(p.channel_id, p.message_id)


@client.event
async def on_raw_reaction_remove(p):
    await board.on_vote_change(p.channel_id, p.message_id)
    await suggest.on_vote_change(p.channel_id, p.message_id)


@client.event
async def on_raw_reaction_clear(p):
    await board.on_vote_change(p.channel_id, p.message_id)
    await suggest.on_vote_change(p.channel_id, p.message_id)


@client.event
async def on_raw_reaction_clear_emoji(p):
    await board.on_vote_change(p.channel_id, p.message_id)
    await suggest.on_vote_change(p.channel_id, p.message_id)


@client.event
async def on_raw_thread_delete(p):
    board.on_thread_delete(p.thread_id)


@client.event
async def on_guild_channel_update(before, after):
    if str(after.id) in (cfg.bugs_id, cfg.suggestions_id):
        try:
            await load_tags()
        except Exception:
            traceback.print_exc()


@client.event
async def on_interaction(i):
    if i.type == discord.InteractionType.application_command:
        print(f"/{i.data.get('name')} by {i.user}")
    captured, token = devlog.begin()
    error = None
    try:
        await handle_interaction(i)
    except Exception as e:
        error = e
        print('interaction')
        traceback.print_exc()
        try:
            if not i.response.is_done():
                await i.response.send_message('Something went wrong.', ephemeral=True)
        except Exception:
            pass
    finally:
        devlog.end(token)
    devlog.record(i, captured, error)


if __name__ == '__main__':
    client.run(cfg.token)
