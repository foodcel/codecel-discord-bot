"""Builds the prompts the /mcp setup card hands out, from CLAUDE.md and settings.json in docs/safe-workspace:
PROMPT.txt (Safe folder: locks the folder, asks simple lock or full box) and BOX.txt (Full box: sets up the WSL2 box).
    python scripts/safe_prompt.py"""
import json
from pathlib import Path

D = Path(__file__).resolve().parent.parent / 'docs' / 'safe-workspace'
NL = chr(10)
BOX = 'codecel'  # the name of the WSL2 box


def prompt():
    rules = (D / 'CLAUDE.md').read_text(encoding='utf8').strip()
    settings = json.dumps(json.loads((D / 'settings.json').read_text(encoding='utf8')), separators=(',', ':'))
    return NL.join([
        'Set this folder up as my locked codecel workspace. Do exactly this, in order, nothing else.',
        '1. If Claude Code is older than 2.1.322, stop and tell me to update.',
        '2. Only on plain Windows (the sandbox already works on WSL, macOS and Linux): ask me to pick, and wait.',
        '   A) Simple lock (recommended): one minute, nothing to install.',
        '   B) Full box: you also set up WSL2, a small Linux inside Windows, so commands are walled in too. About 15 minutes, maybe an admin approval and a PC restart, one more Claude login. It is a guided setup, not a one-click install: it can hit snags.',
        '3. Write CLAUDE.md here with exactly this text:',
        rules,
        '4. Write .claude/settings.json here with exactly this JSON:',
        settings,
        '5. Call list_my_games to check the codecel MCP answers. Never write, ask for or type my token or a password.',
        '6. Tell me in a short list: files written, and that I must restart Claude Code here for the lock to apply. '
        'If I picked B: tell me to then press "Full box" on the Discord card and paste that prompt here.',
    ])


def box():
    return NL.join([
        f'Set up the full box for this locked codecel workspace: a WSL2 Linux named {BOX} where Claude Code runs sandboxed. Do exactly this, in order, from Windows. '
        'Never write, ask for or type my token or a password.',
        '1. If .claude/settings.json is missing here, stop: I must paste the Safe folder prompt first.',
        f'2. If `wsl -l -v` lists no {BOX}: run `wsl --install -d Ubuntu --name {BOX} --no-launch` (on a --name error: `wsl --update`, then retry). '
        'If Windows needs a restart: tell me to restart and paste this prompt here again, then stop.',
        f'3. As root, with `wsl -d {BOX} -u root -- bash -c "..."`: apt-get update; apt-get install -y bubblewrap socat curl ca-certificates git; '
        f'if there is no user dev: useradd -m -s /bin/bash dev, and write /etc/wsl.conf with the line [user] then the line default=dev. Then run `wsl --terminate {BOX}`.',
        f'4. Run `wsl -d {BOX} -- bash -lc "curl -fsSL https://claude.ai/install.sh | bash"`.',
        f'5. Tell me the last steps, which only I can do: in a terminal run `wsl -d {BOX} --cd "<full path of this folder>"`, then `claude` (or ~/.local/bin/claude), '
        'log in, accept the trust question, and paste the "claude mcp add" command from the Discord card. From then on I start Claude Code for my games that way.',
    ])


if __name__ == '__main__':
    for name, text in (('PROMPT.txt', prompt()), ('BOX.txt', box())):
        (D / name).write_text(text + NL, encoding='utf8')
        print(name, len(text), 'chars')
