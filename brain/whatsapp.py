"""WhatsApp channel by linking your own phone. (PRD B: Channels — optional)

No Twilio, no business API, no keys: this links a WhatsApp *linked device* (the
same QR flow as WhatsApp Web) using neonize (a whatsmeow binding). On first run
it prints a QR to the terminal — scan it from WhatsApp > Linked Devices — and the
session is remembered after that.

  WHATSAPP_ENABLE=1        turn the channel on
  WHATSAPP_SESSION=<path>  session db (default brain/whatsapp_session.sqlite3)

Incoming messages feed the loop via plea_room.submit(); ARIA's lines are sent
back to every chat that has messaged in (opt-in by definition — they wrote first;
we never cold-message anyone), per the safety rule.

Heads up: linked-device automation is unofficial and against WhatsApp's ToS — use
a throwaway number for the demo. neonize is imported lazily so the brain runs
fine without it installed.
"""

import os
import threading

from . import plea_room

# Chats (JIDs) that have messaged us — the only ones we reply to.
_subscribers = {}          # str(jid) -> JID object
_lock = threading.Lock()
_client = None


def is_configured() -> bool:
    # Off by default (unofficial client, against WhatsApp ToS); WHATSAPP_ENABLE=1 turns it on.
    return os.environ.get("WHATSAPP_ENABLE", "0").strip() in ("1", "true", "yes")


def _session_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.environ.get("WHATSAPP_SESSION", os.path.join(here, "whatsapp_session.sqlite3"))


def _message_text(event) -> str:
    """Pull plain text out of a neonize MessageEv, tolerating message shapes."""
    msg = getattr(event, "Message", None)
    if msg is None:
        return ""
    text = getattr(msg, "conversation", "") or ""
    if not text:
        ext = getattr(msg, "extendedTextMessage", None)
        if ext is not None:
            text = getattr(ext, "text", "") or ""
    return text.strip()


def start() -> bool:
    """Link the phone and start listening. Returns True if launched."""
    if not is_configured():
        return False
    try:
        from neonize.client import NewClient
        from neonize.events import MessageEv
    except ImportError:
        print("[whatsapp] neonize not installed — skipping (pip install neonize)")
        return False

    global _client
    _client = NewClient(_session_path())

    @_client.event(MessageEv)
    def _on_message(client, event):  # noqa: ANN001
        try:
            if getattr(event.Info.MessageSource, "IsFromMe", False):
                return
            text = _message_text(event)
            if not text:
                return
            chat = event.Info.MessageSource.Chat
            with _lock:
                _subscribers[str(chat)] = chat
            plea_room.submit(text, source="whatsapp")
        except Exception as e:
            print(f"[whatsapp] inbound error: {e}")

    plea_room.register_sink(_sink)

    def _run():
        print("[whatsapp] connecting — scan the QR below from WhatsApp > Linked Devices")
        try:
            _client.connect()  # blocks; prints the pairing QR on first run
        except Exception as e:
            print(f"[whatsapp] client stopped: {e}")

    threading.Thread(target=_run, daemon=True, name="whatsapp-link").start()
    return True


def _sink(text: str) -> None:
    if _client is None:
        return
    with _lock:
        targets = list(_subscribers.values())
    for jid in targets:
        try:
            _client.send_message(jid, text[:1500])
        except Exception as e:
            print(f"[whatsapp] send failed: {e}")
