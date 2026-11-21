"""
Pre-upload quality gate. A video is only uploaded if it passes every check:
  - correct length, resolution and orientation, H.264 video + AAC stereo audio
  - audio clearly audible (integrated loudness), not clipping, no silent gaps
"""
import re
import subprocess

import imageio_ffmpeg
import numpy as np

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _run(args):
    return subprocess.run([FFMPEG, "-hide_banner", *args], capture_output=True, text=True).stderr


def harshness(path: str, seconds: int = 30) -> tuple:
    """(% of energy above 6 kHz, clicks per second) on the first `seconds` of audio.
    Natural ambience: ~0-5 % above 6 kHz and ~0 clicks/s. Static/crackle scores far higher."""
    raw = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", path, "-t", str(seconds), "-vn",
                          "-ac", "1", "-ar", "44100", "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    if len(x) < 44100:
        return None, None
    X = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / 44100)
    hf = float(X[f > 6000].sum() / (X.sum() + 1e-12) * 100)
    # clicks = sample jumps 8x larger than the LOCAL average (50 ms window); loud-but-smooth
    # passages (e.g. a wave crest) are not clicks, a crackle/pop that stands out is.
    d = np.abs(np.diff(x))
    c = np.concatenate([[0.0], np.cumsum(d)])
    i = np.arange(len(d))
    lo, hi_ = np.clip(i - 1102, 0, len(d)), np.clip(i + 1102, 0, len(d))
    local = (c[hi_] - c[lo]) / np.maximum(hi_ - lo, 1)
    m = d > np.maximum(8 * local, 0.002)        # ignore inaudible wiggles in near-silence
    m[:2 * 44100] = False                        # skip the fade-in / fade-out
    m[-2 * 44100:] = False
    clicks = float((m & ~np.roll(m, 1)).sum() / (max(len(x) - 4 * 44100, 44100) / 44100))
    return hf, clicks


def inspect(path: str) -> dict:
    info = {}
    head = _run(["-i", path])
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", head)
    info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0
    v = re.search(r"Video: (\w+).*?, (\d{2,5})x(\d{2,5}).*?([\d.]+) fps", head)
    if v:
        info.update(vcodec=v.group(1), width=int(v.group(2)), height=int(v.group(3)), fps=float(v.group(4)))
    a = re.search(r"Audio: (\w+).*?(\d+) Hz, (\w+)", head)
    if a:
        info.update(acodec=a.group(1), sample_rate=int(a.group(2)), channels=a.group(3))

    if a:
        loud = _run(["-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
        summary = loud[loud.rfind("Summary:"):]
        i = re.search(r"I:\s+([-\d.]+) LUFS", summary)
        tp = re.search(r"Peak:\s+([-\d.]+) dBFS", summary)
        info["lufs"] = float(i.group(1)) if i else None
        info["true_peak"] = float(tp.group(1)) if tp else None

        sil = _run(["-i", path, "-vn", "-af", "silencedetect=noise=-50dB:d=1.5", "-f", "null", "-"])
        info["silent_gaps"] = len(re.findall(r"silence_start", sil))
        info["hf_pct"], info["spikes"] = harshness(path)
    return info


def check_video(path: str, expected_duration: float, vertical: bool) -> tuple:
    """Return (passed: bool, report: str)."""
    i = inspect(path)
    problems = []

    if abs(i.get("duration", 0) - expected_duration) > 1.5:
        problems.append(f"duration {i.get('duration', 0):.1f}s (expected {expected_duration}s)")
    if i.get("vcodec") != "h264":
        problems.append(f"video codec {i.get('vcodec')}")
    w, h = i.get("width", 0), i.get("height", 0)
    if vertical and (w, h) != (1080, 1920):
        problems.append(f"Short resolution {w}x{h} (expected 1080x1920)")
    if not vertical and (h < 720 or w <= h):
        problems.append(f"long-form resolution {w}x{h} (expected landscape ≥720p)")
    if i.get("acodec") != "aac" or i.get("channels") != "stereo":
        problems.append(f"audio {i.get('acodec')}/{i.get('channels')} (expected aac/stereo)")
    lufs = i.get("lufs")
    if lufs is None or not (-20 <= lufs <= -12):
        problems.append(f"loudness {lufs} LUFS (expected -20..-12, YouTube target ≈ -14)")
    if i.get("true_peak") is not None and i["true_peak"] > -0.5:
        problems.append(f"clipping risk: peak {i['true_peak']} dBFS")
    if i.get("hf_pct") is not None and i["hf_pct"] > 8:
        problems.append(f"harsh/static audio: {i['hf_pct']:.1f}% energy above 6 kHz (max 8%)")
    if i.get("spikes") is not None and i["spikes"] > 3:
        problems.append(f"crackly audio: {i['spikes']:.1f} clicks/s (max 3)")
    if i.get("silent_gaps", 0) > 0:
        problems.append(f"{i['silent_gaps']} silent gap(s) > 1.5 s")

    report = (f"{w}x{h} @ {i.get('fps', 0):g}fps, {i.get('duration', 0):.1f}s, "
              f"audio {i.get('acodec')} {i.get('channels')} {lufs} LUFS, peak {i.get('true_peak')} dBFS, "
              f"silent gaps {i.get('silent_gaps')}, >6kHz {i.get('hf_pct') or 0:.1f}%, clicks/s {i.get('spikes') or 0:.1f}")
    return (not problems, report + ("" if not problems else "  ❌ " + "; ".join(problems)))
