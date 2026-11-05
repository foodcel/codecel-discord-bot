"""End-to-end check of the suggestions flow on the real server: a suggestion, a bug posted as a suggestion, a vague post, and a
duplicate are made as the bot, run through Claude and the boards, then removed. The bug boards are never refreshed from this
(local) database, and no announcement draft is made."""
import asyncio
from types import SimpleNamespace

from _boot import boot, finish

from bot.features.bugs import devboard
from bot.features.bugs import fixes
from bot.features.bugs import suggest
from bot.core.ctx import fetch_channel
from bot.core.db import all_, bug_by_id, cancel_timers, kv_del, kv_get, run
from bot.core.env import cfg
from bot.features.bugs.fixes import apply_status
from bot.features.bugs.tags import ensure_suggest_tags, load_tags, suggest_game_tags, tag_name

ADMIN = SimpleNamespace(id=1, roles=[], guild_permissions=SimpleNamespace(administrator=True))
made = []


async def post(forum, title, text, game):
    tag = next((t for t in forum.available_tags if t.name == game), None)
    r = await forum.create_thread(name=title, content=text, applied_tags=[tag] if tag else [])
    made.append(r.thread)
    await asyncio.sleep(1.5)
    return r.thread


async def bot_messages(thread):
    return [m.content for m in [m async for m in thread.history(limit=20, oldest_first=True)] if m.author.bot and m.id != thread.id]


async def main():
    client = await boot(members=True, claims=False)
    devboard.schedule_boards = lambda: None  # the real boards must not be rebuilt from this local database
    fixes.maybe_offer = lambda *a, **k: asyncio.sleep(0)  # and no announcement draft
    # the posts are made by the bot itself, so the intake is told they come from an ordinary player
    real_starter = suggest.fetch_starter

    async def fake_starter(thread):
        m = await real_starter(thread)
        return SimpleNamespace(id=m.id, content=m.content, author=SimpleNamespace(bot=False, id=1))

    async def fake_gather(thread, bug):
        m = await real_starter(thread)
        return {'text': m.content, 'images': [], 'videos': []}

    suggest.fetch_starter = fake_starter
    suggest.gather = fake_gather
    await load_tags()
    await ensure_suggest_tags()
    print('suggestion game tags:', [t['name'] for t in suggest_game_tags()])
    forum = await client.fetch_channel(int(cfg.suggestions_id))
    print('status tags in the forum:', [t.name for t in forum.available_tags if t.moderated])

    # leftovers of an earlier run that stopped half way
    for t in [*[t for t in await client.guilds[0].active_threads() if t.parent_id == forum.id], *[t async for t in forum.archived_threads(limit=50)]]:
        if '[BOT TEST]' in t.name:
            await t.delete()
    for r in all_("SELECT thread_id FROM bugs WHERE title LIKE '%BOT TEST%' OR thread_id NOT IN ('x')") if False else []:
        pass
    old_board = kv_get('devthread:Sunclaimed')
    if old_board:
        try:
            await (await fetch_channel(old_board)).delete()
        except Exception:
            pass
        kv_del('devthread:Sunclaimed')
    run("DELETE FROM bugs WHERE source='suggestions' OR kind='suggestion'")

    # 1. a normal suggestion
    t1 = await post(forum, '[BOT TEST] Add a night mode', 'Please add a night mode to the main menu of Vyra Station, with darker colors, so it is easier on the eyes at night.', 'Vyra Station')
    await suggest.intake_suggestion(t1)
    b1 = all_("SELECT * FROM bugs WHERE thread_id=?", str(t1.id))[0]
    t1 = await fetch_channel(t1.id)
    print('1. suggestion:', {k: b1[k] for k in ('id', 'kind', 'status', 'game_name', 'title', 'routed', 'votes')})
    print('   thread:', t1.name, '| tags:', [t.name for t in t1.applied_tags])
    print('   bot said:', [m[:110] for m in await bot_messages(t1)])
    print('   on the suggestion board:', any(b['id'] == b1['id'] for b in devboard.open_bugs_for('Sunclaimed')),
          '| on the bug board:', any(b['id'] == b1['id'] for b in devboard.open_bugs_for('unclaimed')))
    board_thread = await fetch_channel(kv_get('devthread:Sunclaimed'))
    print('   board post:', board_thread.name if board_thread else None, '| in dev-suggestions:', str(board_thread.parent_id) == cfg.dev_suggestions_id)
    emb = devboard.board_embed('Sunclaimed')
    print('   board embed:', emb.title, '|', (emb.description or '')[:60].replace('\n', ' '), '|', [f.name for f in emb.fields])

    # 2. status commands by kind
    done, skipped = await apply_status([b1['id']], 'investigating', ADMIN, 'suggestion')
    print('2. investigating on a suggestion ->', done, skipped)
    done, skipped = await apply_status([b1['id']], 'fixed', ADMIN, 'bug')
    print('   fixed typed in the BUG board ->', done, skipped)
    done, skipped = await apply_status([b1['id']], 'fixed', ADMIN, 'suggestion')
    await asyncio.sleep(2)
    b1 = bug_by_id(b1['id'])
    t1 = await fetch_channel(t1.id)
    print('   added ->', done, '| status:', b1['status'], '| archived:', t1.archived, '| tags:', [t.name for t in t1.applied_tags])
    print('   bot said:', [m[:90] for m in (await bot_messages(t1))[-1:]])

    # 3. a bug posted as a suggestion (not routed to the real bug board here)
    async def no_route(bug, silent=False):
        run('UPDATE bugs SET routed=1 WHERE id=?', bug['id'])
    suggest.route_bug = no_route
    t2 = await post(forum, '[BOT TEST] Crash', 'The game crashes every time I open the shop in Undertale on my phone. It closes completely.', 'Undertale')
    await suggest.intake_suggestion(t2)
    b2 = all_("SELECT * FROM bugs WHERE thread_id=?", str(t2.id))[0]
    print('3. bug in suggestions:', {k: b2[k] for k in ('id', 'kind', 'source', 'status', 'game_name', 'severity')})
    print('   bot said:', [m[:130] for m in await bot_messages(await fetch_channel(t2.id))])

    # 4. a vague post
    t3 = await post(forum, '[BOT TEST] make it better', 'make it better', 'Gang Beasts')
    await suggest.intake_suggestion(t3)
    b3 = all_("SELECT * FROM bugs WHERE thread_id=?", str(t3.id))[0]
    t3 = await fetch_channel(t3.id)
    print('4. vague:', {k: b3[k] for k in ('id', 'kind', 'status', 'asks')}, '| tags:', [t.name for t in t3.applied_tags])
    print('   bot said:', [m[:160] for m in await bot_messages(t3)])

    # 5. a duplicate of the first (already added)
    t4 = await post(forum, '[BOT TEST] Night mode please', 'Can you add a dark night mode to the Vyra Station menu? Darker colors would be nice.', 'Vyra Station')
    await suggest.intake_suggestion(t4)
    b4 = all_("SELECT * FROM bugs WHERE thread_id=?", str(t4.id))[0]
    print('5. duplicate:', {k: b4[k] for k in ('id', 'kind', 'status', 'dup_of')})
    print('   bot said:', [m[:140] for m in await bot_messages(await fetch_channel(t4.id))])

    # clean up everything this test made
    for t in made:
        try:
            fresh = await fetch_channel(t.id)
            await fresh.delete(reason='e2e test cleanup')
        except Exception as e:
            print('cleanup', e)
        cancel_timers('delete_thread', str(t.id))
        cancel_timers('stale', str(t.id))
    run("DELETE FROM bugs WHERE thread_id IN (%s)" % ','.join('?' * len(made)), *[str(t.id) for t in made])
    if board_thread:
        try:
            await board_thread.delete(reason='e2e test cleanup')
        except Exception as e:
            print('cleanup board', e)
        kv_del('devthread:Sunclaimed')
    print('cleaned up. rows left:', len(all_("SELECT * FROM bugs WHERE title LIKE '%BOT TEST%'")), '| tag name check:', tag_name(forum.available_tags[0].id))
    await finish(client)


asyncio.run(main())
