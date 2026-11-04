# Giveaways and the invite tracker

Code: `bot/giveaway.py`, `bot/invites.py`. Look: see `docs/DESIGN.md` (cards, trees, date button, code chips).

## /giveaway (admins and the Giveaway Manager role)
- `/giveaway new title duration [winners] [channel]` opens a **preview card with buttons**; nothing posts until **Start**.
  Buttons: Prizes & time, Rules, required roles (picker), any/all, invites as entries on/off, ping (none / @Giveaways / @everyone).
- `/giveaway end | reroll [place] | cancel | list`.
- Prizes per place: `1: 2k Robux + Nitro`, `2-5: 2k Robux`; or one line = every winner gets it (winners count in the box).
- Rules: required roles (any or all), blacklisted roles, bonus entries per role (`Booster: 2`), min days in server, min invites,
  every invite = one more entry (optional cap), claim window in hours (unclaimed places are drawn again, up to 3 times).
- Everyone needs the **Verified** role. Everything is checked again when the giveaway ends. The draw is seeded; the seed is on the card and in #dev-logs.
- Winners get one real ping (a reply under the card) and a DM. The card itself never pings.
- Setup: set `GIVEAWAY_MANAGER_ROLE_ID` in `.env` and give that role the **Manage Events** permission (that is what makes `/giveaway` appear in the picker; admins always see it).

## Invite tracker and /invites (a feature of its own, not part of giveaways)
Giveaways only read its numbers for their invite rules.
- Discord does not say which invite a member used, so the bot keeps every invite's use count and finds the one that went up on each join.
- It only knows joins from the moment it ran. Older uses show in "uses" but cannot be checked.
- **Counts for the score:** the person it brought is still in the server AND has the Verified role, checked when the number is needed.
- `/invites stats [user]` shows counting / not verified yet / left / joined / uses and the rank. `/invites top` is the leaderboard.
