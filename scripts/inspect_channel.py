"""Shows what a channel is: python scripts/inspect_channel.py <id>. Run on the VM."""
import asyncio
import sys

from _boot import boot, finish

from bot.core.ctx import ctx


async def main():
    client = await boot(claims=False)
    ch = await client.fetch_channel(int(sys.argv[1]))
    print(type(ch).__name__, ch.name, 'category:', getattr(ch.category, 'name', None), 'parent', getattr(ch, 'category_id', None))
    for t in getattr(ch, 'available_tags', []):
        print('tag', t.id, t.name, 'moderated' if t.moderated else '')
    me = ctx.guild.me
    p = ch.permissions_for(me)
    print('bot can: view', p.view_channel, 'post', p.create_public_threads, 'send_in_threads', p.send_messages_in_threads, 'manage_channels', p.manage_channels, 'manage_threads', p.manage_threads)
    print('require_tag', getattr(ch.flags, 'require_tag', None))
    await finish(client)


asyncio.run(main())
