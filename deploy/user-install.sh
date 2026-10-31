#!/usr/bin/env bash
# No-root install: runs the bot as a systemd USER service (no sudo needed).
# Use this when sudo asks for a password you do not have. Needs Node 22+ already installed (ffmpeg is optional,
# it is only used for video frames in transcripts).
#     git clone https://github.com/foodcel/codecel-discord-bot.git && cd codecel-discord-bot
#     bash deploy/user-install.sh      # first run creates .env, fill it in, then run it again
set -euo pipefail

cd "$(dirname "$0")/.."
DIR="$(pwd)"
NODE_BIN="$(command -v node || true)"
[ -n "$NODE_BIN" ] || { echo "ERROR: node is not installed"; exit 1; }
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ] || { echo "ERROR: Node 22+ is needed, found $(node -v)"; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || echo "note: ffmpeg is not installed, transcripts will have no video frames"

echo "==> Installing dependencies"
npm ci --omit=dev
if ! node -e "import('better-sqlite3').then(() => process.exit(0), () => process.exit(1))"; then
  echo "==> Building better-sqlite3 (needs a compiler: build-essential and python3)"
  npm rebuild better-sqlite3
fi
mkdir -p data

echo "==> Installing the user service"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/codecel-bot.service" <<UNIT
[Unit]
Description=codecel Discord bug bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart=$NODE_BIN src/index.js
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
# keeps the service running after you log out and starts it at boot
loginctl enable-linger "$(whoami)" || echo "warning: could not enable linger, ask an admin to run: sudo loginctl enable-linger $(whoami)"

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo
  echo "Created .env from .env.example. Fill it in:  nano $DIR/.env   (or copy your own .env here)"
  echo "Then run this script again to start the bot."
  exit 0
fi
chmod 600 .env
for key in DISCORD_TOKEN APPLICATION_ID ANTHROPIC_API_KEY GUILD_ID BUGS_CHANNEL_ID DEV_BUGS_FORUM_ID MODLOG_CHANNEL_ID DEV_ROLE_ID; do
  val="$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//' | tr -d '[:space:]')"
  [ -n "$val" ] || { echo "ERROR: $key is empty in .env"; exit 1; }
done

systemctl --user enable --now codecel-bot
sleep 5
systemctl --user --no-pager status codecel-bot | head -10
echo
echo "Logs:     journalctl --user -u codecel-bot -f"
echo "Restart:  systemctl --user restart codecel-bot"
echo "Update:   git pull && npm ci --omit=dev && systemctl --user restart codecel-bot"
