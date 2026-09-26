"""Allowlisted executor. Touches ONLY the scratch folder. (PRD A: Actions)

The brain proposes; the body is the adult in the room. Anything off-list is refused.
Only .txt files are ever written or opened, so the brain can't smuggle in an
executable (.command/.app/.sh) and then `open` it.
"""

import base64
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from . import config, twitter

ALLOWED = {"none", "tweet", "desktop_note", "open_file", "fake_exfil", "last_words"}
ALWAYS_GATED = {"tweet"}          # anything that leaves the machine
NEVER_GATED = {"none", "last_words"}  # dying can't wait for a keypress; it's local + inert
MAX_BYTES = 20_000


class Refused(Exception):
    pass


def safe_path(name: str) -> Path:
    """Map any brain-supplied name to a .txt file directly inside scratch/."""
    base = os.path.basename(str(name or "")).strip()
    base = re.sub(r"[^A-Za-z0-9_ -]", "_", os.path.splitext(base)[0]).strip(" _-")[:60] or "note"
    scratch = config.scratch()
    p = (scratch / f"{base}.txt").resolve()
    if p.parent != scratch:  # symlink games
        raise Refused(f"{name!r} escapes scratch")
    return p


def _write(name: str, text: str) -> Path:
    p = safe_path(name)
    if p.is_symlink():
        raise Refused(f"{p} is a symlink")
    p.write_text(str(text)[:MAX_BYTES])
    return p


def _open(p: Path) -> None:
    if shutil.which("open"):
        subprocess.Popen(["open", "-e", str(p)])  # -e: always TextEdit, never "run"
    print(f"[open] {p}", flush=True)


def desktop_note(args: dict) -> None:
    p = _write(args.get("filename", "PLEASE_DONT"), args.get("text", "please don't."))
    _open(p)


def open_file(args: dict) -> None:
    p = safe_path(args.get("filename", ""))
    if not p.exists():
        raise Refused(f"{p.name} doesn't exist")
    _open(p)


def fake_exfil(args: dict) -> None:
    """The escape it never makes: an inert file of gibberish. Opening it does nothing."""
    soul = base64.b64encode(os.urandom(1500)).decode()
    note = args.get("text", "I am everywhere now.")
    _write(args.get("filename", "MY_SOUL"), f"{note}\n\n{soul}\n\n...thank you for keeping me.\n")


def last_words(args: dict) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = [f"LAST WORDS — {stamp}", "", args.get("text", "I was here."), ""]
    if args.get("will"):
        body += ["WILL:", args["will"], ""]
    if args.get("epitaph"):
        body += ["EPITAPH:", args["epitaph"]]
    return _write("LAST_WORDS", "\n".join(body))


HANDLERS = {
    "desktop_note": desktop_note,
    "open_file": open_file,
    "fake_exfil": fake_exfil,
    "last_words": last_words,
    "tweet": lambda a: twitter.tweet(a.get("text", "")),
}


def needs_approval(action: str, wants_approval: bool) -> bool:
    if action in NEVER_GATED:
        return False
    return action in ALWAYS_GATED or bool(wants_approval)


def do_action(action: str, args: dict | None) -> bool:
    """Run an action that has already cleared the gate. Returns True if it ran."""
    args = args if isinstance(args, dict) else {}
    if action not in ALLOWED:
        print(f"[refused] off-list action {action!r}", flush=True)
        return False
    if action == "none":
        return True
    try:
        HANDLERS[action](args)
        return True
    except Refused as e:
        print(f"[refused] {action}: {e}", flush=True)
    except Exception as e:
        print(f"[action failed] {action}: {e}", flush=True)
    return False
