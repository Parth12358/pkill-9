"""Text-to-speech for the clip farm. (PRD B: clip voices)

Uses edge-tts — free, no key, dozens of distinct high-quality voices (one per
persona). It's an online service, which is fine because the clip farm is a
pre-production/batch tool; the LIVE demo voice stays the Mac's `say` (PRD A).

Each persona is cast a different voice in personas.py; the intro is read by a
narrator voice. edge-tts is imported lazily so the rest of the brain runs without
it. If TTS is unavailable, the clip farm silently renders without voice.
"""

import asyncio
import os
import subprocess


def is_available() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def synth(text: str, voice: str, out_path: str,
          rate: str = "+0%", pitch: str = "+0Hz", trim: bool = True) -> str | None:
    """Synthesize `text` in `voice` to an mp3. Trims leading/trailing silence so
    lines pace tightly. Returns the path, or None on failure (so a flaky network
    never breaks a render). Retries once on a transient error."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        import edge_tts
    except ImportError:
        return None

    async def _go():
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await comm.save(out_path)

    for attempt in (1, 2):
        try:
            asyncio.run(_go())
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return _trim(out_path) if trim else out_path
        except Exception as e:
            print(f"[tts] synth failed ({voice}, try {attempt}): {e}")
    return None


def _trim(path: str) -> str:
    """Trim leading + trailing near-silence (edge-tts pads clips) so pacing is tight."""
    trimmed = path.rsplit(".", 1)[0] + "_t.mp3"
    sr = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
          "areverse,"
          "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
          "areverse")
    proc = subprocess.run(["ffmpeg", "-y", "-i", path, "-af", sr, trimmed],
                          capture_output=True, text=True)
    if proc.returncode == 0 and os.path.exists(trimmed) and os.path.getsize(trimmed) > 0:
        return trimmed
    return path  # trimming is best-effort; fall back to the untrimmed clip


def duration(path: str) -> float:
    """Length of an audio file in seconds (0.0 if unreadable)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True,
        ).stdout.strip()
        return float(out)
    except (ValueError, subprocess.SubprocessError):
        return 0.0
