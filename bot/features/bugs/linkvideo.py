"""Videos from links: a player pastes a clip link (Medal, Streamable, Twitter/X, Imgur, Twitch, Vimeo, TikTok, YouTube) in a report or in a reply, and the bot
downloads the video with yt-dlp and attaches it to the post, so devs and the transcript have the file and not just a link that may die.
Only the sites in HOSTS are tried (the bot never fetches an address a player makes up), a clip must be shorter than MAX_SECONDS and fit the server's upload
limit (100 MB at boost level 3), and one download may take at most TIMEOUT seconds. A link that cannot be downloaded just stays a link."""
import asyncio
import os
import re
import shutil
import tempfile
from urllib.parse import urlsplit

HOSTS = ('medal.tv', 'streamable.com', 'imgur.com', 'x.com', 'twitter.com', 'twitch.tv', 'vimeo.com', 'tiktok.com', 'youtube.com', 'youtu.be', 'v.redd.it')
MAX_SECONDS = 600     # clips longer than 10 minutes are not downloaded
TIMEOUT = 150         # seconds for one download
MAX_LINKS = 3         # downloads per report or reply
URL = re.compile(r'https?://[^\s<>()\[\]"]+')


def video_links(*texts):
    """The links in some text that point to a site the bot may download from (each once, at most MAX_LINKS)."""
    out = []
    for t in texts:
        for u in URL.findall(str(t or '')):
            u = u.rstrip('.,;:!?')
            try:
                host = (urlsplit(u).hostname or '').lower()
            except ValueError:
                continue
            if any(host == h or host.endswith('.' + h) for h in HOSTS) and u not in out:
                out.append(u)
    return out[:MAX_LINKS]


def _download(url, limit, folder):
    import yt_dlp
    opts = {
        'quiet': True, 'no_warnings': True, 'noplaylist': True, 'outtmpl': os.path.join(folder, '%(id)s.%(ext)s'),
        'format': f'bv*[filesize<{limit}][ext=mp4]+ba[ext=m4a]/b[filesize<{limit}][ext=mp4]/bv*[filesize_approx<{limit}]+ba/b[filesize_approx<{limit}]/b',
        'merge_output_format': 'mp4', 'max_filesize': limit, 'socket_timeout': 20, 'retries': 2, 'noprogress': True,
        'match_filter': lambda info, **kw: None if not info.get('duration') or info['duration'] <= MAX_SECONDS else f'longer than {MAX_SECONDS // 60} minutes',
        'allowed_extractors': ['default', '-generic'],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    files = [os.path.join(folder, f) for f in os.listdir(folder)]
    if not files:
        raise RuntimeError('nothing was downloaded')
    path = max(files, key=os.path.getsize)
    if os.path.getsize(path) > limit:
        raise RuntimeError('the video is bigger than the upload limit')
    return path, (info or {}).get('title') or os.path.basename(path)


async def fetch(url, limit):
    """(bytes, file name, title) of the video behind a link, or (None, None, reason). Never raises."""
    folder = tempfile.mkdtemp(prefix='clip-')
    try:
        path, title = await asyncio.wait_for(asyncio.to_thread(_download, url, int(limit), folder), TIMEOUT)
        with open(path, 'rb') as f:
            return f.read(), os.path.basename(path), title
    except asyncio.TimeoutError:
        return None, None, 'it took too long'
    except Exception as e:
        return None, None, str(e).splitlines()[-1][:160] if str(e) else 'it could not be downloaded'
    finally:
        shutil.rmtree(folder, ignore_errors=True)


async def fetch_all(urls, limit):
    """For a list of links: ([{'name', 'type', 'size', 'data', 'url'} for the ones that worked], [links that could not be downloaded])."""
    got, failed = [], []
    used = 0
    for u in urls:
        data, name, info = await fetch(u, max(limit - used, 1))
        if data:
            used += len(data)
            got.append({'url': u, 'name': name, 'size': len(data), 'type': 'video/mp4', 'data': data, 'title': info})
        else:
            failed.append(u)
    return got, failed
