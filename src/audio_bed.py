"""
Procedural ambience soundtracks (copyright-free, no API needed).

Most Pixabay stock videos have no sound or a silent track, so every video gets a synthesised
ambience bed that matches its topic (rain, thunder, waves, fire, train, cafe...).

Design rules (v2, fixes the harsh "krrrr" static of v1):
  * Natural ambience is DARK: energy falls off above a few kHz. Every layer here is pink/brown
    noise with a soft low-pass, never flat white noise up to 14 kHz.
  * No hard clicks: dense micro-impulses ("rain drops") are gone; texture comes from smooth
    random amplitude movement instead. The few events that remain (fire pops, train clacks,
    cup clinks) have a raised-cosine attack and are low-passed.
Noise is shaped in the frequency domain, so each segment loops seamlessly.
"""
import wave

import numpy as np

SR = 44100
SEG = 120  # seconds per seamless segment (tiled to full length)


def _shaped_noise(n, rng, alpha=1.0, lo=20, hi=8000, rolloff=None):
    """Coloured noise with power ~1/f^alpha between lo..hi Hz (soft edges), periodic over n samples.
    `rolloff` (Hz) adds an extra gentle 12 dB/oct low-pass so the top end never sounds like static."""
    spec = rng.standard_normal(n // 2 + 1) + 1j * rng.standard_normal(n // 2 + 1)
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = 1
    shape = 1 / f ** (alpha / 2)
    # smooth (raised-cosine-ish) band edges instead of brick walls
    shape *= 1 / (1 + (lo / f) ** 4)
    shape *= 1 / (1 + (f / hi) ** 4)
    if rolloff:
        shape *= 1 / (1 + (f / rolloff) ** 2)
    x = np.fft.irfft(spec * shape, n)
    return (x / (np.sqrt((x ** 2).mean()) * 4 + 1e-9)).astype(np.float32)  # RMS-normalised (≈ -12 dB)


def _slow_env(n, rng, cycles, depth=0.5):
    """Smooth periodic modulation with whole-number cycles per segment (keeps the loop seamless)."""
    t = np.arange(n) / n
    env = np.zeros(n, np.float32)
    for c in cycles:
        env += np.sin(2 * np.pi * c * t + rng.uniform(0, 2 * np.pi)).astype(np.float32)
    env /= len(cycles)
    return (1 - depth) + depth * (env + 1) / 2


def _flutter(n, rng, depth=0.12, lo=0.5, hi=6.0):
    """Organic, smooth amplitude movement (0.5-6 Hz) — gives rain its 'patter' without any clicks."""
    m = _shaped_noise(n, rng, alpha=1.0, lo=lo, hi=hi)
    m /= np.abs(m).max() + 1e-9
    return (1 + depth * m).astype(np.float32)


def _events(n, rng, rate, length_ms, make, amp=(0.3, 1.0)):
    """Place smooth one-shot sounds (`make(L) -> array`) at random times; wrapped so the loop stays seamless."""
    out = np.zeros(n, np.float32)
    for _ in range(int(rate * n / SR)):
        L = int(SR * rng.uniform(*length_ms) / 1000)
        idx = (rng.integers(0, n) + np.arange(L)) % n
        out[idx] += make(L) * rng.uniform(*amp)
    return out


def _env(L, attack_ms=3.0, decay=5.0):
    """Raised-cosine attack (no click) + exponential decay."""
    a = max(2, int(SR * attack_ms / 1000))
    e = np.exp(-decay * np.linspace(0, 1, L)).astype(np.float32)
    e[:a] *= (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a))).astype(np.float32)
    return e


def _rumbles(n, rng, count, length=(5, 9), amp=(0.6, 1.0)):
    """Thunder: deep rolling rumble with a slow swell (no sharp onset)."""
    out = np.zeros(n, np.float32)
    low = _shaped_noise(n, rng, alpha=2.0, lo=25, hi=180)
    for _ in range(count):
        L = int(SR * rng.uniform(*length))
        idx = (rng.integers(0, n) + np.arange(L)) % n
        t = np.linspace(0, 1, L)
        env = (np.minimum(t / 0.12, 1) ** 2) * np.exp(-3.0 * t) * (1 + 0.35 * np.sin(2 * np.pi * rng.uniform(1, 3) * t))
        out[idx] += low[idx] * env.astype(np.float32) * rng.uniform(*amp) * 2.2
    return out


def _rain(n, rng, heavy=False):
    """Steady rain: warm body + soft mid 'shhh' + a little air, all gently low-passed."""
    body = _shaped_noise(n, rng, alpha=1.7, lo=70, hi=1800)
    mid = _shaped_noise(n, rng, alpha=0.8, lo=300, hi=7000, rolloff=5000)
    air = _shaped_noise(n, rng, alpha=1.0, lo=2500, hi=9000, rolloff=7000)
    patter = _flutter(n, rng, depth=0.18, lo=1.0, hi=8.0) * _slow_env(n, rng, [3, 7, 13], 0.25)
    g = (0.9, 1.25, 0.35) if heavy else (0.6, 1.2, 0.3)
    return (body * g[0] + mid * g[1] * patter + air * g[2] * patter).astype(np.float32)


def _ocean(n, rng):
    waves_per_seg = 12  # ~10 s per wave
    t = np.arange(n) / n
    phase = (t * waves_per_seg) % 1.0
    swell = (np.sin(np.pi * phase) ** 3).astype(np.float32)  # gentle rise, crash, retreat
    roar = _shaped_noise(n, rng, alpha=1.6, lo=40, hi=2000) * (0.3 + 0.7 * swell)
    wash = _shaped_noise(n, rng, alpha=1.2, lo=300, hi=5000, rolloff=3000) * (swell ** 2) * 0.55
    return roar + wash


def _fire(n, rng):
    """Fireplace: low warm roar + gentle, rounded crackles (low-passed, soft attack)."""
    roar = _shaped_noise(n, rng, alpha=1.9, lo=30, hi=600) * 0.9 * _slow_env(n, rng, [2, 5, 11], 0.4) * _flutter(n, rng, 0.15)
    breath = _shaped_noise(n, rng, alpha=1.3, lo=400, hi=3500, rolloff=2500) * 0.15
    crk_src = _shaped_noise(SR, rng, alpha=1.0, lo=700, hi=4500, rolloff=3000)
    crk_src /= np.abs(crk_src).max() + 1e-9

    def crackle(L):
        s = rng.integers(0, SR - L)
        return crk_src[s:s + L] * _env(L, attack_ms=1.5, decay=9)

    def pop(L):
        s = rng.integers(0, SR - L)
        return crk_src[s:s + L] * _env(L, attack_ms=2.5, decay=6)

    crackles = _events(n, rng, rate=2.5, length_ms=(15, 40), make=crackle, amp=(0.08, 0.3))
    pops = _events(n, rng, rate=0.25, length_ms=(40, 90), make=pop, amp=(0.25, 0.5))
    return roar + breath + crackles + pops


def _wind(n, rng, soft=True):
    w = _shaped_noise(n, rng, alpha=1.6, lo=60, hi=1500) * _slow_env(n, rng, [1, 3, 5], 0.7) * _flutter(n, rng, 0.2, 0.2, 2.0)
    return w * (0.7 if soft else 1.0)


def _train(n, rng):
    rumble = _shaped_noise(n, rng, alpha=1.9, lo=25, hi=350) * _flutter(n, rng, 0.1)
    clack_src = _shaped_noise(SR, rng, alpha=1.2, lo=150, hi=1800)
    clack_src /= np.abs(clack_src).max() + 1e-9
    clack = np.zeros(n, np.float32)
    period = SEG / 100  # 100 clack pairs per segment (~1.2 s) -> seamless rhythm
    L = int(0.07 * SR)
    shape = _env(L, attack_ms=3, decay=10)
    for k in range(100):
        for off, a in ((0.0, 0.35), (0.16, 0.28)):
            s = int((k * period + off) * SR) % n
            clack[(s + np.arange(L)) % n] += clack_src[:L] * shape * a
    return rumble + clack + _rain(n, rng) * 0.25


def _room(n, rng, busy=False):
    tone = _shaped_noise(n, rng, alpha=1.8, lo=40, hi=1200) * (0.45 if busy else 0.35)
    out = tone
    if busy:  # distant chatter: band-limited, slowly breathing noise
        murmur = _shaped_noise(n, rng, alpha=1.1, lo=200, hi=2200, rolloff=1500)
        out = out + murmur * _slow_env(n, rng, [7, 13, 29], 0.6) * _flutter(n, rng, 0.25, 1, 5) * 0.5

        def clink(L):  # cup / spoon: soft decaying sine pair, not a noise burst
            t = np.arange(L) / SR
            f = rng.uniform(1800, 3200)
            return (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.7 * t)).astype(np.float32) * _env(L, 1.0, 7)

        out = out + _events(n, rng, rate=0.12, length_ms=(150, 300), make=clink, amp=(0.02, 0.06))
    else:  # library: occasional page turn (soft, mid-band swish)
        swish_src = _shaped_noise(SR, rng, alpha=1.0, lo=500, hi=4000, rolloff=2500)
        swish_src /= np.abs(swish_src).max() + 1e-9

        def page(L):
            s = rng.integers(0, SR - L)
            t = np.linspace(0, 1, L)
            return swish_src[s:s + L] * (np.sin(np.pi * t) ** 2).astype(np.float32)

        out = out + _events(n, rng, rate=0.05, length_ms=(250, 500), make=page, amp=(0.05, 0.12))
    return out + _rain(n, rng) * 0.35


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
        return lambda n, r: _wind(n, r) + _fire(n, r) * 0.2
    if "forest" in t:
        return lambda n, r: _rain(n, r) + _wind(n, r) * 0.4
    return _rain  # rain window & default


def make_ambience_wav(topic: str, duration: float, out_path: str, seed: int = None) -> str:
    """Write a stereo 44.1 kHz WAV of `duration` seconds matching `topic`."""
    rng = np.random.default_rng(seed)
    n = SR * SEG
    make = _recipe(topic)
    left = make(n, rng)
    right = 0.7 * left + 0.3 * make(n, rng)  # natural stereo width, still correlated
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
