"""Posts the pinned "get started" post in the testers forum (or redraws it when it is already there). Run on the VM.   python scripts/post_tester_guide.py"""
import asyncio

from _boot import boot, finish

from bot.botnews import strip, tester_guide_embeds
from bot.ctx import fetch_channel
from bot.db import kv_get, kv_set
from bot.env import cfg


async def main():
    client = await boot(claims=False)
    forum = await fetch_channel(cfg.tester_forum_id)
    thread = None
    if kv_get('tester_guide'):
        try:
            thread = await client.fetch_channel(int(kv_get('tester_guide')))
        except Exception:
            thread = None
    if thread:
        msg = await thread.fetch_message(thread.id)  # the first message of a forum post shares the post's id
        await msg.edit(embeds=tester_guide_embeds(), attachments=[strip()])
        print('redrawn', thread.jump_url)
    else:
        created = await forum.create_thread(name='👋 Get started', embeds=tester_guide_embeds(), files=[strip()], reason='Get started post')
        thread = created.thread
        kv_set('tester_guide', str(thread.id))
        await thread.edit(pinned=True, locked=True)  # pinned at the top, and nobody replies in it
        print('posted and pinned', thread.jump_url)
    await finish(client)


asyncio.run(main())
