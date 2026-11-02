"""Posts a live release preview (with working buttons, test mode) in the test channel: python scripts/demo_draft.py "Jump King". Run on the VM."""
import asyncio
import sys

from _boot import boot, finish

from bot.ctx import fetch_channel
from bot.db import create_pending, one
from bot.env import cfg
from bot.games import _find, clean_name, owner_ids
from bot.release import roblox_info, steam_art, steam_studio
from bot import reldraft


async def main():
    client = await boot()
    k, rel, dev = _find(sys.argv[1])
    link = (one('SELECT link FROM game_status WHERE key=?', k) or {}).get('link')
    info = await roblox_info(link) or {}
    original = clean_name(dev['name'])
    art = await steam_art(dev.get('source_link'), original)
    studio = await steam_studio(dev.get('source_link')) or art['studio']
    pid = create_pending({'kind': 'release', 'user': '0', 'game': sys.argv[1], 'key': k, 'name': dev['name'], 'owners': ','.join(owner_ids(dev)), 'since': dev.get('since'),
                          'quiet': False, 'link': link, 'info': info, 'art': art, 'studio': studio, 'original': original, 'note': 'Multiplayer + VC. Only 1 map so far.',
                          'ping': 'everyone', 'title': None, 'hero_file': None, 'mine': None, 'test': True})
    ch = await fetch_channel(cfg.test_id)
    p = reldraft.payload(pid)
    sent = await ch.send(view=p['view'], files=p['attachments'], allowed_mentions=p['allowed_mentions'])
    print('draft', pid, 'message', sent.id)
    await finish(client)


asyncio.run(main())
