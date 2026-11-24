"""
SEO metadata for ambience videos.

Gemini returns structured JSON (title, description, tags, hashtags, thumbnail text) built around
the phrases people actually type into YouTube search. Output is validated and cleaned so it always
fits YouTube's limits; if Gemini is unavailable, a keyword-optimised fallback is used instead.
"""
import json
import os
import re
import time

from google import genai
from google.genai import types

# Without these a stalled Gemini request waits forever and the whole run dies at the job time limit.
GEMINI_TIMEOUT_MS = 45_000  # one request
GEMINI_BUDGET_S = 240       # all models and retries together; after that the fallback metadata is used

# Search phrases per topic: [primary keyword, secondary keywords...]
# Primary = highest-volume phrase; it leads the title and the first line of the description.
KEYWORDS = {
    "rain window": ["rain on window sounds", "rain sounds for sleeping", "rain on glass", "rainy night ambience", "relaxing rain sounds"],
    "cozy fireplace": ["cozy fireplace sounds", "crackling fireplace", "fireplace ambience", "fire sounds for sleeping", "relaxing fireplace"],
    "lofi cafe night": ["cozy cafe ambience", "coffee shop sounds", "night cafe ambience", "cafe sounds for studying", "lofi cafe"],
    "snow falling window": ["snow falling ambience", "winter window ambience", "snowfall sounds", "cozy winter night", "snow storm sounds"],
    "thunderstorm night": ["thunderstorm sounds for sleeping", "thunder and rain sounds", "heavy rain and thunder", "night storm ambience", "rain and thunder for sleep"],
    "library ambience": ["library ambience", "study ambience", "quiet library sounds", "study with me ambience", "focus sounds for studying"],
    "train window night": ["train ride ambience", "night train sounds", "train sounds for sleeping", "rainy train window", "train journey ambience"],
    "ocean waves night": ["ocean waves sounds", "ocean sounds for sleeping", "sea waves at night", "calming ocean waves", "beach waves sounds"],
    "autumn forest rain": ["forest rain sounds", "autumn rain ambience", "rain in the forest", "nature sounds for sleeping", "gentle rain sounds"],
    "campfire crackling": ["campfire sounds", "crackling campfire", "campfire ambience", "fire crackling sounds for sleep", "night campfire"],
}


SMALL_WORDS = {"a", "an", "and", "as", "at", "for", "in", "of", "on", "or", "the", "to", "with"}


def _title_case(text: str) -> str:
    words = text.split()
    return " ".join(w if i and w.lower() in SMALL_WORDS else w[:1].upper() + w[1:] for i, w in enumerate(words))


def _keywords(topic: str) -> list:
    return KEYWORDS.get(topic.lower(), [f"{topic} sounds", f"{topic} ambience", f"{topic} for sleep", "relaxing ambience", "sleep sounds"])


def _build_prompt(topic: str, is_short: bool, duration_label: str) -> str:
    kw = _keywords(topic)
    fmt = (
        "a YouTube SHORT (30 seconds, vertical). Shorts are found via the Shorts feed and search."
        if is_short
        else f"a long-form YouTube video ({duration_label}, horizontal) of continuous ambience with no talking or music."
    )
    return f"""You are a YouTube SEO expert for sleep / study / relaxation ambience channels.
Write metadata for {fmt}
Theme: "{topic}".
Primary search keyword (MUST appear, word-for-word, at the START of the title and in the first sentence of the description): "{kw[0]}"
Secondary keywords (use naturally): {", ".join(kw[1:])}

Rules:
TITLE
- {"40-60 characters" if is_short else "55-70 characters"}, starts with the primary keyword in Title Case.
- {"Add one short hook (e.g. 'Instant Calm')." if is_short else f"Add the main benefits separated by '|' or '•' (e.g. 'for Sleep, Study & Relaxation') and the length '{duration_label}'."}
- At most ONE emoji, at the end. No ALL-CAPS words, no clickbait, no false claims (never claim a length other than {duration_label}).
DESCRIPTION
- First 2 lines (~150 chars) are what search shows: primary keyword + 1 secondary keyword + the benefit.
- {"3-4 short lines total." if is_short else "Then a short immersive paragraph (2-3 sentences) describing the scene and sounds, then a 'Perfect for:' list of 5 uses (one per line, starting with '•'), then a line inviting viewers to subscribe and turn on notifications for daily ambience."}
- Do NOT include hashtags inside the description (they are added separately). No links. No timestamps.
TAGS
- 18-25 tags: the exact primary keyword, each secondary keyword, long-tail variants people search (e.g. '... for sleeping', '... no music'), and broad terms (ambience, sleep sounds, white noise, study ambience).
- All lowercase, no '#', no duplicates.
HASHTAGS
- {"4" if is_short else "3"} hashtags, CamelCase, most searched first{", first one must be #Shorts" if is_short else ""}.
THUMBNAIL_TEXT
- 2-3 punchy words (e.g. 'DEEP SLEEP RAIN'), uppercase.

Return ONLY JSON: {{"title": str, "description": str, "tags": [str], "hashtags": [str], "thumbnail_text": str}}"""


def _clean(meta: dict, topic: str, is_short: bool, duration_label: str) -> dict:
    kw = _keywords(topic)

    title = re.sub(r"\s+", " ", str(meta.get("title", ""))).strip()
    title = re.sub(r"\s*#\w+", "", title).strip()  # hashtags in titles are re-added below for Shorts only
    if title.lower().startswith(kw[0].lower()):
        title = _title_case(kw[0]) + title[len(kw[0]):]
    elif kw[0].lower() not in title.lower():
        title = f"{_title_case(kw[0])} – {title}" if title else _title_case(kw[0])

    hashtags = []
    for h in meta.get("hashtags", []) or []:
        h = "#" + re.sub(r"[^A-Za-z0-9]", "", str(h))
        if len(h) > 1 and h.lower() not in [x.lower() for x in hashtags]:
            hashtags.append(h)
    if is_short and "#shorts" not in [h.lower() for h in hashtags]:
        hashtags.insert(0, "#Shorts")
    hashtags = hashtags[: 4 if is_short else 3] or ["#Ambience", "#SleepSounds", "#Relaxing"]

    if is_short and len(title) <= 92:
        title = f"{title} #Shorts"
    title = title[:100]

    description = str(meta.get("description", "")).strip()
    description = re.sub(r"(?m)^\s*#\w+(\s+#\w+)*\s*$", "", description).strip()  # strip stray hashtag lines
    description = f"{description}\n\n{' '.join(hashtags)}"[:4900]

    tags, seen, total = [], set(), 0
    for t in list(meta.get("tags", []) or []) + kw + ["ambience", "sleep sounds", "relaxing sounds", "study ambience", "white noise"]:
        t = re.sub(r"[<>#,]", "", str(t)).strip().lower()
        if not t or t in seen:
            continue
        cost = len(t) + (2 if " " in t else 0) + 1  # YouTube counts quotes around multi-word tags + comma
        if total + cost > 480:
            break
        tags.append(t)
        seen.add(t)
        total += cost

    thumb = re.sub(r"[^A-Za-z0-9 &]", "", str(meta.get("thumbnail_text", ""))).strip().upper()
    if not thumb or len(thumb) > 28:
        thumb = topic.upper()

    return {"title": title, "description": description, "tags": tags, "thumbnail_text": thumb}


def generate_ambience_metadata(topic: str, is_short: bool = False, duration_label: str = "10 Minutes") -> dict:
    """Return SEO-optimised {title, description, tags, thumbnail_text} for an ambience video."""
    topic = os.path.splitext(topic)[0].replace("_", " ").strip()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ Warning: GEMINI_API_KEY missing. Using fallback metadata.")
        return get_fallback_metadata(topic, is_short, duration_label)

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))
    deadline = time.monotonic() + GEMINI_BUDGET_S
    prompt = _build_prompt(topic, is_short, duration_label)
    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.9)

    for model in ("gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-2.5-flash"):
        for attempt in range(3):
            if time.monotonic() > deadline:
                print("❌ Gemini is too slow right now. Using fallback metadata.")
                return get_fallback_metadata(topic, is_short, duration_label)
            try:
                response = client.models.generate_content(model=model, contents=prompt, config=config)
                raw = (response.text or "").strip()
                raw = re.sub(r"^```(?:json)?|```$", "", raw).strip()
                return _clean(json.loads(raw), topic, is_short, duration_label)
            except Exception as e:
                print(f"   ⚠️ Gemini ({model}) attempt {attempt + 1} failed: {str(e)[:160]}")
                if "NOT_FOUND" in str(e):
                    break  # model not available -> try the next one straight away
                time.sleep(5 * (attempt + 1))

    print("❌ Gemini unavailable. Using fallback metadata.")
    return get_fallback_metadata(topic, is_short, duration_label)


def get_fallback_metadata(topic: str, is_short: bool, duration_label: str = "10 Minutes") -> dict:
    kw = _keywords(topic)
    primary = _title_case(kw[0])
    if is_short:
        meta = {
            "title": f"{primary} – Instant Calm 🌙",
            "description": (
                f"{primary} to calm your mind in seconds. {kw[1].capitalize()} for sleep, study and relaxation.\n"
                "Subscribe for a new ambience every day."
            ),
            "tags": kw,
            "hashtags": ["#Shorts", "#Ambience", "#SleepSounds", "#Relaxing"],
            "thumbnail_text": topic.upper(),
        }
    else:
        meta = {
            "title": f"{primary} for Sleep, Study & Relaxation | {duration_label}",
            "description": (
                f"{primary} for deep sleep, focused study and relaxation. Enjoy {duration_label.lower()} of {kw[1]} "
                "with no music and no talking.\n\n"
                f"Close your eyes and let the soothing sound of {topic} wash away the day.\n\n"
                "Perfect for:\n• Falling asleep fast\n• Studying and deep focus\n• Reading and working\n"
                "• Meditation and stress relief\n• Calming background noise\n\n"
                "🔔 Subscribe and turn on notifications for new ambience every day."
            ),
            "tags": kw,
            "hashtags": ["#SleepSounds", "#Ambience", "#RelaxingSounds"],
            "thumbnail_text": topic.upper(),
        }
    return _clean(meta, topic, is_short, duration_label)
