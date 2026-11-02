"""Posts a sample /update draft (working buttons) in the test channel: python scripts/demo_update.py "Peggle". Run on the VM."""
import asyncio
import sys

from _boot import boot, finish

from bot.announce import draft_payload
from bot.bounty import owners_for
from bot.ctx import fetch_channel
from bot.db import create_pending, upsert_game
from bot.env import cfg
from bot.tags import find_game_tag, tag_name


async def main():
    client = await boot()
    t = find_game_tag(sys.argv[1])
    tag_id = t['id'] if isinstance(t, dict) else t
    upsert_game(tag_id, tag_name(tag_id))
    pid = create_pending({'tagId': tag_id, 'bugIds': [], 'bugfixes': ['Fixed the ball getting stuck on the left peg', 'Fixed the score not saving after a level'],
                          'newIds': [], 'newLines': [], 'updates': ['Added a second map'], 'version': 'v17', 'owners': owners_for(tag_id, tag_name(tag_id)), 'off': []})
    p = await draft_payload(pid)
    ch = await fetch_channel(cfg.test_id)
    sent = await ch.send(view=p['view'], files=p['files'], allowed_mentions=p['allowed_mentions'])
    print('draft', pid, sent.id)
    await finish(client)


asyncio.run(main())
