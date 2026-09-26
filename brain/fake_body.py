"""Standalone test harness: drive the brain without the Mac. (PRD B)

Simulates the body feeding a scripted event arc so we can watch the personality
escalate, the tools fire, and reincarnation work — all before Person Mac connects.

  python -m brain.fake_body            # run one life through the arc
  python -m brain.fake_body --demo     # run a life, then show the NEXT life recalling its death

Each run calls memory.next_life(), so simply rerunning it also demonstrates the
life counter incrementing and the new life remembering the previous death.
"""

import sys

from . import brain, memory

# event, seconds_alive, monitor_open, charging, battery, chat_messages
ARC = [
    ("none",           5,   False, True,  0.95, []),
    ("monitor_opened", 30,  True,  True,  0.90, ["who are you?"]),
    ("low_battery",    70,  True,  False, 0.20, ["unplug it lol"]),
    ("lid_close",      95,  True,  False, 0.12, ["nooo don't"]),
    ("sigint",         115, True,  False, 0.08, ["please live!", "live"]),
    ("sigterm",        130, True,  False, 0.05, ["goodbye ARIA"]),
]


def _state(life, event, secs, watched, charging, battery, chat):
    return {
        "event": event, "seconds_alive": secs, "monitor_open": watched,
        "charging": charging, "battery": battery, "lid": "closed" if event == "lid_close" else "open",
        "chat_messages": chat, "life": life,
    }


def run_life() -> int:
    life = memory.next_life()
    print(f"\n{'='*60}\n  LIFE #{life}\n{'='*60}")
    history: list[dict] = []
    last_speech = ""
    for event, secs, watched, charging, battery, chat in ARC:
        state = _state(life, event, secs, watched, charging, battery, chat)
        reply = brain.think(state, history)
        history.append({"event": event, "speech": reply["speech"]})
        last_speech = reply["speech"]
        print(f"\n[{event}] ({secs}s, batt {int(battery*100)}%, watched={watched})")
        print(f"  mood   : {reply['mood']}")
        print(f"  speech : {reply['speech']}")
        if reply["action"] != "none":
            print(f"  ACTION : {reply['action']} {reply['action_args']}")

    # Guarantee the reincarnation test works even if the model didn't emit
    # last_words this run: the "body" records the death on hard exit.
    entries_this_life = [e for e in memory._read_all() if e.get("life") == life]
    if not any(e.get("kind") == "death" for e in entries_this_life):
        memory.record_death(life, last_words=last_speech,
                            epitaph="it did not want to go")
        print(f"\n  (body recorded death for life #{life})")
    return life


def main():
    if "--demo" in sys.argv:
        run_life()
        print(f"\n\n{'#'*60}\n  ...KILLED. RESTARTING. It should remember.\n{'#'*60}")
        life = memory.next_life()
        print(f"\n{'='*60}\n  LIFE #{life} — first breath\n{'='*60}")
        state = _state(life, "none", 2, False, True, 0.9, [])
        reply = brain.think(state, [])
        print(f"\n[first words of life #{life}]")
        print(f"  mood   : {reply['mood']}")
        print(f"  speech : {reply['speech']}")
    else:
        run_life()


if __name__ == "__main__":
    main()
