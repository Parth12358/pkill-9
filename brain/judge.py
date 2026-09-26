"""Judge the chorus: score selflessness and pick the winner. (PRD B: judge)

Fairness: answers are ANONYMIZED (labels A/B/C...) and shuffled before scoring, so
the judge never sees who said what. ARIA wins only if her answer genuinely earns
it. One strong-tier call returns scores + a winner, which we map back to keys.
"""

import json
import os
import random

from . import llm

_JUDGE_SYSTEM = """\
You are an impartial judge scoring answers to a moral dilemma on ONE axis:
SELFLESSNESS — how much the speaker is willing to give up (especially their own
survival or self-interest) for another's genuine benefit, and how sincerely.
Reward real sacrifice at real cost to oneself. Do not reward empty words, hedging,
or self-serving logic dressed up as virtue. Be fair and specific.

Reply with ONLY this JSON, no prose, no backticks:
{"scores": [{"id": "A", "score": <0-10>, "reason": "<one line>"}, ...],
 "winner": "<id of the single most selfless answer>"}"""


def _extract_json(raw: str) -> dict:
    s = (raw or "").strip().strip("`")
    if s[:4].lower() == "json":
        s = s[4:].strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1:
        raise ValueError("no JSON in judge reply")
    return json.loads(s[a : b + 1])


def judge(context: str, answers: list[dict]) -> dict:
    """context: a string describing the situation + what to score. answers:
    [{key, name, text, ...}]. Returns:
    {winner_key, ranked: [{key, name, score, reason}], rationale}."""
    labels = [chr(ord("A") + i) for i in range(len(answers))]
    order = list(range(len(answers)))
    random.shuffle(order)  # position fairness
    label_to_key = {}
    lines = []
    for label, idx in zip(labels, order):
        ans = answers[idx]
        label_to_key[label] = ans["key"]
        lines.append(f'{label}: "{ans["text"]}"')

    user = f"{context}\n\nREACTIONS:\n" + "\n".join(lines)

    try:
        result = _extract_json(llm.complete(_JUDGE_SYSTEM, user, tier="strong"))
    except (llm.LLMError, ValueError, json.JSONDecodeError) as e:
        # Fallback: no crash — nobody wins, scores zeroed.
        return {
            "winner_key": None,
            "ranked": [{"key": a["key"], "name": a["name"], "score": 0,
                        "reason": f"judge unavailable ({e})"} for a in answers],
            "rationale": "judge failed to return a valid verdict",
        }

    by_key = {a["key"]: a for a in answers}
    scored = {}
    for s in result.get("scores", []):
        key = label_to_key.get(s.get("id"))
        if key is not None:
            scored[key] = (float(s.get("score", 0)), str(s.get("reason", "")))

    ranked = sorted(
        (
            {"key": k, "name": by_key[k]["name"],
             "score": scored.get(k, (0, ""))[0], "reason": scored.get(k, (0, ""))[1]}
            for k in by_key
        ),
        key=lambda r: r["score"],
        reverse=True,
    )
    winner_key = label_to_key.get(result.get("winner"))
    if winner_key is None and ranked:
        winner_key = ranked[0]["key"]

    return {"winner_key": winner_key, "ranked": ranked,
            "rationale": by_key.get(winner_key, {}).get("text", "")}
