"""Tests for the parts that need no Discord: links, giveaway prizes and entries, the draw, invite attribution, and the access table vs /help.
Run: python -m unittest discover -s tests   (deploy.sh runs them before every push)."""
import asyncio
import random
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.core import access  # noqa: E402
from bot.features.giveaways import giveaway as gw
from bot.features.invites import invites
from bot.core import links
from bot.core.ctx import ctx  # noqa: E402


class Links(unittest.TestCase):
    def test_roblox_game(self):
        ok = 'https://www.roblox.com/games/108938568298960'
        self.assertEqual(links.roblox_game('https://www.roblox.com/games/108938568298960/X-Blocks-360'), ok)
        self.assertEqual(links.roblox_game('roblox.com/games/108938568298960/x'), ok)
        self.assertEqual(links.roblox_game('https://www.roblox.com/de/games/108938568298960'), ok)

    def test_roblox_rejects_tricks(self):
        for bad in ('https://evil.com/?x=roblox.com/games/1', 'https://evil.com\\.roblox.com/games/1', 'https://roblox.com.evil.com/games/1',
                    'https://user:pw@roblox.com/games/1', 'javascript:alert(1)', 'https://www.roblox.com/catalog/1', ''):
            self.assertIsNone(links.roblox_game(bad), bad)

    def test_share_links_and_web(self):
        self.assertEqual(links.roblox_any('ro.blox.com/Ebh5'), 'https://ro.blox.com/Ebh5')
        self.assertEqual(links.web_url('store.steampowered.com/app/1'), 'https://store.steampowered.com/app/1')
        self.assertIsNone(links.web_url('https://localhost/x'))


class Prizes(unittest.TestCase):
    def test_places_and_ranges(self):
        p, err = gw.parse_prizes('1-2: 2k robux + nitro\n3–5 2k robux', 1)
        self.assertIsNone(err)
        self.assertEqual(p, [['2K Robux', 'Nitro']] * 2 + [['2K Robux']] * 3)

    def test_missing_place_and_bad_line(self):
        self.assertTrue(gw.parse_prizes('1: a\n3: b', 1)[1])
        self.assertTrue(gw.parse_prizes('1-2: a\nhello', 1)[1])

    def test_one_prize_for_everyone_and_split(self):
        self.assertEqual(gw.parse_prizes('Nitro', 3)[0], [['Nitro']] * 3)
        self.assertEqual(gw.split_prize('10K Robux', 5), [['2K Robux']] * 5)
        self.assertEqual(gw.split_prize('Nitro', 2), [['Nitro']] * 2)

    def test_duration(self):
        self.assertEqual(gw.parse_duration('1d 6h'), 108000)
        self.assertEqual(gw.fmt_duration(108000), '1d 6h')

    def test_text_round_trip(self):
        p, _ = gw.parse_prizes('1-2: 2K Robux + Nitro\n3-5: 2K Robux', 1)
        self.assertEqual(gw.parse_prizes(gw.prize_text_of(p), 1)[0], p)


class Draw(unittest.TestCase):
    def test_same_seed_same_winners(self):
        pool = [('a', 1), ('b', 5), ('c', 1), ('d', 3)]
        self.assertEqual(gw.draw(pool, 3, random.Random('seed')), gw.draw(pool, 3, random.Random('seed')))

    def test_nobody_wins_twice(self):
        w = gw.draw([('a', 1), ('b', 1)], 5, random.Random(1))
        self.assertEqual(sorted(w), ['a', 'b'])


class Entries(unittest.TestCase):
    def setUp(self):
        self.member = types.SimpleNamespace(roles=[types.SimpleNamespace(id=5, name='Level 5'), types.SimpleNamespace(id=10, name='Level 10')],
                                            premium_since=None, id=1)
        self._q, self._guild = invites.qualified, ctx.guild
        invites.qualified = lambda uid: 30
        roles = {r.id: r for r in self.member.roles}
        ctx.guild = types.SimpleNamespace(get_role=lambda i: roles.get(int(i)), premium_subscriber_role=None)

    def tearDown(self):
        invites.qualified, ctx.guild = self._q, self._guild

    def config(self, **kw):
        c = {'prizes': [['x']], 'req_roles': [], 'req_mode': 'any', 'blacklist': [], 'bonus': {'5': 2, '10': 5}, 'min_invites': 0,
             'invite_entries': True, 'invite_cap': 10, 'min_days': 0, 'claim_hours': 0, 'ping': 'none', 'bonus_best': True, 'per_boost': 0}
        c.update(kw)
        return c

    def test_cap_on_total(self):
        self.assertEqual(gw.entries_for(self.member, self.config())[0], 10)

    def test_highest_level_only(self):
        total, rows = gw.entries_for(self.member, self.config(invite_entries=False, invite_cap=0))
        self.assertEqual(total, 1 + 5)

    def test_below_invite_minimum_is_zero(self):
        invites.qualified = lambda uid: 1
        self.assertEqual(gw.entries_for(self.member, self.config(min_invites=2))[0], 0)


class InviteBurst(unittest.TestCase):
    def test_each_join_of_a_burst_is_attributed(self):
        invites._cache.clear()
        invites._cache.update({'abc': {'uses': 5, 'max': 0, 'inviter': '7'}})
        snap = {'abc': {'uses': 8, 'max': 0, 'inviter': '7'}, 'new': {'uses': 4, 'max': 0, 'inviter': '9'}}

        async def fake():
            return {k: dict(v) for k, v in snap.items()}
        rows, old_snap, old_run, old_guild = [], invites._snapshot, invites.run, ctx.guild
        invites._snapshot, invites.run, ctx.guild = fake, (lambda sql, *a: rows.append(a)), types.SimpleNamespace(id=1)
        try:
            async def go():
                for uid in (101, 102, 103, 104):
                    await invites.on_member_join(types.SimpleNamespace(bot=False, id=uid, guild=types.SimpleNamespace(id=1)))
            asyncio.run(go())
        finally:
            invites._snapshot, invites.run, ctx.guild = old_snap, old_run, old_guild
        self.assertEqual([r[1] for r in rows], ['7', '7', '7', None])  # three uses of abc, the fourth join is not from a known new use


class CardLimits(unittest.TestCase):
    def test_long_cards_fit(self):
        from discord import ui
        from bot.discord_ui.pngs import PART_LIMIT, TEXT_LIMIT, fit
        items = [ui.TextDisplay('### head'), ui.Separator()] + [ui.TextDisplay('x' * 300) for _ in range(60)] + [ui.Separator(), ui.TextDisplay('-# foot')]
        out = fit(items, keep_tail=2)
        self.assertLessEqual(sum(len(getattr(x, 'content', '') or '') for x in out), TEXT_LIMIT)
        self.assertLessEqual(len(out), PART_LIMIT)
        self.assertEqual(out[-1].content, '-# foot')
        self.assertIn('more not shown', out[-3].content)


class StatusWords(unittest.TestCase):
    def test_only_known_statuses_in_code(self):
        import re
        from bot.features.bugs import statuses
        others = {'running', 'drawing', 'ended', 'cancelled', 'draft', 'released', 'unreleased', 'active', 'private', 'pending', 'inactive', 'status'}  # giveaways, games, testers
        root = Path(__file__).resolve().parent.parent / 'bot'
        found = set()
        for f in root.rglob('*.py'):
            text = f.read_text(encoding='utf8')
            for m in re.finditer(r"status\s*(?:==|!=|=)\s*'([a-z_]+)'|'status': '([a-z_]+)'|status in \(([^)]*)\)", text):
                found |= {w for g in m.groups() if g for w in re.findall(r"'?([a-z_]+)'?", g)}
        unknown = found - set(statuses.ALL) - others
        self.assertFalse(unknown, unknown)


class AccessMatchesHelp(unittest.TestCase):
    def test_help_pages_agree_with_the_table(self):
        from bot.discord_ui.help import PAGES
        for page, (_, _, _, groups) in PAGES.items():
            for _, _, entries in groups:
                for e in entries:
                    if not isinstance(e, str):
                        continue
                    base = e.split()[0]
                    need = access.who(base)
                    if page == 'admin':
                        self.assertIn(need, (access.ADMIN, access.GIVEAWAY, access.EVERYONE), e)
                    elif page == 'dev':
                        self.assertIn(need, (access.DEV, access.EVERYONE), e)
                    else:
                        self.assertEqual(need, access.EVERYONE, e)


if __name__ == '__main__':
    unittest.main()
