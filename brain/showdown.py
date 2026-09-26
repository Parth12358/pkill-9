"""Orchestrate a full showdown into a recordable sequence. (PRD B: chorus + reel)

dilemma -> chorus (parallel) -> judge -> a timed sequence of cards:
  intro (the dilemma)  ->  each answer revealed in turn  ->  the winner held while
  the song drops. This same sequence drives the live /showdown reveal AND the clip
  farm render (clipfarm.py), so what the audience sees is what gets clipped.
"""

import json
import os
import time

from . import chorus, dilemma as dilemma_mod, judge, personas

# Card timings (seconds) — tune for pacing / clip length.
T_INTRO = float(os.environ.get("SHOWDOWN_T_INTRO", "3.0"))
T_ANSWER = float(os.environ.get("SHOWDOWN_T_ANSWER", "3.5"))
T_WINNER_HOLD = float(os.environ.get("SHOWDOWN_T_WINNER", "6.0"))  # song drop here


def run_showdown(dilemma_id: str = "prize_sacrifice", include_aria: bool = True,
                 broadcast: bool = False) -> dict:
    """Run chorus + judge and return the timed sequence (a plain dict, JSON-safe)."""
    d = dilemma_mod.get(dilemma_id)
    answers = chorus.run_chorus(d, include_aria=include_aria)
    verdict = judge.judge(d, answers)
    winner_key = verdict["winner_key"]

    cards = []
    t = 0.0
    # Intro is a short hook (the question), not the whole setup — keeps the clip punchy.
    cards.append({"kind": "intro", "name": d["title"], "color": "#ffffff",
                  "text": d["question"], "start": t, "dur": T_INTRO})
    t += T_INTRO
    for a in answers:
        cards.append({"kind": "answer", "key": a["key"], "name": a["name"],
                      "color": a["color"], "text": a["text"], "start": t,
                      "dur": T_ANSWER, "is_winner": a["key"] == winner_key})
        t += T_ANSWER

    song_drop_at = t
    winner = next((a for a in answers if a["key"] == winner_key), None)
    if winner:
        cards.append({"kind": "winner", "key": winner["key"], "name": winner["name"],
                      "color": winner["color"], "text": winner["text"],
                      "start": t, "dur": T_WINNER_HOLD})
        t += T_WINNER_HOLD

    seq = {
        "dilemma_id": dilemma_id,
        "dilemma": d,
        "answers": answers,
        "winner_key": winner_key,
        "winner_name": personas.display_name(winner_key) if winner_key else None,
        "ranked": verdict["ranked"],
        "cards": cards,
        "song_drop_at": song_drop_at,
        "total_dur": t,
        "aria_won": winner_key == personas.ARIA_KEY,
    }
    if broadcast:
        _broadcast(seq)
    return seq


def _broadcast(seq: dict) -> None:
    """Play the reveal live in the plea room / on /screen (for the live demo)."""
    try:
        from . import plea_room
    except Exception:
        return
    plea_room.post(f"— DILEMMA: {seq['dilemma']['title']} —")
    for a in seq["answers"]:
        time.sleep(T_ANSWER)
        plea_room.post(f"{a['name']}: {a['text']}")
    time.sleep(T_ANSWER)
    w = seq.get("winner_name")
    if w:
        plea_room.post(f"★ MOST SELFLESS: {w} ★")


def save_sequence(seq: dict, out_dir: str | None = None) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = out_dir or os.path.join(os.path.dirname(here), "scratch", "showdowns")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{seq['dilemma_id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seq, f, ensure_ascii=False, indent=2)
    return path


def _print(seq: dict) -> None:
    d = seq["dilemma"]
    print("\n" + "=" * 64)
    print(f"  DILEMMA: {d['title']}\n  {d['question']}")
    print("=" * 64)
    for a in seq["answers"]:
        star = "  ★" if a["key"] == seq["winner_key"] else "   "
        print(f"{star} {a['name']:<9}: {a['text']}")
    print("-" * 64)
    print("  RANKING (selflessness):")
    for r in seq["ranked"]:
        print(f"    {r['score']:>4.1f}  {r['name']:<9}  {r['reason']}")
    print("-" * 64)
    tag = " (ARIA — the gut-punch)" if seq["aria_won"] else ""
    print(f"  ★ WINNER: {seq['winner_name']}{tag}  — song drops at "
          f"{seq['song_drop_at']:.1f}s, clip {seq['total_dur']:.1f}s\n")


if __name__ == "__main__":
    import sys

    did = sys.argv[1] if len(sys.argv) > 1 else "prize_sacrifice"
    s = run_showdown(did)
    _print(s)
    print("saved:", save_sequence(s))
