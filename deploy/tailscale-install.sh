#!/usr/bin/env bash
# Run on the VM (no sudo needed): Tailscale in userspace mode as a user service, then a public HTTPS address (Funnel) for the MCP port.
# First run prints a login link: open it once and approve the machine. The address is stable: https://codecel-bot.<tailnet>.ts.net
# Then put MCP_URL=<that address> in .env. --statedir (not --state) is what lets it make the HTTPS certificate.
set -e
mkdir -p ~/ts/state ~/.config/systemd/user
cd ~/ts
V=$(curl -s https://api.github.com/repos/tailscale/tailscale/releases/latest | grep -o '"tag_name": *"v[0-9.]*"' | grep -o '[0-9][0-9.]*' | head -1)
curl -sL -o ts.tgz "https://pkgs.tailscale.com/stable/tailscale_${V}_amd64.tgz" && tar xzf ts.tgz --strip-components=1
cat > ~/.config/systemd/user/codecel-tailscaled.service <<UNIT
[Unit]
Description=Tailscale (userspace) for the codecel MCP
After=network-online.target

[Service]
ExecStart=%h/ts/tailscaled --tun=userspace-networking --statedir=%h/ts/state --socket=%h/ts/tailscaled.sock
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now codecel-tailscaled
sleep 4
S="$HOME/ts/tailscale --socket=$HOME/ts/tailscaled.sock"
$S status --json | grep -q '"BackendState": "Running"' || timeout 20 $S up --hostname=codecel-bot || true
$S funnel --bg "${MCP_PORT:-8765}"
