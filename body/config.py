"""Body settings, all overridable by env vars."""

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

BRAIN_URL = os.environ.get("BRAIN_URL", "")          # empty = use the local canned brain
BRAIN_TIMEOUT = float(os.environ.get("BRAIN_TIMEOUT", "4"))
VOICE = os.environ.get("PKILL9_VOICE", "Daniel")
MUTE = os.environ.get("PKILL9_MUTE") == "1"           # print instead of `say`
TICK = 0.5                                             # seconds between sense polls
IDLE_TURN = float(os.environ.get("PKILL9_IDLE_TURN", "20"))  # brain turn when nothing happens
DEATH_WINDOW = float(os.environ.get("PKILL9_DEATH_WINDOW", "8"))  # hard cap after a kill signal
LOW_BATTERY = 0.2
APPROVAL_TTL = 90                                      # pending approvals expire


def scratch() -> Path:
    """The ONLY folder actions may touch."""
    p = Path(os.environ.get("PKILL9_SCRATCH", REPO / "scratch")).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p
