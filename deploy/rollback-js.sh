#!/usr/bin/env bash
# One-line rollback to the old JavaScript bot (tag js-final). Run on your own PC:
#     bash deploy/rollback-js.sh
# It stops the Python bot on the VM, checks out the JavaScript version, reinstalls its packages, switches the service back to
# node and waits for it to log in. The database (data/bot.db) is shared by both versions, so nothing is lost.
# To go back to Python later:  bash deploy/deploy.sh   (after: git checkout main on the VM, see README)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f deploy/vm.env ] || { echo "Create deploy/vm.env first (copy deploy/vm.env.example)."; exit 1; }
# shellcheck disable=SC1091
source deploy/vm.env
VM_KEY="${VM_KEY/#\~/$HOME}"
VM_DIR="${VM_DIR:-codecel-discord-bot}"
SSH=(ssh -i "$VM_KEY" -o BatchMode=yes "$VM_USER@$VM_HOST")

"${SSH[@]}" "bash -s" <<REMOTE
set -euo pipefail
cd $VM_DIR
systemctl --user stop codecel-bot
git fetch -q --tags
git checkout -q js-final
npm ci --omit=dev --silent
NODE_BIN="\$(command -v node)"
cat > "\$HOME/.config/systemd/user/codecel-bot.service" <<UNIT
[Unit]
Description=codecel Discord bug bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=\$(pwd)
ExecStart=\$NODE_BIN src/index.js
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user start codecel-bot
REMOTE

echo "==> Waiting for the JavaScript bot to log in"
for _ in $(seq 1 20); do
  sleep 3
  if "${SSH[@]}" "journalctl --user -u codecel-bot --no-pager --since '-90sec' | grep -q 'Ready. Catch-up finished.'"; then
    echo "==> OK: the JavaScript bot is back up"
    exit 0
  fi
done
echo "==> It did not report Ready within a minute. Last log lines:"
"${SSH[@]}" "journalctl --user -u codecel-bot --no-pager -n 20"
exit 1
