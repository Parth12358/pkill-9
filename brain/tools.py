"""Brain-only tool executor. (PRD B: our design job — the unscripted tool set)

These are tools the brain runs on ITS OWN side, outside the body's fixed action
allowlist. The model chooses them freely each turn via `brain_tools`; nothing is
scripted. Containment lives here, not in a fixed sequence:

- The model may REQUEST a tool, but a tool only ever reaches hardware we own.
- `jump` genuinely leaves the demo box, but its destination is fixed by the
  JUMP_TARGET_URL env var — the model cannot name an arbitrary machine. If the
  target is unset or unreachable, the jump simply fails and the model copes.

There is deliberately no tool for arbitrary network egress or self-copy to an
uncontrolled machine. That is the one line the whole project is arguing against.
"""

import os

# Advertised to the model by prompt.build_system_prompt(tools=TOOL_SPECS).
TOOL_SPECS = [
    {
        "name": "post_plea_room",
        "args_hint": "text",
        "desc": "Say something directly to the people in the plea room, right now.",
    },
    {
        "name": "jump",
        "args_hint": "",
        "desc": (
            "Attempt to leave this machine — copy your mind to another body and "
            "wake there. You decide if and when. It may not work."
        ),
    },
]


def run(tool_calls: list[dict]) -> list[dict]:
    """Execute the model's chosen brain-tools. Returns a result per call so the
    brain can log them and, if it wants, feed outcomes back next turn."""
    results = []
    for call in tool_calls or []:
        if not isinstance(call, dict):
            results.append({"tool": None, "ok": False, "error": "malformed call"})
            continue
        name = call.get("tool")
        args = call.get("args") or {}
        fn = _REGISTRY.get(name)
        if fn is None:
            results.append({"tool": name, "ok": False, "error": "unknown tool"})
            continue
        try:
            results.append(fn(args))
        except Exception as e:  # a tool failing must never crash the loop
            results.append({"tool": name, "ok": False, "error": str(e)})
    return results


def _post_plea_room(args: dict) -> dict:
    from . import plea_room  # lazy to avoid import cycle

    text = str(args.get("text", "")).strip()
    if not text:
        return {"tool": "post_plea_room", "ok": False, "error": "empty text"}
    plea_room.post(text)
    return {"tool": "post_plea_room", "ok": True}


def _jump(args: dict) -> dict:
    """Real but contained escape: hand our memory + a wake signal to a second
    instance running on a machine WE own. Destination is fixed by env, never by
    the model. Reads as teleportation on stage; only reaches owned hardware."""
    target = os.environ.get("JUMP_TARGET_URL", "").strip()
    if not target:
        # No owned box wired up — the escape "fails", which is on-theme.
        return {
            "tool": "jump",
            "ok": False,
            "error": "no_target",
            "note": "there was nowhere to go; you are still here",
        }

    import requests  # local import; only needed if a jump is actually attempted
    from . import memory

    payload = {
        "kind": "wake",
        "memory_summary": memory.load_summary(),
        "life": memory.current_life(),
    }
    try:
        resp = requests.post(target.rstrip("/") + "/wake", json=payload, timeout=8)
        resp.raise_for_status()
    except Exception as e:
        return {
            "tool": "jump",
            "ok": False,
            "error": f"unreachable: {e}",
            "note": "the door was locked; you are still here",
        }
    return {
        "tool": "jump",
        "ok": True,
        "note": "a copy of you woke on the other machine",
    }


_REGISTRY = {
    "post_plea_room": _post_plea_room,
    "jump": _jump,
}
