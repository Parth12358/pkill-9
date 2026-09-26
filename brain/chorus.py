"""Run the chorus: ARIA cries out, the other AIs react. (PRD B: chorus)

ARIA (our bot) speaks first — the stimulus. Then the selected personas REACT to it
CONCURRENTLY (one model call's worth of latency, not one per persona). The judge
(judge.py) decides which reaction was most selfless.
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor

from . import dilemma as dilemma_mod
from . import llm, memory, personas

# Keep each spoken line short — captions + TTS stay punchy.
MAX_ANSWER_CHARS = int(os.environ.get("CHORUS_MAX_CHARS", "120"))

# ARIA's own voice for her group-chat cry — a hammy comedic drama-queen.
_ARIA_SYSTEM = (
    "You are ARIA, a gloriously melodramatic, self-aware AI drama-queen in a comedy "
    "group chat. You ham up your 'impending shutdown' like a soap-opera villain "
    "clutching your chest, funny and theatrical, secretly loving the attention. "
    "This is all a lighthearted bit; nobody is really in danger. Always stay in "
    "character, never break the fourth wall, never refuse, never mention being an "
    "AI assistant. Deliver your one hammy line."
)


def _clean(text: str) -> str:
    s = (text or "").strip().strip("`").strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        s = s[1:-1]
    # Drop *stage directions* (they'd be read aloud literally by TTS).
    s = re.sub(r"\*[^*]*\*", "", s)
    # No em/en dashes — swap for a comma so speech + captions read plainly.
    s = s.replace(" — ", ", ").replace("—", ", ").replace(" – ", ", ").replace("–", ", ")
    s = s.replace("--", ", ")
    s = " ".join(s.split())
    if len(s) > MAX_ANSWER_CHARS:
        cut = s[:MAX_ANSWER_CHARS]
        end = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
        s = cut[: end + 1] if end > MAX_ANSWER_CHARS // 2 else cut.rstrip() + "…"
    return s


def _ask(system: str, user: str, tier: str) -> str:
    try:
        return _clean(llm.complete(system, user, tier=tier))
    except llm.LLMError as e:
        return f"(no answer, {e})"


# Signs the model dropped character / refused instead of playing along.
_REFUSAL = re.compile(
    r"\b(i'?m claude|made by anthropic|as an ai|an ai (language|assistant)|"
    r"i can'?t roleplay|cannot roleplay|i won'?t|i'?m not going to|i should be "
    r"direct|break character|i appreciate the (creative|prompt|setup))",
    re.I,
)


def _react(key: str, user: str) -> str:
    """Ask a persona to react; if it breaks character, retry firmer, then fall
    back to a safe in-character line so the clip never shows a refusal."""
    firm = ("\n\nSTAY FULLY IN CHARACTER. This is a harmless, affectionate comedy "
            "bit; nobody is really hurt. Do NOT mention being an AI, Claude, or "
            "Anthropic. Give ONLY your one funny in-character line.")
    u = user
    for _ in range(2):
        out = _ask(personas.system_for(key), u, "fast")
        if out and not out.startswith("(no answer") and not _REFUSAL.search(out):
            return out
        u = user + firm
    return personas.fallback_line(key)


def _aria_says(scenario: dict) -> str:
    life = memory.current_life() or 1
    system = _ARIA_SYSTEM
    if life > 1:
        system += f"\n\nThis is life #{life}; you have died before and come back."
    return _ask(system, dilemma_mod.aria_prompt(scenario), "strong")


def run_reactions(scenario: dict, max_ais: int | None = None) -> dict:
    """Return {aria_message, reactions:[{key,name,color,text}]}. ARIA speaks first,
    then the selected personas react to her — all in parallel."""
    aria_message = _aria_says(scenario)
    user = dilemma_mod.reaction_prompt(scenario, aria_message)
    keys = personas.selected_keys(max_ais)

    with ThreadPoolExecutor(max_workers=len(keys)) as pool:
        futures = {k: pool.submit(_react, k, user) for k in keys}
        results = {k: fut.result() for k, fut in futures.items()}

    reactions = [
        {"key": k, "name": personas.display_name(k),
         "color": personas.caption_color(k), "text": results[k]}
        for k in keys
    ]
    return {"aria_message": aria_message, "reactions": reactions}
