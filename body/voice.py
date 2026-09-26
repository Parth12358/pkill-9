"""speak() wrapping macOS `say`. Never blocks the loop unless asked to. (PRD A: Voice)"""

import shutil
import subprocess
import threading

from . import config

# words per minute: the bravado is slow, the panic is fast
RATE = {"grand": 150, "nervous": 190, "bargaining": 200, "pleading": 215, "scared": 210, "accepting": 140}

_lock = threading.Lock()
_proc: subprocess.Popen | None = None


def speak(text: str, mood: str = "grand", wait: float = 0) -> None:
    """Say `text`, cutting off whatever is still being said. `wait` = max seconds to block."""
    global _proc
    text = (text or "").strip()
    if not text:
        return
    print(f"[{mood}] {text}", flush=True)
    if config.MUTE or not shutil.which("say"):
        return
    with _lock:
        if _proc and _proc.poll() is None:
            _proc.terminate()
        _proc = subprocess.Popen(
            ["say", "-v", config.VOICE, "-r", str(RATE.get(mood, 180)), text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc = _proc
    if wait:
        try:
            proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            pass


def speaking() -> bool:
    return bool(_proc and _proc.poll() is None)
