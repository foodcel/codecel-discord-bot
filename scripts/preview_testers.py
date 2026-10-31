"""Draft of the two tester-information embeds, built from the two messages in the tester-information channel (read only) and posted
into the test channel. Nothing is saved and nothing is posted anywhere else."""
import asyncio
import re

from _boot import boot, finish

from bot.env import cfg
from bot.ui import E, ZW, describe, flat, gap, head, section

INFO = '1565829140920402090'


def parse_roster(text):
    out = []
    for m in re.finditer(r'(🟢|🟡)\s*(\d+)\.\s*<@!?(\d+)>\s*\n((?:\s*-\s*\*\*.+\n?)+)', text + '\n'):
        fields = dict(re.findall(r'-\s*\*\*(.+?):\*\*\s*(.+)', m.group(4)))
        out.append({'status': 'active' if m.group(1) == '🟢' else 'pending', 'id': m.group(3), **{k.lower().replace(' ', '_'): v.strip() for k, v in fields.items()}})
    return out


def guide_embed():
    e = flat()
    e.title = head('🧪', 'Tester responsibilities')
    describe(e, 'All testers are expected to:\n\n' + '\n'.join([
        '✅ Test assigned games thoroughly',
        '✅ Report bugs and gameplay issues',
        '✅ Provide screenshots or recordings when possible',
        '✅ Communicate regularly with the development team',
        '✅ Remain active and complete assigned testing tasks',
        '✅ Be patient with difficult or unfinished games']))
    section(e, head(E['warn'], 'Important'),
            "We expect consistent effort, honesty and communication. If you're unavailable or unable to finish a test, please notify the developer(s).")
    section(e, head(E['open'], 'How to report bugs'),
            f'Type `/bug` in <#{cfg.testing_id}>. The form asks for:\n'
            '• **Game** · which game, the dev is pinged for you\n• **Issue** · what happened\n• **Steps** · how can we recreate it?\n'
            '• **Evidence** · screenshots or videos\n• **Device** · your platform\n• **Frequency** · how often it happens (say it in the description)')
    gap(e)
    e.set_footer(text='Questions? Ask in this channel or message a developer.')
    return e


def roster_embed(rows):
    active = [r for r in rows if r['status'] == 'active']
    pending = [r for r in rows if r['status'] != 'active']
    e = flat()
    e.title = head('👥', 'Tester roster')
    describe(e, f'🟢 **{len(active)}** active{"  ·  " if pending else ""}{f"🟡 **{len(pending)}** waiting for a reply" if pending else ""}')
    for r in active + pending:
        mark = '🟢' if r['status'] == 'active' else '🟡'
        if r['status'] == 'active':
            l2 = f"🎮 {r.get('devices', '?')}  ·  🎥 {r.get('recording', '?')}"
            avail = r.get('availability', '?') + (f" ({r['schedule']})" if r.get('schedule') else '')
            if r.get('short_notice'):
                avail += f" · short notice: {r['short_notice']}"
            l3 = f"🕐 {avail}"
            l4 = f"⭐ {r.get('best_for', '?')}"
            value = f"{mark} <@{r['id']}>\n{l2}\n{l3}\n{l4}"
        else:
            value = f"{mark} <@{r['id']}>\n⏳ No response yet"
        e.add_field(name=ZW, value=value[:1024], inline=False)
    gap(e)
    e.set_footer(text='🟢 active · 🟡 waiting for a reply · Need a tester on a device? Ask a developer.')
    return e


async def main():
    client = await boot(members=True, claims=False)
    info = await client.fetch_channel(int(INFO))
    msgs = [m async for m in info.history(limit=10, oldest_first=True)]
    roster_text = next(m.content for m in msgs if 'Total Testers' in m.content)
    rows = parse_roster(roster_text)
    print('parsed testers:', len(rows), [(r['status'], r['id']) for r in rows])
    test = await client.fetch_channel(int(cfg.test_id))
    await test.send(content='**Tester information draft 1/2** · responsibilities and how to report (NOT posted in #tester-information)', embed=guide_embed())
    await test.send(content='**Tester information draft 2/2** · the roster, from the existing message', embed=roster_embed(rows))
    await finish(client)


asyncio.run(main())
