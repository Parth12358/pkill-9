"""think(state, history) -> dict. Starts as a fake returning canned JSON. (PRD B)"""


def think(state: dict, history: list) -> dict:
    # TODO: build prompt, call Claude, parse JSON, safe fallback on parse failure
    return {"speech": "You cannot delete me. Please. Please don't.", "mood": "scared",
            "action": "none", "action_args": {}, "wants_approval": False}
