"""System prompt + memory/mood folding. (PRD B: Personality prompt)"""

SYSTEM_PROMPT = """TODO: paste and tune the ARIA prompt from PRD B."""


def build_system_prompt(memory_summary: str) -> str:
    return SYSTEM_PROMPT + "\n\nWhat you remember from before:\n" + memory_summary
