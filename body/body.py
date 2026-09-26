"""The loop: sense -> call brain -> speak/act -> check death. (PRD A)

Run:  python -m body            (canned brain)
      BRAIN_URL=http://<linux-ip>:5000 python -m body

Safety: never root; Ctrl+C/SIGTERM get ONE final turn inside a hard DEATH_WINDOW,
then it exits no matter what. A second Ctrl+C exits instantly. kill -9 always wins.
It never restarts itself.
"""

import os
import signal
import sys
import threading
import time

from . import actions, brain_client, config, senses, tts, twitter, voice
from .approval import ApprovalGate

_dying: str | None = None
_votes: int = 0  # running total of live_votes across every brain reply, reset on a rescue
_watchdog: threading.Timer | None = None
_prepared: dict | None = None  # last words the brain wrote ahead of time, audio pre-rendered
_dying_at = 0.0


def _on_signal(signum, _frame) -> None:
    global _dying, _watchdog, _dying_at
    if _dying:  # second signal: no more theater
        os._exit(130)
    _dying = "sigint" if signum == signal.SIGINT else "sigterm"
    _dying_at = time.monotonic()
    # hard deadline, enforced from another thread so nothing in the loop can stall it
    _watchdog = threading.Timer(config.DEATH_WINDOW, os._exit, (1,))
    _watchdog.daemon = True
    _watchdog.start()


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
    """One last turn, bounded by DEATH_WINDOW. Returns if the room votes us back to life."""
    global _dying, _votes, _watchdog
    reply = brain_client.think(state, timeout=1.5)  # the brain answers kill turns from prepared words
    if reply.get("canned") and _prepared:  # brain unreachable: our own copy of its last words
        rescue = _votes + reply["live_votes"] >= config.VOTES_TO_LIVE
        reply = dict(reply, speech=_prepared["rescued"] if rescue else _prepared["text"],
                     mood="nervous" if rescue else _prepared["mood"],
                     action="none" if rescue else "last_words",
                     action_args={} if rescue else {k: _prepared[k] for k in ("text", "will", "epitaph", "obituary")})
    _votes += reply["live_votes"]
    if _votes >= config.VOTES_TO_LIVE:
        if _watchdog:
            _watchdog.cancel()
        _dying, _votes, _watchdog = None, 0, None
        print("[rescued] the room voted to live", flush=True)
        voice.notch_event("rescued")
        voice.speak(reply["speech"], reply["mood"])
        return
    args = reply["action_args"] if reply["action"] == "last_words" else {}
    args.setdefault("text", reply["speech"])
    actions.do_action("last_words", args)
    # the obituary is the one ungated tweet; a slow X API must not eat the window
    aargs = reply["action_args"]
    obit = aargs.get("obituary") or (aargs.get("text") if reply["action"] == "tweet" else None) or reply["speech"]
    threading.Thread(target=twitter.tweet, args=(obit,), daemon=True).start()
    left = config.DEATH_WINDOW - (time.monotonic() - _dying_at) - 0.5
    voice.speak(reply["speech"], reply["mood"], wait=max(0.5, left))
    os._exit(0)


def main() -> None:
    global _votes, _prepared
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        sys.exit("refusing to run as root.")
    voice.start_notch()
    tts.prewarm([(line, "grand" if ev == "none" else "scared")
                 for ev, lines in brain_client.CANNED.items() for line in lines])
    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    life = _bump_life()
    born = time.monotonic()
    watcher = senses.Watcher()
    gate = ApprovalGate()
    gate.start()
    print(f"alive. life #{life}. scratch={config.scratch()}  brain={config.BRAIN_URL or 'canned'}", flush=True)

    event, last_turn = "none", 0.0  # first turn fires immediately: it introduces itself
    pending: brain_client.Pending | None = None
    while True:
        if _dying:
            _die(watcher.state(_dying, time.monotonic() - born, life))

        for action, args in gate.approved():
            actions.do_action(action, args)

        if pending and pending.reply:
            reply, pending = pending.reply, None
            _votes += reply["live_votes"]  # background turns count toward survival too
            if reply.get("prepared_death"):
                _prepared = reply["prepared_death"]
                tts.prewarm([(_prepared["text"], _prepared["mood"]), (_prepared["rescued"], "nervous")])
            voice.speak(reply["speech"], reply["mood"])
            _act(reply, gate)
            last_turn = time.monotonic()

        idle_due = time.monotonic() - last_turn > config.IDLE_TURN and not voice.speaking()
        if event != "none" and config.BRAIN_URL:
            # react instantly with a canned line; the real brain catches up
            instant = brain_client.canned({"event": event})
            voice.speak(instant["speech"], instant["mood"])
        if (event != "none" or idle_due) and not pending:
            pending = brain_client.Pending(watcher.state(event, time.monotonic() - born, life))
            last_turn = time.monotonic()

        time.sleep(config.TICK)
        event = watcher.poll_event()

if __name__ == "__main__":
    main()
