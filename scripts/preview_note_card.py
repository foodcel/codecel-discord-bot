"""Posts one testers card WITH a dev note to the TEST channel (no pings), to see how it looks. Uses a throwaway game_status row that is deleted after.
    python scripts/preview_note_card.py [game name]"""
import asyncio
import sys

from _boot import boot, finish

from bot.core.ctx import fetch_channel
from bot.core.db import one, run
from bot.core.env import cfg
from bot.discord_ui.components import NO_MENTIONS
from bot.features.testers.testerboard import card_view

NOTE = 'Need several people in the same server. Also need some to test battle royale. Report in testing, not bugs.'


async def main():
    client = await boot(claims=False)
    name = ' '.join(sys.argv[1:]) or 'Hyperballin'
    src = one('SELECT * FROM game_status WHERE lower(name)=lower(?) OR key=?', name, name.lower()) or {}
    key = 'zz-preview'
    run('DELETE FROM game_status WHERE key=?', key)
    run('INSERT INTO game_status (key, name, art_url, icon_url, hero_url, test_note) VALUES (?,?,?,?,?,?)',
        key, name, src.get('art_url'), src.get('icon_url'), src.get('hero_url'), NOTE)
    try:
        view, files, _ = card_view({'key': key, 'name': name, 'owners': []}, ping=False)
        ch = await fetch_channel(cfg.test_id)
        await ch.send('**Preview: testers card with a dev note** (nothing pinged)', allowed_mentions=NO_MENTIONS)
        await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    finally:
        run('DELETE FROM game_status WHERE key=?', key)
    print('posted')
    await finish(client)


asyncio.run(main())
