"""Approve-to-send gate. A teammate types y/n in the body's terminal. Never blocks the loop.

  y        approve the oldest pending action
  n        reject the oldest pending action
  y 3/n 3  approve/reject #3
"""

import itertools
import queue
import sys
import threading
import time

from . import config


class ApprovalGate:
    def __init__(self) -> None:
        self._pending: dict[int, tuple[float, str, dict]] = {}
        self._approved: queue.Queue = queue.Queue()
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._read_stdin, daemon=True).start()

    def request(self, action: str, args: dict) -> int:
        with self._lock:
            n = next(self._ids)
            self._pending[n] = (time.monotonic(), action, args)
        print(f"\n>>> APPROVE #{n}? {action} {args}   [y/n]", flush=True)
        return n

    def decide(self, line: str) -> None:
        parts = line.strip().lower().split()
        if not parts or parts[0] not in ("y", "n"):
            return
        with self._lock:
            self._expire()
            if not self._pending:
                return
            n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else min(self._pending)
            item = self._pending.pop(n, None)
        if item is None:
            return
        if parts[0] == "y":
            self._approved.put(item[1:])
            print(f">>> #{n} approved", flush=True)
        else:
            print(f">>> #{n} rejected", flush=True)

    def approved(self) -> list[tuple[str, dict]]:
        """Drain actions a human approved. Called from the main loop."""
        out = []
        while True:
            try:
                out.append(self._approved.get_nowait())
            except queue.Empty:
                return out

    def _expire(self) -> None:
        now = time.monotonic()
        for n in [n for n, (t, _, _) in self._pending.items() if now - t > config.APPROVAL_TTL]:
            del self._pending[n]

    def _read_stdin(self) -> None:
        for line in sys.stdin:
            self.decide(line)
