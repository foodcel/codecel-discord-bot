"""Fills in the original game's Steam pictures (and studio, when empty) for released games. Run on the VM (the real database lives there)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.db import all_, run  # noqa: E402
from bot.games import clean_name  # noqa: E402
from bot.release import steam_art  # noqa: E402


async def main():
    for r in all_("SELECT * FROM game_status WHERE status='released'"):
        name = r.get('original_name') or r.get('title') or clean_name(r['name'])
        art = await steam_art(r.get('source_link'), name)
        if not art['art_url'] and not art['art_hero_url']:
            print('no Steam art for', name)
            continue
        run('UPDATE game_status SET art_url=?, art_hero_url=?, studio=COALESCE(studio, ?) WHERE key=?', art['art_url'], art['art_hero_url'], art['studio'], r['key'])
        print('art for', name, '|', art['art_url'].rsplit('/', 2)[-2] if art['art_url'] else None)


asyncio.run(main())
