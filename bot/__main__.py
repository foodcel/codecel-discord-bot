"""Starts the bot: python -m bot"""
import asyncio
import traceback

import discord

from . import board, cards, mog, watch
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
from . import devlog, msgreport, suggest, testers
from .tags import ensure_fixed_tag, ensure_suggest_tags, load_tags
from .timers import run_timers

devlog.install()
intents = discord.Intents.none()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
intents.members = True
intents.guild_reactions = True
intents.webhooks = True  # a webhook made in the library channel is deleted at once
client = discord.Client(intents=intents, activity=discord.CustomActivity(name='*tokenmogs the loser below me*'), status=discord.Status.online)
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
    asyncio.ensure_future(watch.watch_loop())  # every 5 minutes: is each released game still on Roblox?
    asyncio.ensure_future(cards.guard_loop())  # first thing: the library and its cards are always there, a rival bot's posts never
    await load_tags()
    await ensure_suggest_tags()
    await ensure_fixed_tag()
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
    try:
        if await testers.import_old():
            print('tester roster imported')
        if n := await testers.sync_members():
            print(f'{n} tester(s) with a tester role added to the roster')
        await testers.refresh_roster()
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
    if m.guild and cards.in_library_channel(m.channel.id) and cards.is_foreign(m):  # first thing, before anything else: a foreign bot or webhook post in the library channel
        try:
            await m.delete()
        except Exception:
            pass
        return
    if str(m.channel.id) == cfg.bounty_id and not board.is_live():
        return schedule_claims()
    if m.type == discord.MessageType.pins_add and cards.in_library_channel(m.channel.id):  # the "pinned a message" line of the library
        try:
            await m.delete()
        except Exception:
            pass
        return
    try:
        if await mog.maybe_reply(m, client.user.id):  # Redwing Helper talked about Codecel: a GIF back
            return
    except Exception:
        traceback.print_exc()
    if cards.in_library_channel(m.channel.id) and await cards.purge_rivals(m):  # another bot posting in the library channel: gone
        return
    try:
        if msgreport.wants(m) and await msgreport.handle(m):  # a reply of `!bug` or `!improve`
            return
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
async def on_raw_message_delete(p):
    conf = cards.library_config()
    if conf and str(p.channel_id) == str(conf['channel']) and str(p.message_id) in [str(i) for i in conf['messages']]:
        try:
            await cards.keep_library()
        except Exception:
            traceback.print_exc()


@client.event
async def on_raw_bulk_message_delete(p):
    if cards.in_library_channel(p.channel_id):
        try:
            await cards.keep_library()
        except Exception:
            traceback.print_exc()


@client.event
async def on_message_edit(before, after):
    if cards.in_library_channel(after.channel.id):
        await cards.purge_rivals(after)


@client.event
async def on_webhooks_update(channel):
    if cards.in_library_channel(channel.id):
        try:
            await cards.purge_webhooks(channel)
        except Exception:
            traceback.print_exc()


@client.event
async def on_raw_thread_delete(p):
    board.on_thread_delete(p.thread_id)


@client.event
async def on_member_update(before, after):
    if before.display_name != after.display_name:  # a dev's board post carries their name
        schedule_boards()
    try:
        await testers.on_member_update(before, after)
    except Exception:
        traceback.print_exc()


@client.event
async def on_user_update(before, after):
    if (before.global_name, before.name) != (after.global_name, after.name):
        schedule_boards()


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
