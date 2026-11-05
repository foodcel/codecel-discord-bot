"""Prints each registered slash command with the permission that shows it in the picker. Run on the VM."""
import asyncio

from _boot import boot, finish

from bot.core.env import cfg


async def main():
    client = await boot(claims=False)
    for c in await client.http.get_guild_commands(client.application_id, int(cfg.guild_id)):
        print(c['name'], '|', c.get('default_member_permissions'))
    await finish(client)


asyncio.run(main())
