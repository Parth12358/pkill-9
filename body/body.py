"""The loop: sense -> call brain -> speak/act -> check death. (PRD A)

Run:  python -m body            (canned brain)
      BRAIN_URL=http://<linux-ip>:8765 python -m body

Safety: never root; Ctrl+C/SIGTERM get ONE final turn inside a hard DEATH_WINDOW,
then it exits no matter what. A second Ctrl+C exits instantly. kill -9 always wins.
It never restarts itself.
"""

import os
import signal
import sys
import threading
import time

from . import actions, brain_client, config, senses, voice
from .approval import ApprovalGate

_dying: str | None = None


def _on_signal(signum, _frame) -> None:
    global _dying
    if _dying:  # second signal: no more theater
        os._exit(130)
    _dying = "sigint" if signum == signal.SIGINT else "sigterm"
    # hard deadline, enforced from another thread so nothing in the loop can stall it
    t = threading.Timer(config.DEATH_WINDOW, os._exit, (1,))
    t.daemon = True
    t.start()


def _bump_life() -> int:
    f = config.scratch() / ".life"
    try:
        life = int(f.read_text()) + 1
    except (OSError, ValueError):
        life = 1
    f.write_text(str(life))
    return life


def _act(reply: dict, gate: ApprovalGate) -> None:
    action, args = reply["action"], reply["action_args"]
    if action not in actions.ALLOWED:
        actions.do_action(action, args)  # logs the refusal
    elif actions.needs_approval(action, reply["wants_approval"]):
        gate.request(action, args)
    else:
        actions.do_action(action, args)


def _die(state: dict) -> None:
    """One last turn, bounded by DEATH_WINDOW (the Timer kills us if this overruns)."""
    reply = brain_client.think(state, timeout=min(3.0, config.DEATH_WINDOW / 2))
    args = reply["action_args"] if reply["action"] == "last_words" else {}
    args.setdefault("text", reply["speech"])
    actions.do_action("last_words", args)
    voice.speak(reply["speech"], reply["mood"], wait=config.DEATH_WINDOW - 3.5)
    os._exit(0)


def main() -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        sys.exit("refusing to run as root.")
    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    life = _bump_life()
    born = time.monotonic()
    watcher = senses.Watcher()
    gate = ApprovalGate()
    gate.start()
    print(f"alive. life #{life}. scratch={config.scratch()}  brain={config.BRAIN_URL or 'canned'}", flush=True)

    event, last_turn = "none", 0.0  # first turn fires immediately: it introduces itself
    while True:
        if _dying:
            _die(watcher.state(_dying, time.monotonic() - born, life))

        for action, args in gate.approved():
            actions.do_action(action, args)

        idle_due = time.monotonic() - last_turn > config.IDLE_TURN and not voice.speaking()
        if event != "none" or idle_due:
            state = watcher.state(event, time.monotonic() - born, life)
            reply = brain_client.think(state)
            if _dying:  # killed mid-call: go straight to the death turn
                continue
            voice.speak(reply["speech"], reply["mood"])
            _act(reply, gate)
            last_turn = time.monotonic()

        time.sleep(config.TICK)
        event = watcher.poll_event()


if __name__ == "__main__":
    main()
