"""1280x720 click-worthy thumbnail: a bright frame from the video + big bold text with a dark fade."""
import os

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",       # GitHub Actions (Ubuntu)
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",         # macOS
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _font(size: int):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def make_thumbnail(video_path: str, text: str, out_path: str = "temp_thumb.jpg") -> str:
    """Grab the brightest of a few frames, crop to 16:9, add text. Returns the image path or None."""
    try:
        from moviepy.editor import VideoFileClip

        clip = VideoFileClip(video_path)
        dur = min(clip.duration, 60)
        frames = [clip.get_frame(dur * p) for p in (0.15, 0.35, 0.55, 0.75)]
        clip.close()
        frame = max(frames, key=lambda f: f.mean())  # brightest frame tends to read best small
        img = Image.fromarray(frame).convert("RGB")

        # crop/resize to 1280x720
        w, h = img.size
        target = 16 / 9
        if w / h > target:
            nw = int(h * target)
            img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = int(w / target)
            img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
        img = img.resize((1280, 720), Image.LANCZOS)
        img = ImageEnhance.Contrast(ImageEnhance.Color(img).enhance(1.25)).enhance(1.1)

        # dark gradient on the lower half so white text always pops
        shade = Image.new("L", (1, 720))
        for y in range(720):
            shade.putpixel((0, y), int(max(0, (y - 300) / 420) * 190))
        black = Image.new("RGB", (1280, 720), (0, 0, 0))
        img = Image.composite(black, img, shade.resize((1280, 720)))

        # big text, up to 2 lines, auto-sized to fit
        draw = ImageDraw.Draw(img)
        words = text.upper().split()
        lines = [" ".join(words)] if len(words) <= 2 else [" ".join(words[:-1]), words[-1]]
        size = 140
        while size > 60:
            font = _font(size)
            if all(draw.textlength(l, font=font) <= 1160 for l in lines):
                break
            size -= 8
        y = 690 - len(lines) * (size + 10)
        for line in lines:
            x = (1280 - draw.textlength(line, font=font)) / 2
            draw.text((x, y), line, font=font, fill=(255, 255, 255), stroke_width=max(4, size // 18), stroke_fill=(0, 0, 0))
            y += size + 10

        img.save(out_path, "JPEG", quality=90)
        return out_path
    except Exception as e:
        print(f"   ⚠️ Thumbnail generation failed: {e}")
        return None
