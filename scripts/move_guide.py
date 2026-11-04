"""Moves the tester responsibilities card out of the tester board's channel into another channel (it keeps updating there).
    python scripts/move_guide.py <channel id>      Run on the VM."""
import asyncio
import json
import sys

from _boot import boot, finish

from bot.ctx import fetch_channel
from bot.db import kv_get, kv_set
from bot.look import card_from_embed
from bot.testers import guide_embed


async def main():
    client = await boot(claims=False)
    b = json.loads(kv_get('testerboard'))
    dest = await fetch_channel(sys.argv[1])
    print('destination:', dest, getattr(dest, 'name', ''))
    view, files = card_from_embed(guide_embed())
    new = await dest.send(view=view, files=files)
    old_channel, old_id = b.get('guideChannelId') or b['channelId'], b['guide']
    b['guide'], b['guideChannelId'] = str(new.id), str(dest.id)
    kv_set('testerboard', json.dumps(b))
    try:
        await (await fetch_channel(old_channel)).get_partial_message(int(old_id)).delete()
        print('old card removed')
    except Exception as e:
        print('old card not removed', repr(e))
    print('new card', new.jump_url)
    await finish(client)


asyncio.run(main())
