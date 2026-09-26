"""The brain (PRD B). Loads the repo's .env (gitignored) before anything reads env vars."""

import os
from pathlib import Path


def _load_env() -> None:
    try:
        lines = (Path(__file__).resolve().parent.parent / ".env").read_text().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.split(" #", 1)[0].strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
