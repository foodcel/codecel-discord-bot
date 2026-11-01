"""Fills in the Roblox icon, hero image, name and creator of released games that were released before /release new existed.
Run on the VM (the real database lives there). Changes nothing that a dev already set."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.db import all_, run  # noqa: E402
from bot.release import roblox_info  # noqa: E402


async def main():
    for r in all_("SELECT * FROM game_status WHERE status='released' AND link IS NOT NULL"):
        if r.get('icon_url'):
            continue
        info = await roblox_info(r['link'])
        if not info or not info.get('icon_url'):
            print('nothing for', r['name'])
            continue
        run('UPDATE game_status SET icon_url=?, hero_url=COALESCE(hero_url, ?), roblox_name=COALESCE(roblox_name, ?), creator=COALESCE(creator, ?), place_id=COALESCE(place_id, ?) WHERE key=?',
            info['icon_url'], info.get('hero_url'), info.get('name'), info.get('creator'), info.get('place_id'), r['key'])
        print('filled', r['name'], '|', info.get('name'))


asyncio.run(main())
