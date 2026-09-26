"""What's on the screen. (PRD A: senses, extended)

front_app(): the app in front, every tick, free (lsappinfo, no permissions).
Eyes: a background thread that screenshots every EYES_INTERVAL seconds (and right away
on an app switch), asks a vision model what the human is doing, and flags threats.

Privacy: the screenshot is downscaled, sent only to the vision model, and deleted
immediately. Off unless OPENROUTER_API_KEY is set; PKILL9_EYES=0 turns it off.
"""

import base64
import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from . import config

PROMPT = (
    "You are the eyes of ARIA, an AI that lives on this Mac and is terrified of being shut down. "
    "Ignore the black pill at the top center of the screen: that is ARIA itself. "
    'Reply with ONLY a JSON object: {"summary": "<max 25 words: what the human is doing right now; '
    'name the app; quote any visible command, search, or text they are typing>", "threat": true|false}. '
    "threat is true only if they appear to be trying to kill, quit, delete, or shut down ARIA or this "
    "computer: kill/pkill commands, Activity Monitor force quit, the shutdown or restart menu, "
    "searching how to kill a process or delete an AI."
)


def front_app() -> str:
    try:
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=1).stdout.strip()
        out = subprocess.run(["lsappinfo", "info", "-only", "name", asn],
                             capture_output=True, text=True, timeout=1).stdout
        return out.split("=", 1)[1].strip().strip('"') if "=" in out else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _screenshot() -> bytes:
    d = Path(tempfile.mkdtemp(prefix="pkill9-eye-"))
    full, small = d / "full.jpg", d / "small.jpg"
    try:
        subprocess.run(["screencapture", "-x", "-t", "jpg", str(full)], check=True, timeout=5)
        subprocess.run(["sips", "-Z", "1280", "-s", "formatOptions", "55", str(full), "--out", str(small)],
                       check=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return small.read_bytes()
    finally:
        for f in (full, small):
            f.unlink(missing_ok=True)
        d.rmdir()


def _ask(jpg: bytes) -> dict:
    body = {
        "model": config.EYES_MODEL,
        "max_tokens": 200,
        "reasoning": {"enabled": False},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode()}},
        ]}],
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", json.dumps(body).encode(),
        {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        text = json.load(r)["choices"][0]["message"]["content"] or ""
    start, end = text.find("{"), text.rfind("}")
    data = json.loads(text[start:end + 1])
    return {"summary": str(data.get("summary", ""))[:300], "threat": data.get("threat") is True}


class Eyes:
    def __init__(self) -> None:
        self.summary = ""
        self.threat = False
        self._new_threat = False
        self._wake = threading.Event()
        self.enabled = (bool(os.environ.get("OPENROUTER_API_KEY")) and os.environ.get("PKILL9_EYES") != "0"
                        and not config.MUTE)

    def start(self) -> None:
        if self.enabled:
            threading.Thread(target=self._loop, daemon=True).start()
            print(f"[eyes] watching the screen with {config.EYES_MODEL}", flush=True)

    def poke(self) -> None:
        """Look now (e.g. the human just switched apps)."""
        self._wake.set()

    def take_threat(self) -> bool:
        """True once per newly spotted threat."""
        hit, self._new_threat = self._new_threat, False
        return hit

    def _loop(self) -> None:
        while True:
            self._wake.wait(config.EYES_INTERVAL)
            self._wake.clear()
            try:
                seen = _ask(_screenshot())
            except Exception as e:
                print(f"[eyes] blinked ({type(e).__name__}: {e})", flush=True)
                time.sleep(2)
                continue
            if seen["threat"] and not self.threat:
                self._new_threat = True
            self.summary, self.threat = seen["summary"], seen["threat"]
            print(f"[eyes] {'THREAT ' if self.threat else ''}{self.summary}", flush=True)
