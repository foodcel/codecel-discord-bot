# Ideas (saved, not built)

## 1. Report a message as a bug, with the form already filled in
Devs and testers can turn any message into a report without retyping it.

- **How it would work.** A message command: right click (or long press) a message, Apps, **Report as bug** (and a second one, **Suggest as improvement**).
  A slash command cannot see which message you replied to, so the message command is the way. A fallback: `/bug message:<link>`.
- **What gets filled in.** The message text becomes "What happened", the first line becomes the title, its images and videos are attached,
  and the bot guesses the game from the text (Claude), shown as a pick list to confirm. The form then opens with everything filled in and
  the person only checks it and sends. Same result as `/bug`: a post in the bug forum, checked by the bot, sent to the dev who owns the game.
- **Credit.** The post says "Reported from a message by @author" and keeps a link back to the original message. The reporter is the person who used the command.
- **Who.** Devs and testers only at first (players could spam it).
- **Cons to design away.** Message commands cannot take options, so the game is guessed or asked in a pick list first. Long threads: only the one message is used.
  Private channels: the original text is copied into a public forum, so show a warning when the message is not in a public channel.

## 2. `/helper`, a help command that shows only what you can use
One command that explains the bot, organized per role. You only see the sections for the roles you have.

- **Sections.** Everyone (`/bug`, `/improvement`, where to use them), Tester (`/tester profile`, the testing channel and `/bug` there),
  Dev (`/claim`, `/unclaim`, `/release`, `/unrelease`, `/progress`, `/gamelink`, `/update`, `/config`, `/pings`, `/tester find`, typed commands like `12 fixed`
  and `7 added`), Admin (`/assign`, `/exclude`, `/include`, `/bounty-board`, `/tester add|remove|status|edit|post`, `/games`, `/strikes`, `/pardon`, `/botrules`, `/preview`).
  Jr devs see the dev section marked "read only".
- **Look.** One embed in the same style as the boards: a section per role with a tree of commands and one short line each, plus a footer with where to ask.
  Private reply (only you see it). Admins get a dropdown to view the page of another role.
- **Never goes stale.** Build the list from the command definitions in `bot/commands.py` (name, description, who may use it) instead of typing it twice.
- **Extras.** A line per section on what the bot does by itself (tags, numbers, 24 hour delete), and a "what's new" line that links the last announcement.
