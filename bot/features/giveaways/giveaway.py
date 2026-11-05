"""/giveaway: customizable giveaways, in the community look (docs/DESIGN.md, "Community"): a banner made for each giveaway, short lines, real role pings.
An admin (or someone with the Giveaway Manager role) runs /giveaway new with only what the banner needs (the prize, how long, how many winners).
That opens a preview with buttons: prizes and time, rules, banner (draw it again with other words), hosts, required roles, ping, channel.
Nothing posts until Start. People enter with a button. When the time is up the bot draws the winners.
What a giveaway can have:
  - a prize per place ("1: 2K Robux + Nitro", "2-5: 2K Robux"); by default the prize is split over the winners (10K Robux, 5 winners = 2K each), shown as a podium
  - required roles (any / all), blacklisted roles, a minimum time in the server, bonus entries for roles (Booster +2, Donator +3...)
  - a minimum number of invites (invites that count = the person is still here and has the Verified role, see invites.py)
  - every invite as one more entry (with an optional cap)
  - a claim window: winners press Claim in time or their place is drawn again
  - hosts: whoever the admin picks, not only the person who ran the command
Everything is checked again when the giveaway ends, so someone who left, lost the role or got un-verified is skipped.
The draw is seeded (the seed is shown), so it can be re-run to prove it was fair.

The code lives in rules.py, card.py, draw.py, draft.py, stats.py and command.py; this module re-exports it for the rest of the bot."""

from bot.features.giveaways.rules import can_run, parse_prizes, split_prize, parse_duration, fmt_duration, prize_text_of, entries_for, eligible
from bot.features.giveaways.card import container, banner_for
from bot.features.giveaways.draw import draw, end, claim_expired, reroll, cancel, redraw, valid_pool, enter, mine, leave, claim
from bot.features.giveaways.draft import on_component, on_modal, new_draft, payload, start
from bot.features.giveaways.stats import stats_card
from bot.features.giveaways.command import autocomplete, command_giveaway

__all__ = ['can_run', 'parse_prizes', 'split_prize', 'parse_duration', 'fmt_duration', 'prize_text_of', 'entries_for', 'eligible', 'container', 'banner_for', 'draw', 'end', 'claim_expired', 'reroll', 'cancel', 'redraw', 'valid_pool', 'enter', 'mine', 'leave', 'claim', 'on_component', 'on_modal', 'new_draft', 'payload', 'start', 'stats_card', 'autocomplete', 'command_giveaway']
