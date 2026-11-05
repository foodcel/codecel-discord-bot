"""Prints an embed's fields as text (for checking the card conversion). Run on the VM:  python scripts/dump_embed.py roster"""
import asyncio

from _boot import boot, finish

from bot import testers


async def main():
    client = await boot(claims=False)
    e = testers.roster_embed()
    print('TITLE', repr(e.title), '| DESC', repr(e.description))
    for f in e.fields:
        print('FIELD', repr(f.name), 'inline' if f.inline else 'block')
        for ln in f.value.split(chr(10))[:14]:
            print('   ', repr(ln))
    await finish(client)


asyncio.run(main())
