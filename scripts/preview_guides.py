"""Posts the two forum guide embeds (bugs and suggestions) into the test channel. Nothing is changed in the forums."""
import asyncio

from _boot import boot, finish

from bot.env import cfg
from bot.guides import bugs_guide_embed, suggestions_guide_embed


async def main():
    client = await boot(claims=False)
    ch = await client.fetch_channel(int(cfg.test_id))
    await ch.send(content='**Bug forum guide draft** · would replace the pinned post "Bug Reports - Guidelines & Template" (NOT changed yet)', embed=bugs_guide_embed())
    await ch.send(content='**Suggestions forum guide draft** · would replace the pinned post "START HERE" (NOT changed yet)', embed=suggestions_guide_embed())
    await finish(client)


asyncio.run(main())
