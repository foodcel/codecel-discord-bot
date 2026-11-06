"""End-to-end check of the MCP write tools on a throwaway game and report in the TEST channel (nothing touches a real game, the dev log or the dev boards):
asks the reporter, reads the transcript, posts an update, merges a second one into it (🆕), edits it, then removes everything it made. Run on the VM:
    python scripts/e2e_mcp.py --yes"""
import asyncio
import json
import sys

from _boot import boot, finish

from bot.core.ctx import ctx, fetch_channel
from bot.core.db import all_, kv_del, now, run, upsert_game
from bot.core.env import cfg

TAG, NAME = 'e2e-mcp-test', 'MCP Test'


async def main():
    client = await boot(members=True)
    if '--yes' not in sys.argv:
        print('Not running. Pass --yes.')
        return await finish(client)
    from bot.discord_ui import devlog
    from bot.features.updates import announce
    from bot.features.bugs.transcript import bug_bundle
    from bot.mcp import reports, writes

    async def quiet(*a, **k):
        return None
    devlog.update_step = quiet  # no entries in #dev-logs
    announce.schedule_boards = lambda *a, **k: None  # no refresh of the real dev boards
    from bot.features.games import games as games_mod

    async def no_refresh(*a, **k):
        return None
    games_mod.refresh_game_board = no_refresh  # nor of the real games board
    owner = ctx.guild.get_member(int(ctx.guild.owner_id))
    ch = await fetch_channel(cfg.test_id)
    made = []
    threads = []
    ok = True

    def check(name, cond, detail=''):
        nonlocal ok
        ok = ok and bool(cond)
        print(('PASS ' if cond else 'FAIL ') + name + (f' | {detail}' if detail and not cond else ''))

    try:
        upsert_game(TAG, NAME, {'announce_channel_id': str(cfg.test_id)})
        starter = await ch.send('MCP end-to-end test (this is removed again)')
        made.append(starter)
        thread = await starter.create_thread(name='E2E MCP test report')
        threads.append(thread)
        row = run("INSERT INTO bugs(thread_id,reporter_id,game_tag_id,game_name,title,summary,severity,status,routed,created_at,kind,body) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                  str(thread.id), str(owner.id), TAG, NAME, 'E2E test report', 'A made-up report for the MCP test.', 'low', 'new', 1, now(), 'bug', 'The car falls through the road when I drive fast.')
        bug_id = row.lastrowid
        allowed = [(TAG, NAME)]

        t = reports.list_text(allowed, 'MCP', 'bug', '')
        check('list_bugs finds the report', f'id {bug_id}' in t, t)
        check('search finds it by words', f'id {bug_id}' in reports.search_text(allowed, 'MCP', 'car road'))
        check('report text is wrapped as untrusted', reports.UNTRUSTED in reports.report_text(allowed, bug_id, cfg.guild_id))
        check('another game cannot read it', 'No report' in reports.report_text([('x', 'Other')], bug_id, cfg.guild_id))

        a1 = await writes.ask_reporter(owner, allowed, bug_id, ['Which map were you on?'])
        check('ask_reporter posts', a1.startswith('Asked'), a1)
        a2 = await writes.ask_reporter(owner, allowed, bug_id, ['again?'])
        check('a second question is refused for 6 hours', 'asked less than' in a2, a2)
        bundle = await bug_bundle(all_('SELECT * FROM bugs WHERE id=?', bug_id)[0])
        check('transcript contains the question', 'Which map were you on' in bundle['md'], bundle['md'][-400:])

        s1 = await writes.set_status(owner, allowed, [bug_id], 'fixed')
        check('set_status previews without changing', 'Nothing changed yet' in s1 and all_('SELECT status FROM bugs WHERE id=?', bug_id)[0]['status'] == 'new', s1)
        check('set_status refuses a wrong code', 'does not match' in await writes.set_status(owner, allowed, [bug_id], 'fixed', 'nope'))

        check('add_note adds a developer note', writes.add_note(allowed, bug_id, 'Looks like a collision problem') == 'Note added.' and 'collision' in (all_('SELECT note FROM bugs WHERE id=?', bug_id)[0]['note'] or ''))
        check('settings default: manual, no merging, no pings', all(w in writes.set_settings(allowed, 'MCP') for w in ('only when you say so', 'Merging: off', 'may not ping')))
        check('settings can change', 'every' in writes.set_settings(allowed, 'MCP', mode='every'))

        p1 = await writes.post_update(owner, allowed, 'MCP', fixes=['Fixed the car falling through the road'], version='1.0')
        check('post_update posts', p1.startswith('Posted'), p1)
        p_ping = await writes.post_update(owner, allowed, 'MCP', changes=['x'], ping='role')
        check('a ping is refused while pings are off', 'not allowed pings' in p_ping, p_ping)
        p_off = await writes.post_update(owner, allowed, 'MCP', changes=['Too soon'])
        check('with merging off a second post inside 20 minutes is refused', 'under 20 minutes' in p_off, p_off)
        check('merging can be switched on', '6 hours' in writes.set_settings(allowed, 'MCP', merge=6))
        p2 = await writes.post_update(owner, allowed, 'MCP', whats_new=['A night mode'], changes=['Faster loading'])
        check('a second update merges into the first', p2.startswith('Added to the earlier update'), p2)
        ann = all_('SELECT * FROM announcements WHERE tag_id=? ORDER BY id DESC', TAG)
        check('one card holds all lines', len(ann) == 1 and 'A night mode' in json.loads(ann[0]['payload'])['new'], str(ann))
        check('the added lines are marked fresh', 'A night mode' in (json.loads(ann[0]['payload']).get('fresh') or []))
        e1 = await writes.edit_update(owner, allowed, ann[0]['id'], fixes=['Fixed the car falling through the road (edited)'])
        check('edit_update edits the card', e1.startswith('Edited'), e1)
        check('the edit is saved', 'edited' in json.loads(all_('SELECT payload FROM announcements WHERE id=?', ann[0]['id'])[0]['payload'])['bugfixes'][0])
        gk = games_mod.key(NAME)
        run("INSERT OR REPLACE INTO game_status(key,name,owners,since,status,released_at,released_by,link) VALUES(?,?,?,?,'released',?,?,?)", gk, NAME, str(owner.id), '2026-01-01', now(), str(owner.id), 'https://www.roblox.com/games/1/x')
        eg = await writes.edit_game(owner, allowed, 'MCP', title='MCP Test Renamed', online='offline', description='Only 1 map so far')
        row_ = all_('SELECT title, online, notes FROM game_status WHERE key=?', gk)[0]
        check('edit_game changes title, online and description', eg.startswith('Updated') and row_['title'] == 'MCP Test Renamed' and row_['online'] == 0 and row_['notes'] == 'Only 1 map so far', f'{eg} {row_}')
        check('edit_game with nothing to change says so', 'Nothing to change' in await writes.edit_game(owner, allowed, 'MCP'))
        check('list_testers answers', 'volunteered' in writes.testers_text(owner, allowed, 'MCP'))
        check('list_updates shows it', 'night' in writes.updates_text(allowed, 'MCP').lower() or 'edited' in writes.updates_text(allowed, 'MCP'))
        check('the owner of another game cannot edit it', 'No update' in await writes.edit_update(owner, [('z', 'Z')], ann[0]['id'], fixes=['x']))
    finally:
        for a in all_('SELECT channel_id, message_id FROM announcements WHERE tag_id=?', TAG):
            try:
                m = await (await fetch_channel(a['channel_id'])).fetch_message(int(a['message_id']))
                await m.delete()
            except Exception:
                pass
        for t in threads:
            try:
                await t.delete()  # a thread outlives its starter message, so it is deleted itself
            except Exception:
                pass
        for m in made:
            try:
                await m.delete()
            except Exception:
                pass
        ids = [b['id'] for b in all_('SELECT id FROM bugs WHERE game_tag_id=?', TAG)]
        for i in ids:
            kv_del(f'mcp_ask:{i}')
        run('DELETE FROM bugs WHERE game_tag_id=?', TAG)
        run('DELETE FROM announcements WHERE tag_id=?', TAG)
        run('DELETE FROM games WHERE tag_id=?', TAG)
        run('DELETE FROM game_status WHERE key=?', games_mod.key(NAME))
        run("DELETE FROM pending WHERE data LIKE ?", f'%{TAG}%')
        print('cleaned up')
    print('ALL PASSED' if ok else 'SOMETHING FAILED')
    await finish(client)


asyncio.run(main())
