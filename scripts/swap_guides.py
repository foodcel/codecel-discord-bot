"""Replaces the pinned guide post of a forum with a new one made by the bot (the embed from bot/guides.py): the new post is made first,
the old one is unpinned, the new one pinned and locked like it, and only then the old post is deleted.
    python scripts/swap_guides.py --which=bugs|suggestions|games --yes        Run it where the bot's database is (the VM)."""
import asyncio
import sys

from _boot import boot, finish

from bot.env import cfg
from bot.guides import bugs_guide_embed, games_guide_embed, suggestions_guide_embed

GAMES_FORUM = '1562961976387174452'
JOBS = {
    'bugs': {'forum': cfg.bugs_id, 'old': '1563050995695616070', 'embed': bugs_guide_embed, 'tag': None},
    'suggestions': {'forum': cfg.suggestions_id, 'old': '1564659699264135278', 'embed': suggestions_guide_embed, 'tag': 'Vyra Station'},
    'games': {'forum': GAMES_FORUM, 'old': '1562995535374192811', 'embed': games_guide_embed, 'tag': None},
}


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


if '--yes' not in sys.argv or arg('which') not in JOBS:
    print('Not doing anything. Pass --which=bugs|suggestions|games and --yes.')
    sys.exit(0)


async def main():
    client = await boot(claims=False)
    job = JOBS[arg('which')]
    forum = await client.fetch_channel(int(job['forum']))
    old = await client.fetch_channel(int(job['old']))
    tags = [t for t in forum.available_tags if t.name == job['tag']] if job['tag'] else []
    needs_tag = forum.flags.require_tag and not tags
    if needs_tag:  # the old post was made by an admin without a tag: allow that for the few seconds this takes
        await forum.edit(require_tag=False)
    try:
        made = await forum.create_thread(name=old.name, embed=job['embed'](), applied_tags=tags, reason='Guide post replaced')
    finally:
        if needs_tag:
            await forum.edit(require_tag=True)
    new = made.thread
    await old.edit(locked=False, pinned=False, archived=False)  # one pinned post per forum: the old one lets go first
    await new.edit(pinned=True)
    await new.edit(locked=True)
    await old.delete(reason='Replaced by the new guide post')
    if forum.id == int(GAMES_FORUM):  # the bounty board must not list the guide as a suggestion
        from bot import board
        if board.is_live():
            board.forget_posts([str(new.id)])
            await board.refresh_board()
    print(f'{arg("which")}: new post {new.jump_url} pinned={True} locked={True}; old post deleted')
    await finish(client)


asyncio.run(main())
