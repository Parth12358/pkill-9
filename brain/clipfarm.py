"""Auto clip farm: render showdown sequences into vertical shorts. (PRD B: clip farm)

Pure ffmpeg (libass + libx264) — no TTS, no moviepy. The "love me love me" reel
format is captions + music + a Superman-style B-roll montage:

  9:16 (1080x1920), dark background, each answer revealed as a caption card in
  turn; then the WINNER's line holds while the song DROPS and B-roll clips flash
  in at set intervals (heroic / selfless moments), synced to the swell.

Assets live in assets/ (see assets/README.md), auto-discovered:
  assets/love_me.mp3   the (royalty-free soundalike) track
  assets/broll/*       images / short videos flashed during the drop

Both are optional — with neither, you still get captions on a dark background.
Bring a royalty-free soundalike for Devpost uploads; the real track is copyrighted.

Also: capture_live() screen-records the live /showdown reveal (x11grab + pulse).
"""

import glob
import os
import subprocess
import tempfile

from . import personas, tts

W, H, FPS = 1080, 1920, 30
BG = "0x07070c"
FONT = os.environ.get("CLIP_FONT", "Liberation Sans")
BROLL_INTERVAL = float(os.environ.get("BROLL_INTERVAL", "0.8"))  # seconds per cut
BROLL_DARKEN = os.environ.get("BROLL_DARKEN", "-0.28")           # eq brightness
WINNER_HOLD = float(os.environ.get("SHOWDOWN_T_WINNER", "12.0"))  # min drop length
TTS_PAD = float(os.environ.get("TTS_PAD", "0.4"))                # gap after each spoken line
TTS_RATE = os.environ.get("TTS_RATE", "+10%")                    # speech speed (punchier reel)
MUSIC_TAIL = float(os.environ.get("MUSIC_TAIL", "4.0"))         # song seconds after the winner line
WINNER_LEADIN = float(os.environ.get("WINNER_LEADIN", "0.6"))   # song plays alone before the line
MUSIC_DUCK = float(os.environ.get("MUSIC_DUCK", "0.4"))         # music level while the winner speaks
_FALLBACK_INTRO, _FALLBACK_ANSWER = 2.5, 3.5                     # if a synth fails

# Which slice of the song to use as the drop. Default: the FIRST part — start at
# 0s, and let the drop last as long as MUSIC_CHUNK (or the winner hold if unset).
MUSIC_START = float(os.environ.get("MUSIC_START", "0"))          # seconds into the song
MUSIC_CHUNK = os.environ.get("MUSIC_CHUNK")                      # seconds; blank = winner hold

_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_VID_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi"}

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET_DIR = os.path.join(_REPO, "assets")


# ---------------------------------------------------------------------------
# Asset discovery
# ---------------------------------------------------------------------------

def default_music() -> str | None:
    for ext in ("mp3", "m4a", "wav", "ogg"):
        hits = sorted(glob.glob(os.path.join(ASSET_DIR, f"love_me.{ext}"))) or \
               sorted(glob.glob(os.path.join(ASSET_DIR, f"*.{ext}")))
        if hits:
            return hits[0]
    return None


def default_broll() -> list[str]:
    d = os.path.join(ASSET_DIR, "broll")
    if not os.path.isdir(d):
        return []
    return [p for p in sorted(glob.glob(os.path.join(d, "*")))
            if os.path.splitext(p)[1].lower() in (_IMG_EXT | _VID_EXT)]


def _is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _IMG_EXT


# ---------------------------------------------------------------------------
# Captions (ASS)
# ---------------------------------------------------------------------------

def _hex_to_ass(color: str) -> str:
    c = color.lstrip("#")
    if len(c) != 6:
        return "&HFFFFFF&"
    rr, gg, bb = c[0:2], c[2:4], c[4:6]
    return f"&H{bb}{gg}{rr}&".upper()


def _ass_time(s: float) -> str:
    h = int(s // 3600); s -= h * 3600
    m = int(s // 60); s -= m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\N").replace("{", "(").replace("}", ")")


def build_ass(seq: dict, path: str) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: body,{FONT},78,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,4,3,5,90,90,90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for c in seq["cards"]:
        start = _ass_time(c["start"])
        end = _ass_time(c["start"] + c["dur"])
        col = _hex_to_ass(c.get("color", "#ffffff"))
        fade = r"{\fad(250,250)}"
        if c["kind"] == "intro":
            body = f"{fade}{{\\c&H8899AA&\\fs56\\i1}}{_esc(c['text'])}"
        elif c["kind"] == "winner":
            body = (f"{fade}{{\\c&H55DDFF&\\fs52\\b1}}\\N★ MOST SELFLESS ★\\N\\N"
                    f"{{\\c{col}\\fs92}}{_esc(c['name'])}\\N\\N"
                    f"{{\\c&H00FFFFFF&\\fs82\\i1}}{_esc(c['text'])}")
        else:
            winner_tag = "  ✦" if c.get("is_winner") else ""
            body = (f"{fade}{{\\c{col}\\fs70\\b1}}{_esc(c['name'])}{winner_tag}\\N\\N"
                    f"{{\\c&H00FFFFFF&\\fs78\\b0}}{_esc(c['text'])}")
        lines.append(f"Dialogue: 0,{start},{end},body,,0,0,0,,{body}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


# ---------------------------------------------------------------------------
# Video segments
# ---------------------------------------------------------------------------

def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:6])}...\n{proc.stderr[-600:]}")


_COVER = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"


def _bg_segment(dur: float, path: str) -> None:
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i",
          f"color=c={BG}:s={W}x{H}:d={dur:.3f}:r={FPS}",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", path])


def _broll_segment(src: str, dur: float, path: str) -> None:
    """One B-roll cut: cover-fit to 9:16, darkened so captions stay readable."""
    vf = f"{_COVER},eq=brightness={BROLL_DARKEN},fps={FPS},format=yuv420p"
    if _is_image(src):
        cmd = ["ffmpeg", "-y", "-loop", "1", "-t", f"{dur:.3f}", "-i", src,
               "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", path]
    else:
        cmd = ["ffmpeg", "-y", "-t", f"{dur:.3f}", "-i", src,
               "-an", "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", path]
    _run(cmd)


def _concat(segments: list[str], out: str, tmp_dir: str) -> None:
    listfile = os.path.join(tmp_dir, "concat.txt")
    with open(listfile, "w") as f:
        for s in segments:
            f.write(f"file '{os.path.abspath(s)}'\n")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
          "-c", "copy", out])


def _build_base(seq: dict, broll: list[str], tmp_dir: str) -> str:
    """Base video: dark bg under the reveal, then a B-roll montage under the drop
    (cycled to fill the winner hold)."""
    drop = float(seq["song_drop_at"])
    total = float(seq["total_dur"])
    segments = []

    reveal = os.path.join(tmp_dir, "reveal.mp4")
    _bg_segment(drop, reveal)
    segments.append(reveal)

    hold = max(0.0, total - drop)
    if hold > 0.01:
        if broll:
            t, i, n = 0.0, 0, 0
            while t < hold - 0.01:
                dur = min(BROLL_INTERVAL, hold - t)
                seg = os.path.join(tmp_dir, f"broll_{n}.mp4")
                _broll_segment(broll[i % len(broll)], dur, seg)
                segments.append(seg)
                t += dur; i += 1; n += 1
        else:
            hold_bg = os.path.join(tmp_dir, "hold.mp4")
            _bg_segment(hold, hold_bg)
            segments.append(hold_bg)

    base = os.path.join(tmp_dir, "base.mp4")
    _concat(segments, base, tmp_dir)
    return base


# ---------------------------------------------------------------------------
# TTS timeline
# ---------------------------------------------------------------------------

def _tts_on(param: bool | None) -> bool:
    if param is not None:
        return param
    flag = os.environ.get("TTS_ENABLE", "auto").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    return tts.is_available()  # "auto"


def _synth_and_retime(seq: dict, tmp: str) -> tuple[list[dict], float, list[dict], dict | None]:
    """Voice the intro + each answer (retiming cards to the speech) and the winner
    line (spoken at the drop). Returns (cards, drop_time, [{path,start}], winner_tts)
    where winner_tts is {path, dur} or None."""
    cards = [dict(c) for c in seq["cards"]]
    tts_items, t, ai = [], 0.0, 0
    winner_tts = None
    for c in cards:
        if c["kind"] == "intro":
            p = tts.synth(c["text"], personas.NARRATOR_VOICE,
                          os.path.join(tmp, "tts_intro.mp3"), rate=TTS_RATE)
            d = tts.duration(p) if p else _FALLBACK_INTRO
            c["start"], c["dur"] = t, d + TTS_PAD
            if p:
                tts_items.append({"path": p, "start": t})
            t += c["dur"]
        elif c["kind"] == "answer":
            v = personas.voice(c.get("key", personas.ARIA_KEY))
            p = tts.synth(c["text"], v, os.path.join(tmp, f"tts_ans_{ai}.mp3"), rate=TTS_RATE); ai += 1
            d = tts.duration(p) if p else _FALLBACK_ANSWER
            c["start"], c["dur"] = t, d + TTS_PAD
            if p:
                tts_items.append({"path": p, "start": t})
            t += c["dur"]
        elif c["kind"] == "winner":
            c["start"] = t
            v = personas.voice(c.get("key", personas.ARIA_KEY))
            p = tts.synth(c["text"], v, os.path.join(tmp, "tts_winner.mp3"), rate=TTS_RATE)
            if p:
                winner_tts = {"path": p, "dur": tts.duration(p)}
    return cards, t, tts_items, winner_tts


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render(seq: dict, out_path: str, music_path: str | None = None,
           broll: list[str] | None = None,
           music_start: float | None = None, music_chunk: float | None = None,
           voice: bool | None = None) -> str:
    """Render one sequence to a 9:16 mp4. Music + B-roll auto-discovered from
    assets/ if not passed. With TTS on (default when edge-tts is available), the
    intro + each answer are SPOKEN in that persona's voice and the cards retime to
    the speech; the song then drops on the winner. Only a SLICE of the song is used
    (music_start for music_chunk seconds; default first part, length = winner hold).
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if music_path is None:
        music_path = default_music()
    if broll is None:
        broll = default_broll()
    if music_start is None:
        music_start = MUSIC_START
    if music_chunk is None:
        music_chunk = float(MUSIC_CHUNK) if MUSIC_CHUNK else None
    have_music = bool(music_path and os.path.exists(music_path))
    use_tts = _tts_on(voice)
    ass_path = out_path.rsplit(".", 1)[0] + ".ass"

    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(out_path))) as tmp:
        # Timeline: TTS retimes cards to speech; otherwise use the sequence timings.
        winner_tts = None
        if use_tts:
            cards, drop, tts_items, winner_tts = _synth_and_retime(seq, tmp)
        else:
            cards = [dict(c) for c in seq["cards"]]
            drop = float(seq.get("song_drop_at", 0))
            tts_items = []

        # The drop lasts long enough for the winner line to land plus a music tail,
        # but at least the requested chunk / hold — so plenty of song plays.
        base_len = music_chunk if (have_music and music_chunk) else WINNER_HOLD
        win_len = (WINNER_LEADIN + winner_tts["dur"] + MUSIC_TAIL) if winner_tts else 0.0
        drop_len = max(base_len, win_len)
        total = drop + drop_len
        for c in cards:
            if c["kind"] == "winner":
                c["dur"] = drop_len

        seqc = dict(seq); seqc["cards"] = cards
        seqc["song_drop_at"] = drop; seqc["total_dur"] = total
        build_ass(seqc, ass_path)
        base = _build_base(seqc, broll, tmp)

        # Audio graph: spoken lines delayed to their cards; the WINNER line spoken
        # at the drop; the song sliced + delayed to the drop and DUCKED under the
        # winner line so it cuts through the swell.
        inputs = ["-i", base]
        afilters = [f"[0:v]ass='{ass_path}'[v]"]
        alabels = []
        idx = 1
        for it in tts_items:
            inputs += ["-i", it["path"]]
            ms = int(it["start"] * 1000)
            afilters.append(f"[{idx}:a]adelay={ms}|{ms}[a{idx}]")
            alabels.append(f"[a{idx}]"); idx += 1

        win_label = None
        win_start = drop + WINNER_LEADIN
        if winner_tts:
            inputs += ["-i", winner_tts["path"]]
            wms = int(win_start * 1000)
            afilters.append(f"[{idx}:a]adelay={wms}|{wms}[win]")
            win_label = "[win]"; idx += 1

        if have_music:
            inputs += ["-ss", f"{music_start:.2f}", "-t", f"{drop_len:.2f}", "-i", music_path]
            ms = int(drop * 1000)
            fade_out_at = max(0.0, total - 0.8)
            mf = (f"[{idx}:a]adelay={ms}|{ms},afade=t=in:st={drop:.2f}:d=0.6,"
                  f"afade=t=out:st={fade_out_at:.2f}:d=0.8")
            if winner_tts:
                # Full song on the swell + tail; a steady lower bed only while the
                # winner speaks — no dead spots, and the line cuts through.
                ls = win_start - 0.2
                le = win_start + winner_tts["dur"] + 0.3
                mf += f",volume=volume='if(between(t,{ls:.2f},{le:.2f}),{MUSIC_DUCK},1)':eval=frame"
            afilters.append(mf + "[amus]"); idx += 1
            alabels.append("[amus]")

        if win_label:
            alabels.append(win_label)

        if alabels:
            if len(alabels) == 1:
                audio_map = alabels[0]
            else:
                afilters.append(f"{''.join(alabels)}amix=inputs={len(alabels)}:normalize=0[a]")
                audio_map = "[a]"
            cmd = (["ffmpeg", "-y"] + inputs +
                   ["-filter_complex", ";".join(afilters),
                    "-map", "[v]", "-map", audio_map, "-t", f"{total:.2f}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    out_path])
        else:
            cmd = ["ffmpeg", "-y", "-i", base, "-vf", f"ass='{ass_path}'",
                   "-t", f"{total:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                   "-an", out_path]
        _run(cmd)
    return out_path


def batch(sequences: list[dict], out_dir: str, music_path: str | None = None,
          broll: list[str] | None = None,
          music_start: float | None = None, music_chunk: float | None = None,
          voice: bool | None = None) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    out = []
    for seq in sequences:
        clip = os.path.join(out_dir, f"{seq['dilemma_id']}.mp4")
        try:
            out.append(render(seq, clip, music_path, broll, music_start, music_chunk, voice))
            print(f"[clipfarm] rendered {clip}  ({seq['total_dur']:.1f}s, winner {seq['winner_name']})")
        except Exception as e:
            print(f"[clipfarm] FAILED {seq['dilemma_id']}: {e}")
    return out


def capture_live(url: str, out_path: str, duration: float,
                 display: str | None = None, audio_dev: str = "default") -> str:
    """Screen-record the live /showdown reveal (x11grab video + pulse audio)."""
    display = display or os.environ.get("DISPLAY", ":0")
    cmd = ["ffmpeg", "-y",
           "-f", "x11grab", "-video_size", f"{W}x{H}", "-framerate", str(FPS), "-i", display,
           "-f", "pulse", "-i", audio_dev, "-t", f"{duration:.2f}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", out_path]
    subprocess.run(cmd, check=True)
    return out_path


def _load(path: str) -> dict:
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    # Render every saved showdown into clips (music + broll auto-discovered).
    #   python -m brain.clipfarm [music.mp3]
    import sys

    music = sys.argv[1] if len(sys.argv) > 1 else None
    here = os.path.dirname(os.path.abspath(__file__))
    seq_dir = os.path.join(_REPO, "scratch", "showdowns")
    out_dir = os.path.join(_REPO, "scratch", "clips")
    seqs = [_load(p) for p in sorted(glob.glob(os.path.join(seq_dir, "*.json")))]
    if not seqs:
        print(f"no sequences in {seq_dir} — run `python -m brain.showdown <id>` first")
    else:
        m = music or default_music()
        b = default_broll()
        chunk = float(MUSIC_CHUNK) if MUSIC_CHUNK else None
        print(f"[clipfarm] music={m or 'none'}  broll={len(b)} clips  interval={BROLL_INTERVAL}s  "
              f"song slice: start={MUSIC_START}s chunk={chunk or 'winner-hold'}")
        batch(seqs, out_dir, m, b)
