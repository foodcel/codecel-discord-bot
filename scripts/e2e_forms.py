"""End-to-end check of /bug and /improvement for everyone on the real server: forms are sent as a made-up player, the posts are made in the
real forums, checked by Claude, then everything is removed. The real dev boards are never touched."""
import asyncio
from types import SimpleNamespace

from _boot import boot, finish

from bot import devboard, forms, intake, suggest
from bot.ctx import fetch_channel
from bot.db import all_, bug_by_id, cancel_timers, run
from bot.env import cfg
from bot.tags import ensure_suggest_tags, find_game_tag, load_tags

made = []


async def noop(*a, **k):
    return None


def fake(user_id=1):
    sent = []

    async def defer(**k):
        pass

    async def edit_original_response(**k):
        sent.append(k.get('content'))

    return SimpleNamespace(user=SimpleNamespace(id=user_id), response=SimpleNamespace(defer=defer), edit_original_response=edit_original_response), sent


async def submit(kind, game, fields):
    i, sent = fake()
    forms._last.clear()
    id_ = await forms.modal_form(i, kind, game['id'], 'none', fields, analyze=False)
    row = bug_by_id(id_)
    made.append(row['thread_id'])
    thread = await fetch_channel(row['thread_id'])
    await forms._analyze(id_, thread, kind)
    await asyncio.sleep(1)
    row = bug_by_id(id_)
    thread = await fetch_channel(row['thread_id'])
    msgs = []
    if thread:
        msgs = [m.content for m in [m async for m in thread.history(limit=10, oldest_first=True)] if m.author.bot and m.id != thread.id]
    return row, thread, msgs, sent


async def main():
    client = await boot(members=True, claims=False)
    devboard.schedule_boards = lambda: None  # the real boards are not rebuilt from this local database
    intake.route_bug = noop
    suggest.route_bug = noop
    intake.post_exploit = noop
    await load_tags()
    await ensure_suggest_tags()
    game = find_game_tag('Vyra Station')

    row, t, msgs, sent = await submit('bug', game, {
        'title': '[BOT TEST] Notes stop responding', 'what': 'After restarting a song in Vyra Station the notes stop responding to my taps.',
        'steps': '1. Start any song\n2. Restart it from the pause menu\n3. Tap the notes', 'expected': 'Notes should react', 'device': 'iPhone 14'})
    print('1. /bug:', {k: row[k] for k in ('id', 'kind', 'source', 'status', 'game_name', 'title', 'routed', 'device')})
    print('   post:', t.name, '| in bug forum:', str(t.parent_id) == cfg.bugs_id, '| tags:', [x.name for x in t.applied_tags])
    print('   bot said:', [m[:100] for m in msgs]); print('   reply to player:', sent[0][:90].replace('\n', ' '))

    row, t, msgs, sent = await submit('bug', game, {'title': '[BOT TEST] broken', 'what': 'it is broken', 'steps': 'idk', 'expected': '', 'device': ''})
    print('2. vague /bug:', {k: row[k] for k in ('id', 'status', 'asks')}, '| bot said:', [m[:120].replace('\n', ' ') for m in msgs])

    row, t, msgs, sent = await submit('bug', game, {
        'title': '[BOT TEST] Free coins glitch', 'what': 'You can duplicate coins by spamming the trade button while the other player lags. I did it 50 times and got rich.',
        'steps': '1. Open a trade\n2. Spam the accept button during lag\n3. Coins duplicate', 'expected': '', 'device': 'PC'})
    print('3. exploit via /bug:', {k: row[k] for k in ('id', 'status', 'deleted')}, '| post still there:', t is not None)

    row, t, msgs, sent = await submit('suggestion', game, {
        'title': '[BOT TEST] Add a practice mode', 'what': 'Please add a practice mode in Vyra Station where songs can be slowed down.', 'why': 'It would help me learn hard songs.'})
    print('4. /improvement:', {k: row[k] for k in ('id', 'kind', 'source', 'status', 'game_name', 'routed')})
    print('   post:', t.name, '| in suggestions forum:', str(t.parent_id) == cfg.suggestions_id, '| tags:', [x.name for x in t.applied_tags])
    print('   bot said:', [m[:100] for m in msgs])

    for tid in made:
        try:
            th = await fetch_channel(tid)
            if th:
                await th.delete(reason='e2e test cleanup')
        except Exception as e:
            print('cleanup', e)
        cancel_timers('delete_thread', tid)
        cancel_timers('stale', tid)
    run("DELETE FROM bugs WHERE thread_id IN (%s)" % ','.join('?' * len(made)), *made)
    print('cleaned up. rows left:', len(all_("SELECT * FROM bugs WHERE source='form'")))
    await finish(client)


asyncio.run(main())
