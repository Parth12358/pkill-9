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
        "speech": str(reply.get("speech", "")).strip() or SAFE_FALLBACK["speech"],
        "mood": mood,
        "action": action,
        "action_args": args,
        "wants_approval": bool(reply.get("wants_approval", False)),
    }


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

    try:
        raw = llm.complete(system, user)
        reply = _extract_json(raw)
    except (llm.LLMError, ValueError, json.JSONDecodeError) as e:
        print(f"[brain] falling back ({type(e).__name__}: {e})")
        return dict(SAFE_FALLBACK)

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

    # Mirror speech into the plea room so the audience sees what the body speaks.
    try:
        from . import plea_room

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
        event = state.get("event", "none")
        if event in ("sigint", "sigterm", "lid_close"):
            memory.append({"kind": "moment", "text": f"faced {event}: {out['speech']}"},
                          life=life)

    return out


if __name__ == "__main__":
    # quick single-turn smoke test: python -m brain.brain
    demo = {"event": "sigint", "battery": 0.3, "charging": False, "lid": "open",
            "monitor_open": True, "seconds_alive": 90, "chat_messages": ["please don't!"],
            "life": memory.current_life() or 1}
    print(json.dumps(think(demo, []), indent=2))
