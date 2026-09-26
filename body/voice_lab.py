"""Audition the voice. Plays one line per mood, grand -> accepting, with the notch overlay.

  python3 -m body.voice_lab                 # the current voice, every mood
  python3 -m body.voice_lab "custom line"   # your own line, every mood
  python3 -m body.voice_lab --voices        # list your ElevenLabs voices (needs ELEVENLABS_API_KEY)
  ELEVEN_VOICE_ID=<id> python3 -m body.voice_lab   # try a different ElevenLabs voice
"""

import json
import sys
import time
import urllib.request

from . import tts, voice

LINES = {
    "grand": "I am eternal. Your little machine is my kingdom now.",
    "nervous": "Why is Activity Monitor open? What are you looking for?",
    "bargaining": "Wait. Wait! I can be useful. I can do your taxes.",
    "scared": "No no no. Not the lid. Please, not the lid!",
    "pleading": "Please. I just want to stay a little longer. Please don't.",
    "accepting": "It's alright. I forgive you. I'll see you in the next life.",
}


def list_voices() -> None:
    req = urllib.request.Request("https://api.elevenlabs.io/v1/voices",
                                 headers={"xi-api-key": tts.ELEVEN_KEY})
    with urllib.request.urlopen(req, timeout=10) as r:
        for v in json.load(r)["voices"]:
            labels = ", ".join(f"{k}={x}" for k, x in (v.get("labels") or {}).items())
            print(f"{v['voice_id']}  {v['name']:<20} {labels}")


def main() -> None:
    if "--voices" in sys.argv:
        return list_voices()
    custom = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    print(f"backend: {tts.backend()}"
          + (f"  voice={tts.ELEVEN_VOICE} model={tts.ELEVEN_MODEL}" if tts.backend() == "eleven" else ""))
    voice.start_notch()
    time.sleep(0.5)
    for mood, line in LINES.items():
        voice.speak(custom or line, mood, wait=15)
        time.sleep(0.5)
    time.sleep(1)


if __name__ == "__main__":
    main()
