"""Screenshots and videos a reporter posted, for the bug page."""
import re
import time

from bot.core.ctx import ctx
from bot.core.env import cfg

IMG = re.compile(r'^image/(png|jpe?g|gif|webp)')
VIDEO_LINK = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com|youtu\.be|streamable\.com|medal\.tv|clips\.twitch\.tv|twitch\.tv|vimeo\.com|tiktok\.com|gyazo\.com|imgur\.com)/\S+',
    re.I)


def jump(thread_id, msg_id):
    return f'https://discord.com/channels/{cfg.guild_id}/{thread_id}/{msg_id}'


_live_cache = {}  # bug id -> (time, result)


async def live_media(thread, bug):
    """For the bug view: fresh attachment URLs straight from the live thread (no downloads). Cached for a minute."""
    hit = _live_cache.get(bug['id'])
    if hit and time.time() * 1000 - hit[0] < 60000:
        return hit[1]
    try:
        msgs = [m async for m in thread.history(limit=50)]
    except Exception:
        msgs = []
    mine = sorted(
        (m for m in msgs if str(m.author.id) == bug['reporter_id']
         or (bug.get('source') in ('tester', 'form') and m.author.id == ctx.client.user.id)),
        key=lambda m: m.created_at)
    images = []
    videos = []
    for m in mine:
        for a in m.attachments:
            typ = a.content_type or ''
            if IMG.search(typ) and len(images) < 4:
                images.append(a.url)
            elif typ.startswith('video/') or IMG.search(typ):
                videos.append({'label': f"{'🎥' if typ.startswith('video/') else '🖼️'} {a.filename}", 'url': jump(thread.id, m.id)})
        for link in VIDEO_LINK.findall(m.content or ''):
            videos.append({'label': f'🎥 {link[:60]}', 'url': link})
    text = (bug.get('body') or '') if bug.get('source') in ('tester', 'form') else (mine[0].content if mine else '')
    v = {'text': text, 'images': images, 'videos': videos}
    _live_cache[bug['id']] = (time.time() * 1000, v)
    return v
