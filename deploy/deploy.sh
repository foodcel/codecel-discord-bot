#!/usr/bin/env bash
# Run on your own PC after committing: pushes to GitHub, updates the VM, restarts the bot and checks it came up.
#     bash deploy/deploy.sh
# Needs deploy/vm.env (see deploy/vm.env.example) and an SSH key that is allowed on the VM.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f deploy/vm.env ] || { echo "Create deploy/vm.env first (copy deploy/vm.env.example)."; exit 1; }
# shellcheck disable=SC1091
source deploy/vm.env
VM_KEY="${VM_KEY/#\~/$HOME}"
VM_DIR="${VM_DIR:-codecel-discord-bot}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "You have uncommitted changes. Commit them first."; exit 1
fi

echo "==> Syntax check"
PYBIN=python3
"$PYBIN" --version >/dev/null 2>&1 || PYBIN=python  # Windows has no working python3
"$PYBIN" -m compileall -q bot scripts

echo "==> Lint (unused code, undefined names)"
"$PYBIN" -m pyflakes bot scripts tests || { echo "Fix the lint above first (pip install pyflakes if it is missing)."; exit 1; }

echo "==> Tests"
"$PYBIN" -m unittest discover -s tests -q || { echo "Tests failed: nothing was deployed."; exit 1; }

echo "==> Pushing to GitHub"
git push

SSH=(ssh -i "$VM_KEY" -o BatchMode=yes "$VM_USER@$VM_HOST")
echo "==> Updating the VM and restarting the bot"
"${SSH[@]}" "cd $VM_DIR && git pull -q && .venv/bin/pip install -q -r requirements.txt && systemctl --user restart codecel-bot"

echo "==> Waiting for the bot to log in"
for _ in $(seq 1 60); do
  sleep 4
  if "${SSH[@]}" "journalctl --user -u codecel-bot --no-pager --since '-90sec' | grep -q 'Ready. Catch-up finished.'"; then
    echo "==> OK: the bot is up on the VM at commit $("${SSH[@]}" "cd $VM_DIR && git log --oneline -1")"
    exit 0
  fi
done
echo "==> The bot did not report Ready within 4 minutes. Last log lines:"
"${SSH[@]}" "journalctl --user -u codecel-bot --no-pager -n 20"
exit 1
