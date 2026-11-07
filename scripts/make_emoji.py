"""Draws the animated "vibecoding" emoji (a little orange pixel buddy typing, with dots that grow) as a 128x128 GIF: python scripts/make_emoji.py
Writes assets/emoji/vibecoding.gif and a preview strip next to it."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / 'assets' / 'emoji'
S = 4  # a 32x32 pixel grid drawn at 128x128
ORANGE, DARK, EYE = (217, 119, 87), (170, 88, 62), (24, 20, 28)
KEYS, LIT, DOT, DOT_OFF = (59, 59, 70), (255, 209, 102), (120, 190, 255), (80, 84, 100)


def frame(n):
    im = Image.new('RGBA', (32 * S, 32 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def px(x0, y0, x1, y1, c):
        d.rectangle([x0 * S, y0 * S, (x1 + 1) * S - 1, (y1 + 1) * S - 1], fill=c)

    bob = 1 if n % 4 in (1, 2) else 0
    px(9, 9 + bob, 22, 18 + bob, ORANGE)                       # body
    px(11, 7 + bob, 12, 8 + bob, ORANGE)                       # two little ears
    px(19, 7 + bob, 20, 8 + bob, ORANGE)
    blink = n == 5
    px(12, 12 + bob, 13, 13 + bob if not blink else 12 + bob, EYE)  # eyes
    px(18, 12 + bob, 19, 13 + bob if not blink else 12 + bob, EYE)
    px(15, 15 + bob, 16, 15 + bob, DARK)                       # tiny mouth
    for x in (10, 13, 18, 21):                                 # legs
        px(x, 19 + bob, x + 1, 21, DARK)
    left_down, right_down = n % 2 == 0, n % 2 == 1             # arms take turns typing
    px(6, 17 if left_down else 14, 8, 18 if left_down else 15, ORANGE)
    px(23, 17 if right_down else 14, 25, 18 if right_down else 15, ORANGE)
    px(4, 23, 27, 28, KEYS)                                    # keyboard
    for k in range(7):
        px(5 + k * 3, 24, 6 + k * 3, 25, LIT if k == (n * 3) % 7 or k == (n * 3 + 2) % 7 else (88, 88, 100))
        px(5 + k * 3, 26, 6 + k * 3, 27, (88, 88, 100))
    lit = [1, 2, 3, 2, 1, 2, 3, 3][n % 8]                      # the "..." grows
    for k in range(3):
        px(21 + k * 3, 3, 22 + k * 3, 4, DOT if k < lit else DOT_OFF)
    return im


def to_gif_frame(im):
    alpha = im.getchannel('A')
    p = im.convert('RGB').convert('P', palette=Image.ADAPTIVE, colors=255)
    p.paste(255, Image.eval(alpha, lambda a: 255 if a < 128 else 0))
    p.info['transparency'] = 255
    return p


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frames = [frame(n) for n in range(8)]
    gifs = [to_gif_frame(f) for f in frames]
    gifs[0].save(OUT / 'vibecoding.gif', save_all=True, append_images=gifs[1:], duration=130, loop=0, transparency=255, disposal=2, optimize=False)
    strip = Image.new('RGBA', (128 * 4, 128 * 2), (47, 49, 54, 255))
    for n, f in enumerate(frames):
        strip.alpha_composite(f, ((n % 4) * 128, (n // 4) * 128))
    strip.save(OUT / 'preview.png')
    print('size', (OUT / 'vibecoding.gif').stat().st_size, 'bytes')


main()
