#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu VM (Oracle Cloud Always Free, x86 or ARM, Ubuntu 24.04 has Python 3.12).
# Run it from inside the cloned repo as a normal user that has sudo:
#     git clone https://github.com/foodcel/codecel-discord-bot.git && cd codecel-discord-bot
#     bash deploy/oracle-setup.sh
# It installs Python 3.12, a virtualenv and ffmpeg, installs the dependencies and sets the bot up as a systemd service
# that starts at boot and restarts if it crashes. It will not start the bot until .env is filled in.
set -euo pipefail

cd "$(dirname "$0")/.."
DIR="$(pwd)"

echo "==> Installing system packages (git, ffmpeg, python)"
sudo apt-get update
sudo apt-get install -y ca-certificates git ffmpeg python3 python3-venv python3-pip

PY="$(command -v python3)"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || { echo "ERROR: Python 3.12+ is needed (Ubuntu 24.04 has it), found $("$PY" -V)"; exit 1; }
echo "$("$PY" -V), ffmpeg $(ffmpeg -version | head -1 | cut -d' ' -f3)"

echo "==> Installing dependencies"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

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
sed -e "s|__USER__|$(id -un)|g" -e "s|__DIR__|$DIR|g" deploy/codecel-bot.service \
  | sudo tee /etc/systemd/system/codecel-bot.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now codecel-bot
sleep 5
sudo systemctl --no-pager status codecel-bot | head -12
echo
echo "Done. Logs:    journalctl -u codecel-bot -f"
echo "Restart:       sudo systemctl restart codecel-bot"
echo "Update:        git pull && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart codecel-bot"
