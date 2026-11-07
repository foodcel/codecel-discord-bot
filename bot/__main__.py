"""Starts the bot: python -m bot"""
import asyncio
import traceback

import discord

from bot.features.games import board
from bot.features.games import cards
from bot.features.invites import invites
from bot.features.fun import mog
from bot.features.games import watch
from bot.features.games.bounty import refresh_claims
from bot.core.catchup import catchup
from bot.discord_ui.commands_sync import register_commands
from bot.core.ctx import ctx, sleep
from bot.features.bugs.devboard import schedule_boards
from bot.core.env import cfg
from bot.features.bugs.fixlog import backfill_snapshots
from bot.features.bugs.intake import intake_thread
from bot.discord_ui.interactions import handle_interaction
from bot.discord_ui.router import handle_message
from bot.discord_ui import devlog
from bot.features.bugs import msgreport
from bot.features.bugs import suggest
from bot.features.testers import testers
from bot.features.bugs.tags import ensure_fixed_tag, ensure_suggest_tags, load_tags
from bot.core.timers import run_timers

devlog.install()
intents = discord.Intents.none()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
intents.members = True
intents.invites = True  # the invite tracker
intents.guild_reactions = True
intents.webhooks = True  # a webhook made in the library channel is deleted at once
# nothing pings @everyone or a role unless that one message allows it by name (a game named @everyone, a line in an update...)
SAFE = discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True)
client = discord.Client(intents=intents, allowed_mentions=SAFE, activity=discord.CustomActivity(name='vibecoding...'), status=discord.Status.online)
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
    n = 0
    while True:
        await asyncio.sleep(60)
        n += 1
        try:
            await run_timers()
        except Exception:
            traceback.print_exc()
        if n % 10 == 1:  # every 10 minutes: reporters of fixes in a posted update who were never told (Discord failed, or a restart)
            try:
                from bot.features.bugs.fixes import retry_untold
                await retry_untold()
            except Exception:
                traceback.print_exc()


# The status goes through themes. Each theme has its animated server emoji (for messages), a standard emoji that leads the status (a bot cannot show a
# custom emoji in its status), and words that fit it. Every STATUS_EVERY seconds the status moves to the next word (a new theme, and its emoji, every third word); the dots grow in between.
THEMES = [
    ('vibecoding', '💻', ['vibecoding', 'typing', 'writing code']),
    ('bugsquash', '🐛', ['squashing bugs', 'hunting bugs', 'swatting bugs']),
    ('fixed_it', '✅', ['fixing it', 'patching', 'polishing']),
    ('shipit', '🚀', ['shipping', 'launching', 'deploying']),
    ('thinking_hard', '🤔', ['thinking', 'pondering', 'planning']),
    ('playtesting', '🎮', ['playtesting', 'grinding', 'speedrunning']),
    ('crashed', '💥', ['crashing', 'rebooting', 'recovering']),
    ('reading_reports', '📖', ['reading reports', 'reading logs', 'checking tickets']),
    ('coffee_break', '☕', ['brewing coffee', 'taking a break', 'refueling']),
    ('napping', '😴', ['resting', 'napping', 'idling']),
    ('compiling', '⚙️', ['compiling', 'building', 'loading']),
]
DOT_STEP = 3       # seconds between the dots: the word, then one more dot each step (Discord limits how often a status may change, so not every second)
STATUS_EVERY = 60  # seconds each word stays


async def status_loop():
    n, flat = 0, [(name, mark, word) for name, mark, words in THEMES for word in words]
    try:  # the bot's own (application) emoji: those show in its status
        mine = {e.name: e for e in await client.fetch_application_emojis()}
    except Exception:
        mine = {}
    while True:
        name, mark, word = flat[(n * DOT_STEP // STATUS_EVERY) % len(flat)]
        custom = mine.get(name)  # only logged: Discord drops any emoji a bot puts in its status, so the matching standard emoji goes in the text
        try:
            await client.change_presence(activity=discord.CustomActivity(name=f"{mark} {word}{'.' * (n % 4)}"), status=discord.Status.online)
        except Exception as e:
            if n % 200 == 0:
                print('status', repr(e)[:200])
        if n == 0:
            print('status emoji:', getattr(custom, 'id', None) or mark, 'app emoji found:', len(mine))
        n += 1
        await asyncio.sleep(DOT_STEP)


@client.event
async def on_ready():
    global _started
    if _started:
        return  # reconnects fire on_ready again
    _started = True
    ctx.guild = client.get_guild(int(cfg.guild_id)) or await client.fetch_guild(int(cfg.guild_id))
    print(f'Logged in as {client.user}')
    # the loops start first: a failing step below must never stop timers (giveaways, unbans, deletions) or the watches
    asyncio.ensure_future(timer_loop())
    asyncio.ensure_future(board.sync_loop())
    asyncio.ensure_future(watch.watch_loop())  # every 5 minutes: is each released game still on Roblox?
    from bot.mcp.server import serve as mcp_serve
    asyncio.ensure_future(mcp_serve())  # the MCP for devs' AI agents; a failure only skips it
    asyncio.ensure_future(status_loop())  # the status "types": a small emoji and dot animation
    asyncio.ensure_future(cards.guard_loop())  # the library and its cards are always there, a rival bot's posts never

    async def step(name, work):
        try:
            return await work()
        except Exception:
            print(f'start-up step failed: {name}')
            traceback.print_exc()

    await step('tags', load_tags)
    await step('suggestion tags', ensure_suggest_tags)
    await step('fixed tag', ensure_fixed_tag)
    await step('commands', register_commands)
    await step('invites', invites.load)
    if board.is_live():  # this bot runs the bounty board: read the forum again before anything uses the claims
        await step('bounty board sync', board.sync_forum)
    await step('claims', refresh_claims)
    await step('catch-up', catchup)
    await step('snapshots', backfill_snapshots)  # transcripts for bugs fixed before the log existed

    async def roster():
        if n := await testers.sync_members():
            print(f'{n} tester(s) with a tester role added to the roster')
        await testers.refresh_roster()
    await step('roster', roster)
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
        if msgreport.wants(m) and await msgreport.handle(m):  # a reply of `!bug` or `!suggest`
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
    if conf and str(p.channel_id) == str(conf['channel']) and str(p.message_id) in {str(i) for i in cards.expected_ids()}:  # the library or a live card
        try:
            await cards.refresh_library()
        except Exception:
            traceback.print_exc()


@client.event
async def on_raw_bulk_message_delete(p):
    if cards.in_library_channel(p.channel_id):
        try:
            await cards.refresh_library()
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
async def on_member_join(member):
    try:
        await invites.on_member_join(member)
    except Exception:
        traceback.print_exc()


@client.event
async def on_member_remove(member):
    try:
        await invites.on_member_remove(member)
    except Exception:
        traceback.print_exc()


@client.event
async def on_invite_create(invite):
    await invites.on_invite_create(invite)


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
        try:  # the person always hears back, also when the handler had already started ("thinking...")
            text = 'Something went wrong. Try again in a minute, or tell a developer.'
            if not i.response.is_done():
                await i.response.send_message(text, ephemeral=True)
            else:
                await i.followup.send(text, ephemeral=True)
        except Exception:
            pass
    finally:
        devlog.end(token)
    devlog.record(i, captured, error)


if __name__ == '__main__':
    client.run(cfg.token)
