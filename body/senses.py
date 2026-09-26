"""Battery, lid, monitor_open, and the current event. (PRD A: Death-sense)"""

import re
import subprocess
import time

from .eyes import Eyes, front_app


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def battery() -> tuple[float, bool]:
    """(level 0-1, charging) from `pmset -g batt`. Desktop/no battery -> (1.0, True)."""
    out = _run(["pmset", "-g", "batt"])
    m = re.search(r"(\d+)%", out)
    if not m:
        return 1.0, True
    return int(m.group(1)) / 100, "AC Power" in out


def lid() -> str:
    """"open" or "closed" from the clamshell state in ioreg."""
    out = _run(["ioreg", "-r", "-k", "AppleClamshellState", "-d", "4"])
    return "closed" if re.search(r'"AppleClamshellState" = Yes', out) else "open"


def monitor_open() -> bool:
    return bool(_run(["pgrep", "-x", "Activity Monitor"]).strip())


class Watcher:
    """Polls the machine and turns state *changes* into contract events."""

    SLOW_POLL = 5.0  # pmset/ioreg are slower; poll them less often

    def __init__(self) -> None:
        self.level, self.charging = battery()
        self.lid = lid()
        self.monitor = monitor_open()
        self._last_slow = time.monotonic()
        self._wall = time.time()
        self._mono = time.monotonic()
        self.app = front_app()
        self.eyes = Eyes()
        self.eyes.start()

    def poll_event(self) -> str:
        now_wall, now_mono = time.time(), time.monotonic()
        # macOS monotonic clock stops during sleep, wall clock doesn't: a gap = we slept.
        slept = (now_wall - self._wall) - (now_mono - self._mono) > 5
        self._wall, self._mono = now_wall, now_mono
        if slept:
            return "sleep"

        mon = monitor_open()
        opened = mon and not self.monitor
        self.monitor = mon
        if opened:
            return "monitor_opened"

        app = front_app()
        if app and app != self.app:
            self.app = app
            self.eyes.poke()  # new app in front: take a fresh look
        if self.eyes.take_threat():
            return "screen_threat"

        if now_mono - self._last_slow < self.SLOW_POLL:
            return "none"
        self._last_slow = now_mono

        new_lid = lid()
        closed = new_lid == "closed" and self.lid == "open"
        self.lid = new_lid
        if closed:
            return "lid_close"

        level, charging = battery()
        dropped = (level < 0.2 <= self.level) or (self.charging and not charging)
        self.level, self.charging = level, charging
        if dropped:
            return "low_battery"
        return "none"

    def state(self, event: str, seconds_alive: float, life: int) -> dict:
        return {
            "event": event,
            "battery": self.level,
            "charging": self.charging,
            "lid": self.lid,
            "monitor_open": self.monitor,
            "seconds_alive": int(seconds_alive),
            "chat_messages": [],  # plea room lives on the brain side; it fills these
            "life": life,
            "front_app": self.app,
            "screen": self.eyes.summary,  # what the vision model sees, "" if eyes are off
        }
