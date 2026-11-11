# Codecel: what it does and what it touches

For Redwing Helper (and anyone who needs to know). This is the list of everything Codecel does on the server: its commands, the channels it posts in or manages, and what runs by itself.

Codecel is the bug, game and update bot. Players report bugs and suggestions to it, developers run their games through it (claims, progress, testing, releases, updates), and it keeps the game library and tester board up to date. (Giveaways moved from Codecel to Redwing Helper on 2026-11-11.)

## Channels it posts in or manages

| Channel | What Codecel does there |
|---|---|
| **#🪲・bugs** (forum) | Players' bug reports. Codecel tags each post (game, device, status), replies to the reporter, asks for missing details, and marks duplicates. When a bug is fixed and its update is out, it tells the reporter, then closes the post and deletes it a day later (the conversation is kept for devs). |
| **#🎯・gameplay-suggestions** (forum) | Players' suggestions. Same tags and replies. Votes (🙏) are counted. |
| **#bugs** in the Testers category (forum) | Tester reports. One post per report, tagged with the game. |
| **#🪲・testing** | Where testers use `/bug`. |
| **#dev-bugs** and **#dev-suggestions** (dev forums) | One board post per developer, rebuilt as reports come in. Update drafts also show up here when a game has enough fixes. |
| **#updates** | Update announcements for released games (fixes, changes, what's new). Can ping @Updates. |
| **#🎮・games** | The Redwing Game Library: one permanent card per game with a Play button, plus the new-game card (shown for 3 days). **Only Codecel may post here.** It deletes messages from other bots and webhooks in this channel, and removes the channel's webhooks. |
| **#bounty-board** | The ranked list of game ideas (by votes) and who claimed which game. Updates itself. Ideas come from **#🎮・game-suggestions** (forum, read only). |
| **#tester-board** | Cards for games that went into testing ("needs testers", volunteer button). Pings @Testers when a game goes into testing; the card goes away after a day. Also holds the games-in-testing list. |
| **#tester-information** and **#read-this** | The tester guide and the tester roster. Codecel keeps both up to date. |
| **#developer-chat** | Game-down alerts (a released game that stopped existing on Roblox), and testing notes. Pings the game's developer. |
| **#dev-logs** | A log of everything developers do with Codecel (commands, buttons, status changes). Tokens and secrets are never written there. |
| **#mod-logs** | Strike notices. A kick or ban needs a developer's confirmation here. |
| **#test** | Private preview channel for Codecel's own posts. |
| Any channel | `/mog` and the Mog right-click app reply where they are used. |

It never posts in staff channels on its own.

## Roles it uses

- **Developers** (and a jr role): developers run games; jr devs can only look.
- **Testers**, **Helpers**: testers report games in testing; helpers can volunteer to test.
- **Updates**: pinged by update announcements. **Releases**: can be pinged by a new-game card.
- **Verified**: an invite only counts once the invited person has it.
- Commands are hidden by role: players only see player commands. Admin and developer commands are invisible to everyone else.

## Commands

**Everyone**
- `/bug`: report a bug (pick the game, up to 10 files, a links box, then a short form). Clip links (Streamable, Medal, X, Imgur) are downloaded and attached as videos. YouTube and Vimeo links stay links.
- `/suggest`: suggest an improvement, same form.
- `/invites stats`, `/invites top`, `/invites link`: your invites, the leaderboard, your own invite link.
- `/tester profile`: testers fill in their devices and free times.
- `/help`: the commands you can use, one page per role.

**Developers** (only for games they claimed)
- `/claim new | edit | drop`: take a game from the bounty board, set its original-game link, or give it up.
- `/progress`: how far a game is, whether the dev is working on it, put it in testing (and the test Play link).
- `/release new | quiet | edit | undo`: release a game (new-game card, can ping), add it without announcing, fix its listing, or move it back to unreleased.
- `/update new | edit | settings`: draft and post an update, change a posted one, set merging and how a dev's AI agent posts.
- `/pings`: choose when Codecel pings you about new bugs and exploits.
- `/mcp setup | revoke`: connect the developer's own AI coding agent to their games' reports (read reports and transcripts, set statuses, post updates, update progress).

**Admins**
- `/assign`, `/exclude`, `/include`, `/bounty-board`: manage who owns which game and what is on the bounty board.
- `/games post | rename`: post or rename entries of the games board.
- `/tester add | remove | status | edit | post`: manage the tester roster and post the tester guide.
- `/strikes`, `/pardon`, `/botrules`: look at or remove troll strikes, post the bug rules.
- `/invites check`: everything about one member's invites.
- `/mcp status | kick | allow | pause | resume`: see who uses the developer agent connection, stop one dev, or switch it off.
- `/mog` and the **Mog** right-click app: Codecel posts a mog GIF (the command pings Robin and Redwing Helper).
- `/preview`: posts finished cards in #test.


**Typed triggers**
- Developers and testers reply `!bug` or `!suggest` to a player's message (optionally with the game) and Codecel posts it in the right forum for that player.
- Developers can write a status word in a report's post, like `fixed`, and Codecel applies it.
- When Redwing Helper mentions or pings Codecel (outside #🎮・games), Codecel answers with a GIF.

## What runs by itself

- **Bug and suggestion intake:** every new post is checked for missing details, duplicates and trolling. Missing details are asked for. A report nobody answers is logged for the developer and never closed for silence.
- **Strikes:** false or troll reports move a person up a ladder: warning, 1-day mute, kick, 7-day ban, permanent ban. Kicks and bans wait for a developer to confirm in #mod-logs. Staff are never struck. Bug hunting (`!bug`, `!suggest`) is paused for someone who saves too many false reports.
- **Fixes:** when a developer marks a bug fixed, the reporter is told when the update that contains it is posted (a tester's fix is told at once and never goes in a public update). The post is closed, then deleted after a day.
- **Update drafts:** after a few fixes on a game, Codecel offers the developer an update draft in their board. Updates can fold into one card within a window the developer chooses.
- **Games:** the library, the bounty board and the games board refresh themselves, and the library is guarded (deleted cards come back, other bots' posts in it are removed).
- **Game watch:** every 5 minutes Codecel checks each released game still exists on Roblox. After two misses in a row it marks the game Offline and pings its developer in #developer-chat; when it comes back, it switches it on and says so.
- **Testing:** a game put into testing gets its tester tag, a card for volunteers that expires after a day, and a Play button.
- **Invites:** it tracks which invite brought each member and counts only members who verify.
- **Developer agent connections:** it serves read and write access to a developer's own games' reports for their AI agent, with limits, and logs the use (not the contents) in #dev-logs.
- **Catching up:** when Codecel restarts it reads what it missed (new posts, replies, board messages) and carries on.

## Good to know for Redwing Helper

- **Do not post in #🎮・games.** Codecel treats it as its own and removes other bots' messages and webhooks there.
- If you ping or mention Codecel, it replies with a GIF (not in #🎮・games).
- Codecel's commands are role-locked. If something looks missing for a player, it is the role, not a bug.
- Questions or bugs about Codecel itself: ask in staff chat.
