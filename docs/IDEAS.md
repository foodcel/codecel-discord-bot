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
  Dev (`/claim`, `/release`, `/progress`, `/update`, `/config`, `/pings`, typed commands like `12 fixed`
  and `7 added`), Admin (`/assign`, `/exclude`, `/include`, `/bounty-board`, `/tester add|remove|status|edit|post`, `/games`, `/strikes`, `/pardon`, `/botrules`, `/preview`).
  Jr devs see the dev section marked "read only".
- **Look.** One embed in the same style as the boards: a section per role with a tree of commands and one short line each, plus a footer with where to ask.
  Private reply (only you see it). Admins get a dropdown to view the page of another role.
- **Never goes stale.** Build the list from the command definitions in `bot/commands.py` (name, description, who may use it) instead of typing it twice.
- **Extras.** A line per section on what the bot does by itself (tags, numbers, 24 hour delete), and a "what's new" line that links the last announcement.

## 3. Plain-message look for updates and for the /bug and /improvement posts (from the user, 2026-11-01)
The user shared a screenshot of an update post (Peggle Deluxe, v16) and wants this form factor for the update announcements and for the forms.

- **What the look is.** No embed box. A normal message: role pings on the first line, a bold title (`Game — Update (vN)`), bold section names
  (Fixes, Changes, New) each followed by bullets, nested bullets for detail, small grey footer line ("The servers will restart in 1 minute.").
  Blank line between sections. Reads like a person wrote it, full width, wraps cleanly on a phone.
- **Updates.** `/update` would post this text instead of the embed. Sections come from the draft: Fixes (bug fixes), Changes (updates), New (new features / Added
  suggestions). The ping line stays the ping question (Updates role or none). Merging within 12 hours would append bullets under the right section.
- **Forms.** The post the bot makes for `/bug` and `/improvement` would use the same layout: bold title, bold "What happened" / "Steps" / "Expected" sections with bullets, small footer for game and device.
- **Cons to design away.** Plain messages have no colour bar and no fields, so the design language (rules, columns) does not apply. Text cannot be edited into columns, so keep to bullets.
  Mentions in plain text DO ping, so the update message must keep allowed_mentions on purpose for the role only. 2000 characters per message (4000 for embeds), so long updates need a split.
  Questions to settle before building: should the older embed announcements be converted too, and does the bug post stay an embed in the forum (the dev boards read it)?

## 4. Game library and update posts in the #games style, linked to /release (from the user, 2026-11-01)
The user asked to reverse engineer #games (1562940878685872149) and bring its look to our own library, `/release` and the update posts, in our design
language: more minimal, less wording, clear what to read and where to press, and keep the hero image at the top.

**How #games is built today (read live, 4 messages).**
- It is made with Discord's newer message layout (Components V2), not embeds: one **container** (a card with a coloured side bar) holding text, images and buttons. It is posted by the "Redwing Helper" bot.
- **Message 1, "Redwing Game Library"** (red bar `#C8161D`): hero banner gif on top (a media gallery), `## 🎮 Redwing Game Library` plus one line of intro, a divider, `### 🕹️ Console hubs`,
  two rows (Vyra Station, X-Blocks 360) each with a small Roblox icon on the right, then two **Play** link buttons side by side, then a grey credits line.
- **Message 2, "Games"** (dark blue bar `#13294B`): `### 🎲 Games`, then one row per game: bold name linked to the Roblox game, " · on Roblox as **X**" when the Roblox name differs,
  or " · *Original name*" when ours is a renamed version (Thunderball Deluxe · *Peggle Deluxe*), a line `📱 Mobile · 💻 Computer · 🎮 Controller`,
  and `-# Original game: <studio>` (credit). The original game's cover art sits on the right of every row (a Steam `library_600x900.jpg`, or Wikipedia for non-Steam games).
  Ends with a divider, a "community" line that points to #game-suggestions and #bugs, and a long fan-made / no-affiliation disclaimer.
- **New game announcements** are done by hand: a dev posts the same row (`**[Thunderball Deluxe](roblox link)** · *Peggle Deluxe*`, platforms, original game) and someone pings the Updates role.
- **Update posts** (the Mythos 5.1 / Peggle v16 screenshot) are plain text: role pings, bold title `Game — Update (v16)`, bold Fixes / Changes / New with bullets, small footer. No hero, no button.

**Plan to link it with /release, the bounty board and the games board.**
1. `/release game link` stays the one action: it completes the bounty claim, moves the game to Released on our games board, and now also adds or refreshes the game's row in the #games library.
   `/unrelease` removes the row. Extra optional fields on /release: `original` (studio credit), `roblox_name` (when the Roblox name differs), `platforms`. Remembered, so later updates reuse them.
2. **Art comes for free from data we already have.** The Steam link given on `/claim new link:` / `/progress source:` contains the Steam app id, so the cover is
   `.../steam/apps/<id>/library_600x900.jpg` (and `header.jpg` for a wide hero). Non-Steam games: a Roblox game icon from the Roblox link, or one `art:` image the dev attaches.
3. **Our library layout (minimal).** One container per page: hero banner, a short title, a divider, then one row per game: name linked, one grey line `Original: studio`, platform icons only
   (no words), and a **Play** button on the right as the only thing to press (clear target; the cover art moves to the hero or a small thumbnail instead of the button). The long disclaimer shrinks to one footer line.
   Released games only; Unreleased stays on the bounty board.
4. **Updates in the same family.** `/update` posts a container: hero image of the game (Steam header or a Roblox thumbnail), a big title `# Game — Update v16`,
   bold Fixes / Changes / New with bullets (same sections we already draft), a divider, a small footer, and a **Play** button that opens the Roblox link saved by /release.
   The ping stays the ping question; the Updates role mention is a line inside the message, because this layout cannot have text outside the card.
   Merging within 12 hours adds bullets under the right section in the same card.
5. **Forms (/bug, /improvement) stay as they are until decided** (see idea 3).

**Cons to design away.** (a) This layout allows at most 40 pieces per message, one row costs 3, so about 12 games per message: the library must split across messages and refresh them all.
(b) These messages cannot hold normal text or embeds at the same time, so the update ping and the "new game" ping live inside the card or in a separate small message before it.
(c) The dev boards and update drafts read our embeds, so the post builders must change together. (d) A rename or new link means editing every message of the library; keep it behind one `refresh_library()` like the boards.
(e) The hero image needs a source per game (Steam header works for Steam games only). (f) Our own bot sends raw JSON, so it must set the "components v2" message flag; discord.py 2.7.1 supports it.
Questions to settle before building: where the library lives (a new post in #games, or edit the Redwing Helper messages, which we do not own), whether /release also announces "new game" with the Updates ping, the banner source, and whether the console hubs stay a separate section.

## 5. (from the user, 2026-10-31) Keep adding ideas here as they come
The user will keep sending ideas. Add each one to this file under a new numbered heading.
