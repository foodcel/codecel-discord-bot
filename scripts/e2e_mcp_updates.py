"""End-to-end check of the MCP update tools with # headings and long updates, on a throwaway game in the TEST channel:
a long public update with headings (more than one card), an edit of it, and a tester update. The cards stay in the test channel to look at;
everything else the test made is removed. Run on the VM:
    python scripts/e2e_mcp_updates.py --yes"""
import asyncio
import json
import sys

from _boot import boot, finish

from bot.core.ctx import ctx, fetch_channel
from bot.core.db import all_, kv_del, now, run, upsert_game
from bot.core.env import cfg

TAG, NAME = 'e2e-mcp-updates', 'MCP Test'


async def main():
    client = await boot(members=True)
    if '--yes' not in sys.argv:
        print('Not running. Pass --yes.')
        return await finish(client)
    from bot.discord_ui import devlog
    from bot.features.games import games as games_mod
    from bot.features.updates import announce
    from bot.mcp import writes

    async def quiet(*a, **k):
        return None
    devlog.update_step = quiet  # no entries in #dev-logs
    devlog.post = quiet
    announce.schedule_boards = lambda *a, **k: None  # no refresh of the real dev boards
    games_mod.refresh_game_board = quiet
    cfg.future_games_id = cfg.test_id  # the tester update goes to the test channel, not the tester board
    owner = ctx.guild.get_member(int(ctx.guild.owner_id))
    ch = await fetch_channel(cfg.test_id)
    gk = games_mod.key(NAME)
    ok = True

    def check(name, cond, detail=''):
        nonlocal ok
        ok = ok and bool(cond)
        print(('PASS ' if cond else 'FAIL ') + name + (f' | {detail}' if detail and not cond else ''))

    try:
        upsert_game(TAG, NAME, {'announce_channel_id': str(cfg.test_id)})
        run("INSERT OR REPLACE INTO game_status(key,name,owners,since,status,released_at,released_by,link) VALUES(?,?,?,?,'released',?,?,?)",
            gk, NAME, str(owner.id), '2026-01-01', now(), str(owner.id), 'https://www.roblox.com/games/1/x')
        allowed = [(TAG, NAME)]
        writes.set_settings(allowed, 'MCP', mode='every')
        await ch.send('**MCP test: update with # headings, a long one, then an edit** (throwaway game, not posted anywhere else)', allowed_mentions=announce.NO_MENTIONS)
        changes = ['# 🧱 New blocks'] + [f'Block set {n}: stone, wood, glass and a few more words so the line is long' for n in range(1, 31)]
        changes += ['# 🐰 New mobs'] + [f'Mob {n} with its own sounds and a small drop table' for n in range(1, 21)]
        changes += ['# 💾 Saving and loading', 'Saves remember your exact spot', 'Big maps load about twice as fast']
        p = await writes.post_update(owner, allowed, 'MCP', changes=changes, fixes=['Flower pots no longer flicker'], version='TU31')
        check('post_update with headings posts', p.startswith('Posted'), p)
        ann = all_('SELECT * FROM announcements WHERE tag_id=?', TAG)
        pay = json.loads(ann[0]['payload']) if ann else {}
        check('the headings are kept word for word', '# 🐰 New mobs' in pay.get('changes', []), str(pay.get('changes', [])[:3]))
        check('the long update went on in a second card', len(pay.get('more') or []) >= 1, str(pay.get('more')))
        e = await writes.edit_update(owner, allowed, ann[0]['id'], changes=changes[:5] + ['# 🗺️ Maps', 'The Dropper works now'])
        pay2 = json.loads(all_('SELECT payload FROM announcements WHERE id=?', ann[0]['id'])[0]['payload'])
        check('edit_update edits it', e.startswith('Edited'), e)
        check('the shorter edit removed the extra card', not pay2.get('more'), str(pay2.get('more')))
        run("UPDATE game_status SET status='unreleased', released_at=NULL, testing_at=?, test_link=? WHERE key=?", now(), 'https://www.roblox.com/games/2/test', gk)
        await ch.send('**MCP test: tester update with # headings** (throwaway game)', allowed_mentions=announce.NO_MENTIONS)
        t = await writes.post_tester_update(owner, allowed, 'MCP', fixes=['The car no longer falls through the road'],
                                            what_to_test=['# 🗺️ Chapter 2', 'Drive to the harbour', 'Try the night mode', '# 🎵 Music', 'Does the menu music loop?'], version='0.4')
        check('post_tester_update posts', t.startswith('Posted'), t)
        check('a second one inside 20 minutes is refused', 'under 20 minutes' in await writes.post_tester_update(owner, allowed, 'MCP', what_to_test=['x']))
        check('the tester update did not ping', '(no ping)' in t, t)
    finally:
        run('DELETE FROM announcements WHERE tag_id=?', TAG)  # the cards stay in the test channel to look at
        run('DELETE FROM games WHERE tag_id=?', TAG)
        run('DELETE FROM game_status WHERE key=?', gk)
        run("DELETE FROM pending WHERE data LIKE ?", f'%{TAG}%')
        kv_del(f'testupdate:{gk}')
        print('cleaned up')
    print('ALL PASSED' if ok else 'SOMETHING FAILED')
    await finish(client)


asyncio.run(main())
