#!/usr/bin/env bash
# Run on the VM (no sudo needed): installs cloudflared in ~/bin and keeps a quick tunnel to the MCP port running as a user service.
# The address (https://<random>.trycloudflare.com) is written to ~/cloudflared.log and read by /mcp setup. It changes only when this service restarts.
set -e
mkdir -p ~/bin ~/.config/systemd/user
[ -x ~/bin/cloudflared ] || { curl -sL -o ~/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x ~/bin/cloudflared; }
cat > ~/.config/systemd/user/codecel-tunnel.service <<UNIT
[Unit]
Description=codecel MCP quick tunnel
After=network-online.target

[Service]
ExecStartPre=/bin/rm -f %h/cloudflared.log
ExecStart=%h/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:${MCP_PORT:-8765} --logfile %h/cloudflared.log
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now codecel-tunnel
sleep 12
grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' ~/cloudflared.log | tail -1
