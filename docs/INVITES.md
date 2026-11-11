# The invite tracker

Code: `bot/features/invites/invites.py`. Look: see `docs/DESIGN.md` (cards, trees, date button, code chips).

## Invite tracker and /invites
- Discord does not say which invite a member used, so the bot keeps every invite's use count and finds the one that went up on each join.
- It only knows joins by name from the moment it ran. Earlier uses of a person's live links (Discord's own count) are **counted too** as "earlier invites", but cannot be checked (nobody knows if those people stayed or verified). Links that expired or were deleted are gone with their uses.
- **Counts for the score:** tracked people who are still in the server AND have the Verified role (checked when the number is needed), plus the earlier invites.
- `/invites stats [user]` shows counting / not verified yet / left / joined / uses and the rank. `/invites top` is the leaderboard.
- `/invites link` gives a member their own permanent link (the bot makes it once and remembers the owner, since Discord lists the bot as the creator).
  Joins through it count for that member. The server's vanity link (discord.gg/redwing) is shared, so joins through it cannot be credited to anyone.
