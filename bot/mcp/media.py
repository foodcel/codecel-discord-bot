"""Pictures and videos for the agent: images are shrunk and returned inline, videos are served from short-lived links of the bot's own
(Discord's links expire and need a login). The address of the MCP comes from MCP_URL (the Tailscale address)."""
import io
import os
import secrets
import time

from PIL import Image as PILImage

TTL = 30 * 60
MAX_BYTES = 300 * 1024 * 1024  # all videos waiting for download together
MAX_SIDE = 1280
_files = {}  # token -> {'data', 'mime', 'name', 'until'}


def public_url():
    """The address devs use (MCP_URL, no trailing slash), or None when it is not set."""
    return (os.environ.get('MCP_URL') or '').rstrip('/') or None


def shrink(data):
    """JPEG bytes of a picture, at most MAX_SIDE on the long side. None when it is not a picture."""
    try:
        im = PILImage.open(io.BytesIO(data))
        im.load()
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        im.convert('RGB').save(out, 'JPEG', quality=80)
        return out.getvalue()
    except Exception:
        return None


def _sweep():
    t = time.time()
    for k in [k for k, v in _files.items() if v['until'] < t]:
        del _files[k]
    while _files and sum(len(v['data']) for v in _files.values()) > MAX_BYTES:
        del _files[min(_files, key=lambda k: _files[k]['until'])]


def serve(data, name, mime='video/mp4'):
    """A link that downloads this file for the next 30 minutes (anyone with the link can, so it is long and random)."""
    _sweep()
    token = secrets.token_urlsafe(24)
    _files[token] = {'data': data, 'mime': mime, 'name': name, 'until': time.time() + TTL}
    base = public_url() or 'http://127.0.0.1:8765'
    return f'{base}/media/{token}/{name}'


def get(token):
    _sweep()
    return _files.get(token)
