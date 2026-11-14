"""One-time move from game tags to status tags in the bugs forum and the testers' forum (2026-11-14).
1. every post without its game in the title gets it: "#12 Minecraft · title" (the game from the database, else from the post's game tag)
2. every game tag is removed from both forums; the six status tags (tags.STATUS_TAG) are made, with their emoji
3. every post gets the status tag of its report
    python scripts/forum_tags.py           dry run: prints every change, changes nothing
    python scripts/forum_tags.py --yes     does it, silently
    --suggestions                          the same for the suggestions forum: its status tags are Added and Declined"""
import asyncio
import re
import sys

from _boot import boot, finish

from bot.core.db import all_, bug_by_thread
from bot.core.env import cfg
from bot.features.bugs import tags as T
from bot.features.games.games import clean_name

YES = '--yes' in sys.argv
SUG = '--suggestions' in sys.argv
STATUS = T.SUGGEST_STATUS_TAG if SUG else T.STATUS_TAG


def tag_list(forum):
    """Status tags only. The suggestions forum keeps Added and Declined, with their emoji."""
    if not SUG:
        return T.status_tag_list(forum, keep_games=False)
    keep = [t for t in forum.available_tags if t.name in STATUS.values()]
    return [t if T._has_emoji(t, T.STATUS_EMOJI[t.name]) and t.moderated else T._status_tag(t.name, T.STATUS_EMOJI[t.name], t.id) for t in keep]


def full(name):
    """A forum tag name is cut at 20 characters ("Stick Fight: The Gam"): the game's whole name when one game starts with it."""
    k = re.sub(r'[^a-z0-9]', '', (name or '').lower())
    if len(name or '') >= 20:
        hits = [r['name'] for r in all_('SELECT name FROM game_status') if re.sub(r'[^a-z0-9]', '', r['name'].lower()).startswith(k)]
        if len(hits) == 1:
            return clean_name(hits[0])
    return name


def _game_of(thread, bug):
    if SUG and bug:  # the tag and the report disagree (the forum was full, tags were picked wrong): the title is left alone, listed for a person
        status = {n.lower() for n in STATUS.values()}
        tag = next((t for t in thread.applied_tags if t.name.lower() not in status), None)
        g = T.canonical_game(tag.name) if tag else None
        if g and T._norm(bug.get('game_name') or '') != T._norm(g['name']):
            print(f"[check] {thread.name!r}: report says {bug.get('game_name')!r}, tag says {g['name']!r}: title left alone")
            return None
    if bug and bug.get('game_tag_id') and T.tag_name(bug['game_tag_id']):
        return full(T.tag_name(bug['game_tag_id']))
    if bug and bug.get('game_name'):
        return full(clean_name(bug['game_name']))
    status = {n.lower() for n in STATUS.values()}
    tag = next((t for t in thread.applied_tags if t.name.lower() not in status), None)
    if tag and SUG:  # suggestion tags were typed by hand ("SUEPRHOT", "FNAF 1"): the game they stand for
        g = T.canonical_game(tag.name)
        return full(g['name']) if g else clean_name(tag.name)
    return full(clean_name(tag.name)) if tag else None


def _names_another_game(rest, game):
    """The title already names a game (another one than the report's): adding a second game would confuse, so it is left alone."""
    words = re.sub(r'[^a-z0-9]', '', rest.lower())
    return any(len(k) >= 5 and k in words for k in (re.sub(r'[^a-z0-9]', '', t['name'].lower()) for t in T.game_tags()))


def new_title(thread, game):
    m = re.match(r'^(#\d+\s+)?(.*)$', thread.name, re.S)
    num, rest = m.group(1) or '', m.group(2)
    k = re.sub(r'[^a-z0-9]', '', game.lower()) if game else ''
    if not k or re.sub(r'[^a-z0-9]', '', rest.lower()).startswith(k[:max(4, len(k) - 2)]):
        return None  # no game known, or the title already starts with it
    if _names_another_game(rest, game):
        return None
    return (num + T.titled(game, rest))[:100]


async def posts(forum):
    out = list(forum.threads)
    async for t in forum.archived_threads(limit=None):
        out.append(t)
    return [t for t in out if not t.flags.pinned]


async def edit(thread, **kw):
    was = thread.archived
    await thread.edit(**({'archived': False} if was else {}), **kw)
    if was:
        await thread.edit(archived=True)


async def main():
    client = await boot(claims=False)
    forums = [await client.fetch_channel(int(f)) for f in ((cfg.suggestions_id,) if SUG else (cfg.bugs_id, cfg.tester_forum_id)) if f]
    renamed = tagged = 0
    for forum in forums:  # 1. titles, while the game tags are still there to read
        for t in await posts(forum):
            title = new_title(t, _game_of(t, bug_by_thread(t.id)))
            if title:
                print(f'[{forum.name}] title: {t.name!r} -> {title!r}')
                renamed += 1
                if YES:
                    await edit(t, name=title)
    for forum in forums:  # 2. the tag list: status tags only
        tags = tag_list(forum)
        gone = [t.name for t in forum.available_tags if t.name not in {x.name for x in tags}]
        print(f'[{forum.name}] tags removed: {gone}')
        print(f'[{forum.name}] tags now: {[t.name for t in tags]}')
        if YES:
            await forum.edit(available_tags=tags, reason='Games are in the post title; status tags only')
    if YES:
        await T.load_tags()
        forums = [await client.fetch_channel(int(f.id)) for f in forums]
    for forum in forums:  # 3. each post's status
        by_name = {t.name: t for t in forum.available_tags}
        for t in await posts(forum):
            bug = bug_by_thread(t.id)
            name = STATUS.get((bug or {}).get('status'))
            if not name:
                continue
            print(f'[{forum.name}] status: {t.name[:50]!r} -> {name}')
            tagged += 1
            if YES and name in by_name and by_name[name] not in t.applied_tags:
                await edit(t, applied_tags=[by_name[name]])
    print(f"{'done' if YES else 'dry run'}: {renamed} titles, {tagged} status tags")
    await finish(client)


if __name__ == '__main__':
    asyncio.run(main())
