"""Fix all on the bug page: three throwaway bugs of a throwaway game, as an admin. Checks the list the button counts, the confirm page, and that all end up fixed.
    python scripts/e2e_fixall.py        run on the VM (cleans up after itself)"""
import asyncio
from types import SimpleNamespace

from _boot import boot, finish

from bot.core.db import all_, bug_by_id, now, run
from bot.features.bugs import bugview
from bot.features.bugs.nums import forget

GAME, TAG = 'ZZ Fixall Test', 'g-zzfixall'


async def main():
    client = await boot(claims=False)
    admin = SimpleNamespace(id=1, guild_permissions=SimpleNamespace(administrator=True), roles=[])
    ids = [run("INSERT INTO bugs(thread_id,reporter_id,game_tag_id,game_name,title,status,created_at,routed,kind,source) VALUES(?,?,?,?,?,'new',?,1,'bug','form')",
               f'fake-{k}', '1', TAG, GAME, f'[BOT TEST] fixall {k}', now()).lastrowid for k in range(3)]
    forget()
    try:
        print('counted by the button:', len(bugview.fixable(admin, 'unclaimed', TAG)), '(expect 3)')
        page = bugview._confirm_page('x', 'v:fixyes:a:b:1', 'v:fixno:a:b:1')
        print('confirm page buttons:', [c.label for c in page['view'].children[1].children])
        from bot.features.bugs.fixes import apply_status
        done, skipped = await apply_status(ids, 'fixed', admin, via='e2e')
        print('done', len(done), 'skipped', skipped)
        print('statuses:', [bug_by_id(i)['status'] for i in ids], '| left open in list:', len(bugview.fixable(admin, 'unclaimed', TAG)))
    finally:
        run('DELETE FROM bugs WHERE id IN (%s)' % ','.join('?' * len(ids)), *ids)
        forget()
        print('cleaned up. rows left:', len(all_("SELECT id FROM bugs WHERE title LIKE '[BOT TEST] fixall%'")))
    await finish(client)


asyncio.run(main())
