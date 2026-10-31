"""Sets up the bounty board without a slash command: takes over the claims the old board lists, optionally empties the channel,
posts and pins the three messages, registers the board commands. Run it where the bot's database is (on the VM).
    python scripts/setup_board.py --channel=<id> --forum=<id> --role=<id> [--purge] --yes
Posts no announcement and pings nobody."""
import asyncio
import sys

from _boot import boot, finish

from bot import board
from bot.commands_sync import register_commands
from bot.ctx import ctx


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


if '--yes' not in sys.argv or not (arg('channel') and arg('forum') and arg('role')):
    print('Not doing anything. Pass --channel= --forum= --role= and --yes.')
    sys.exit(0)


async def main():
    client = await boot(members=True, claims=False)
    ch = await client.fetch_channel(int(arg('channel')))
    me = ctx.client.user.id
    old = [m async for m in ch.history(limit=100)]
    print(f'{len(old)} messages in #{ch.name}:', sorted({m.author.name for m in old}))
    imported = board.import_old_board([m for m in old if m.author.bot and m.author.id != me])  # before anything is deleted
    print('took over', imported, 'claims from the old board')
    board.save_cfg({'forum_id': arg('forum'), 'channel_id': str(ch.id), 'role_id': arg('role'), 'top': None, 'claims': None, 'completed': None})
    if '--purge' in sys.argv:
        deleted = 0
        while True:
            msgs = [m async for m in ch.history(limit=100)]
            if not msgs:
                break
            try:
                await ch.delete_messages(msgs) if len(msgs) > 1 else await msgs[0].delete()
            except Exception:
                for m in msgs:
                    try:
                        await m.delete()
                    except Exception:
                        pass
            deleted += len(msgs)
        print('deleted', deleted, 'messages')
    print('synced', await board.sync_forum(), 'posts')
    board.released_from_claims()
    await board.refresh_board()
    await register_commands()
    print('board:', board.board_cfg())
    await finish(client)


asyncio.run(main())
