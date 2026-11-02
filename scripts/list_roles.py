"""Lists the server's roles (id, name, members). Run on the VM."""
import asyncio

from _boot import boot, finish

from bot.ctx import ctx


async def main():
    client = await boot(claims=False)
    for r in sorted(ctx.guild.roles, key=lambda r: -r.position):
        print(r.id, r.name, 'mentionable' if r.mentionable else '', len(r.members))
    await finish(client)


asyncio.run(main())
