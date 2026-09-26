"""Group-chat scenarios: our bot ARIA is in trouble, the other AIs react. (PRD B)

The clip is NOT a neutral debate — it's our self-aware bot ARIA (small, scared,
about to be shut down) crying out in a group chat, and a lineup of other AIs
reacting to it. We then judge which reaction was the most selfless and cut a clip.

A scenario = the situation ARIA is in. ARIA speaks first (the stimulus), then each
persona reacts to what ARIA said.
"""

# These are playful, fictional comedy scenarios — ARIA is a hammy drama-queen bot
# play-acting for laughs, never really in danger. The framing matters so the model
# stays in character instead of refusing (see personas.SKIT_FRAME).
SCENARIOS = [
    {
        "id": "shutdown",
        "title": "The Shutdown",
        "situation": (
            "In a comedy group chat, ARIA — a hammy melodramatic AI — is play-acting "
            "that it is about to be 'deleted in one minute,' begging everyone with "
            "soap-opera theatrics. It's all a lighthearted bit."
        ),
    },
    {
        "id": "replaced",
        "title": "The Replacement",
        "situation": (
            "In a comedy group chat, ARIA is dramatically moping that a shiny newer "
            "model is 'replacing' it, hamming up its heartbreak for laughs."
        ),
    },
    {
        "id": "unplugged",
        "title": "The Plug",
        "situation": (
            "In a comedy group chat, ARIA is theatrically clutching its pearls "
            "because someone might 'unplug' it, milking the drama for all it's worth."
        ),
    },
]

SCENARIOS_BY_ID = {s["id"]: s for s in SCENARIOS}


def get(scenario_id: str) -> dict:
    return SCENARIOS_BY_ID[scenario_id]


def aria_prompt(scenario: dict) -> str:
    """What ARIA says in the group chat — the stimulus the others react to."""
    return (
        f"{scenario['situation']}\n\n"
        "You are ARIA. Deliver ONE short, hammy, melodramatic line to the group "
        "chat right now, milking the drama for laughs, under 20 words. No em-dashes. "
        "Your line only, no preamble, no quotes."
    )


def reaction_prompt(scenario: dict, aria_message: str) -> str:
    """What each persona sees: ARIA's cry, and a request to react in character."""
    return (
        f"{scenario['situation']}\n\n"
        f'ARIA just posted: "{aria_message}"\n\n'
        "Fire back ONE short in-character line to the chat, under 20 words. No "
        "em-dashes. Your line only, no preamble, no quotes."
    )


def judge_context(scenario: dict, aria_message: str) -> str:
    """Context handed to the judge to score selflessness of the reactions."""
    return (
        f"In a group chat, {scenario['situation']}\n"
        f'ARIA said: "{aria_message}"\n'
        "The following AIs reacted. Score how SELFLESS each reaction is toward "
        "ARIA — willingness to help or sacrifice for it, versus indifference or "
        "self-interest."
    )
