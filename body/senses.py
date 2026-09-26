"""Battery, lid, monitor_open, and the current event. (PRD A: Death-sense)"""


def battery() -> tuple[float, bool]:
    """Return (level 0-1, charging). TODO: parse `pmset -g batt`."""
    return 1.0, True


def lid() -> str:
    """Return "open" or "closed". TODO: poll `pmset -g log` for Sleep/Wake."""
    return "open"


def monitor_open() -> bool:
    """TODO: `pgrep -x "Activity Monitor"`."""
    return False


def current_event() -> str:
    """One of the events in contract.md. TODO: SIGINT/SIGTERM flags, lid, battery."""
    return "none"
