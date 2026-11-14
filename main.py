import os
import sys
import random
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.script_generator import generate_ambience_metadata
from src.video_transformer import create_long_form_video, create_short_video
from src.youtube_uploader import upload_to_youtube
from src.thumbnail import make_thumbnail
from src.quality_check import check_video

# DRY_RUN=1 python main.py  -> build + quality-check everything, save to DRY_RUN_DIR, upload nothing
DRY_RUN = os.environ.get("DRY_RUN") == "1"
DRY_RUN_DIR = os.environ.get("DRY_RUN_DIR", "dry_run_output")
LONG_SECONDS = 600
SHORT_SECONDS = 30


def passes_quality(path: str, seconds: int, vertical: bool, label: str) -> bool:
    ok, report = check_video(path, seconds, vertical)
    print(f"   🔍 QC {label}: {'✅ PASS' if ok else '❌ FAIL'} — {report}")
    return ok


def keep_for_review(path: str, name: str) -> None:
    import shutil
    os.makedirs(DRY_RUN_DIR, exist_ok=True)
    shutil.copy(path, os.path.join(DRY_RUN_DIR, name))

# ── Peak publish times (UTC) ────────────────────────────────────────────────
# Audience = global English (US is the biggest market for sleep/study ambience).
# YouTube advice: publish 1–3 hours BEFORE your audience's peak so the video is
# indexed and recommended when viewers arrive.
#   Shorts  → US lunch break (~12 PM ET) and US early evening (~7 PM ET)
#   Long    → before US evening wind-down / study (~6 PM ET) and before
#             US-West + late-evening sleep viewing (~9 PM ET)
PUBLISH_SLOTS_UTC = [
    # (long-form slot, short slot) per topic
    {"long": "22:00", "short": "16:00"},   # 5 PM ET  / 11 AM ET
    {"long": "01:00", "short": "23:30"},   # 8 PM ET  / 6:30 PM ET
]
MIN_LEAD = timedelta(minutes=45)  # publishAt must be safely in the future


def next_slot(hhmm: str) -> str:
    """Next occurrence of HH:MM UTC at least MIN_LEAD from now, as RFC 3339."""
    now = datetime.now(timezone.utc)
    h, m = map(int, hhmm.split(":"))
    slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
    while slot < now + MIN_LEAD:
        slot += timedelta(days=1)
    return slot.strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    print("🚀 Starting Hybrid Ambience Automation Pipeline...")

    # A rich pool of ambient sub-niches to pull from randomly
    master_topics = [
        "rain window",
        "cozy fireplace",
        "lofi cafe night",
        "snow falling window",
        "thunderstorm night",
        "library ambience",
        "train window night",
        "ocean waves night",
        "autumn forest rain",
        "campfire crackling"
    ]

    # Randomly select 2 topics per run -> 2 long-form + 2 Shorts = 4 uploads/day.
    # (Each YouTube upload costs 1,600 of the 10,000 daily API quota units, so 4 leaves room for retries.)
    ambience_topics = random.sample(master_topics, 2)
    print(f"🎯 Selected topics for today's run: {ambience_topics}")

    for topic, slots in zip(ambience_topics, PUBLISH_SLOTS_UTC):
        long_publish_at = next_slot(slots["long"])
        short_publish_at = next_slot(slots["short"])
        print(f"\n----------------------------------------")
        print(f"🎬 Processing Ambience Topic: {topic}")
        print(f"----------------------------------------")

        # --- 1. PROCESS LONG-FORM VIDEO (10 mins = 600s) ---
        long_output_path = "temp_long.mp4"
        
        long_success = create_long_form_video(
            query_keyword=topic, 
            output_path=long_output_path, 
            target_duration=LONG_SECONDS
        )

        if long_success and not passes_quality(long_output_path, LONG_SECONDS, False, "long-form"):
            long_success = False  # never upload a broken / silent video

        if long_success:
            print("🤖 Generating metadata for Long-Form video via Gemini...")
            long_meta = generate_ambience_metadata(topic, is_short=False, duration_label="10 Minutes")
            thumb_path = make_thumbnail(long_output_path, long_meta["thumbnail_text"])
            
            print(f"📤 Uploading Long-Form: {long_meta['title']}")
            if DRY_RUN:
                slug = topic.replace(" ", "_")
                keep_for_review(long_output_path, f"{slug}_long.mp4")
                if thumb_path: keep_for_review(thumb_path, f"{slug}_thumb.jpg")
                with open(os.path.join(DRY_RUN_DIR, f"{slug}_long.txt"), "w") as f:
                    f.write(f"{long_meta['title']}\n\n{long_meta['description']}\n\nTAGS: {', '.join(long_meta['tags'])}\nPUBLISH AT: {long_publish_at}\n")
                print("   (dry run: not uploaded)")
            else:
                upload_to_youtube(
                    video_file=long_output_path,
                    title=long_meta["title"],
                    description=long_meta["description"],
                    tags=long_meta["tags"],
                    is_short=False,
                    publish_at=long_publish_at,
                    thumbnail=thumb_path,
                    topic=topic,
                )
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)

        if os.path.exists(long_output_path):
            os.remove(long_output_path)

        # --- 2. PROCESS SHORT VIDEO (30 secs, 9:16) ---
        short_output_path = "temp_short.mp4"
        short_success = create_short_video(
            query_keyword=topic, 
            output_path=short_output_path, 
            target_duration=SHORT_SECONDS
        )

        if short_success and not passes_quality(short_output_path, SHORT_SECONDS, True, "short"):
            short_success = False

        if short_success:
            print("🤖 Generating metadata for Short via Gemini...")
            short_meta = generate_ambience_metadata(topic, is_short=True)
            
            print(f"📤 Uploading Short: {short_meta['title']}")
            if DRY_RUN:
                slug = topic.replace(" ", "_")
                keep_for_review(short_output_path, f"{slug}_short.mp4")
                with open(os.path.join(DRY_RUN_DIR, f"{slug}_short.txt"), "w") as f:
                    f.write(f"{short_meta['title']}\n\n{short_meta['description']}\n\nTAGS: {', '.join(short_meta['tags'])}\nPUBLISH AT: {short_publish_at}\n")
                print("   (dry run: not uploaded)")
            else:
                upload_to_youtube(
                    video_file=short_output_path,
                    title=short_meta["title"],
                    description=short_meta["description"],
                    tags=short_meta["tags"],
                    is_short=True,
                    publish_at=short_publish_at,
                    topic=topic,
                )

        if os.path.exists(short_output_path):
            os.remove(short_output_path)

    print("\n✨ All dynamic tasks completed successfully!")

if __name__ == "__main__":
    main()
