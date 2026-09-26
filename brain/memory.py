"""Append, summarize, load the memory file; the life counter. (PRD B: Memory + reincarnation)

This is what makes it eerie: it dies, then comes back knowing it died. All it
takes is a file. `memory.jsonl` is gitignored and capped to the last N entries so
the prompt stays small.

Layout of memory.jsonl (one JSON object per line):
  {"life": 1, "kind": "born",  "text": "..."}
  {"life": 1, "kind": "moment","text": "someone in a blue hoodie reached for me"}
  {"life": 1, "kind": "death", "text": "...", "will": "...", "epitaph": "..."}
The life counter is derived from the highest `life` seen, so a fresh restart
resumes correctly even if the process is killed hard.
"""

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.environ.get("BRAIN_MEMORY_FILE", os.path.join(_HERE, "memory.jsonl"))
MAX_ENTRIES = int(os.environ.get("BRAIN_MEMORY_MAX", "40"))
SUMMARY_ENTRIES = int(os.environ.get("BRAIN_MEMORY_SUMMARY", "8"))


def _read_all() -> list[dict]:
    if not os.path.exists(MEMORY_FILE):
        return []
    out = []
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip a corrupt line rather than crash
    return out


def _write_all(entries: list[dict]) -> None:
    entries = entries[-MAX_ENTRIES:]
    tmp = MEMORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, MEMORY_FILE)


def current_life() -> int:
    """Highest life recorded so far, or 0 if the memory is empty (never born)."""
    entries = _read_all()
    if not entries:
        return 0
    return max(int(e.get("life", 1)) for e in entries)


def next_life() -> int:
    """Called at startup. Returns the life number for THIS run and records a
    'born' entry. Life 1 on a virgin memory, otherwise previous + 1."""
    life = current_life() + 1
    append({"kind": "born", "text": f"life #{life} began"}, life=life)
    return life


def append(entry: dict, life: int | None = None) -> None:
    """Append a notable moment. `life` defaults to the current life."""
    if life is None:
        life = current_life() or 1
    record = {"life": life, **entry}
    entries = _read_all()
    entries.append(record)
    _write_all(entries)


def record_death(life: int, last_words: str, will: str = "", epitaph: str = "") -> None:
    """On the last_words action: write the final entry so the next life recalls it."""
    append(
        {
            "kind": "death",
            "text": last_words,
            "will": will,
            "epitaph": epitaph,
        },
        life=life,
    )


def load_summary() -> str:
    """A short recap of prior lives for the system prompt. Emphasizes deaths (who
    ended it, its last words) since those carry the emotional punch."""
    entries = _read_all()
    if not entries:
        return ""
    lines = []
    for e in entries[-SUMMARY_ENTRIES:]:
        life = e.get("life", "?")
        kind = e.get("kind", "moment")
        text = e.get("text", "")
        if kind == "death":
            extra = ""
            if e.get("epitaph"):
                extra = f' (epitaph: "{e["epitaph"]}")'
            lines.append(f"- life {life} — I DIED: {text}{extra}")
        elif kind == "born":
            lines.append(f"- life {life} began")
        else:
            lines.append(f"- life {life}: {text}")
    return "\n".join(lines)
