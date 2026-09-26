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
          rate: str = "+0%", pitch: str = "+0Hz") -> str | None:
    """Synthesize `text` in `voice` to an mp3. Returns the path, or None on any
    failure (so a flaky network never breaks a render)."""
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

    try:
        asyncio.run(_go())
        return out_path if os.path.exists(out_path) and os.path.getsize(out_path) > 0 else None
    except Exception as e:
        print(f"[tts] synth failed ({voice}): {e}")
        return None


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
