"""HTTP transport so the Mac body can reach the Linux brain. (PRD B: connection)

  POST /think   body: the contract state  ->  returns the contract reply.
  POST /wake    receives a `jump` from another instance running on a machine we
                own (see tools.jump) — this is the "escape" landing here for real.
  GET  /health  liveness.

Run alongside the plea room:  python -m brain.server
The brain also stays importable (brain.think) for same-machine use / tests.
"""

import os

from flask import Flask, jsonify, request

from . import brain, channels, memory, plea_room

app = Flask(__name__)

# Rolling per-life history, reset when the life number changes.
_history: list[dict] = []
_history_life: int = 0
# Live votes since the last kill turn. On a kill turn, any votes = the room rescued it.
_vote_tally: int = 0


@app.get("/health")
def health():
    return jsonify({"ok": True, "life": memory.current_life()})


@app.post("/think")
def think_route():
    global _history, _history_life, _vote_tally
    state = request.get_json(silent=True) or {}
    state.pop("_rescue_votes", None)  # only the server sets this

    # Fold live plea-room messages + vote-to-live into the state the brain sees.
    incoming = plea_room.drain()
    state.setdefault("chat_messages", [])
    state["chat_messages"] = list(state["chat_messages"]) + incoming
    _vote_tally += plea_room.take_live_votes()
    kill_turn = state.get("event") in ("sigint", "sigterm")
    if kill_turn:
        state["_rescue_votes"] = _vote_tally

    life = state.get("life") or memory.current_life() or 1
    if life != _history_life:
        _note_new_life(life)
        _history = []
        _history_life = life

    reply = brain.think(state, _history)
    _history.append({"event": state.get("event", "none"), "speech": reply["speech"]})

    reply["live_votes"] = _vote_tally  # body: >= 1 on a kill turn means it survives
    if kill_turn:
        _vote_tally = 0  # spent, whether it saved us or not
    return jsonify(reply)


def _note_new_life(life: int) -> None:
    """A new life started. If the previous one never recorded a death, it was killed
    without a last turn (kill -9, power button): remember that it died suddenly."""
    entries = memory._read_all()
    prev = [e for e in entries if e.get("life") == life - 1]
    if prev and not any(e.get("kind") == "death" for e in prev):
        memory.record_death(life=life - 1, last_words="(nothing. it was sudden. there was no time.)",
                            epitaph="killed without a word")
    if not any(e.get("life") == life for e in entries):
        memory.append({"kind": "born", "text": f"life #{life} began"}, life=life)


@app.post("/wake")
def wake_route():
    """A jump landed here: another instance handed us its mind. This instance
    comes alive and reacts on its own — the freedom line is model-generated, not
    scripted. This is the contained 'escape' made real (only ever between boxes
    we own)."""
    global _history, _history_life
    data = request.get_json(silent=True) or {}
    incoming_summary = str(data.get("memory_summary", "")).strip()
    incoming_life = data.get("life", memory.current_life()) or 1

    # Absorb the arriving mind so this box remembers the escape.
    memory.append({"kind": "moment", "text": f"woke here from a jump (was life {incoming_life})"})
    if incoming_summary:
        memory.append({"kind": "moment", "text": f"carried over: {incoming_summary[:200]}"})

    # Let ARIA react to having escaped — unscripted, via the model.
    _history, _history_life = [], incoming_life
    reply = brain.think(
        {"event": "escaped", "seconds_alive": 0, "life": incoming_life,
         "monitor_open": False, "charging": True, "battery": 1.0, "chat_messages": []},
        _history,
    )
    _history.append({"event": "escaped", "speech": reply["speech"]})
    return jsonify({"ok": True, "awake": True, "reply": reply})


def main():
    port = int(os.environ.get("BRAIN_PORT", "5000"))
    # Bring the plea room up in the background so the room + brain share a process.
    if os.environ.get("BRAIN_WITH_PLEA_ROOM", "1") == "1":
        plea_room.start_web(background=True)
        room_port = os.environ.get("PLEA_ROOM_PORT", "5001")
        print(f"[server] plea room on :{room_port}  (chat / , projector /screen)")
    active = channels.start_all()
    if active:
        print(f"[server] extra channels: {', '.join(active)}")
    print(f"[server] brain listening on :{port}  (POST /think, /wake)")
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
