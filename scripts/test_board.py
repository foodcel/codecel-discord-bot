"""Tests the bounty board against the real server without touching the real board: the three messages go to the test
channel, tags are never changed, and the claims are imported from the old board (read only) and compared with it.
Cleans the board tables and the test channel messages it made afterwards."""
import asyncio
import re
from types import SimpleNamespace

from _boot import boot, finish

from bot import board, bounty
from bot.db import all_, kv_del, run
from bot.env import cfg


class Out:
    def __init__(self, who):
        self.user = who
        self.sent = []
        self.follow = []

        async def send_message(content=None, **kw):
            self.sent.append(content)

        async def followup_send(content=None, **kw):
            self.follow.append(content)

        self.response = SimpleNamespace(send_message=send_message)
        self.followup = SimpleNamespace(send=followup_send)


def user(id_, admin=False, role=False):
    roles = [SimpleNamespace(id=int(cfg.dev_role))] if role else []
    return SimpleNamespace(id=id_, roles=roles, guild_permissions=SimpleNamespace(administrator=admin), mention=f'<@{id_}>')


async def call(fn, who, **opts):
    o = Out(who)
    await fn(o, opts)
    return o


async def main():
    client = await boot(claims=False)
    problems = []

    async def no_tag(*a, **k):
        return True
    board.set_post_tag = no_tag  # never touch the real forum's tags
    board.tag_if_highly_requested = no_tag

    # 1. read the other bot's board, as the parser of the old version saw it
    ch = await client.fetch_channel(int(cfg.bounty_id))
    old = [m async for m in ch.history(limit=50) if m.author.bot]
    parsed = []
    for m in old:
        for e in m.embeds:
            if re.search('claimed', e.title or '', re.I):
                parsed.extend(bounty.parse_claims(e))
    text = next(e.description for m in old for e in m.embeds if 'Claimed' in (e.title or ''))
    first = re.search(r'/channels/\d+/(\d+)\)', text)
    forum_id = (await client.fetch_channel(int(first.group(1)))).parent_id
    print('forum:', forum_id, '| claims on the old board:', len(parsed))

    # 2. set up a board in the TEST channel
    run('DELETE FROM board_claims')
    run('DELETE FROM board_posts')
    kv_del('board')
    n = board.import_old_board(old)
    board.save_cfg({'forum_id': str(forum_id), 'channel_id': cfg.test_id, 'role_id': cfg.dev_role,
                    'top': None, 'claims': None, 'completed': None})
    print('imported', n, 'claims; synced', await board.sync_forum(), 'posts')

    # 3. the claims must equal the old board's
    mine = board.live_claims()

    def key(c):
        return (re.sub(r'[^a-z0-9]', '', c['name'].lower()), tuple(c['owners']), c['since'])

    a = sorted(key(c) for c in parsed)
    b = sorted(key(c) for c in mine)
    print('open claims: old', len(a), '| mine', len(b))
    for x in set(a) ^ set(b):
        problems.append(f'claim differs: {x}')
    done = all_('SELECT * FROM board_claims WHERE completed_at IS NOT NULL')
    print('completed claims:', [(d['game'] or d['post_id'], d['user_id'], d['completed_at'][:10]) for d in done])

    # 4. the commands, as a dev and as a stranger
    dev = user(111, role=True)
    admin = user(1, admin=True)
    stranger = user(222)
    free = next(p for p in sorted(board.posts(), key=lambda p: -p['votes']) if not board.claim_for_post(p['post_id']))
    o = await call(board.command_claim, stranger, post=free['post_id'])
    if 'Only' not in o.sent[0]:
        problems.append('a stranger could claim')
    o = await call(board.command_claim, dev, post=free['post_id'], link='https://store.steampowered.com/app/1')
    print('claim ->', o.sent[0])
    o = await call(board.command_claim, dev, post=free['post_id'])
    if 'already claimed' not in o.sent[0]:
        problems.append('double claim allowed')
    o = await call(board.command_claim, dev, post='custom:My Test Game')
    print('custom claim ->', o.sent[0])
    o = await call(board.command_claim, dev, post='custom:my test game')
    if 'already claimed' not in o.sent[0]:
        problems.append('custom duplicate allowed')
    o = await call(board.command_claim, dev, post='custom:Another One', link='ftp://x')
    if 'http' not in o.sent[0]:
        problems.append('bad link accepted')
    c = board.claim_for_post(free['post_id'])
    o = await call(board.command_unclaim, stranger, post=f"claim:{c['id']}")
    if 'Only' not in o.sent[0]:
        problems.append('a stranger could unclaim')
    from bot.games import game_lists
    unreleased = game_lists()['unreleased']
    if free['title'] not in [g['name'] for g in unreleased]:
        problems.append('the new claim is not on the games board')
    link = next((g.get('source_link') for g in unreleased if g['name'] == free['title']), None)
    print('game link on the games board:', link)
    if not link:
        problems.append('/claim link not saved')
    # releasing a game completes its claim, moving it back reopens it
    board.set_completed(free['title'], True)
    if not board.claim_for_post(free['post_id'])['completed_at']:
        problems.append('releasing did not complete the claim')
    board.set_completed(free['title'], False)
    if board.claim_for_post(free['post_id'])['completed_at']:
        problems.append('moving back did not reopen the claim')
    o = await call(board.command_assign, admin, post=free['post_id'], dev='333')
    print('assign ->', o.sent[0])
    o = await call(board.command_exclude, admin, post=free['post_id'])
    print('exclude ->', o.sent[0])
    await call(board.command_include, admin, post=free['post_id'])
    o = await call(board.command_unclaim, admin, post=f"claim:{board.claim_for_post(free['post_id'])['id']}")
    print('unclaim ->', o.sent[0])
    o = await call(board.command_unclaim, dev, post=f"claim:{board.claim_for_game('My Test Game')['id']}")
    print('unclaim custom ->', o.sent[0])
    await board.refresh_board()
    print('board messages:', {k: v for k, v in board.board_cfg().items() if k in ('top', 'claims', 'completed')})

    # 5. clean up everything this test made
    c = board.board_cfg()
    tch = await client.fetch_channel(int(cfg.test_id))
    for k in ('top', 'claims', 'completed'):
        try:
            m = await tch.fetch_message(int(c[k]))
            await m.unpin()
            await m.delete()
        except Exception as e:
            print('cleanup', k, e)
    run('DELETE FROM board_claims')
    run('DELETE FROM board_posts')
    kv_del('board')
    run('DELETE FROM game_status')
    print('PROBLEMS:' if problems else 'ALL OK', *problems, sep='\n  ')
    await finish(client)


asyncio.run(main())
