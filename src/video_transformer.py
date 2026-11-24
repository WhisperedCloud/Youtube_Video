"""
Pixabay clip -> finished video (all rendering done directly with ffmpeg, so it is fast on CI).

1. Build ONE seamless loop unit: the clip's last second cross-fades into its first second,
   so when the unit repeats there is no visible jump.
2. Repeat that unit to the target length without re-encoding (-stream_loop + copy).
3. Add a topic-matched ambience soundtrack (+ the clip's own sound if it has any),
   loudness-normalised for YouTube.
"""
import os
import random
import re
import subprocess

import imageio_ffmpeg
import requests

from src.audio_bed import make_ambience_wav

TRACKER_FILE = "used_video_ids.txt"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
REAL_AUDIO_DB = -45.0  # clip audio quieter than this (mean) is treated as silent
FPS = 30
XFADE = 1.0            # seconds of cross-fade at the loop point
ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS)]

LONG_VF = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1"
SHORT_VF = "crop='min(iw,ih*9/16)':ih,scale=1080:1920,setsar=1"


def load_used_ids():
    if not os.path.exists(TRACKER_FILE):
        return set()
    with open(TRACKER_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())


def save_used_id(video_id):
    with open(TRACKER_FILE, "a") as f:
        f.write(f"{video_id}\n")


def _ff(args, check=True):
    return subprocess.run([FFMPEG, "-hide_banner", "-y", "-nostdin", "-loglevel", "error", *args], check=check,
                          capture_output=True, text=True, timeout=1200)


def media_duration(path: str) -> float:
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def clip_mean_volume(path: str):
    """Mean loudness of a file's audio in dB, or None if it has no audio stream."""
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: ([-\d.]+) dB", out)
    return float(m.group(1)) if m else None


def make_seamless_unit(source: str, vf: str, out_path: str) -> None:
    """Encode one loopable unit of the clip (end cross-faded into start)."""
    d = media_duration(source) - 0.3  # drop the last frames (often black / glitchy)
    x = min(XFADE, d / 4)
    if d < 3:
        _ff(["-i", source, "-t", f"{d:.3f}", "-vf", f"{vf},fps={FPS}", "-an", *ENCODE, out_path])
        return
    graph = (
        f"[0:v]{vf},fps={FPS},format=yuv420p,split=3[a][b][c];"
        f"[a]trim=0:{x:.3f},setpts=PTS-STARTPTS,fps={FPS},settb=AVTB[head];"
        f"[b]trim={d - x:.3f}:{d:.3f},setpts=PTS-STARTPTS,fps={FPS},settb=AVTB[tail];"
        f"[c]trim={x:.3f}:{d - x:.3f},setpts=PTS-STARTPTS,fps={FPS},settb=AVTB[mid];"
        f"[tail][head]xfade=transition=fade:duration={x:.3f}:offset=0[blend];"
        f"[blend][mid]concat=n=2:v=1:a=0[v]"
    )
    _ff(["-i", source, "-filter_complex", graph, "-map", "[v]", "-an", *ENCODE, out_path])


def finish_with_audio(unit: str, source_clip: str, topic: str, duration: float, out_path: str) -> None:
    """Loop the unit to `duration` (no re-encode) and add ambience audio, loudness-normalised."""
    bed = make_ambience_wav(topic, duration, "temp_bed.wav")
    clip_db = clip_mean_volume(source_clip)
    use_clip_audio = clip_db is not None and clip_db > REAL_AUDIO_DB
    print(f"   -> Audio: synthesised '{topic}' ambience" +
          (f" + clip's own sound ({clip_db:.0f} dB)" if use_clip_audio else " (clip has no usable sound)"))

    args = ["-stream_loop", "-1", "-i", unit, "-i", bed]
    if use_clip_audio:
        args += ["-stream_loop", "-1", "-i", source_clip, "-filter_complex",
                 f"[2:a]atrim=0:{duration},asetpts=N/SR/TB[c];[1:a]volume=0.6[b];"
                 f"[c][b]amix=inputs=2:normalize=0,loudnorm=I=-20:TP=-3:LRA=7,alimiter=limit=0.63:level=false:attack=5:release=80[a]"]
    else:
        args += ["-filter_complex", "[1:a]loudnorm=I=-20:TP=-3:LRA=7,alimiter=limit=0.63:level=false:attack=5:release=80[a]"]
    args += ["-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
             "-ac", "2", "-movflags", "+faststart", "-t", str(duration), out_path]
    _ff(args)
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

        # prefer longer clips (fewer loop repeats) and HD sources
        random.shuffle(fresh_hits)
        fresh_hits.sort(key=lambda h: (h.get("duration", 0) >= 10, (h["videos"].get("large") or {}).get("width", 0) >= 1920), reverse=True)

        for hit in fresh_hits:
            video_id = str(hit["id"])
            large = hit["videos"].get("large") or {}
            video_url = large.get("url") or hit["videos"]["medium"]["url"]
            with open(output_path, "wb") as f:
                f.write(requests.get(video_url, timeout=180).content)
            if media_duration(output_path) >= 3:
                save_used_id(video_id)
                print(f"   -> Using Pixabay clip {video_id} ({hit.get('duration')}s, {large.get('width', '?')}x{large.get('height', '?')})")
                return True
            os.remove(output_path)
    except Exception as e:
        print(f"❌ Pixabay API Error: {e}")

    return False


def _create(kind: str, query_keyword: str, output_path: str, target_duration: int, vf: str) -> bool:
    source, unit = f"temp_{kind}_source.mp4", f"temp_{kind}_unit.mp4"
    label = "Long-Form (16:9 1080p" if kind == "long" else "Short (9:16 1080x1920"
    print(f"   -> [{kind}] Searching fresh Pixabay asset for '{query_keyword}'...")
    if not fetch_specific_pixabay_video(query_keyword, source):
        return False
    try:
        print(f"   -> Processing {label}, {target_duration}s)...")
        make_seamless_unit(source, vf, unit)
        finish_with_audio(unit, source, query_keyword, target_duration, output_path)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {kind} rendering error: {(e.stderr or '')[-400:]}")
        return False
    except Exception as e:
        print(f"❌ {kind} rendering error: {e}")
        return False
    finally:
        for f in (source, unit):
            if os.path.exists(f):
                os.remove(f)


def create_long_form_video(query_keyword: str, output_path: str, target_duration: int = 600) -> bool:
    return _create("long", query_keyword, output_path, target_duration, LONG_VF)


def create_short_video(query_keyword: str, output_path: str, target_duration: int = 30) -> bool:
    return _create("short", query_keyword, output_path, target_duration, SHORT_VF)
