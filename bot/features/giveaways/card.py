"""The giveaway card in the community look: banner, facts, podium prizes, Required, Bonus entries, hosts, buttons."""
from datetime import datetime, timezone
import discord
from discord import ui
from bot.discord_ui.card import notice
from bot.discord_ui.banner import banner_file
from bot.features.updates.botnews import code_chip
from bot.core.ctx import ctx
from bot.core.env import cfg
from bot.discord_ui.pngs import fit
from bot.features.giveaways.rules import NL, SMALL, _level_of, _role, groups, hosts_of, ordinal


BANNER = 'giveaway.png'


PINGS = [('none', 'No ping', 'The card appears silently'), ('giveaways', '@Giveaways', 'Only people who want giveaways'), ('everyone', '@everyone', 'Everyone in the server')]


# ---- the card (community look: banner, short lines, real pings, no trees, no code blocks, no medal emojis) ----
def place_label(places, long=True):
    a, b = places[0], places[-1]
    if a == b:
        return f'{ordinal(a)} place' if long else ordinal(a)
    if b == a + 1:
        return f'{ordinal(a)} and {ordinal(b)} place' if long else f'{ordinal(a)}–{ordinal(b)}'
    return f'{ordinal(a)} to {ordinal(b)} place' if long else f'{ordinal(a)}–{ordinal(b)}'


def prize_block(prizes):
    """The podium: the first prize as a heading, the others in bold under it, each with its place in small letters."""
    lines = []
    for k, (pl, p) in enumerate(groups(prizes)):
        lines.append(f"{'### ' if k == 0 else '**'}{' + '.join(p)}{'' if k == 0 else '**'}")
        lines.append(f'-# {place_label(pl)}')
    return NL.join(lines)


def required_block(c):
    rows = [f'✅ {_role(cfg.verified_role)}']
    if c['req_roles']:
        shown = [f'{_role(r)} or higher' if _level_of(ctx.guild.get_role(int(r))) is not None else _role(r) for r in c['req_roles']]
        rows.append('🎭 ' + (' and ' if c['req_mode'] == 'all' else ' or ').join(shown))
    if c['min_invites']:
        rows.append(f"📨 **{c['min_invites']}** invite{'s' if c['min_invites'] != 1 else ''} for your first entry")
    if c['min_days']:
        rows.append(f"🕓 **{c['min_days']}+** days in the server")
    if c['blacklist']:
        rows.append('🚫 Not for ' + ' '.join(_role(r) for r in c['blacklist']))
    return '**Required**' + NL + NL.join(rows)


def bonus_block(c):
    rows = [f"⭐ {_role(r)} **+{n}** {'entry' if n == 1 else 'entries'}" for r, n in c['bonus'].items()]
    if c.get('per_boost'):
        rows.append(f"🚀 **+{c['per_boost']}** {'entry' if c['per_boost'] == 1 else 'entries'} for every server boost")
    if c['invite_entries']:
        rows.append('➕ **+1** entry for every invite' + (f" · max **{c['invite_cap']}** entries in total" if c['invite_cap'] else ''))
    if rows and c.get('bonus_best') and len(c['bonus']) > 1:
        has_levels = any(_level_of(ctx.guild.get_role(int(r))) is not None for r in c['bonus'])
        rows.append('-# Level bonuses do not stack: only your highest level counts' if has_levels else '-# Role bonuses do not stack: only your highest counts')
    return '**Bonus entries**' + NL + NL.join(rows) if rows else None


def winners_block(res, c):
    mark = {'claimed': ' ✅', 'pending': ' ⏳' if c['claim_hours'] else ''}
    rows = [f"**{ordinal(w['place'])}** · <@{w['user']}> · {' + '.join(w['prizes'])}{mark.get(w['state'], '')}" for w in res['winners']]
    return '**Winners**' + NL + (NL.join(rows) or 'Nobody could win: no one who entered still qualified.')


def banner_for(g, ended=False):
    """The banner file of a giveaway: its own words, or the prize with the winners and the end date. Drawn in code, no model is used."""
    c, b = g['config'], g['config'].get('banner') or {}
    n = len(c['prizes'])
    day = datetime.fromtimestamp(g['ends_at'] / 1000, timezone.utc).strftime('%b %d').replace(' 0', ' ')
    sub = b.get('sub') or f"{n} {'winner' if n == 1 else 'winners'} · ends {day}"
    if ended:
        return banner_file(b.get('headline') or g['title'], 'Winners below', 'GIVEAWAY ENDED', filename=BANNER)
    return banner_file(b.get('headline') or g['title'], sub, b.get('pill') or 'ENTER BELOW', filename=BANNER)


def card_items(g, gid=None, status='running', count=0):
    """The giveaway as a card (a Container). status running | ended | draft. The banner is the message's attachment BANNER.
    A draft (the preview, a mockup) has the same buttons, switched to "only a mockup" ids."""
    c = g['config']
    n, ends = len(c['prizes']), g['ends_at'] // 1000
    when = f'ended <t:{ends}:f>' if status == 'ended' else f'ends <t:{ends}:f>'
    items = [ui.MediaGallery(discord.MediaGalleryItem(f'attachment://{BANNER}')),
             ui.TextDisplay(f"**{n}** {'winner' if n == 1 else 'winners'}  ·  **{count}** entered  ·  {when}"),
             ui.Separator(visible=True, spacing=SMALL)]
    if status == 'ended':
        items.append(ui.TextDisplay(winners_block(g['result'], c)))
    else:
        items.append(ui.TextDisplay(prize_block(c['prizes'])))
        items.append(ui.TextDisplay(required_block(c)))
        if bonus := bonus_block(c):
            items.append(ui.TextDisplay(bonus))
    items.append(ui.Separator(visible=True, spacing=SMALL))
    foot = [f"-# Hosted by: {' '.join(f'<@{h}>' for h in hosts_of(g))}"]
    if c['claim_hours']:
        foot.append(f"-# Winners claim within {c['claim_hours']}h")
    if status == 'ended':
        foot.append(f"-# Fair draw · seed `{g['result']['seeds'][0]}` · {g['result']['entries']} entries counted")
    elif c['min_invites'] or c['invite_entries']:
        foot.append('-# ' + code_chip('/invites stats · see how many of your invites count'))
    items.append(ui.TextDisplay(NL.join(foot)))
    if status in ('running', 'draft'):
        enter, mine = (f'gw:enter:{gid}', f'gw:mine:{gid}') if gid else ('mock:enter', 'mock:mine')
        items.append(ui.ActionRow(ui.Button(custom_id=enter, label='Enter giveaway', style=discord.ButtonStyle.success, emoji='🎉'),
                                  ui.Button(custom_id=mine, label='My entries', style=discord.ButtonStyle.secondary, emoji='🎟️')))
    if status == 'ended' and gid and c['claim_hours'] and any(w['state'] == 'pending' for w in g['result']['winners']):
        items.append(ui.ActionRow(ui.Button(custom_id=f'gw:claim:{gid}', label='Claim prize', style=discord.ButtonStyle.primary, emoji='🏆')))
    tail = 3 if isinstance(items[-1], ui.ActionRow) else 2
    return ui.Container(*fit(items, keep_tail=tail, extra_parts=1))


def ping_text(c):
    return {'giveaways': f'<@&{cfg.giveaways_role}>', 'everyone': '@everyone'}.get(c.get('ping'))


def container(g, gid=None, status='running', count=0):
    """The card as a message view. The ping, when there is one, sits right above the card, outside it."""
    view = ui.LayoutView()
    if p := ping_text(g['config']):
        view.add_item(ui.TextDisplay(p))
    view.add_item(card_items(g, gid, status, count))
    return view


def names_only(g):
    """The mentions an edit may carry. An edit must keep the card's ping allowed (@everyone or the role), or Discord strips the mention from the message and
    nobody who comes later sees it as a ping. Hosts are allowed so their names show. A giveaway posted before this rule (no 'v': 2) keeps users only:
    allowing its ping now would add the mention again and ping the server a second time."""
    c = g['config']
    ping = c.get('ping') if c.get('v') == 2 else None
    return discord.AllowedMentions(everyone=ping == 'everyone', roles=[discord.Object(id=int(cfg.giveaways_role))] if ping == 'giveaways' else False,
                                   users=[discord.Object(id=int(h)) for h in hosts_of(g)], replied_user=False)


def text_view(text):
    return notice(text)[0]
