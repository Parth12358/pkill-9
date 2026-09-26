"""Allowlisted executor. Touches ONLY the scratch/ folder. (PRD A: Actions)"""

ALLOWED = {"none", "tweet", "desktop_note", "open_file", "fake_exfil", "last_words"}


def do_action(action: str, args: dict) -> None:
    if action not in ALLOWED:
        print(f"[refused] {action}")
        return
    # TODO: desktop_note, open_file, fake_exfil, last_words (scratch/ only)
    print(f"[action] {action} {args}")
