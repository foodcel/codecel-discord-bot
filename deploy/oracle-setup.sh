#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu VM (Oracle Cloud Always Free, x86 or ARM, Ubuntu 22.04 / 24.04).
# Run it from inside the cloned repo as a normal user that has sudo:
#     git clone https://github.com/foodcel/codecel-discord-bot.git && cd codecel-discord-bot
#     bash deploy/oracle-setup.sh
# It installs Node 24 and ffmpeg, installs the dependencies and sets the bot up as a systemd service
# that starts at boot and restarts if it crashes. It will not start the bot until .env is filled in.
set -euo pipefail

cd "$(dirname "$0")/.."
DIR="$(pwd)"

echo "==> Installing system packages (git, ffmpeg, build tools)"
sudo apt-get update
sudo apt-get install -y ca-certificates curl git ffmpeg build-essential python3

if ! command -v node >/dev/null 2>&1 || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 22 ]; then
  echo "==> Installing Node.js 24"
  curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
echo "Node $(node -v), ffmpeg $(ffmpeg -version | head -1 | cut -d' ' -f3)"

echo "==> Installing dependencies"
npm ci --omit=dev
# better-sqlite3 is a native module: if no prebuilt binary matched this CPU, build it here.
if ! node -e "import('better-sqlite3').then(() => process.exit(0), () => process.exit(1))"; then
  echo "==> Building better-sqlite3 for this CPU"
  npm rebuild better-sqlite3
fi

mkdir -p data
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo
  echo "Created .env from .env.example. Fill it in:  nano $DIR/.env"
  echo "Then run this script again to start the bot."
  exit 0
fi
chmod 600 .env

# Refuse to start with an empty required value.
for key in DISCORD_TOKEN APPLICATION_ID ANTHROPIC_API_KEY GUILD_ID BUGS_CHANNEL_ID DEV_BUGS_FORUM_ID MODLOG_CHANNEL_ID DEV_ROLE_ID; do
  val="$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//' | tr -d '[:space:]')"
  if [ -z "$val" ]; then echo "ERROR: $key is empty in .env"; exit 1; fi
done

echo "==> Installing the systemd service"
NODE_BIN="$(command -v node)"
sed -e "s|__USER__|$(id -un)|g" -e "s|__DIR__|$DIR|g" -e "s|__NODE__|$NODE_BIN|g" deploy/codecel-bot.service \
  | sudo tee /etc/systemd/system/codecel-bot.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now codecel-bot
sleep 5
sudo systemctl --no-pager status codecel-bot | head -12
echo
echo "Done. Logs:    journalctl -u codecel-bot -f"
echo "Restart:       sudo systemctl restart codecel-bot"
echo "Update:        git pull && npm ci --omit=dev && sudo systemctl restart codecel-bot"
