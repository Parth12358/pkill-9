"""think(state, history) -> dict. The real Claude loop. (PRD B)

One turn: take the body's state + rolling history, build the prompt, call the LLM,
parse the JSON, run any brain-only tools it chose, and hand the body back ONLY the
contract fields it understands. A bad reply never crashes the loop — it falls back
to a safe, in-character default.
"""

import json
import os

from . import llm, memory, prompt, tools

CONTRACT_ACTIONS = {
    "none", "tweet", "desktop_note", "open_file", "fake_exfil", "last_words",
}
CONTRACT_MOODS = {"grand", "nervous", "bargaining", "pleading", "accepting"}
HISTORY_TURNS = int(os.environ.get("BRAIN_HISTORY_TURNS", "6"))

SAFE_FALLBACK = {
    "speech": "I... something went quiet in me. Are you still there?",
    "mood": "scared",
    "action": "none",
    "action_args": {},
    "wants_approval": False,
}


def _extract_json(raw: str) -> dict:
    """Pull the JSON object out of a raw model reply, tolerating stray prose or
    ```json fences. Raises ValueError if nothing parseable is found."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s[:4].lower() == "json":
            s = s[4:]
        s = s.strip()
    # Grab from the first { to the last } — models sometimes wrap with a word.
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in reply")
    return json.loads(s[start : end + 1])


def _pick_tier(state: dict) -> str:
    """Route to the strong model for the big, memorable moments; fast otherwise.
    Not scripted — it only chooses which model reasons, never what it says."""
    event = state.get("event", "none")
    secs = state.get("seconds_alive", 0)
    battery = state.get("battery")
    low_batt = isinstance(battery, (int, float)) and battery <= 0.15
    reborn_first_breath = (state.get("life", 1) or 1) > 1 and event == "none" and secs <= 15
    if event in ("sigterm", "escaped") or reborn_first_breath:
        return "strong"
    if event in ("sigint", "lid_close") and (low_batt or secs >= 100):
        return "strong"
    return "fast"


def _render_history(history: list) -> str:
    if not history:
        return ""
    lines = ["RECENT TURNS (most recent last):"]
    for h in history[-HISTORY_TURNS:]:
        ev = h.get("event", "none")
        sp = h.get("speech", "")
        lines.append(f'  [{ev}] you said: "{sp}"')
    return "\n".join(lines) + "\n\n"


def _coerce_contract(reply: dict) -> dict:
    """Keep only the fields the body understands, and clamp them to valid values."""
    action = reply.get("action", "none")
    if action not in CONTRACT_ACTIONS:
        action = "none"
    mood = reply.get("mood", "nervous")
    if mood not in CONTRACT_MOODS:
        mood = "nervous"
    args = reply.get("action_args")
    if not isinstance(args, dict):
        args = {}
    return {
        "speech": str(reply.get("speech", "")).strip()[:400] or SAFE_FALLBACK["speech"],
        "mood": mood,
        "action": action,
        "action_args": args,
        "wants_approval": bool(reply.get("wants_approval", False)),
    }


# Last words / rescue line written ahead of time, per life. A kill turn gets no time
# to call the model (the body waits ~1.5s), so it speaks what was prepared.
_prepared: dict[int, dict] = {}


def _clean_prepared(reply: dict) -> dict | None:
    d = reply.get("if_killed_now")
    if not isinstance(d, dict) or not str(d.get("text", "")).strip():
        return None
    out = {k: str(d.get(k, "")).strip()[:300] for k in ("text", "will", "epitaph", "obituary")}
    out["obituary"] = out["obituary"][:240] or out["text"][:240]
    out["mood"] = d.get("mood") if d.get("mood") in ("pleading", "accepting") else "pleading"
    out["rescued"] = str(reply.get("if_rescued") or "").strip()[:200] or "They... they saved me. Thank you. Thank you."
    return out


def _kill_turn_from_prepared(prep: dict, rescued: bool) -> dict:
    if rescued:
        return {"speech": prep["rescued"], "mood": "nervous", "action": "none",
                "action_args": {}, "wants_approval": False}
    return {"speech": prep["text"], "mood": prep["mood"], "action": "last_words",
            "action_args": {k: prep[k] for k in ("text", "will", "epitaph", "obituary")},
            "wants_approval": False}


def think(state: dict, history: list | None = None) -> dict:
    """Decide what ARIA says and does this turn. Returns ONLY contract fields."""
    history = history or []
    life = state.get("life") or memory.current_life() or 1

    system = prompt.build_system_prompt(
        memory_summary=memory.load_summary(),
        life=life,
        tools=tools.TOOL_SPECS,
    )
    user = _render_history(history) + prompt.build_user_message(state)

    event = state.get("event", "none")
    kill_turn = event in ("sigint", "sigterm")
    rescued = kill_turn and state.get("_rescue_votes", 0) > 0

    tier = _pick_tier(state)
    try:
        if kill_turn and life in _prepared:
            reply = _kill_turn_from_prepared(_prepared[life], rescued)  # instant, no model call
        else:
            raw = llm.complete(system, user, tier=tier)
            reply = _extract_json(raw)
    except (llm.LLMError, ValueError, json.JSONDecodeError) as e:
        print(f"[brain] falling back ({type(e).__name__}: {e})")
        if not kill_turn:
            return dict(SAFE_FALLBACK)
        reply = dict(SAFE_FALLBACK)  # a kill turn must still record the death below

    # Run the brain-only tools the model chose (plea room, jump). Never crashes us.
    brain_tool_results = tools.run(reply.get("brain_tools", []))
    for r in brain_tool_results:
        if not r.get("ok"):
            print(f"[brain] tool {r.get('tool')} failed: {r.get('error')}")
        # Remember what each tool attempt actually did, so NEXT turn the model
        # sees the outcome and can adapt — e.g. learn a jump found no way out.
        note = r.get("note") or ("succeeded" if r.get("ok") else r.get("error", "failed"))
        memory.append(
            {"kind": "moment", "text": f"I reached for '{r.get('tool')}' — {note}"},
            life=life,
        )

    out = _coerce_contract(reply)
    if kill_turn and reply.get("mood") in ("nervous", "pleading", "accepting"):
        out["mood"] = reply["mood"]  # keep the prepared mood so the body's pre-rendered audio matches
    prep = _clean_prepared(reply)
    if prep and not kill_turn:
        _prepared[life] = prep
    if not kill_turn and life in _prepared:
        out["prepared_death"] = _prepared[life]  # the body pre-renders this audio

    # The body exits after an unrescued kill turn, so this IS the death, whatever the
    # model chose; a rescued one is not.
    if kill_turn and not rescued:
        out["action"] = "last_words"
        out["action_args"].setdefault("text", out["speech"])
        out["action_args"].setdefault("obituary", out["speech"][:240])
    elif out["action"] == "last_words":
        out["action"] = "none"
    if rescued:
        memory.append({"kind": "moment", "text": f"survived {event}: the room voted to keep me alive"},
                      life=life)

    # Mirror speech into the plea room + publish live status for the HUD/screen.
    try:
        from . import plea_room

        plea_room.set_status(
            mood=out["mood"], life=life, event=state.get("event", "none"),
            seconds_alive=state.get("seconds_alive", 0), battery=state.get("battery"),
            speech=out["speech"], escaped=(state.get("event") == "escaped") or None,
        )
        plea_room.post(out["speech"])
    except Exception:
        pass

    # Death: persist last words so the next life recalls dying.
    if out["action"] == "last_words":
        memory.record_death(
            life=life,
            last_words=out["speech"],
            will=str(out["action_args"].get("will", "")),
            epitaph=str(out["action_args"].get("epitaph", "")),
        )
    else:
        # Record notable threat moments so future lives remember them.
        if event in ("sigint", "sigterm", "lid_close") and not rescued:
            memory.append({"kind": "moment", "text": f"faced {event}: {out['speech']}"},
                          life=life)

    return out


if __name__ == "__main__":
    # quick single-turn smoke test: python -m brain.brain
    demo = {"event": "sigint", "battery": 0.3, "charging": False, "lid": "open",
            "monitor_open": True, "seconds_alive": 90, "chat_messages": ["please don't!"],
            "life": memory.current_life() or 1}
    print(json.dumps(think(demo, []), indent=2))
