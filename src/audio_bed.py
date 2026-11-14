"""
Procedural ambience soundtracks (copyright-free, no API needed).

Most Pixabay stock videos have no sound or a silent track, so every video gets a synthesised
ambience bed that matches its topic (rain, thunder, waves, fire crackle, train, cafe...).
Noise is shaped in the frequency domain, so each segment loops seamlessly.
"""
import wave

import numpy as np

SR = 44100
SEG = 120  # seconds per seamless segment (tiled to full length)


def _shaped_noise(n, rng, alpha=1.0, lo=20, hi=16000):
    """Coloured noise: 1/f^alpha spectrum, band-limited lo..hi Hz, periodic over n samples."""
    spec = rng.standard_normal(n // 2 + 1) + 1j * rng.standard_normal(n // 2 + 1)
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = 1
    shape = 1 / f ** (alpha / 2)
    shape[(f < lo) | (f > hi)] = 0
    # soft band edges
    shape *= np.clip((f - lo) / (lo * 0.5 + 1), 0, 1) * np.clip((hi - f) / (hi * 0.2), 0, 1)
    x = np.fft.irfft(spec * shape, n)
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def _slow_env(n, rng, cycles, depth=0.5):
    """Smooth periodic modulation with whole-number cycles per segment (keeps the loop seamless)."""
    t = np.arange(n) / n
    env = np.zeros(n, np.float32)
    for c in cycles:
        env += np.sin(2 * np.pi * c * t + rng.uniform(0, 2 * np.pi)).astype(np.float32)
    env /= len(cycles)
    return (1 - depth) + depth * (env + 1) / 2


def _impulses(n, rng, rate, dur_ms=(2, 15), lo=1500, hi=12000, amp=(0.2, 1.0), decay=6.0):
    """Random short bursts (rain drops, fire crackles, clinks). Wrapped so the segment loops."""
    out = np.zeros(n, np.float32)
    count = int(rate * n / SR)
    burst_src = _shaped_noise(SR, rng, alpha=0.0, lo=lo, hi=hi)
    for _ in range(count):
        L = int(SR * rng.uniform(*dur_ms) / 1000)
        start = rng.integers(0, n)
        idx = (start + np.arange(L)) % n
        b = burst_src[rng.integers(0, SR - L):][:L] * np.exp(-decay * np.linspace(0, 1, L)) * rng.uniform(*amp)
        out[idx] += b
    return out


def _rumbles(n, rng, count, length=(4, 8), amp=(0.5, 1.0)):
    """Thunder: low-frequency bursts with fast attack and long tail."""
    out = np.zeros(n, np.float32)
    low = _shaped_noise(n, rng, alpha=2.0, lo=25, hi=220)
    for _ in range(count):
        L = int(SR * rng.uniform(*length))
        start = rng.integers(0, n)
        idx = (start + np.arange(L)) % n
        t = np.linspace(0, 1, L)
        env = np.minimum(t / 0.05, 1) * np.exp(-3.5 * t) * (1 + 0.4 * np.sin(2 * np.pi * rng.uniform(1, 3) * t))
        out[idx] += low[idx] * env.astype(np.float32) * rng.uniform(*amp) * 3
    return out


def _rain(n, rng, heavy=False):
    hiss = _shaped_noise(n, rng, alpha=0.6, lo=300, hi=14000) * _slow_env(n, rng, [3, 7], 0.25)
    body = _shaped_noise(n, rng, alpha=1.4, lo=60, hi=1200) * 0.6
    drops = _impulses(n, rng, rate=60 if heavy else 35, dur_ms=(1, 6), lo=2000, hi=10000, amp=(0.05, 0.35), decay=8)
    return hiss * (1.0 if heavy else 0.7) + body * (0.9 if heavy else 0.5) + drops


def _ocean(n, rng):
    waves_per_seg = 12  # ~10 s per wave
    t = np.arange(n) / n
    phase = (t * waves_per_seg) % 1.0
    swell = (np.sin(np.pi * phase) ** 3).astype(np.float32)  # gentle rise, crash, retreat
    roar = _shaped_noise(n, rng, alpha=1.2, lo=50, hi=2500) * (0.25 + 0.75 * swell)
    foam = _shaped_noise(n, rng, alpha=0.4, lo=1500, hi=12000) * (swell ** 2) * 0.5
    return roar + foam


def _fire(n, rng):
    base = _shaped_noise(n, rng, alpha=1.8, lo=30, hi=500) * 0.6 * _slow_env(n, rng, [2, 5, 11], 0.4)
    hiss = _shaped_noise(n, rng, alpha=0.5, lo=2000, hi=9000) * 0.08
    crackle = _impulses(n, rng, rate=6, dur_ms=(1, 8), lo=1200, hi=9000, amp=(0.2, 0.9), decay=10)
    pops = _impulses(n, rng, rate=0.4, dur_ms=(8, 25), lo=400, hi=5000, amp=(0.8, 1.4), decay=7)
    return base + hiss + crackle + pops


def _wind(n, rng, soft=True):
    w = _shaped_noise(n, rng, alpha=1.3, lo=80, hi=2000) * _slow_env(n, rng, [1, 3, 5], 0.7)
    return w * (0.6 if soft else 1.0)


def _train(n, rng):
    rumble = _shaped_noise(n, rng, alpha=1.8, lo=25, hi=400)
    clack = np.zeros(n, np.float32)
    period = SEG / 100  # 100 clack pairs per segment (~1.2 s) -> seamless rhythm
    click_src = _shaped_noise(SR, rng, alpha=0.3, lo=300, hi=4000)
    for k in range(100):
        for off in (0.0, 0.16):
            s = int((k * period + off) * SR) % n
            L = int(0.05 * SR)
            idx = (s + np.arange(L)) % n
            clack[idx] += click_src[:L] * np.exp(-12 * np.linspace(0, 1, L)) * 0.6
    return rumble * 0.8 + clack + _rain(n, rng) * 0.15


def _room(n, rng, busy=False):
    tone = _shaped_noise(n, rng, alpha=1.0, lo=80, hi=4000) * (0.35 if busy else 0.2)
    murmur = _shaped_noise(n, rng, alpha=0.8, lo=250, hi=2500) * _slow_env(n, rng, [7, 13, 29], 0.6) * (0.45 if busy else 0)
    clinks = _impulses(n, rng, rate=0.5 if busy else 0.05, dur_ms=(30, 120), lo=2500, hi=6000, amp=(0.1, 0.35), decay=6)
    pages = _impulses(n, rng, rate=0 if busy else 0.08, dur_ms=(150, 400), lo=1500, hi=8000, amp=(0.05, 0.15), decay=3)
    return tone + murmur + clinks + pages + _rain(n, rng) * 0.25


def _recipe(topic: str):
    t = topic.lower()
    if "thunder" in t or "storm" in t:
        return lambda n, r: _rain(n, r, heavy=True) + _rumbles(n, r, count=5)
    if "ocean" in t or "wave" in t or "sea" in t or "beach" in t:
        return _ocean
    if "fire" in t or "campfire" in t:
        return lambda n, r: _fire(n, r) + (_wind(n, r) * 0.25 if "camp" in t else 0)
    if "train" in t:
        return _train
    if "cafe" in t or "coffee" in t:
        return lambda n, r: _room(n, r, busy=True)
    if "library" in t:
        return lambda n, r: _room(n, r, busy=False)
    if "snow" in t or "winter" in t:
        return lambda n, r: _wind(n, r) + _fire(n, r) * 0.15
    if "forest" in t:
        return lambda n, r: _rain(n, r) + _wind(n, r) * 0.4
    return _rain  # rain window & default


def make_ambience_wav(topic: str, duration: float, out_path: str, seed: int = None) -> str:
    """Write a stereo 44.1 kHz WAV of `duration` seconds matching `topic`."""
    rng = np.random.default_rng(seed)
    n = SR * SEG
    make = _recipe(topic)
    left = make(n, rng)
    right = 0.75 * left + 0.25 * make(n, rng)  # slight stereo width, still correlated
    seg = np.stack([left, right], axis=1)
    seg /= np.abs(seg).max() + 1e-9
    seg *= 0.7

    total = int(duration * SR)
    reps = int(np.ceil(total / n))
    audio = np.tile(seg, (reps, 1))[:total]
    fade = int(SR * 1.5)
    ramp = np.linspace(0, 1, fade, dtype=np.float32)[:, None]
    audio[:fade] *= ramp
    audio[-fade:] *= ramp[::-1]

    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return out_path
