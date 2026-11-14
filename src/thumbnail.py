"""1280x720 branded thumbnail: graded video frame, Manrope headline, length badge and Rainora mark."""
import os

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from src.brand import AMBER, ICE, NIGHT, draw_logo, manrope, tinted


def _best_frame(video_path):
    from moviepy.editor import VideoFileClip
    clip = VideoFileClip(video_path)
    dur = min(clip.duration, 60)
    frames = [clip.get_frame(dur * p) for p in (0.15, 0.35, 0.55, 0.75)]
    clip.close()
    return Image.fromarray(max(frames, key=lambda f: f.std() + f.mean() * 0.3))  # contrasty + bright


def _fit_lines(draw, lines, max_w, start, weight="ExtraBold"):
    size = start
    while size > 50:
        f = manrope(size, weight)
        if all(draw.textlength(l, font=f) <= max_w for l in lines):
            return f, size
        size -= 6
    return manrope(size, weight), size


def make_thumbnail(video_path: str, text: str, out_path: str = "temp_thumb.jpg", badge: str = "10 MIN") -> str:
    try:
        img = _best_frame(video_path).convert("RGB")
        w, h = img.size
        if w / h > 16 / 9:
            nw = int(h * 16 / 9); img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = int(w * 9 / 16); img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
        img = img.resize((1280, 720), Image.LANCZOS)
        img = ImageEnhance.Contrast(ImageEnhance.Color(img).enhance(1.3)).enhance(1.12)
        img = img.convert("RGBA")

        # cinematic grade: dark left side for text, vignette
        grad = Image.new("L", (1280, 720), 0)
        gp = grad.load()
        for x in range(1280):
            a = int(max(0, 1 - x / 820) ** 1.4 * 215)
            for y in range(720):
                gp[x, y] = a
        img = Image.alpha_composite(img, tinted((1280, 720), NIGHT, grad))
        vig = Image.new("L", (1280, 720), 0)
        ImageDraw.Draw(vig).rectangle((0, 0, 1280, 720), outline=255, width=90)
        img = Image.alpha_composite(img, tinted((1280, 720), NIGHT, vig.filter(ImageFilter.GaussianBlur(90)).point(lambda v: v * 0.7)))

        # headline: last word in moonlight-blue accent, others white
        words = text.upper().split() or ["AMBIENCE"]
        lines = [" ".join(words[:-1]), words[-1]] if len(words) > 1 else [words[0]]
        d = ImageDraw.Draw(img)
        f, size = _fit_lines(d, lines, 700, 150)
        y = 360 - (len(lines) * size * 1.02) / 2
        shadow = Image.new("L", (1280, 720), 0)
        sd = ImageDraw.Draw(shadow)
        for i, line in enumerate(lines):
            sd.text((72, y + i * size * 1.02 + 6), line, font=f, fill=230)
        img = Image.alpha_composite(img, tinted((1280, 720), (0, 0, 0), shadow.filter(ImageFilter.GaussianBlur(10))))
        d = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            d.text((66, y + i * size * 1.02), line, font=f, fill=ICE if i == len(lines) - 1 and len(lines) > 1 else (255, 255, 255))

        # accent bar + badge
        d.rounded_rectangle((66, y - 34, 166, y - 22), radius=6, fill=AMBER)
        bf = manrope(38, "ExtraBold")
        bw = d.textlength(badge, font=bf)
        d.rounded_rectangle((1280 - bw - 92, 40, 1240, 104), radius=32, fill=AMBER)
        d.text((1240 - (bw + 52) / 2, 72), badge, font=bf, fill=NIGHT, anchor="mm")

        # brand mark bottom-left
        logo = draw_logo(78)
        img.alpha_composite(logo, (60, 610))
        d = ImageDraw.Draw(img)
        d.text((150, 649), "RAINORA", font=manrope(32, "ExtraBold"), fill=(255, 255, 255), anchor="lm")

        img.convert("RGB").save(out_path, "JPEG", quality=92)
        return out_path
    except Exception as e:
        print(f"   ⚠️ Thumbnail generation failed: {e}")
        return None
