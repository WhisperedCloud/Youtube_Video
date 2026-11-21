"""Account D: Stoic quote Reels.

Real quote (hand-checked list) set in a serif face, revealed line by line over moody graded footage,
then the author, then an original one-line "what it means today" — the part that makes each Reel original.
"""
import os
import random

from PIL import ImageDraw, ImageFilter

from audio import stoic_track
from common import H, W, clean_hashtags, download, font, gemini_json, load_used, mark_used, pixabay_search
from quotes import BACKDROPS, QUOTES
from render import canvas, compose, fit_lines, gradient, save, shadow_text

GOLD = (214, 178, 112)


def pick_quote(used: list):
    done = {u[2:] for u in used if u.startswith("q:")}
    pool = [q for q in QUOTES if q[0][:60] not in done]
    if not pool:  # every quote used once -> start a new cycle (new footage + new meaning line each time)
        mark_used("stoic", "cycle:reset")
        pool = QUOTES[:]
    return random.choice(pool)


def pick_backdrop(used: list):
    choices = BACKDROPS[:]
    random.shuffle(choices)
    for query, tags in choices:
        try:
            clips = pixabay_search(query, must_tags=tags, min_seconds=10, exclude=used)
        except Exception as e:
            print(f"   ⚠️ Pixabay search failed for {query}: {e}")
            continue
        if clips:
            clip = random.choice(clips[:10])
            print(f"   🌫️ backdrop '{query}'  ←  Pixabay {clip['id']}")
            return clip
    raise RuntimeError("No backdrop footage found")


def stoic_text(quote: str, author: str) -> dict:
    prompt = f"""You run a thoughtful Stoicism Instagram account. Today's quote:
"{quote}" — {author}
Do NOT change or re-word the quote. Return JSON:
- "meaning": ONE plain-English line applying it to modern life (work, phones, relationships, money, stress).
  Specific, warm, not preachy. Max 95 characters. No emoji, no quotation marks.
- "hook": first caption line that stops the scroll, max 70 characters, no emoji.
- "reflection": 2-3 short sentences expanding the idea for the caption, practical, second person.
- "hashtags": 6 relevant hashtags (no '#')."""
    g = gemini_json(prompt, temperature=0.9) or {}
    meaning = str(g.get("meaning", "")).strip().strip('"“”')
    if not (15 <= len(meaning) <= 110):
        meaning = ""
    return {"meaning": meaning,
            "hook": str(g.get("hook", "")).strip()[:90] or f"{author} wrote this 2,000 years ago. Still true.",
            "reflection": str(g.get("reflection", "")).strip()[:600],
            "hashtags": g.get("hashtags", [])}


def build(handle: str, work: str, dry_run: bool):
    used = load_used("stoic")
    quote, author, source = pick_quote(used)
    clip = pick_backdrop(used)
    text = stoic_text(quote, author)
    clip_path = download(clip["url"], os.path.join(work, "clip.mp4"))
    p = lambda n: os.path.join(work, n)

    probe = ImageDraw.Draw(canvas())
    qf, lines = fit_lines(probe, quote, lambda s: font("serif", s, "SemiBold"), 880, 6, 92, 58)
    words = len(quote.split())
    line_gap = 0.55
    q_start = 0.4
    q_done = q_start + line_gap * len(lines) + 0.4
    author_at = q_done + max(0.6, words * 0.22 - line_gap * len(lines))
    meaning_at = author_at + 1.4
    duration = round(min(18.0, max(11.0, meaning_at + (4.2 if text["meaning"] else 2.6))), 2)

    base = gradient(0, H, 95, 95)
    vign = canvas()
    ImageDraw.Draw(vign).ellipse((-260, 120, W + 260, H - 120), fill=(0, 0, 0, 0))
    mask = canvas()
    ImageDraw.Draw(mask).rectangle((0, 0, W, H), fill=(0, 0, 0, 170))
    ImageDraw.Draw(mask).ellipse((-200, 220, W + 200, H - 220), fill=(0, 0, 0, 0))
    base.alpha_composite(mask.filter(ImageFilter.GaussianBlur(140)))
    bd = ImageDraw.Draw(base)
    if handle:
        bd.text((W / 2, 205), f"@{handle}".upper(), font=font("sans", 26, "Bold"), fill=(255, 255, 255, 150), anchor="mm")

    lh = int(qf.size * 1.22)
    block_h = lh * len(lines)
    top = 860 - block_h / 2
    overlays = [{"png": save(base, p("base.png"))}]

    mark = canvas()
    shadow_text(mark, (W / 2, top - 70), "“", font("serif", 170, "Bold"), GOLD + (255,), blur=8)
    overlays.append({"png": save(mark, p("mark.png")), "start": 0.0, "fade": 0.6})
    for i, line in enumerate(lines):
        c = canvas()
        shadow_text(c, (W / 2, top + lh * i + lh / 2), line, qf, (250, 246, 238), blur=12, strength=230)
        overlays.append({"png": save(c, p(f"l{i}.png")), "start": q_start + line_gap * i, "fade": 0.7})

    a = canvas()
    ay = top + block_h + 70
    ad = ImageDraw.Draw(a)
    ad.line([(W / 2 - 40, ay - 34), (W / 2 + 40, ay - 34)], fill=GOLD + (230,), width=3)
    shadow_text(a, (W / 2, ay + 12), author.upper(), font("sans", 38, "ExtraBold"), GOLD + (255,), blur=8)
    shadow_text(a, (W / 2, ay + 60), source, font("serif", 40, "Medium"), (235, 230, 220, 210), blur=8)
    overlays.append({"png": save(a, p("author.png")), "start": author_at, "fade": 0.8})

    if text["meaning"]:
        m = canvas()
        md = ImageDraw.Draw(m)
        mf, mlines = fit_lines(md, text["meaning"], lambda s: font("sans", s, "SemiBold"), 860, 3, 44, 34)
        my = max(ay + 170, 1240)
        shadow_text(m, (W / 2, my), "TODAY, THIS MEANS", font("sans", 26, "ExtraBold"), (255, 255, 255, 170), blur=6)
        for i, line in enumerate(mlines):
            shadow_text(m, (W / 2, my + 64 + i * (mf.size + 16)), line, mf, (255, 255, 255), blur=10)
        overlays.append({"png": save(m, p("meaning.png")), "start": meaning_at, "fade": 0.8})

    audio = stoic_track(p("audio.wav"), duration, seed=random.randint(0, 10_000))
    out = compose(clip_path, overlays, audio, p("reel.mp4"), duration,
                  grade="eq=brightness=-0.06:contrast=1.06:saturation=0.55,vignette=PI/4.5")

    tags = clean_hashtags(text["hashtags"], ["Stoicism", "Stoic", "MarcusAurelius", "Seneca", "Philosophy", "Mindset"], 8)
    body = f"{text['hook']}\n\n“{quote}”\n— {author}, {source}\n"
    if text["meaning"]:
        body += f"\nToday, this means: {text['meaning']}\n"
    if text["reflection"]:
        body += f"\n{text['reflection']}\n"
    body += ("\nSave this for the day you need it, and send it to someone who does.\n"
             f"{'Follow @' + handle + ' for one Stoic idea every day.' if handle else 'Follow for one Stoic idea every day.'}"
             f"\n\n{' '.join(tags)}")
    return {"video": out, "caption": body, "duration": duration, "thumb_ms": int((author_at + 1.0) * 1000),
            "used": [clip["id"], f"q:{quote[:60]}"], "summary": f"{author}: {quote} | meaning: {text['meaning']}"}
