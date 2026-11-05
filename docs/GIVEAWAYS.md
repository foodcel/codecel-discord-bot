# Giveaways and the invite tracker

Code: `bot/features/giveaways/giveaway.py`, `bot/features/invites/invites.py`. Look: see `docs/DESIGN.md` (cards, trees, date button, code chips).

## /giveaway (admins and the Giveaway Manager role)
- `/giveaway new title duration [winners] [channel]` opens a **preview card with buttons**; nothing posts until **Start**.
  Buttons: Prizes & time, Rules, required roles (picker), any/all, invites as entries on/off, ping (none / @Giveaways / @everyone).
- `/giveaway end | reroll [place] | cancel | list`.
- Prizes per place: `1: 2k Robux + Nitro`, `2-5: 2k Robux`; or one line = every winner gets it (winners count in the box).
- Rules: required roles (any or all), blacklisted roles, bonus entries per role (`Booster: 2`), min days in server, min invites,
  every invite = one more entry, with an optional cap on one person's entries in total, claim window in hours (unclaimed places are drawn again, up to 3 times).
- Invite giveaways: anyone verified can enter, but they have **0 entries** until their counting invites reach the minimum; then 1 entry, and (if on) one more for every invite past it. Role-bound giveaways: only those roles can enter.
- **Always allowed in** (preview picker): members with those roles (e.g. Server Boost+) skip the role and time requirements. It is not shown on the card. They still need Verified and are not blacklisted.
- Everyone needs the **Verified** role. Everything is checked again when the giveaway ends. The draw is seeded; the seed is on the card and in #dev-logs.
- Winners get one real ping (a reply under the card) and a DM. The card itself never pings.
- Setup: set `GIVEAWAY_MANAGER_ROLE_ID` in `.env` and give that role the **Manage Events** permission (that is what makes `/giveaway` appear in the picker; admins always see it).

## Invite tracker and /invites (a feature of its own, not part of giveaways)
Giveaways only read its numbers for their invite rules.
- Discord does not say which invite a member used, so the bot keeps every invite's use count and finds the one that went up on each join.
- It only knows joins by name from the moment it ran. Earlier uses of a person's live links (Discord's own count) are **counted too** as "earlier invites", but cannot be checked (nobody knows if those people stayed or verified). Links that expired or were deleted are gone with their uses.
- **Counts for the score:** tracked people who are still in the server AND have the Verified role (checked when the number is needed), plus the earlier invites.
- `/invites stats [user]` shows counting / not verified yet / left / joined / uses and the rank. `/invites top` is the leaderboard.
- `/invites link` gives a member their own permanent link (the bot makes it once and remembers the owner, since Discord lists the bot as the creator).
  Joins through it count for that member. The server's vanity link (discord.gg/redwing) is shared, so joins through it cannot be credited to anyone.
- **Per boost:** a line `each boost: 3` in the bonus box gives +3 per server boost. The number of boosts per member is read from the boosters channel (`bot/features/giveaways/boosts.py`); a member who boosts now counts at least 1.
