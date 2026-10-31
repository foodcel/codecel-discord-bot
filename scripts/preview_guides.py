"""Posts the two forum guide embeds (bugs and suggestions) into the test channel. Nothing is changed in the forums."""
import asyncio

from _boot import boot, finish

from bot.env import cfg
from bot.guides import bugs_guide_embed, games_guide_embed, suggestions_guide_embed


async def main():
    client = await boot(claims=False)
    ch = await client.fetch_channel(int(cfg.test_id))
    async for m in ch.history(limit=60):  # my earlier drafts of these two are replaced
        if m.author.id == client.user.id and m.content.startswith(('**Bug forum guide draft**', '**Suggestions forum guide draft**', '**Game suggestions forum guide draft**')):
            await m.delete()
    await ch.send(content='**Bug forum guide draft** · would replace the pinned post "Bug Reports - Guidelines & Template" (NOT changed yet)', embed=bugs_guide_embed())
    await ch.send(content='**Suggestions forum guide draft** · would replace the pinned post "START HERE" (NOT changed yet)', embed=suggestions_guide_embed())
    await ch.send(content='**Game suggestions forum guide draft** · would replace the pinned post "START HERE | Game Suggestions, Rules & Tags" (NOT changed yet)', embed=games_guide_embed())
    await finish(client)


asyncio.run(main())
