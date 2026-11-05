"""End-to-end check of /bug against the real server using a fake interaction. Uses an unclaimed game (no dev is pinged)
and the bot itself as the "tester", then removes everything it created."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

from _boot import boot, finish

from bot.features.games.bounty import owners_for
from bot.features.bugs.bugview import bug_embeds
from bot.core.ctx import fetch_channel, remove_thread_notice
from bot.core.db import DATA_DIR, bug_by_id, cancel_timers, one, run
from bot.features.bugs.devboard import open_bugs_for, refresh_all_boards
from bot.core.env import cfg
from bot.features.bugs.fixes import mark_fixed
from bot.features.bugs.tags import game_tags
from bot.features.bugs.tester import modal_bug
from bot.features.bugs.transcript import single_transcript


async def main():
    client = await boot(members=True)
    tag = next(t for t in game_tags() if not owners_for(t['id'], t['name']))
    print('unclaimed game used:', tag['name'])
    form = {'title': '[BOT TEST] Car falls through the map', 'what': 'After checkpoint 2 the car drops through the road',
            'steps': '1. Start race\n2. Pass checkpoint 2', 'expected': 'Car stays on the road', 'device': 'PS5'}

    async def defer(**kw):
        pass

    async def edit_original_response(**kw):
        print('REPLY TO TESTER:', kw)

    fake = SimpleNamespace(user=SimpleNamespace(id=client.user.id), response=SimpleNamespace(defer=defer),
                           edit_original_response=edit_original_response)
    await modal_bug(fake, tag['id'], 'none', form)
    bug = one("SELECT * FROM bugs WHERE source='tester' ORDER BY id DESC LIMIT 1")
    print('bug row:', {k: bug[k] for k in ('id', 'game_name', 'title', 'severity', 'device', 'status', 'routed')})
    thread = await fetch_channel(bug['thread_id'])
    print('thread in #testing:', thread.name if thread else None, '| parent ok:', bool(thread) and str(thread.parent_id) == cfg.testing_id)
    emb = (await bug_embeds(bug))[0]
    print('bug page device field:', next((f.value.strip() for f in emb.fields if 'DEVICE' in f.name), None),
          '| quote shown:', 'What happened' in (emb.description or ''))
    print('on unclaimed board:', any(b['id'] == bug['id'] for b in open_bugs_for('unclaimed')))
    t = await single_transcript(bug['id'])
    print('transcript has tester body:', 'Report as written by the tester' in (t['inline'] or ''))
    await mark_fixed(bug, str(client.user.id))
    await asyncio.sleep(4)
    after = await fetch_channel(bug['thread_id'])
    print('after fix, status:', bug_by_id(bug['id'])['status'], '| thread archived:', after.archived if after else None)
    th = await fetch_channel(bug['thread_id'])
    if th:
        await remove_thread_notice(th)
        try:
            await th.delete(reason='e2e test cleanup')
        except Exception:
            pass
    cancel_timers('delete_thread', bug['thread_id'])
    run('DELETE FROM bugs WHERE id=?', bug['id'])
    for ext in ('zip', 'md'):
        Path(DATA_DIR, 'archive', f"bug-{bug['id']}.{ext}").unlink(missing_ok=True)
    await refresh_all_boards()
    print('cleaned up. bug row left:', bool(bug_by_id(bug['id'])))
    await finish(client)


asyncio.run(main())
