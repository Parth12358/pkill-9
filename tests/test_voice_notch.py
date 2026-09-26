"""Voice envelope + notch overlay plumbing. Run: python3 -m unittest -v"""

import math
import os
import struct
import tempfile
import unittest
import wave
from unittest import mock

os.environ["PKILL9_MUTE"] = "1"

from body import voice  # noqa: E402


class Envelope(unittest.TestCase):
    def test_silence_then_loud(self):
        path = os.path.join(tempfile.mkdtemp(), "t.wav")
        rate = 22050
        frames = [0] * (rate // 2) + [int(20000 * math.sin(i / 5)) for i in range(rate // 2)]
        with wave.open(path, "w") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
            w.writeframes(struct.pack(f"<{len(frames)}h", *frames))
        env = voice.envelope(path, fps=60)
        self.assertLessEqual(abs(len(env) - 60), 1)
        self.assertTrue(all(0 <= v <= 1 for v in env))
        self.assertLess(max(env[:25]), 0.05)
        self.assertGreater(min(env[35:]), 0.9)


class Overlay(unittest.TestCase):
    def test_broken_pipe_disables_quietly(self):
        fake = mock.Mock()
        fake.stdin.write.side_effect = BrokenPipeError
        voice._notch = fake
        voice.notch({"type": "stop"})  # must not raise
        self.assertIsNone(voice._notch)

    def test_mute_spawns_nothing(self):
        with mock.patch("subprocess.Popen") as po, mock.patch("subprocess.run") as ru:
            voice.start_notch()
            voice.speak("hello", "grand")
            po.assert_not_called()
            ru.assert_not_called()


if __name__ == "__main__":
    unittest.main()
