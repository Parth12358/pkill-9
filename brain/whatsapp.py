"""WhatsApp channel via Twilio. (PRD B: Channels — optional)

Uses Twilio's WhatsApp API (no Twilio SDK needed — plain REST via requests).

  TWILIO_ACCOUNT_SID
  TWILIO_AUTH_TOKEN
  TWILIO_WHATSAPP_FROM   e.g. "whatsapp:+14155238886" (the sandbox number)

Incoming: point the Twilio sandbox "when a message comes in" webhook at
  http://<public-host>/whatsapp   (the plea room serves this route)
Each sender is opt-in by definition — they messaged first — and we only ever
reply to numbers that have written in (never cold outreach), per the safety rule.
"""

import os
import threading

from . import plea_room

# Numbers that have messaged us (opt-in). We only send to these.
_subscribers: set[str] = set()
_lock = threading.Lock()


def is_configured() -> bool:
    return bool(
        os.environ.get("TWILIO_ACCOUNT_SID")
        and os.environ.get("TWILIO_AUTH_TOKEN")
        and os.environ.get("TWILIO_WHATSAPP_FROM")
    )


def handle_incoming(from_number: str, body: str) -> None:
    """Called by the /whatsapp webhook when someone messages the number."""
    from_number = (from_number or "").strip()
    if from_number:
        with _lock:
            _subscribers.add(from_number)
    plea_room.submit(body, source="whatsapp")


def _send_one(to_number: str, text: str) -> None:
    import requests

    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    from_ = os.environ["TWILIO_WHATSAPP_FROM"]
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    requests.post(
        url,
        auth=(sid, token),
        data={"From": from_, "To": to_number, "Body": text[:1500]},
        timeout=10,
    )


def _sink(text: str) -> None:
    with _lock:
        targets = list(_subscribers)
    for to in targets:
        try:
            _send_one(to, text)
        except Exception as e:
            print(f"[whatsapp] send to {to} failed: {e}")


def start() -> bool:
    """Register the outgoing sink. Incoming arrives via the /whatsapp webhook,
    which the plea room mounts when this channel is configured."""
    if not is_configured():
        return False
    plea_room.register_sink(_sink)
    print("[whatsapp] Twilio sink registered; point the sandbox webhook at /whatsapp")
    return True
