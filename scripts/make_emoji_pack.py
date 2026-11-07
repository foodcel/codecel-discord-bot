"""Draws a pack of animated emoji in the same pixel style as :vibecoding: (one little orange buddy, many moods): python scripts/make_emoji_pack.py
Writes assets/emoji/<name>.gif for each and one preview sheet, preview-pack.png."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / 'assets' / 'emoji'
S = 4  # a 32x32 pixel grid drawn at 128x128
ORANGE, DARK, EYE = (217, 119, 87), (170, 88, 62), (24, 20, 28)
WHITE, GREY, METAL, WOOD = (235, 235, 245), (88, 88, 100), (170, 172, 184), (140, 95, 60)
GREEN, RED, YELLOW, BLUE, PINK, CYAN = (80, 200, 110), (235, 80, 80), (255, 209, 102), (120, 190, 255), (255, 140, 200), (90, 230, 230)


class Pad:
    """A 32x32 pixel canvas drawn at 4x."""

    def __init__(self):
        self.im = Image.new('RGBA', (32 * S, 32 * S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def px(self, x0, y0, x1, y1, c):
        self.d.rectangle([x0 * S, y0 * S, (x1 + 1) * S - 1, (y1 + 1) * S - 1], fill=c)

    def dot(self, x, y, c):
        self.px(x, y, x, y, c)


def buddy(p, ox=0, bob=0, eyes='open', mouth='flat', arms=('mid', 'mid'), legs=True):
    """The orange buddy. eyes: open, blink, x, up, wide. mouth: flat, smile, o. arms: mid, up, down, chin."""
    def r(x0, y0, x1, y1, c):
        p.px(x0 + ox, y0 + bob, x1 + ox, y1 + bob, c)
    r(9, 9, 22, 18, ORANGE)
    r(11, 7, 12, 8, ORANGE)
    r(19, 7, 20, 8, ORANGE)
    for ex in (12, 18):
        if eyes == 'open':
            r(ex, 12, ex + 1, 13, EYE)
        elif eyes == 'blink':
            r(ex, 12, ex + 1, 12, EYE)
        elif eyes == 'wide':
            r(ex, 11, ex + 1, 13, EYE)
        elif eyes == 'up':
            r(ex - 1, 11, ex, 12, EYE)
        elif eyes == 'left':
            r(ex - 1, 12, ex, 13, EYE)
        elif eyes == 'right':
            r(ex + 1, 12, ex + 2, 13, EYE)
        elif eyes == 'closed':
            r(ex, 13, ex + 1, 13, EYE)
        elif eyes == 'x':
            for dx, dy in ((0, 0), (2, 0), (1, 1), (0, 2), (2, 2)):
                r(ex - 1 + dx, 11 + dy, ex - 1 + dx, 11 + dy, EYE)
    if mouth == 'flat':
        r(15, 15, 16, 15, DARK)
    elif mouth == 'smile':
        r(14, 15, 14, 15, DARK)
        r(17, 15, 17, 15, DARK)
        r(15, 16, 16, 16, DARK)
    elif mouth == 'o':
        r(15, 15, 16, 16, EYE)
    if legs:
        for x in (10, 13, 18, 21):
            r(x, 19, x + 1, 21, DARK)
    left, right = arms
    for side, pose in ((0, left), (1, right)):
        x0 = 6 if side == 0 else 23
        y = {'mid': 14, 'up': 9, 'down': 17, 'chin': 16}[pose]
        if pose == 'chin' and side == 1:
            r(19, 15, 24, 16, ORANGE)
        else:
            r(x0, y, x0 + 2, y + 1, ORANGE)


def bugsquash(n):
    p = Pad()
    p.px(0, 29, 31, 31, (60, 62, 74))  # ground
    buddy(p, ox=-5, arms=('mid', 'up' if n in (2, 3) else 'down' if n in (4, 5) else 'mid'), mouth='smile' if n >= 4 else 'flat', eyes='wide' if n in (3, 4) else 'open')
    if n < 4:
        bx = [29, 27, 25, 25][n]
        p.px(bx, 26, bx + 3, 27, (60, 140, 70))
        p.dot(bx + (n % 2), 28, (60, 140, 70))
        p.dot(bx + 3 - (n % 2), 28, (60, 140, 70))
        p.dot(bx - 1, 25, (60, 140, 70))
    if n in (2, 3):
        p.px(22, 14, 23, 24, WOOD)
        p.px(19, 11, 26, 14, METAL)
    if n in (4, 5):
        p.px(24, 17, 25, 27, WOOD)
        p.px(21, 24, 28, 28, METAL)
    if n in (4, 5):
        p.px(24, 28, 29, 28, (60, 140, 70))
        for sx, sy in ((19, 22), (30, 22), (20, 27), (30, 26)):
            p.dot(sx, sy, YELLOW)
    if n == 6:
        p.px(24, 28, 29, 28, (60, 140, 70))
        p.dot(21, 25, YELLOW)
        p.dot(30, 25, YELLOW)
    return p.im


def fixed(n):
    p = Pad()
    bob = [0, -1, -3, -4, -3, -1, 0, 0][n]
    up = 2 <= n <= 5
    buddy(p, bob=bob, eyes='blink' if n == 4 else 'open', mouth='smile', arms=('up', 'up') if up else ('mid', 'mid'))
    if n >= 2:
        for k, (cx, cy0, c) in enumerate(((3, 0, PINK), (8, 6, YELLOW), (24, 2, BLUE), (28, 9, GREEN), (14, 12, PINK), (20, 5, YELLOW))):
            p.dot(cx, (cy0 + (n - 2) * 3) % 30, c)
    if n >= 3:
        for x, y in ((24, 5), (25, 6), (26, 7), (27, 6), (28, 5), (29, 4)):
            p.px(x, y - 3, x + 1, y - 2, GREEN)
    return p.im


def shipit(n):
    p = Pad()
    p.px(0, 29, 31, 31, (60, 62, 74))
    buddy(p, ox=-6, mouth='smile', arms=('up', 'mid') if n % 2 == 0 else ('mid', 'up'))
    top = 21 - n * 3
    p.px(23, top + 2, 26, top + 10, WHITE)         # rocket body
    p.px(24, top, 25, top + 1, WHITE)               # nose
    p.px(24, top + 4, 25, top + 5, (90, 160, 235))  # window
    p.px(21, top + 8, 22, top + 11, RED)            # fins
    p.px(27, top + 8, 28, top + 11, RED)
    p.px(24, top + 11, 25, top + 11 + (3 if n % 2 == 0 else 2), (255, 160, 60))  # flame
    p.dot(24, top + 14 if n % 2 == 0 else top + 13, YELLOW)
    if n < 4:
        for sx in (20, 29):
            p.px(sx, 27 - n, sx + 1, 28 - n, (190, 190, 200))
    return p.im


def thinking(n):
    p = Pad()
    buddy(p, ox=-4, eyes='up', mouth='flat', arms=('mid', 'chin'))
    if n >= 0:
        p.px(21, 8, 22, 9, WHITE)
    if n >= 1:
        p.px(23, 5, 25, 7, WHITE)
    if n >= 2:
        p.px(22, 0, 31, 5, WHITE)
        if n <= 4:
            for x, y in ((25, 1), (26, 1), (27, 2), (26, 3), (26, 4)):
                p.dot(x, y, EYE)
        else:
            glow = YELLOW if n != 6 else (255, 240, 170)
            p.px(25, 1, 28, 4, glow)
            p.dot(26, 5, GREY)
            if n in (5, 7):
                for rx, ry in ((24, 0), (29, 0), (31, 2)):
                    p.dot(rx, ry, YELLOW)
    return p.im


def testing(n):
    p = Pad()
    buddy(p, eyes='wide', mouth='o' if n % 4 in (1, 2) else 'smile', arms=('down', 'down'))
    p.px(8, 17, 23, 23, (50, 50, 62))               # controller
    p.px(6, 19, 9, 23, (50, 50, 62))
    p.px(22, 19, 25, 23, (50, 50, 62))
    p.px(11, 19, 13, 19, (150, 150, 165))           # d-pad
    p.px(12, 18, 12, 20, (150, 150, 165))
    for k, (bx, by, c) in enumerate(((19, 18, RED), (21, 19, GREEN), (19, 20, BLUE), (17, 19, YELLOW))):
        p.dot(bx, by, c if k == n % 4 else tuple(int(v * 0.45) for v in c))
    for sx, sy in (((4, 5), (27, 8)), ((5, 7), (26, 5)))[n % 2]:
        p.dot(sx, sy, YELLOW)
        p.dot(sx - 1, sy, YELLOW)
        p.dot(sx + 1, sy, YELLOW)
        p.dot(sx, sy - 1, YELLOW)
        p.dot(sx, sy + 1, YELLOW)
    return p.im


def crash(n):
    p = Pad()
    ox = [0, 1, -1, 1, -1, 0, 1, -1][n]
    buddy(p, ox=ox, eyes='x', mouth='o', arms=('up', 'up') if n % 2 else ('mid', 'mid'))
    for y, c in (((12, CYAN), (16, PINK)), ((10, PINK), (14, CYAN)))[n % 2] if n % 2 == 1 else ():
        p.px(7 + ox, y, 24 + ox, y, c)
    if n % 2 == 0:
        p.px(26, 3, 27, 9, RED)
        p.px(26, 11, 27, 12, RED)
    return p.im


def reading(n):
    p = Pad()
    buddy(p, eyes=['left', 'left', 'right', 'right', 'left', 'left', 'right', 'right'][n], mouth='flat', arms=('down', 'down'))
    p.px(8, 15, 23, 27, WHITE)                      # the report
    p.px(8, 15, 23, 15, METAL)
    for k in range(5):
        p.px(10, 17 + k * 2, 21 - (k % 2) * 4, 17 + k * 2, GREY)
    scan = 17 + (n % 5) * 2
    p.px(10, scan, 21, scan, YELLOW)                # the line being read
    p.px(25, 5, 28, 8, (150, 200, 255))             # a magnifier
    p.px(26, 6, 27, 7, (230, 245, 255))
    p.px(24, 9, 25, 10, WOOD)
    return p.im


def coffee(n):
    p = Pad()
    sip = n in (3, 4)
    buddy(p, eyes='blink' if sip else 'open', mouth='smile', arms=('down', 'up' if sip else 'chin'))
    my = 12 if sip else 17
    p.px(24, my, 28, my + 5, WHITE)                 # the mug
    p.px(29, my + 1, 30, my + 3, WHITE)
    p.px(25, my + 1, 27, my + 1, (110, 70, 45))
    for k in range(3):                              # steam
        p.dot(25 + ((n + k) % 3), my - 2 - k * 2, (200, 205, 220))
    return p.im


def napping(n):
    p = Pad()
    bob = 1 if n % 4 in (2, 3) else 0
    buddy(p, bob=bob, eyes='closed', mouth='flat', arms=('down', 'down'))
    for k in range(3):                              # the Zs float up and grow
        step = (n + k * 3) % 8
        x, y = 22 + k * 3 - (step // 4), 9 - step
        size = 2 if step < 4 else 3
        if y >= 0:
            p.px(x, y, x + size, y, BLUE)
            p.px(x + size - 1, y + 1, x + size - 1, y + 1, BLUE) if size == 2 else p.px(x + 1, y + 1, x + 1, y + 1, BLUE)
            p.px(x, y + size, x + size, y + size, BLUE)
    return p.im


def compiling(n):
    p = Pad()
    buddy(p, eyes='up' if n % 2 == 0 else 'open', mouth='flat', arms=('mid', 'mid'))
    p.px(4, 24, 27, 28, (50, 50, 62))               # the progress bar
    p.px(5, 25, 26, 27, (30, 30, 40))
    fill = 2 + n * 3
    p.px(5, 25, min(5 + fill, 26), 27, GREEN)
    gx, gy = 25, 4                                  # a spinning gear
    p.px(gx, gy + 1, gx + 3, gy + 2, GREY)
    p.px(gx + 1, gy, gx + 2, gy + 3, GREY)
    if n % 2 == 0:
        p.dot(gx, gy, GREY)
        p.dot(gx + 3, gy + 3, GREY)
    else:
        p.dot(gx + 3, gy, GREY)
        p.dot(gx, gy + 3, GREY)
    p.dot(gx + 1, gy + 1, (47, 49, 54))
    return p.im


EMOJI = {'bugsquash': bugsquash, 'fixed_it': fixed, 'shipit': shipit, 'thinking_hard': thinking, 'playtesting': testing, 'crashed': crash,
         'reading_reports': reading, 'coffee_break': coffee, 'napping': napping, 'compiling': compiling}


def to_gif_frame(im):
    alpha = im.getchannel('A')
    pal = im.convert('RGB').convert('P', palette=Image.ADAPTIVE, colors=255)
    pal.paste(255, Image.eval(alpha, lambda a: 255 if a < 128 else 0))
    pal.info['transparency'] = 255
    return pal


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sheet = Image.new('RGBA', (128 * 8, 128 * len(EMOJI)), (47, 49, 54, 255))
    for row, (name, fn) in enumerate(EMOJI.items()):
        frames = [fn(n) for n in range(8)]
        gifs = [to_gif_frame(f) for f in frames]
        gifs[0].save(OUT / f'{name}.gif', save_all=True, append_images=gifs[1:], duration=130, loop=0, transparency=255, disposal=2, optimize=False)
        for n, f in enumerate(frames):
            sheet.alpha_composite(f, (n * 128, row * 128))
        print(name, (OUT / f'{name}.gif').stat().st_size, 'bytes')
    sheet.save(OUT / 'preview-pack.png')


main()
