"""Posts an EXAMPLE tester roster in the test channel: every status at once and made-up report counts. Nothing is saved."""
import asyncio

from _boot import boot, finish

from bot.env import cfg
from bot.testers import roster_embed

IDS = ['730122432005799936', '1538291492844474431', '444835664102555649', '1194076216769130517', '1487659910807162932',
       '492051688023261196', '793202570700259328', '1504563246584299721', '1153897865077330022']


def t(i, status, devices=None, recording=None, availability=None, best_for=None, only_for=None):
    return {'user_id': IDS[i], 'status': status, 'devices': devices, 'recording': recording, 'availability': availability,
            'best_for': best_for, 'only_for': only_for, 'added_at': i}


ROWS = [
    t(0, 'active', 'PC, Mobile, PS4 Controller', 'OBS, Medal', 'Frequently available; short notice ok (After school)', 'PC, Mobile, Controller, Urgent testing'),
    t(1, 'active', 'Xbox, Mobile, PC (limited)', 'Built-in recording', 'Most days; short notice available', 'Xbox, Mobile, Cross-platform testing'),
    t(2, 'active', 'PC', 'OBS, Medal', 'After 2 PM (Brazil time)', 'PC, Gameplay recording, Bug testing'),
    t(3, 'active', 'PlayStation, Mobile', 'Built-in recording', '5-7 hours/day, 3-4 days/week', 'PlayStation, Mobile, Long-term testing'),
    t(4, 'private', 'Xbox', 'Twitch/OBS', '12 PM-3 AM', 'Xbox, Difficult games', only_for='945836832548089886'),
    t(5, 'pending'),
    t(6, 'pending', 'Playstation, Mobile, Laptop', 'Medal', '4-8 hours a day', None),
    t(7, 'inactive', 'PC', 'OBS', 'On a break until next week', 'Everything'),
    t(8, 'pending'),
]
REPORTS = {IDS[0]: 14, IDS[1]: 9, IDS[2]: 1, IDS[3]: 6, IDS[4]: 3}  # made up


async def main():
    client = await boot(members=True, claims=False)
    ch = await client.fetch_channel(int(cfg.test_id))
    await ch.send(content='**Example roster** · every status at once, made-up report counts (nothing here is real data except the names)',
                  embed=roster_embed(ROWS, REPORTS))
    await finish(client)


asyncio.run(main())
