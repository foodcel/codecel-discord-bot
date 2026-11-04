"""The Redwing Experiences banner for giveaways, drawn in code: the navy background with diagonal stripes, the red wing logo (cut from assets/games-banner.gif),
a faint wing behind, a title in big condensed letters and a red bar at the bottom. The headline can be any text (the prize), so every giveaway gets its own banner."""
import io
import re
from pathlib import Path

import discord
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ASSETS = Path(__file__).resolve().parent.parent / 'assets'
W, H = 1200, 400
NAVY_TOP, NAVY_BOTTOM = (25, 47, 87), (13, 26, 53)
CREAM, ORANGE, RED, WHITE = (250, 244, 230), (226, 125, 96), (214, 24, 32), (255, 255, 255)
_logo = None


def _font(name, size):
    return ImageFont.truetype(str(ASSETS / 'fonts' / name), size)


def _logo_rgba():
    """The wing and gear from the library banner: the picture of it with the background made see-through."""
    global _logo
    if _logo is None:
        src = Image.open(ASSETS / 'games-banner.gif').convert('RGB').crop((40, 45, 400, 395))
        bg = Image.new('RGB', src.size, (19, 38, 72))
        mask = ImageChops.difference(src, bg).convert('L').point(lambda v: min(255, v * 5))
        mask = mask.filter(ImageFilter.GaussianBlur(1.2))
        rgba = src.convert('RGBA')
        rgba.putalpha(mask)
        _logo = rgba
    return _logo


def _background():
    img = Image.new('RGB', (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(NAVY_TOP, NAVY_BOTTOM)))
    stripes = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripes)
    for x in range(-H, W + H, 78):  # slanted stripes, a few levels lighter
        sd.polygon([(x, H), (x + 26, H), (x + 26 + H * 0.62, 0), (x + H * 0.62, 0)], fill=(255, 255, 255, 9))
    return Image.alpha_composite(img.convert('RGBA'), stripes)


def _clean(text):
    return re.sub(r'[^A-Za-z0-9 .,!?&+\'%:/#$€£·–-]', '', str(text or '')).strip().upper()


def _fit(text, name, size, width):
    """The biggest font size (down from `size`) at which the text fits the width."""
    while size > 28:
        f = _font(name, size)
        if f.getlength(text) <= width:
            return f
        size -= 4
    return _font(name, 28)


def _spaced(draw, xy, text, font, fill, spacing=3):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += font.getlength(ch) + spacing
    return x


def giveaway_banner(headline='GIVEAWAY', sub='', pill='ENTER BELOW'):
    """PNG bytes of the banner. headline: the big text (the prize). sub: a short line under the red bar. pill: the outlined text at the bottom."""
    img = _background()
    logo = _logo_rgba()
    ghost = logo.resize((int(logo.width * 1.7), int(logo.height * 1.7)))
    ghost.putalpha(ghost.getchannel('A').point(lambda v: int(v * 0.10)))
    img.alpha_composite(ghost, (W - ghost.width + 140, H - ghost.height + 120))
    glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    glow.paste(logo.resize((300, 312)), (36, 44))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)).point(lambda v: v if v < 90 else 90))
    img.alpha_composite(logo.resize((300, 312)), (36, 44))
    d = ImageDraw.Draw(img)
    x = 400
    _spaced(d, (x, 40), 'REDWING EXPERIENCES', _font('BarlowCondensed-SemiBold.ttf', 34), ORANGE, 4)
    head = _clean(headline) or 'GIVEAWAY'
    f = _fit(head, 'Anton-Regular.ttf', 124, W - x - 50)
    box = f.getbbox(head)
    top = 92
    d.text((x, top - box[1]), head, font=f, fill=CREAM)
    by = top + (box[3] - box[1]) + 20
    d.rectangle([x + 2, by, x + 92, by + 6], fill=RED)
    y = by + 24
    if sub:
        d.text((x, y), _clean(sub), font=_font('BarlowCondensed-SemiBold.ttf', 40), fill=WHITE)
        y += 56
    if pill:
        pf = _font('BarlowCondensed-SemiBold.ttf', 28)
        text = _clean(pill)
        w = pf.getlength(text) + 70
        d.rounded_rectangle([x, y, x + w, y + 46], radius=23, outline=(148, 160, 190), width=2)
        d.text((x + 24, y + 7), text, font=pf, fill=(190, 200, 225))
        d.polygon([(x + w - 38, y + 15), (x + w - 22, y + 23), (x + w - 38, y + 31)], fill=RED)
    d.rectangle([0, H - 14, W, H], fill=RED)
    d.rectangle([0, H - 18, W, H - 15], fill=WHITE)
    out = io.BytesIO()
    img.convert('RGB').save(out, 'PNG', optimize=True)
    return out.getvalue()


def banner_file(headline='GIVEAWAY', sub='', pill='ENTER BELOW', filename='giveaway.png'):
    return discord.File(io.BytesIO(giveaway_banner(headline, sub, pill)), filename=filename)
