"""Tests for the parts that need no Discord: links, invite attribution, and the access table vs /help.
Run: python -m unittest discover -s tests   (deploy.sh runs them before every push)."""
import asyncio
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.core import access  # noqa: E402
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
        others = {'draft', 'released', 'unreleased', 'active', 'private', 'pending', 'inactive', 'status'}  # games, testers
        root = Path(__file__).resolve().parent.parent / 'bot'
        found = set()
        for f in root.rglob('*.py'):
            text = f.read_text(encoding='utf8')
            for m in re.finditer(r"status\s*(?:==|!=|=)\s*'([a-z_]+)'|'status': '([a-z_]+)'|status in \(([^)]*)\)", text):
                found |= {w for g in m.groups() if g for w in re.findall(r"'?([a-z_]+)'?", g)}
        unknown = found - set(statuses.ALL) - others
        self.assertFalse(unknown, unknown)


class PlayerReplies(unittest.TestCase):
    def test_every_reply_is_readable_text(self):
        from bot.features.bugs import replies
        for status in ('investigating', 'fixing', 'not_a_bug', 'duplicate', 'declined'):
            view, _ = replies.status_note(status)
            texts = [c.content for c in view.walk_children() if hasattr(c, 'content')]
            self.assertTrue(all(chr(10) * 2 not in t and len(t.split(chr(10))) < 4 for t in texts), (status, texts))


class CardsOnly(unittest.TestCase):
    def test_the_bot_never_builds_an_embed(self):
        import re
        root = Path(__file__).resolve().parent.parent / 'bot'
        found = [f'{f.name}:{n + 1}' for f in root.rglob('*.py') for n, line in enumerate(f.read_text(encoding='utf8').splitlines())
                 if re.search(r'discord\.Embed\(|embeds=\[(?!\])|embed=', line)]
        self.assertFalse(found, f'cards only (docs/DESIGN.md): {found}')


class AccessMatchesHelp(unittest.TestCase):
    def test_help_pages_agree_with_the_table(self):
        from bot.discord_ui.help import PAGES
        for page, (_, _, _, groups) in PAGES.items():
            for _, _, entries in groups:
                for e in entries:
                    if not isinstance(e, str):
                        continue
                    base = e.split('+')[0].split()[0]
                    if base == 'mcp' and page == 'admin':
                        continue  # /mcp is a dev command; its status, kick, pause and resume parts check for an admin themselves
                    need = access.who(base)
                    if page == 'admin':
                        self.assertIn(need, (access.ADMIN, access.EVERYONE), e)
                    elif page == 'dev':
                        self.assertIn(need, (access.DEV, access.EVERYONE), e)
                    else:
                        self.assertEqual(need, access.EVERYONE, e)


if __name__ == '__main__':
    unittest.main()
