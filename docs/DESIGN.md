# Design language for the bot's posts

Every post the bot makes (announcements, boards, update/new-game cards, forum posts, help) follows this. Read it before adding or changing one.
Code: `bot/look.py` (any embed -> card), `bot/botnews.py` (`tree`, `make`, `as_card`, `code_chip`, `date_button`), `bot/pngs.py` (`with_strip`), `bot/cards.py`, `bot/testerboard.py`.

## Philosophy
- **One look everywhere.** A new post must look like it belongs next to the old ones. If a post looks different, that is a bug, not a style.
- **Compact and clean.** No dead space, no empty lines that are not meant, no emojis that repeat what the text says. If a line says "13 released", it needs no icon.
- **Dates are real dates, not "2 minutes ago".** The only exception is the update card, which has a counting chip (`<t:stamp:R>`).
- **Ping inside the card** (a label line or under the title), never floating above with dead space. An announcement ping sits right above the card with nothing between.
- **Short text.** Branch lines stay under 56 characters (a channel link counts as 16). Check with `too_long()`.
- **No new features through design.** A restyle changes how a post looks, not what it does.
- **Show before you push.** Mock it in the test channel (only the post that changed, never the whole set), get a yes, then roll it out by editing the existing messages in place. Never repost, never ping.
- **Know the limits and say so.** Columns, lines and colours cannot all be had at once (see below). Offer A/B mockups instead of guessing; the user picks.

## The card (Components V2)
Order, top to bottom:
1. **Header**: `### Title` with the date as a greyed-out disabled button on the right (the only thing Discord puts right of a title). A thumbnail replaces the date when the post has a picture.
2. **Line** (small visible Separator) under the header. Lines are only for separating header and footer, never in the middle.
3. **Body**: text displays. Groups are trees (below). A blank line between groups.
4. **Line** above the footer. It is the faint line PNG (`with_strip`) so it also forces the full card width.
5. **Footer**: commands as code chips in small text: `` -# `/cmd` · what it does ``. Only a command at the start of the line (`/` or `!`) becomes a chip (`code_chip`).
6. **Pickers and buttons** sit below the card (outside), never inside it.

Counts go in the title: `🛠️ UNRELEASED GAMES · 22 in development`, `💡 TOP SUGGESTIONS · 380 open`. No emoji in front of the counts.

## Trees
Lists are trees: `├─ **Name** · text`, last row `└─`. Built with `botnews.tree()`. Inside a board, a dev is a heading and their games are the branches, with a blank line between devs and between testers.

## Pings and roles
- Dev announcements ping Developers, tester ones ping Tester, updates ping Updates, helpers ping Helpers (IDs in `bot/env.py`).
- New game card: ping in the label line `-# 🎉 NEW GAME · @everyone`. Update card: title, then `-# ping`, then `-# <t:stamp:R>`.
- The bot never pings `@everyone` or a role on its own. Restores and re-posts go out silent (`AllowedMentions.none()`).

## What Discord allows (the walls)
- Only embeds have side-by-side columns. Only cards have thin lines. Pick one per post.
- A V2 message has no `content` and no embeds, max 40 components. A classic embed message can be edited into a card in place (`msg.edit(content=None, embeds=[], view=..., attachments=...)`); a card cannot go back.
- The width strip (1400x2 PNG in a media gallery) makes every card the same width. Hero images are cropped to ratio 3.1 (`cards._cropped`).
- Cards on the bounty board have no columns, so progress sits on the same line as the game ("B card").

## Where each post stands
- Cards: announcements, bounty board (3 messages), dev boards, tester board, `/help`, roster, guides, update / new-game / needs-testers cards, `/release` and `/update` previews, `!bug` replies.
- Intentionally still embeds: bug page and fix log (they need columns), strike / mod-log, dev-log entries, exploit high-priority card, the `/games` board.
- Forums: bug numbers are per game (`#3`, `Game #3`, via `bot/nums.py`). Tags use ✅ fixed / added and ❌ declined with the emoji next to the game.

## Rules when you build one
1. Start from `look.card_from_embed(...)` or `botnews.as_card(...)`; do not hand-roll a layout.
2. Keep the embed fallback (`edit_card` falls back to the old embed if Discord refuses).
3. Dates via `date_button()`. Commands via `code_chip()`. Width via `with_strip()`.
4. Invisible spacer characters (`​ ㅤ       ⠀`) count as blank in `look.ZWS`; never leave one as a stray line.
5. Preview in the test channel, wait for the user's yes, then edit in place.
