import os
import random
import re
import subprocess

import imageio_ffmpeg
import requests
from PIL import Image

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import VideoFileClip, concatenate_videoclips

from src.audio_bed import make_ambience_wav

TRACKER_FILE = "used_video_ids.txt"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
REAL_AUDIO_DB = -45.0  # clip audio quieter than this (mean) is treated as silent


def load_used_ids():
    if not os.path.exists(TRACKER_FILE):
        return set()
    with open(TRACKER_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())


def save_used_id(video_id):
    with open(TRACKER_FILE, "a") as f:
        f.write(f"{video_id}\n")


def clip_mean_volume(path: str):
    """Mean loudness of a file's audio in dB, or None if it has no audio stream."""
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: ([-\d.]+) dB", out)
    return float(m.group(1)) if m else None


def add_ambience_audio(video_only: str, source_clip: str, topic: str, duration: float, out_path: str) -> None:
    """Mux a topic-matched ambience bed (+ the clip's real audio, if any) onto the video, loudness-normalised."""
    bed = make_ambience_wav(topic, duration, "temp_bed.wav")
    clip_db = clip_mean_volume(source_clip)
    use_clip_audio = clip_db is not None and clip_db > REAL_AUDIO_DB
    print(f"   -> Audio: synthesised '{topic}' ambience" + (f" + clip's own sound ({clip_db:.0f} dB)" if use_clip_audio else " (clip has no usable sound)"))

    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", video_only, "-i", bed]
    if use_clip_audio:
        # loop the source clip's audio for the full duration and blend it with the bed
        cmd += ["-stream_loop", "-1", "-i", source_clip,
                "-filter_complex",
                f"[2:a]atrim=0:{duration},asetpts=N/SR/TB,volume=1.0[c];[1:a]volume=0.6[b];"
                f"[c][b]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-filter_complex", "[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]", "-map", "0:v", "-map", "[a]"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-t", str(duration), out_path]
    subprocess.run(cmd, check=True)
    os.remove(bed)


def fetch_specific_pixabay_video(query: str, output_path: str) -> bool:
    """Download an unused Pixabay clip for the query (sound is added separately, so silent clips are fine)."""
    api_key = os.environ.get("PIXABAY_API_KEY")
    if not api_key:
        print("⚠️ PIXABAY_API_KEY missing.")
        return False

    url = "https://pixabay.com/api/videos/"
    used_ids = load_used_ids()

    try:
        hits, fresh_hits = [], []
        for page in range(1, 4):
            params = {"key": api_key, "q": query, "video_type": "film", "per_page": 50, "page": page}
            response = requests.get(url, params=params, timeout=30)
            if response.status_code != 200:
                break
            page_hits = response.json().get("hits", [])
            if not page_hits:
                break
            hits.extend(page_hits)
            fresh_hits.extend(h for h in page_hits if str(h["id"]) not in used_ids)
            if len(fresh_hits) >= 5:
                break

        if not fresh_hits:
            print(f"   ⚠️ No unused Pixabay clips left for '{query}' — reusing an older clip.")
            fresh_hits = hits

        random.shuffle(fresh_hits)

        for hit in fresh_hits:
            video_id = str(hit["id"])
            video_url = (hit["videos"].get("large") or {}).get("url") or hit["videos"]["medium"]["url"]
            with open(output_path, "wb") as f:
                f.write(requests.get(video_url, timeout=180).content)
            try:
                c = VideoFileClip(output_path)
                ok = c.duration and c.duration >= 3
                c.close()
                if ok:
                    save_used_id(video_id)
                    return True
            except Exception:
                pass
            if os.path.exists(output_path):
                os.remove(output_path)
    except Exception as e:
        print(f"❌ Pixabay API Error: {e}")

    return False


def _looped(clip, target_duration):
    safe = max(clip.duration - 0.3, 1.0)
    sub = clip.subclip(0, safe).without_audio()
    reps = int(target_duration // safe) + 1
    return concatenate_videoclips([sub] * reps).subclip(0, target_duration)


def create_long_form_video(query_keyword: str, output_path: str, target_duration: int = 600) -> bool:
    print(f"   -> [Long-Form] Searching fresh Pixabay asset for '{query_keyword}'...")
    source = "temp_long_source.mp4"
    if not fetch_specific_pixabay_video(query_keyword, source):
        return False

    clip = final_clip = None
    try:
        print(f"   -> Processing Long-Form (16:9, {target_duration}s)...")
        clip = VideoFileClip(source)
        final_clip = _looped(clip, target_duration)
        if final_clip.h > 1080:
            final_clip = final_clip.resize(height=1080)
        final_clip.write_videofile("temp_long_video.mp4", fps=24, codec="libx264", audio=False,
                                   preset="veryfast", logger=None)
        add_ambience_audio("temp_long_video.mp4", source, query_keyword, target_duration, output_path)
        return True
    except Exception as e:
        print(f"❌ Long-Form Rendering Error: {e}")
        return False
    finally:
        if final_clip: final_clip.close()
        if clip: clip.close()
        for f in (source, "temp_long_video.mp4"):
            if os.path.exists(f): os.remove(f)


def create_short_video(query_keyword: str, output_path: str, target_duration: int = 30) -> bool:
    print(f"   -> [Short] Searching SEPARATE fresh Pixabay asset for '{query_keyword}'...")
    source = "temp_short_source.mp4"
    if not fetch_specific_pixabay_video(query_keyword, source):
        return False

    clip = vertical_clip = None
    try:
        print(f"   -> Processing Short (9:16 vertical, {target_duration}s)...")
        clip = VideoFileClip(source)
        looped = _looped(clip, target_duration)
        w, h = looped.size
        new_w = int(h * (9 / 16))
        x_center = w / 2
        vertical_clip = looped.crop(x1=x_center - new_w / 2, y1=0, x2=x_center + new_w / 2, y2=h).resize((1080, 1920))
        vertical_clip.write_videofile("temp_short_video.mp4", fps=24, codec="libx264", audio=False,
                                      preset="veryfast", logger=None)
        add_ambience_audio("temp_short_video.mp4", source, query_keyword, target_duration, output_path)
        return True
    except Exception as e:
        print(f"❌ Short Rendering Error: {e}")
        return False
    finally:
        if vertical_clip: vertical_clip.close()
        if clip: clip.close()
        for f in (source, "temp_short_video.mp4"):
            if os.path.exists(f): os.remove(f)
