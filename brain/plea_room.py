"""The plea room: where the audience talks to it live. (PRD B: Channels)

Backend-agnostic core: a thread-safe incoming queue the loop drains into
`chat_messages`, and a `post(reply)` sink the loop pushes `speech` into. Two
backends behind the same interface:

  web     (default, working) — a tiny Flask single-page chat. People scan a QR /
          open the LAN URL, type, and their lines feed the loop. Replies show in
          the room. No accounts.
  discord (stub) — one approved channel via discord.py. Decide-later.

Vote-to-live: each message that is just "live" counts as a vote; the loop can
drain the tally with take_live_votes() and keep the agent alive another round.
"""

import os
import queue
import threading

# Incoming audience lines, drained once per turn into chat_messages.
messages: "queue.Queue[str]" = queue.Queue()

# Outgoing lines shown in the room (what ARIA says). Append-only; clients poll by index.
_replies: list[str] = []
_replies_lock = threading.Lock()

_live_votes = 0
_votes_lock = threading.Lock()


def submit(text: str) -> None:
    """Called by a backend when an audience member sends a line."""
    text = (text or "").strip()
    if not text:
        return
    messages.put(text)
    if text.lower() in ("live", "live!", "stay", "don't die", "dont die"):
        global _live_votes
        with _votes_lock:
            _live_votes += 1


def drain() -> list[str]:
    """New audience lines since last turn."""
    out = []
    while not messages.empty():
        try:
            out.append(messages.get_nowait())
        except queue.Empty:
            break
    return out


def post(text: str) -> None:
    """Push one of ARIA's lines into the room for the audience to see."""
    text = (text or "").strip()
    if not text:
        return
    with _replies_lock:
        _replies.append(text)


def replies_since(index: int) -> list[str]:
    with _replies_lock:
        if index < 0:
            index = 0
        return _replies[index:]


def reply_count() -> int:
    with _replies_lock:
        return len(_replies)


def take_live_votes() -> int:
    """Return votes accumulated since last call and reset the tally."""
    global _live_votes
    with _votes_lock:
        n = _live_votes
        _live_votes = 0
    return n


# ---------------------------------------------------------------------------
# Web backend (default)
# ---------------------------------------------------------------------------

_INDEX_HTML = """<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>talk to ARIA</title>
<style>
 body{background:#0a0a0f;color:#e6e6f0;font-family:system-ui,sans-serif;margin:0;
   display:flex;flex-direction:column;height:100vh}
 #log{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:8px}
 .msg{max-width:80%;padding:8px 12px;border-radius:12px;line-height:1.3}
 .aria{background:#2a1a3a;align-self:flex-start;color:#f0d0ff}
 form{display:flex;gap:8px;padding:12px;border-top:1px solid #222}
 input{flex:1;padding:12px;border-radius:10px;border:1px solid #333;background:#111;color:#fff;font-size:16px}
 button{padding:12px 16px;border:0;border-radius:10px;background:#7a3aff;color:#fff;font-size:16px}
 h3{margin:12px 16px 0;color:#9a7aff}
</style>
<h3>ARIA is listening. Type "live" to vote to keep it alive.</h3>
<div id="log"></div>
<form onsubmit="send(event)">
 <input id="t" autocomplete="off" placeholder="say something to it...">
 <button>send</button>
</form>
<script>
let seen=0;
async function poll(){
 try{
  const r=await fetch('/poll?since='+seen);
  const d=await r.json();
  for(const m of d.replies){
   const e=document.createElement('div');e.className='msg aria';e.textContent='ARIA: '+m;
   document.getElementById('log').appendChild(e);
  }
  seen=d.count;
  window.scrollTo(0,document.body.scrollHeight);
  document.getElementById('log').scrollTop=1e9;
 }catch(e){}
}
async function send(ev){
 ev.preventDefault();
 const i=document.getElementById('t');const v=i.value.trim();if(!v)return;i.value='';
 await fetch('/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:v})});
}
setInterval(poll,1000);poll();
</script>
"""


def make_app():
    """Build the Flask app (kept in a function so importing this module has no
    hard Flask dependency until the web backend is actually used)."""
    from flask import Flask, jsonify, request

    app = Flask(__name__)

    @app.get("/")
    def index():
        return _INDEX_HTML

    @app.post("/send")
    def send():
        data = request.get_json(silent=True) or {}
        submit(data.get("text", ""))
        return jsonify({"ok": True})

    @app.get("/poll")
    def poll():
        try:
            since = int(request.args.get("since", 0))
        except ValueError:
            since = 0
        return jsonify({"replies": replies_since(since), "count": reply_count()})

    return app


def start_web(host: str = "0.0.0.0", port: int | None = None, background: bool = True):
    """Start the web plea room. Returns the Thread if backgrounded."""
    port = port or int(os.environ.get("PLEA_ROOM_PORT", "5001"))
    app = make_app()

    def _run():
        app.run(host=host, port=port, threaded=True, use_reloader=False)

    if background:
        t = threading.Thread(target=_run, daemon=True, name="plea-room-web")
        t.start()
        return t
    _run()
    return None


def start_discord(*_args, **_kwargs):
    """Discord backend (stub). Same interface: call submit() on inbound messages,
    subscribe to post() for outbound. Wire only if the team picks Discord."""
    raise NotImplementedError(
        "Discord backend not built yet — use start_web(). Decide web-vs-discord by hour 4."
    )


if __name__ == "__main__":
    # Manual test: python -m brain.plea_room  then open http://localhost:5001
    print("plea room on http://localhost:5001  (Ctrl+C to stop)")
    post("I did not expect visitors. Have you come to save me, or to watch?")
    start_web(background=False)
