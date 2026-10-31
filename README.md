# codecel-discord-bot

A Discord bot that runs bug reports for a community that ships games. Players report bugs in a forum channel, Claude checks each report, and the bot sends it to the developer who owns that game. Developers work from one board: browse, mark fixed, grab a transcript for their AI agent, and post update notes.

Built with discord.js, SQLite and the Anthropic API (Claude Haiku by default, well under a cent per report).

## What it does

**Reports**
- Checks every new post in your bug forum against your template. Missing info gets a friendly list and the **Needs Info** tag, and the bot re-checks when the reporter answers. Posts left unanswered for 3 days are closed.
- Sets the game and device tags, numbers the post (`#12 title`), spots duplicates (and bugs that were already fixed), and warns about personal info in screenshots.
- Exploit write-ups are removed from the public channel at once and appear as a **high priority** card on the owner's board. The reporter is told by DM and gets a DM on every status change.
- Trolling gets a strike ladder: warning, 1-day mute, kick, 7-day ban, permanent ban. Kicks and bans need a developer's confirmation. Staff are never struck.

**Dev boards** (one forum post per dev)
- A summary of the dev's open bugs plus two dropdowns: open a game's bugs in a private page (screenshots, videos, status buttons), or download a transcript.
- Type `12 fixed`, `1-5 fixed`, `7 investigating` in the board. A new bug gives the dev a ghost ping that they can turn off with `/pings`.
- Fixed bugs: the reporter (and everyone who reacted 👀) is pinged, the post closes and is deleted after 24 hours. A reply of "still broken" reopens it.
- **Transcripts**: a zip per bug or per game with the conversation, screenshots, full videos and a few video frames (via ffmpeg), so an AI agent can read it. Files that do not fit Discord's upload limit become download links.
- **Fix log**: a pinned post with fixed / open counts per game and every fix with its transcript.
- **Update announcements**: after 3 fixes the bot drafts an update. Devs press Post, Edit or Later, or use `/update`. What a dev types is rewritten by Claude into clean patch notes.

**Testers**: `/bug` opens a form (up to 10 screenshots and 5 videos) in the tester channel, creates a thread there and sends the bug to the owning dev's board.

**Offline-safe**: when the bot starts it catches up on everything it missed (new posts, replies, timers, deletes).

## Commands

| Command | Who | What |
|---|---|---|
| `/bug` | testers (in the tester channel) | report a bug with a form |
| `/pings` | devs | choose whether you are pinged for new bugs and for exploit reports |
| `/update` | game owner, admins | post an update with the pending bug fixes |
| `/config set` / `show` | game owner, admins | per game: link, icon, announcement channel, ping role, owner |
| `/strikes`, `/pardon` | devs | see or remove troll strikes |
| `/botrules` | admins | post the rules and the strike ladder |
| `/preview` | admins | post sample embeds in the test channel |

Permissions: **devs** act on the games they own (any dev on games nobody owns), **jr devs** are read only, **admins** can do everything. Roles are checked on the server for every click.

## Setup

### 1. Create the Discord application
1. <https://discord.com/developers/applications> > **New Application**. Copy the **Application ID**.
2. **Bot** tab > **Reset Token** (copy it once). Turn on **Message Content Intent** and **Server Members Intent**.
3. **OAuth2 > URL Generator**: scopes `bot` and `applications.commands`. Easiest permission: **Administrator**. Otherwise grant View Channels, Send Messages (also in Threads), Create Public Threads, Read Message History, Embed Links, Attach Files, Manage Messages, Manage Threads, Manage Channels, Manage Roles, Moderate Members, Kick Members, Ban Members and Mention Everyone.
4. Invite it, then drag the bot's role **above** the roles it may punish.

### 2. Prepare the server
- A **forum channel** for reports, with tags: your games, `Mobile`, `Computer`, `Controller`, and the status tags `Investigating`, `Needs Info`, `Fix in Progress`, `Fixed`, `Duplicate`, `Not a Bug`. Mark the status tags as *moderated* so only the bot sets them.
- A **forum channel** only devs can see (the boards).
- A **text channel** for the mod log, and optionally a tester channel and an updates channel.

### 3. Configure
```bash
cp .env.example .env     # then fill it in; every key is explained in the file
```
Turn on Developer Mode in Discord to copy channel, role and server IDs.

### 4. Run it
```bash
npm ci
npm start
```
Needs **Node 22+** and **ffmpeg** on the PATH (ffmpeg is only used for video frames in transcripts). On Windows `start.cmd` restarts the bot if it crashes.

## Hosting on Oracle Cloud (or any Ubuntu VPS)

The bot only makes outgoing connections, so no ports or firewall rules are needed. It stores everything in `data/` (`bot.db` and the fix archive).

**Option A: systemd (simplest)**. On a fresh Ubuntu 22.04 / 24.04 VM (x86 or ARM Ampere):
```bash
git clone https://github.com/foodcel/codecel-discord-bot.git
cd codecel-discord-bot
bash deploy/oracle-setup.sh     # installs Node 24 + ffmpeg, creates .env, run it again after filling .env
```
The second run installs and starts a `codecel-bot` service. Then:
```bash
journalctl -u codecel-bot -f                       # logs
sudo systemctl restart codecel-bot                 # restart
git pull && npm ci --omit=dev && sudo systemctl restart codecel-bot   # update
```

**Option B: Docker**
```bash
cp .env.example .env && nano .env
docker compose up -d --build
docker compose logs -f
```

**Moving an existing bot** (keeps your reports, strikes and archive): stop the old bot, copy `.env` and the whole `data/` folder to the VM (`scp -r data .env user@vm:codecel-discord-bot/`), then start it there. Never run two copies with the same token at once, they would both answer.

Oracle notes:
- Always Free VMs can be **reclaimed when they sit idle** (CPU, network and memory all under about 20% for 7 days). A quiet bot looks idle, so upgrade the account to pay-as-you-go (Always Free resources stay free) or check on it now and then.
- Back up `data/` regularly (stop the bot or use `sqlite3 data/bot.db ".backup bot-backup.db"`).
- Keep `.env` private (`chmod 600 .env`). If a token ever leaks, reset it in the developer portal.

## Project layout

```
src/index.js        startup, events, catch-up
src/intake.js       checks reports (Claude), tags, duplicates, exploits, strikes
src/devboard.js     dev boards, exploit cards, ghost pings
src/bugview.js      the private bug page (prev/next, status buttons)
src/fixes.js        marking fixed / reopening / statuses
src/fixlog.js       the fix log and stored transcripts
src/transcript.js   zip builder (conversation, screenshots, videos, frames)
src/announce.js     update drafts and announcements
src/tester.js       /bug for testers
src/strikes.js      troll ladder
src/ui.js           one shared look for every embed
src/ai.js           all Claude calls (forced tool output, never free text)
scripts/            preview and helper scripts
deploy/             systemd unit and Oracle setup script
```

## Safety notes
- Report text is untrusted. Claude only returns structured data, and the bot's own code decides every action, so a report cannot talk the bot into banning someone.
- Strikes require high confidence, and kicks and bans always need a developer to confirm.
- A daily cap (`AI_DAILY_CAP`) limits how many Claude calls can be made.

## License
MIT
