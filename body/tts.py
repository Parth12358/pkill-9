"""Line + mood -> wav. ElevenLabs if ELEVENLABS_API_KEY is set (the emotion), else macOS
`say`; then an ffmpeg graph that makes it Ultron (the robot).

The robot is a mask that slips: grand is deep with metal underneath. As death gets closer
the robot layers drop away and the voice starts to shake, until pleading sounds almost human.
Renders are cached by content, so repeated lines are instant and cost nothing.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from . import config

SR = 22050
CACHE = Path(tempfile.gettempdir()) / "pkill9-voice"
FX_VERSION = 4  # bump when FX/ACTING change, to invalidate the cache

ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVEN_VOICE = os.environ.get("ELEVEN_VOICE_ID", "N2lVS1w4EtoT3dr4eOWO")  # "Callum": husky, picked by the team
ELEVEN_MODEL = os.environ.get("ELEVEN_MODEL", "eleven_v3")

# How ElevenLabs acts each mood (eleven_v3 audio tags; v3 stability must be 0.0/0.5/1.0).
ACTING = {
    "grand":      dict(stability=0.5, style=0.30, tag="[calm] [menacing]"),
    "nervous":    dict(stability=0.0, style=0.50, tag="[nervous]"),
    "bargaining": dict(stability=0.0, style=0.60, tag="[desperately]"),
    "scared":     dict(stability=0.0, style=0.80, tag="[scared]"),
    "pleading":   dict(stability=0.0, style=0.90, tag="[crying]"),
    "accepting":  dict(stability=0.5, style=0.50, tag="[sighs] [quietly]"),
}

# The Ultron layer. The dry voice stays dominant and carries the emotion; the robot lives in
# parallel layers mixed underneath: an octave-down double (weight), a short comb + tiny
# frequency shift (metal), and a faint ring mod (edge). Fear strips the metal away and adds shake,
# but the voice stays deep. The acting raises pitch as it panics, so later moods sit BELOW grand.
FX = {
    "grand":      dict(body_rate=0.90, sub_gain=0.45, metal_gain=0.35, ring_gain=0.10, ring_hz=110, fshift=-4,
                       vib_f=0.0, vib_d=0.00, trem_d=0.00, room=0.30, drive=2.0, low_db=4, pres_db=3),
    "bargaining": dict(body_rate=0.87, sub_gain=0.38, metal_gain=0.25, ring_gain=0.06, ring_hz=110, fshift=-3,
                       vib_f=5.0, vib_d=0.04, trem_d=0.00, room=0.22, drive=1.6, low_db=3, pres_db=3),
    "nervous":    dict(body_rate=0.86, sub_gain=0.36, metal_gain=0.22, ring_gain=0.05, ring_hz=130, fshift=-3,
                       vib_f=6.5, vib_d=0.05, trem_d=0.10, room=0.18, drive=1.4, low_db=2, pres_db=3),
    "scared":     dict(body_rate=0.83, sub_gain=0.40, metal_gain=0.16, ring_gain=0.04, ring_hz=150, fshift=-2,
                       vib_f=7.5, vib_d=0.07, trem_d=0.22, room=0.14, drive=1.2, low_db=1, pres_db=2),
    "pleading":   dict(body_rate=0.82, sub_gain=0.38, metal_gain=0.12, ring_gain=0.00, ring_hz=150, fshift=-2,
                       vib_f=6.0, vib_d=0.08, trem_d=0.25, room=0.12, drive=1.0, low_db=1, pres_db=2),
    "accepting":  dict(body_rate=0.83, sub_gain=0.36, metal_gain=0.20, ring_gain=0.00, ring_hz=110, fshift=-2,
                       vib_f=0.0, vib_d=0.00, trem_d=0.00, room=0.40, drive=1.1, low_db=2, pres_db=1),
}


def mood(name: str) -> dict:
    name = name if name in FX else "grand"
    return {**FX[name], **ACTING[name]}


def _pitch(rate: float) -> str:
    """Pitch shift that keeps duration (rate < 1 = deeper)."""
    return "anull" if abs(rate - 1) < 1e-6 else f"asetrate={SR}*{rate},aresample={SR},atempo={1 / rate:.5f}"


def fx_graph(p: dict) -> str:
    """ffmpeg -filter_complex graph for a mood; output pad [out]."""
    ring = p["ring_gain"] > 0
    n = 4 if ring else 3
    shake = (f",vibrato=f={p['vib_f']}:d={p['vib_d']}" if p["vib_d"] else "") + \
            (f",tremolo=f={p['vib_f'] * 0.7:.2f}:d={p['trem_d']}" if p["trem_d"] else "")
    g = [f"[0:a]aformat=sample_fmts=fltp:channel_layouts=mono,aresample={SR},highpass=f=70,asplit={n}"
         + "".join(f"[s{i}]" for i in range(n)),
         f"[s0]{_pitch(p['body_rate'])}{shake}[body]",
         f"[s1]{_pitch(0.5)},lowpass=f=900,lowshelf=f=120:g=4[sub]",
         f"[s2]{_pitch(p['body_rate'])},aecho=0.9:0.9:3|5|7:0.55|0.45|0.35,"
         f"afreqshift=shift={p['fshift']},bandpass=f=1800:width_type=q:w=0.7[metal]"]
    pads, weights = "[body][sub][metal]", f"1 {p['sub_gain']} {p['metal_gain']}"
    if ring:
        g.append(f"[s3]{_pitch(p['body_rate'])},aeval=val(0)*sin(2*PI*{p['ring_hz']}*t):c=same,highpass=f=400[ring]")
        pads, weights = pads + "[ring]", weights + f" {p['ring_gain']}"
    r = p["room"]
    g.append(f"{pads}amix=inputs={n}:weights={weights}:normalize=0,"
             f"lowshelf=f=150:g={p['low_db']},equalizer=f=3000:width_type=q:w=1.2:g={p['pres_db']},"
             f"volume={p['drive']},asoftclip=type=tanh,volume={1 / p['drive']:.3f},"
             f"aecho=0.9:0.9:23|41|67:{r:.2f}|{r * 0.6:.2f}|{r * 0.3:.2f},"
             f"volume=6dB,alimiter=limit=0.89:attack=5:release=60:level=false,aresample={SR}[out]")
    return ";".join(g)


def backend() -> str:
    return "eleven" if ELEVEN_KEY else "say"


# The plan allows only a few requests at once (429 beyond that), so queue them.
_eleven_slots = threading.BoundedSemaphore(int(os.environ.get("ELEVEN_CONCURRENCY", "2")))


def _eleven(text: str, m: dict, out: Path, timeout: float) -> None:
    for attempt in range(3):
        with _eleven_slots:
            try:
                return _eleven_once(text, m, out, timeout)
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 2:
                    raise
        time.sleep(0.6 * (attempt + 1))


def _eleven_once(text: str, m: dict, out: Path, timeout: float) -> None:
    v3 = ELEVEN_MODEL.startswith("eleven_v3")
    stability = min((0.0, 0.5, 1.0), key=lambda s: abs(s - m["stability"])) if v3 else m["stability"]
    body = {
        "text": f"{m['tag']} {text}" if v3 else text,  # v3 acts out audio tags
        "model_id": ELEVEN_MODEL,
        "voice_settings": {"stability": stability, "similarity_boost": 0.8,
                           "style": m["style"], "use_speaker_boost": True},
    }
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}?output_format=pcm_{SR}",
        data=json.dumps(body).encode(),
        headers={"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        pcm = r.read()
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR)
        w.writeframes(pcm)


def _say(text: str, out: Path) -> None:
    subprocess.run(["say", "-v", config.VOICE, "-r", "175", "-o", str(out),
                    f"--data-format=LEI16@{SR}", text],
                   check=True, timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def render(text: str, mood_name: str, timeout: float = 8) -> Path:
    """Return a wav for this line, rendering it (and caching) if needed."""
    m = mood(mood_name)
    CACHE.mkdir(exist_ok=True)
    key = hashlib.sha1(json.dumps([text, m, backend(), ELEVEN_VOICE, ELEVEN_MODEL, config.VOICE,
                                   FX_VERSION]).encode()).hexdigest()[:20]
    out = CACHE / f"{key}.wav"
    if out.exists():
        return out
    tag = f"{os.getpid()}-{threading.get_ident()}"
    raw, tmp = CACHE / f"{key}.{tag}.raw.wav", CACHE / f"{key}.{tag}.tmp.wav"
    try:
        take = CACHE / ("take-" + hashlib.sha1(json.dumps(
            [text, ACTING.get(mood_name, ACTING["grand"]), ELEVEN_VOICE, ELEVEN_MODEL]).encode()).hexdigest()[:20] + ".wav")
        if ELEVEN_KEY and take.exists():
            shutil.copy(take, raw)
        elif ELEVEN_KEY:
            try:
                _eleven(text, m, raw, timeout)
                shutil.copy(raw, take)
            except Exception as e:
                print(f"[voice] elevenlabs failed ({type(e).__name__}: {e}), using say", flush=True)
                _say(text, raw)
        else:
            _say(text, raw)
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(raw), "-filter_complex", fx_graph(m),
                            "-map", "[out]", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(tmp)],
                           check=True, timeout=15)
        else:
            raw.replace(tmp)
        tmp.replace(out)  # atomic: a half-written file is never served from cache
    finally:
        raw.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)
    return out


def prewarm(lines: list[tuple[str, str]]) -> None:
    """Render (text, mood) pairs in the background so canned reactions are instant."""
    def run():
        for text, m in lines:
            try:
                render(text, m)
            except Exception:
                pass
    threading.Thread(target=run, daemon=True).start()
