"""Lists the tester roster with whether each person is still in the server. Run on the VM."""
import asyncio

from _boot import boot, finish

from bot.ctx import ctx
from bot.testers import everyone


async def main():
    client = await boot(members=True, claims=False)
    for r in everyone():
        m = ctx.guild.get_member(int(r['user_id']))
        print(r['user_id'], r['status'], '| in server' if m else '| NOT IN SERVER', '|', m.display_name if m else '')
    await finish(client)


asyncio.run(main())
