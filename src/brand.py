"""Rainora brand kit: Manrope typography, palette and the drop-and-moon logo (shared by banner, logo, thumbnails)."""
import math
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FONT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts", "Manrope-Variable.ttf")

# Palette: midnight indigo -> deep teal, moonlight, cozy amber accent
NIGHT = (8, 10, 30)
INDIGO = (30, 27, 75)
TEAL = (16, 70, 92)
MOON = (236, 243, 255)
ICE = (158, 214, 240)
AMBER = (255, 184, 92)
LILAC = (150, 130, 230)


def manrope(size: int, weight: str = "ExtraBold") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT_PATH, size)
    f.set_variation_by_name(weight)
    return f


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def vertical_gradient(w, h, stops):
    """stops: [(pos 0..1, (r,g,b)), ...]"""
    col = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                col.putpixel((0, y), lerp(c0, c1, (t - p0) / max(p1 - p0, 1e-6)))
                break
    return col.resize((w, h)).convert("RGBA")


def tinted(size, color, mask):
    """Solid colour layer whose alpha is `mask` (blurring only the mask avoids dark halos)."""
    layer = Image.new("RGBA", size, color + (255,))
    layer.putalpha(mask)
    return layer


def soft_blob(img, cx, cy, rx, ry, color, alpha, blur):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=alpha)
    return Image.alpha_composite(img, tinted(img.size, color, m.filter(ImageFilter.GaussianBlur(blur))))


def rain_layer(size, n, length, alpha, width, blur, seed=1, angle=0.12):
    rnd = random.Random(seed)
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    w, h = size
    for _ in range(n):
        x, y = rnd.uniform(-50, w + 50), rnd.uniform(-150, h)
        L = rnd.uniform(*length)
        d.line((x, y, x - L * angle, y + L), fill=int(rnd.uniform(*alpha)), width=width)
    return tinted(size, (205, 228, 248), m.filter(ImageFilter.GaussianBlur(blur)) if blur else m)


def glass_droplets(size, n, rmax, seed=3):
    """Water droplets sitting on a window pane: dark rim, bright highlight."""
    rnd = random.Random(seed)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w, h = size
    for _ in range(n):
        r = rnd.uniform(rmax * 0.25, rmax)
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        d.ellipse((x - r, y - r * 1.15, x + r, y + r * 1.15), fill=(190, 220, 245, 38), outline=(10, 20, 40, 60), width=max(1, int(r / 6)))
        hr = r * 0.32
        d.ellipse((x - r * 0.45 - hr, y - r * 0.5 - hr, x - r * 0.45 + hr, y - r * 0.5 + hr), fill=(255, 255, 255, 150))
    return layer.filter(ImageFilter.GaussianBlur(0.7))


def crescent_mask(size, cx, cy, r, bite=0.55, tilt=-0.35):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    ox, oy = r * bite * math.cos(tilt), r * bite * math.sin(tilt)
    d.ellipse((cx - r + ox, cy - r + oy, cx + r + ox, cy + r + oy), fill=0)
    return m


def drop_polygon(cx, cy, r, steps=120, tip_ratio=2.1):
    """Classic raindrop: round bottom (radius r, centre cx,cy), pointed tip straight above."""
    d = r * tip_ratio
    half = math.acos(r / d)                       # angle from 'up' to each tangent point
    a_start, a_end = -math.pi / 2 + half, 1.5 * math.pi - half
    pts = [(cx, cy - d)]
    for i in range(steps + 1):
        a = a_start + (a_end - a_start) * i / steps
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def gradient_fill(size, mask, top, bottom):
    g = vertical_gradient(size[0], size[1], [(0, top), (1, bottom)])
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(g, (0, 0), mask)
    return out


def draw_logo(size: int, background: bool = True) -> Image.Image:
    """Rainora mark: a glowing raindrop with sound-ripples below and a crescent moon, on a night disc."""
    S = size * 2  # supersample for smooth edges
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    if background:
        bg = vertical_gradient(S, S, [(0, INDIGO), (0.55, (20, 40, 86)), (1, TEAL)])
        bg = soft_blob(bg, S * 0.3, S * 0.25, S * 0.35, S * 0.25, LILAC, 70, S * 0.12)
        bg = soft_blob(bg, S * 0.75, S * 0.85, S * 0.4, S * 0.25, (40, 160, 190), 80, S * 0.12)
        # stars
        rnd = random.Random(11)
        sd = ImageDraw.Draw(bg)
        for _ in range(26):
            x, y, r = rnd.uniform(0, S), rnd.uniform(0, S * 0.55), rnd.uniform(1, 3.2) * S / 800
            sd.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, int(rnd.uniform(90, 220))))
        bg.alpha_composite(rain_layer((S, S), 70, (S * 0.03, S * 0.09), (20, 55), max(2, S // 400), 1, seed=5))
        img = bg

    cx, cy, r = S * 0.5, S * 0.6, S * 0.17
    # ripples (sound waves on water)
    ring = Image.new("L", (S, S), 0)
    rd = ImageDraw.Draw(ring)
    for k, a in ((1.35, 170), (1.75, 110), (2.2, 60)):
        rx, ry = r * k, r * k * 0.28
        rd.ellipse((cx - rx, cy + r * 0.95 - ry, cx + rx, cy + r * 0.95 + ry), outline=a, width=max(3, S // 160))
    img = Image.alpha_composite(img, tinted((S, S), ICE, ring.filter(ImageFilter.GaussianBlur(S / 900))))
    # glow behind the drop
    img = soft_blob(img, cx, cy - r * 0.5, r * 1.5, r * 1.9, (140, 200, 255), 110, S * 0.06)
    # drop with gradient
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).polygon(drop_polygon(cx, cy, r), fill=255)
    img = Image.alpha_composite(img, gradient_fill((S, S), m, (255, 255, 255), (150, 210, 245)))
    # inner highlight
    hm = Image.new("L", (S, S), 0)
    ImageDraw.Draw(hm).ellipse((cx - r * 0.6, cy - r * 0.7, cx - r * 0.25, cy - r * 0.05), fill=200)
    img = Image.alpha_composite(img, tinted((S, S), (255, 255, 255), hm.filter(ImageFilter.GaussianBlur(S / 120))))
    # crescent moon tucked at the upper right, glowing amber-white
    mx, my, mr = cx + r * 1.35, cy - r * 1.95, r * 0.62
    img = soft_blob(img, mx, my, mr * 1.5, mr * 1.5, (200, 220, 255), 90, S * 0.04)
    moon = Image.new("RGBA", (S, S), MOON + (255,))
    img = Image.composite(moon, img, crescent_mask((S, S), mx, my, mr, bite=0.52, tilt=-2.5))

    if background:  # circular crop (YouTube shows avatars as circles)
        circ = Image.new("L", (S, S), 0)
        ImageDraw.Draw(circ).ellipse((0, 0, S, S), fill=255)
        img.putalpha(ImageChops.multiply(img.getchannel("A"), circ))
    return img.resize((size, size), Image.LANCZOS)


def spaced_text(draw, center_xy, text, font, tracking, fill, anchor_y="m"):
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = center_xy[0] - total / 2
    for ch, cw in zip(text, widths):
        draw.text((x, center_xy[1]), ch, font=font, fill=fill, anchor="l" + anchor_y)
        x += cw + tracking
    return total
