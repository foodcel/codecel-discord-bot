"""Prints the permissions of the roles that matter for hiding commands (only the ones that are on). Run on the VM."""
import asyncio

from _boot import boot, finish

from bot.ctx import ctx
from bot.env import cfg


async def main():
    client = await boot(claims=False)
    ids = {str(cfg.dev_role), '1562726451797565521', '1565120384519381052'}
    for r in ctx.guild.roles:
        if r.is_default() or str(r.id) in ids:
            on = [n for n, v in r.permissions if v]
            print(r.id, r.name, '|', ', '.join(on))
    await finish(client)


asyncio.run(main())
