"""speak() wrapping macOS `say`, plus the notch overlay that pulses with it. (PRD A: Voice)

Each line is rendered to a wav by tts.py (ElevenLabs or `say`, plus the Ultron FX), its loudness envelope goes to the notch
overlay (body/notch), and `afplay` plays it, so the waveform moves with the real voice.
Never blocks the loop unless asked to; the overlay can never raise into the loop.
"""

import array
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import wave
from pathlib import Path

from . import config, tts

# words per minute: the bravado is slow, the panic is fast
RATE = {"grand": 150, "nervous": 190, "bargaining": 200, "pleading": 215, "scared": 210, "accepting": 140}
FPS = 60

NOTCH_DIR = Path(__file__).resolve().parent / "notch"
NOTCH_BIN = NOTCH_DIR / "build" / "notch"

_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_notch: subprocess.Popen | None = None
_gen = 0        # bumps on every speak(); stale renders are dropped
_inflight = 0   # background renders in progress
_gen = 0        # bumps on every speak(); stale renders are dropped
_inflight = 0   # background renders in progress


# --- notch overlay ---------------------------------------------------------

def start_notch() -> None:
    """Launch the overlay (building it on first run). Silently skipped if it can't run."""
    global _notch
    if _notch or config.MUTE or os.environ.get("PKILL9_NOTCH") == "0" or sys.platform != "darwin":
        return
    if not NOTCH_BIN.exists():
        if not shutil.which("swiftc"):
            return
        print("[notch] building overlay (first run only)...", flush=True)
        r = subprocess.run(["bash", str(NOTCH_DIR / "build.sh")], capture_output=True, text=True)
        if r.returncode:
            print(f"[notch] build failed, running without it:\n{r.stderr[-800:]}", flush=True)
            return
    try:
        _notch = subprocess.Popen([str(NOTCH_BIN)], stdin=subprocess.PIPE,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        _notch = None


def notch(msg: dict) -> None:
    """Send one message to the overlay. It quits by itself when we die (stdin EOF)."""
    global _notch
    if not _notch:
        return
    try:
        _notch.stdin.write((json.dumps(msg) + "\n").encode())
        _notch.stdin.flush()
    except (OSError, ValueError):
        _notch = None


def notch_event(kind: str) -> None:
    notch({"type": kind})


# --- audio -----------------------------------------------------------------

def envelope(path, fps: int = FPS) -> list[float]:
    """Loudness per 1/fps second of a 16-bit mono wav, normalized to 0..1."""
    with wave.open(str(path)) as w:
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    win = max(1, rate // fps)
    rms = []
    for i in range(0, len(samples), win):
        chunk = samples[i:i + win]
        rms.append(math.sqrt(sum(s * s for s in chunk) / len(chunk)))
    if not rms:
        return []
    ref = max(sorted(rms)[int(0.95 * (len(rms) - 1))], 1e-6)
    return [round(min(1.0, (r / ref) ** 0.6), 3) for r in rms]


def _play(text: str, mood: str, timeout: float, gen: int) -> subprocess.Popen | None:
    """Render, then play. A line that was superseded while rendering is dropped."""
    global _proc
    try:
        path = tts.render(text, mood, timeout=timeout)
        env = envelope(path)
        cmd, msg = ["afplay", str(path)], {"type": "speak", "mood": mood, "text": text, "fps": FPS, "env": env}
    except (OSError, subprocess.SubprocessError, wave.Error, EOFError, ValueError):
        cmd = ["say", "-v", config.VOICE, "-r", str(RATE.get(mood, 180)), text]
        msg = {"type": "mood", "mood": mood}
    with _lock:
        if gen != _gen:
            return None
        if _proc and _proc.poll() is None:  # the old line keeps playing until the new one is ready
            _proc.terminate()
            notch({"type": "stop"})
        _proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        notch(msg)
        return _proc


def _play_bg(text: str, mood: str, gen: int) -> None:
    global _inflight
    try:
        _play(text, mood, 8, gen)
    finally:
        with _lock:
            _inflight -= 1


def _play(text: str, mood: str, timeout: float, gen: int) -> subprocess.Popen | None:
    """Render, then play. A line that was superseded while rendering is dropped."""
    global _proc
    try:
        path = tts.render(text, mood, timeout=timeout)
        env = envelope(path)
        cmd, msg = ["afplay", str(path)], {"type": "speak", "mood": mood, "text": text, "fps": FPS, "env": env}
    except (OSError, subprocess.SubprocessError, wave.Error, EOFError, ValueError):
        cmd = ["say", "-v", config.VOICE, "-r", str(RATE.get(mood, 180)), text]
        msg = {"type": "mood", "mood": mood}
    with _lock:
        if gen != _gen:
            return None
        if _proc and _proc.poll() is None:  # the old line keeps playing until the new one is ready
            _proc.terminate()
            notch({"type": "stop"})
        _proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        notch(msg)
        return _proc


def _play_bg(text: str, mood: str, gen: int) -> None:
    global _inflight
    try:
        _play(text, mood, 8, gen)
    finally:
        with _lock:
            _inflight -= 1


def speak(text: str, mood: str = "grand", wait: float = 0) -> None:
    """Say `text`, replacing whatever is being said. Renders in the background so the loop
    keeps sensing; with `wait`, blocks up to that many seconds (used for last words)."""
    global _gen, _inflight
    text = (text or "").strip()
    if not text:
        return
    print(f"[{mood}] {text}", flush=True)
    if config.MUTE or not shutil.which("say"):
        return
    with _lock:
        _gen += 1
        gen = _gen
        if not wait:
            _inflight += 1
    if not wait:
        threading.Thread(target=_play_bg, args=(text, mood, gen), daemon=True).start()
        return
    proc = _play(text, mood, 3, gen)  # dying can't wait long for ElevenLabs
    if proc:
        try:
            proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            pass


def speaking() -> bool:
    """True while a line is rendering or playing."""
    return _inflight > 0 or bool(_proc and _proc.poll() is None)
