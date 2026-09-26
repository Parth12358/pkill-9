"""Auto clip farm: render showdown sequences into vertical shorts. (PRD B: clip farm)

Pure ffmpeg (libass + libx264) — no TTS, no moviepy. The "love me love me" reel
format is captions + music, so each clip is:

  9:16 (1080x1920), dark background, each answer revealed as a caption card in
  turn, then the WINNER's line held big while the song drops.

Batch many dilemmas into many clips. Bring your own royalty-free "Love Me"
SOUNDALIKE for anything uploaded to Devpost; save the real trending audio for your
own social posts (the real track is copyrighted).

Also provides capture_live() to screen-record the live /showdown reveal (x11grab +
pulse) for the in-person demo.
"""

import os
import subprocess

W, H, FPS = 1080, 1920, 30
BG = "0x07070c"
FONT = os.environ.get("CLIP_FONT", "Liberation Sans")


def _hex_to_ass(color: str) -> str:
    """#rrggbb -> ASS &HBBGGRR& (ASS colors are BGR)."""
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
    """Write an .ass subtitle script with one timed event per card."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: name,{FONT},64,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,2,5,90,90,90,1
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
        else:  # answer
            winner_tag = "  ✦" if c.get("is_winner") else ""
            body = (f"{fade}{{\\c{col}\\fs70\\b1}}{_esc(c['name'])}{winner_tag}\\N\\N"
                    f"{{\\c&H00FFFFFF&\\fs78\\b0}}{_esc(c['text'])}")
        lines.append(f"Dialogue: 0,{start},{end},body,,0,0,0,,{body}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def render(seq: dict, out_path: str, music_path: str | None = None) -> str:
    """Render one sequence to a 9:16 mp4. If music_path is given, the song starts
    (drops) at seq['song_drop_at'] over the winner reveal."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    ass_path = out_path.rsplit(".", 1)[0] + ".ass"
    build_ass(seq, ass_path)
    total = float(seq["total_dur"])
    drop_ms = int(float(seq.get("song_drop_at", 0)) * 1000)

    base = ["ffmpeg", "-y", "-f", "lavfi", "-i",
            f"color=c={BG}:s={W}x{H}:d={total:.2f}:r={FPS}"]

    if music_path and os.path.exists(music_path):
        cmd = base + [
            "-i", music_path,
            "-filter_complex",
            f"[0:v]ass='{ass_path}'[v];[1:a]adelay={drop_ms}|{drop_ms},"
            f"afade=t=in:st={drop_ms/1000:.2f}:d=0.6[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            out_path,
        ]
    else:
        cmd = base + ["-vf", f"ass='{ass_path}'", "-t", f"{total:.2f}",
                      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", out_path]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-600:]}")
    return out_path


def batch(sequences: list[dict], out_dir: str, music_path: str | None = None) -> list[str]:
    """Render many sequences into many clips."""
    os.makedirs(out_dir, exist_ok=True)
    out = []
    for seq in sequences:
        clip = os.path.join(out_dir, f"{seq['dilemma_id']}.mp4")
        try:
            out.append(render(seq, clip, music_path))
            print(f"[clipfarm] rendered {clip}  ({seq['total_dur']:.1f}s, winner {seq['winner_name']})")
        except Exception as e:
            print(f"[clipfarm] FAILED {seq['dilemma_id']}: {e}")
    return out


def capture_live(url: str, out_path: str, duration: float,
                 display: str | None = None, audio_dev: str = "default") -> str:
    """Screen-record the live /showdown reveal (x11grab video + pulse audio) for
    the in-person demo. `url` is informational; point a browser at it fullscreen
    first, or pass a region. Requires an X session + PulseAudio."""
    display = display or os.environ.get("DISPLAY", ":0")
    cmd = [
        "ffmpeg", "-y",
        "-f", "x11grab", "-video_size", f"{W}x{H}", "-framerate", str(FPS), "-i", display,
        "-f", "pulse", "-i", audio_dev,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def _load(path: str) -> dict:
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    # Render every saved showdown into clips.
    #   python -m brain.clipfarm [music.mp3]
    import glob
    import sys

    music = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CLIP_MUSIC")
    here = os.path.dirname(os.path.abspath(__file__))
    seq_dir = os.path.join(os.path.dirname(here), "scratch", "showdowns")
    out_dir = os.path.join(os.path.dirname(here), "scratch", "clips")
    seqs = [_load(p) for p in sorted(glob.glob(os.path.join(seq_dir, "*.json")))]
    if not seqs:
        print(f"no sequences in {seq_dir} — run `python -m brain.showdown <id>` first")
    else:
        batch(seqs, out_dir, music)
