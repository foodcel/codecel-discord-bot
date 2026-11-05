"""Hides the dev and admin slash commands by ROLE, with Discord's own per-command rules (Server Settings > Integrations > codecel), not with a permission bit.
Discord only lets an admin's login change those rules (the bot's own token cannot), so this takes a short-lived token you get once:
    python scripts/lock_commands.py --link                 prints the login link (the redirect below must be added in the Developer Portal first)
    python scripts/lock_commands.py --token <token>        sets the rules on every dev / admin command (the token is used once and never saved)
    python scripts/lock_commands.py --check                shows the rules that are set now (needs no token)
The rules: admin commands = administrator roles only; dev commands = the Developers role and administrator roles; /giveaway = the Giveaway Manager role (if set)
and administrator roles. @everyone is denied. Commands not listed here stay open to everyone."""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import dotenv_values

ENV = dotenv_values(Path(__file__).resolve().parent.parent / '.env')
API = 'https://discord.com/api/v10'
UA = 'DiscordBot (https://github.com/foodcel/codecel-discord-bot, 1.0)'
REDIRECT = 'http://localhost:8080/callback'
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot import access  # noqa: E402  the one table of who may use what

ADMIN = access.names(access.ADMIN)
DEV = access.names(access.DEV)


def call(method, path, auth, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': auth, 'Content-Type': 'application/json', 'User-Agent': UA})
    for _ in range(8):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read() or 'null')
        except urllib.error.HTTPError as e:
            text = e.read().decode()
            if e.code == 429:  # rate limited: wait as long as Discord says, then try again
                time.sleep(float(json.loads(text).get('retry_after', 3)) + 0.5)
                continue
            raise SystemExit(f'{method} {path} -> {e.code} {text[:300]}')
    raise SystemExit(f'{method} {path} -> still rate limited')


def main():
    args = sys.argv[1:]
    app, guild, bot = ENV['APPLICATION_ID'], ENV['GUILD_ID'], 'Bot ' + ENV['DISCORD_TOKEN']
    if '--link' in args:
        q = urllib.parse.urlencode({'client_id': app, 'response_type': 'token', 'redirect_uri': REDIRECT, 'scope': 'applications.commands.permissions.update', 'prompt': 'consent'})
        print('1. Developer Portal > your application > OAuth2 > Redirects > add exactly:', REDIRECT)
        print('2. Open this link logged in as a server admin and press Authorize:\n   https://discord.com/oauth2/authorize?' + q)
        print('3. The page will not load. Copy the WHOLE address from the browser bar (it contains access_token=...) and give it to Claude.')
        return
    commands = {c['name']: c for c in call('GET', f'/applications/{app}/guilds/{guild}/commands', bot)}
    if '--check' in args:
        for p in call('GET', f'/applications/{app}/guilds/{guild}/commands/permissions', bot):
            name = next((n for n, c in commands.items() if c['id'] == p['id']), p['id'])
            print(name, [(x['type'], x['id'], x['permission']) for x in p['permissions']])
        return
    token = args[args.index('--token') + 1] if '--token' in args else None
    if not token:
        raise SystemExit('Give --token <token>, or use --link / --check.')
    token = urllib.parse.parse_qs(token.split('#', 1)[1]).get('access_token', [token])[0] if '#' in token else token  # the whole address works too
    roles = call('GET', f'/guilds/{guild}/roles', bot)
    admin_roles = [r['id'] for r in roles if int(r['permissions']) & 8 and not r.get('managed') and r['id'] != guild]
    dev, giveaway = ENV.get('DEV_ROLE_ID'), ENV.get('GIVEAWAY_MANAGER_ROLE_ID')
    allow = {**{n: admin_roles for n in ADMIN}, **{n: [dev, *admin_roles] for n in DEV}, 'giveaway': [x for x in (giveaway, *admin_roles) if x]}
    for name, role_ids in allow.items():
        if name not in commands:
            print('skip (not registered):', name)
            continue
        rules = [{'id': guild, 'type': 1, 'permission': False}] + [{'id': r, 'type': 1, 'permission': True} for r in dict.fromkeys(role_ids)]  # @everyone denied, these roles allowed
        call('PUT', f'/applications/{app}/guilds/{guild}/commands/{commands[name]["id"]}/permissions', 'Bearer ' + token, {'permissions': rules})
        print('locked', name, 'to', len(rules) - 1, 'roles')


main()
