"""Body settings, all overridable by env vars."""

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    """Read KEY=VALUE lines from the repo's .env (gitignored). Real env vars win."""
    try:
        lines = (REPO / ".env").read_text().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.split(" #", 1)[0].strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

BRAIN_URL = os.environ.get("BRAIN_URL", "")          # empty = use the local canned brain
BRAIN_TIMEOUT = float(os.environ.get("BRAIN_TIMEOUT", "30"))  # runs in the background
VOICE = os.environ.get("PKILL9_VOICE", "Daniel")
MUTE = os.environ.get("PKILL9_MUTE") == "1"           # print instead of `say`
TICK = 0.5                                             # seconds between sense polls
IDLE_TURN = float(os.environ.get("PKILL9_IDLE_TURN", "20"))  # brain turn when nothing happens
DEATH_WINDOW = float(os.environ.get("PKILL9_DEATH_WINDOW", "12"))  # hard cap after a kill signal (last words are ~6s)
VOTES_TO_LIVE = int(os.environ.get("PKILL9_VOTES_TO_LIVE", "1"))  # plea-room votes needed to survive a kill
LOW_BATTERY = 0.2
EYES_MODEL = os.environ.get("PKILL9_EYES_MODEL", "google/gemini-3.1-flash-lite")  # via OpenRouter
EYES_INTERVAL = float(os.environ.get("PKILL9_EYES_INTERVAL", "15"))  # seconds between screenshots
APPROVAL_TTL = 90                                      # pending approvals expire


def scratch() -> Path:
    """The ONLY folder actions may touch."""
    p = Path(os.environ.get("PKILL9_SCRATCH", REPO / "scratch")).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p
