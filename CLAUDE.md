# codecel Discord bot

- Any post, embed or card the bot sends must follow `docs/DESIGN.md` (the design language). Read it first.
- Never post in staff #announcements (1562720074111123536) without asking. Never ping @everyone or roles on my own; restores and re-posts go silent.
- Preview in the test channel: only what changed. Never delete in #dev-logs. Never run two bots with the same token.
- Short answers, no unrequested features.
- Command replies are private (ephemeral) by default; only what a command exists to post is public. See `docs/DESIGN.md`.
- Dev/admin commands are hidden by ROLE with Discord's per-command rules, never with a permission bit. Adding one: add its name to `scripts/lock_commands.py` and run it with a fresh admin token (`--link` explains how). Until then it shows to everyone (the bot still refuses).
