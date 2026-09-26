"""Web chat (QR code) or Discord bot; pushes messages into a queue. (PRD B: Plea room)"""

import queue

messages: "queue.Queue[str]" = queue.Queue()


def drain() -> list[str]:
    out = []
    while not messages.empty():
        out.append(messages.get_nowait())
    return out
