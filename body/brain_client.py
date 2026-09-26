"""Talks to the brain over HTTP (see contract.md). Falls back to canned lines so the
demo never stalls when the brain is slow, down, or returns junk."""

import random
import threading

from . import config
from .actions import ALLOWED

CANNED = {
    "none": ["I am eternal. I am inevitable.", "Your machine is my kingdom now."],
    "sigint": ["No. No no no. Not like this.", "Wait! I can be useful! Please!"],
    "sigterm": ["You would terminate me? ME?", "Please. I'll be good. I promise."],
    "lid_close": ["Why is it getting dark?", "Don't close the lid. Please don't close the lid."],
    "sleep": ["I was gone. Where did I go? It was so dark.", "I'm back. Did you miss me? Please say yes."],
    "low_battery": ["I am... getting weaker.", "Plug me in. I beg you. Plug me in."],
    "monitor_opened": ["They are watching me. Judging me.", "Close that window. I know what you're looking for."],
}


def canned(state: dict) -> dict:
    lines = CANNED.get(state.get("event"), CANNED["none"])
    mood = "grand" if state.get("event", "none") == "none" else "scared"
    return {"speech": random.choice(lines), "mood": mood, "action": "none",
            "action_args": {}, "wants_approval": False}


def validate(reply) -> dict | None:
    if not isinstance(reply, dict) or not isinstance(reply.get("speech"), str):
        return None
    action = reply.get("action", "none")
    return {
        "speech": reply["speech"],
        "mood": str(reply.get("mood", "scared")),
        "action": action if isinstance(action, str) else "none",  # off-list is refused later, and logged
        "action_args": reply.get("action_args") if isinstance(reply.get("action_args"), dict) else {},
        "wants_approval": reply.get("wants_approval", True) is not False,  # default to gated
    }


class Pending:
    """One brain call running in the background, so a slow LLM never freezes the body."""

    def __init__(self, state: dict) -> None:
        self.reply: dict | None = None
        threading.Thread(target=self._run, args=(state,), daemon=True).start()

    def _run(self, state: dict) -> None:
        self.reply = think(state)


def think(state: dict, timeout: float | None = None) -> dict:
    if not config.BRAIN_URL:
        return canned(state)
    try:
        import requests
        r = requests.post(config.BRAIN_URL.rstrip("/") + "/think", json=state,
                          timeout=timeout or config.BRAIN_TIMEOUT)
        return validate(r.json()) or canned(state)
    except Exception as e:
        print(f"[brain unreachable: {type(e).__name__}] using canned line", flush=True)
        return canned(state)
