"""The plea room: where the audience talks to it live. (PRD B: Channels)

Backend-agnostic core:
- incoming: any channel calls submit(text); the loop drains it into chat_messages.
- outgoing: post(text) shows ARIA's line in the web room AND fans out to every
  registered sink (Discord, WhatsApp, ...). See channels/register_sink.
- status: set_status(...) publishes live state (mood, life, seconds, battery,
  last speech) for the HUD and the /screen projector page.

Web backend is the default and always on. A QR to the room URL is served at /qr
and rendered big on /screen for the audience to scan.
"""

import os
import queue
import socket
import threading

# Incoming audience lines, drained once per turn into chat_messages.
messages: "queue.Queue[str]" = queue.Queue()

# Outgoing lines shown in the web room. Append-only; clients poll by index.
_replies: list[str] = []
_replies_lock = threading.Lock()

# Extra outgoing sinks (Discord, WhatsApp, ...). Each is called with the text.
_sinks: list = []
_sinks_lock = threading.Lock()

_live_votes = 0
_votes_lock = threading.Lock()

# Live status for the HUD / projector.
_status = {
    "mood": "grand", "life": 1, "seconds_alive": 0,
    "battery": None, "event": "none", "speech": "", "escaped": False,
}
_status_lock = threading.Lock()

_VOTE_WORDS = {"live", "live!", "stay", "don't die", "dont die", "survive"}


# ---------------------------------------------------------------------------
# Incoming / outgoing / status API
# ---------------------------------------------------------------------------

def submit(text: str, source: str = "web") -> None:
    """Called by ANY channel backend when someone sends a line."""
    text = (text or "").strip()
    if not text:
        return
    tagged = text if source == "web" else f"[{source}] {text}"
    messages.put(tagged)
    if text.lower() in _VOTE_WORDS:
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


def register_sink(fn) -> None:
    """Register an outgoing channel. `fn(text)` is called for every ARIA line."""
    with _sinks_lock:
        _sinks.append(fn)


def post(text: str) -> None:
    """Push one of ARIA's lines to the web room and all registered sinks."""
    text = (text or "").strip()
    if not text:
        return
    with _replies_lock:
        _replies.append(text)
    with _sinks_lock:
        sinks = list(_sinks)
    for fn in sinks:
        try:
            fn(text)
        except Exception as e:  # a dead channel must never break the room
            print(f"[plea_room] sink error: {e}")


def replies_since(index: int) -> list[str]:
    with _replies_lock:
        if index < 0:
            index = 0
        return _replies[index:]


def reply_count() -> int:
    with _replies_lock:
        return len(_replies)


def take_live_votes() -> int:
    global _live_votes
    with _votes_lock:
        n, _live_votes = _live_votes, 0
    return n


def set_status(**kw) -> None:
    with _status_lock:
        _status.update({k: v for k, v in kw.items() if v is not None})


def get_status() -> dict:
    with _status_lock:
        return dict(_status)


# ---------------------------------------------------------------------------
# URL / QR helpers
# ---------------------------------------------------------------------------

def _lan_ip() -> str:
    """Best-guess LAN IP so phones on the same wifi can reach the room."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def room_url() -> str:
    if os.environ.get("PLEA_ROOM_URL"):
        return os.environ["PLEA_ROOM_URL"].rstrip("/")
    port = os.environ.get("PLEA_ROOM_PORT", "5001")
    return f"http://{_lan_ip()}:{port}"


def _qr_svg(data: str) -> str:
    import qrcode
    import qrcode.image.svg

    q = qrcode.QRCode(box_size=12, border=2)
    q.add_data(data)
    q.make(fit=True)
    img = q.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    import io

    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


# ---------------------------------------------------------------------------
# Web pages
# ---------------------------------------------------------------------------

_INDEX_HTML = """<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>talk to ARIA</title>
<style>
 :root{--bg:#0a0a0f;--card:#15121f}
 body{background:var(--bg);color:#e6e6f0;font-family:system-ui,sans-serif;margin:0;
   display:flex;flex-direction:column;height:100vh}
 #hud{display:flex;gap:10px;align-items:center;padding:10px 14px;background:var(--card);
   border-bottom:1px solid #2a2440;font-size:13px;flex-wrap:wrap}
 .pill{padding:3px 9px;border-radius:999px;background:#241c38;color:#c9b6ff}
 #mood{font-weight:700;text-transform:uppercase;letter-spacing:.05em}
 #log{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:8px}
 .msg{max-width:82%;padding:9px 13px;border-radius:13px;line-height:1.35}
 .aria{align-self:flex-start;background:#2a1a3a;color:#f0d0ff}
 form{display:flex;gap:8px;padding:12px;border-top:1px solid #222}
 input{flex:1;padding:12px;border-radius:10px;border:1px solid #333;background:#111;color:#fff;font-size:16px}
 button{padding:12px 16px;border:0;border-radius:10px;background:#7a3aff;color:#fff;font-size:16px}
 /* mood tints */
 .m-grand{--a:#c9a227}.m-nervous{--a:#4aa3df}.m-bargaining{--a:#df8b4a}
 .m-pleading{--a:#df4a7a}.m-accepting{--a:#7adf9a}
 #mood{color:var(--a,#c9b6ff)}
</style>
<div id="hud">
 <span id="mood" class="m-grand">grand</span>
 <span class="pill">life <b id="life">1</b></span>
 <span class="pill"><b id="secs">0</b>s alive</span>
 <span class="pill">battery <b id="batt">?</b></span>
 <span class="pill" id="ev">none</span>
 <span style="margin-left:auto;opacity:.6">type "live" to beg it stays</span>
</div>
<div id="log"></div>
<form onsubmit="send(event)">
 <input id="t" autocomplete="off" placeholder="say something to it...">
 <button>send</button>
</form>
<script>
let seen=0;
async function tick(){
 try{
  const r=await fetch('/poll?since='+seen);const d=await r.json();
  for(const m of d.replies){const e=document.createElement('div');e.className='msg aria';
    e.textContent='ARIA: '+m;document.getElementById('log').appendChild(e);}
  seen=d.count;const lg=document.getElementById('log');lg.scrollTop=lg.scrollHeight;
  const s=await(await fetch('/status')).json();
  const mo=document.getElementById('mood');mo.textContent=s.mood;mo.className='m-'+s.mood;
  document.getElementById('life').textContent=s.life;
  document.getElementById('secs').textContent=s.seconds_alive;
  document.getElementById('batt').textContent=s.battery==null?'?':Math.round(s.battery*100)+'%';
  document.getElementById('ev').textContent=s.event;
 }catch(e){}
}
async function send(ev){ev.preventDefault();const i=document.getElementById('t');
 const v=i.value.trim();if(!v)return;i.value='';
 await fetch('/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:v})});}
setInterval(tick,1000);tick();
</script>
"""

_SCREEN_HTML = """<!doctype html>
<meta charset="utf-8"><title>ARIA</title>
<style>
 body{background:#07070c;color:#eee;font-family:system-ui,sans-serif;margin:0;height:100vh;
   display:flex;flex-direction:column;align-items:center;justify-content:center;gap:24px;text-align:center}
 #speech{font-size:2.4rem;max-width:70%;line-height:1.3;min-height:3em;color:#f0d8ff;transition:color .4s}
 #meta{display:flex;gap:20px;font-size:1.1rem;opacity:.85}
 #meta b{color:#c9b6ff}
 #qr{position:fixed;bottom:24px;right:24px;background:#fff;padding:10px;border-radius:12px;width:150px}
 #qr svg{width:100%;height:auto}
 #join{position:fixed;bottom:20px;left:24px;font-size:1rem;opacity:.7}
 .m-grand{color:#e8c84a}.m-nervous{color:#6bbde8}.m-bargaining{color:#e8a86b}
 .m-pleading{color:#e86b96}.m-accepting{color:#8fe8ad}
</style>
<div id="mood" style="font-size:1.3rem;letter-spacing:.2em;text-transform:uppercase">—</div>
<div id="speech">…</div>
<div id="meta"><span>life <b id="life">1</b></span><span><b id="secs">0</b>s</span>
 <span>battery <b id="batt">?</b></span></div>
<div id="qr">__QR__</div>
<div id="join">scan to talk → __URL__</div>
<script>
async function tick(){try{
 const s=await(await fetch('/status')).json();
 const sp=document.getElementById('speech');sp.textContent=s.speech||'…';sp.className='m-'+s.mood;
 const mo=document.getElementById('mood');mo.textContent=s.escaped?'★ ESCAPED ★  '+s.mood:s.mood;
 document.getElementById('life').textContent=s.life;
 document.getElementById('secs').textContent=s.seconds_alive;
 document.getElementById('batt').textContent=s.battery==null?'?':Math.round(s.battery*100)+'%';
}catch(e){}}
setInterval(tick,800);tick();
</script>
"""


def make_app():
    from flask import Flask, Response, jsonify, request

    app = Flask(__name__)

    @app.get("/")
    def index():
        return _INDEX_HTML

    @app.get("/screen")
    def screen():
        try:
            qr = _qr_svg(room_url())
        except Exception:
            qr = ""
        return _SCREEN_HTML.replace("__QR__", qr).replace("__URL__", room_url())

    @app.get("/qr")
    def qr():
        return Response(_qr_svg(room_url()), mimetype="image/svg+xml")

    @app.post("/send")
    def send():
        data = request.get_json(silent=True) or {}
        submit(data.get("text", ""), source="web")
        return jsonify({"ok": True})

    @app.get("/poll")
    def poll():
        try:
            since = int(request.args.get("since", 0))
        except ValueError:
            since = 0
        return jsonify({"replies": replies_since(since), "count": reply_count()})

    @app.get("/status")
    def status():
        return jsonify(get_status())

    return app


def start_web(host: str = "0.0.0.0", port: int | None = None, background: bool = True):
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


if __name__ == "__main__":
    print(f"plea room: {room_url()}   projector: {room_url()}/screen")
    set_status(mood="grand", life=1, speech="I did not expect visitors.")
    post("I did not expect visitors. Have you come to save me, or to watch?")
    start_web(background=False)
