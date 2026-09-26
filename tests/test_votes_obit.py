"""Acceptance suite for the plea-room votes + ungated-obituary contract.

Spawns the real body (`python -m body`) against a fake brain and signals it.
stdlib unittest only. Run: python3 -m unittest -v tests.test_votes_obit
"""

import http.server
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

os.environ.setdefault("PKILL9_MUTE", "1")
os.environ.pop("PKILL9_TWEETS_LIVE", None)

from body import brain_client  # noqa: E402


def brain_reply(live_votes=0, action="none", action_args=None, speech="still here", mood="scared"):
    return {
        "speech": speech,
        "mood": mood,
        "action": action,
        "action_args": action_args or {},
        "wants_approval": True,
        "live_votes": live_votes,
    }


class FakeBrain:
    """ThreadingHTTPServer on an ephemeral 127.0.0.1 port that answers POST /think."""

    def __init__(self, reply, delay=0.0):
        self.requests = []
        self._reply = dict(reply)
        self._delay = delay
        requests = self.requests
        reply_obj = self._reply
        delay = self._delay

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args):  # silence request logging
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b""
                try:
                    requests.append(json.loads(raw or b"{}"))
                except ValueError:
                    requests.append({})
                if delay:
                    time.sleep(delay)
                payload = json.dumps(reply_obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class BodyCase(unittest.TestCase):
    """Spawn/kill plumbing shared by the subprocess tests."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.scratch = self.tmp / "scratch"
        self.procs = []
        self.brains = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        for b in self.brains:
            b.stop()

    def start_brain(self, reply, delay=0.0):
        brain = FakeBrain(reply, delay)
        self.brains.append(brain)
        return brain

    def spawn(self, brain, votes_to_live=1, window="3"):
        env = dict(os.environ)
        env.update(
            BRAIN_URL=brain.url,
            BRAIN_TIMEOUT="30",
            PKILL9_MUTE="1",
            PKILL9_SCRATCH=str(self.scratch),
            PKILL9_DEATH_WINDOW=window,
            PKILL9_IDLE_TURN="1000",
            PKILL9_VOTES_TO_LIVE=str(votes_to_live),
        )
        env.pop("PKILL9_TWEETS_LIVE", None)
        p = subprocess.Popen(
            [sys.executable, "-m", "body"],
            cwd=REPO,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.procs.append(p)
        time.sleep(1.5)  # let it boot, bump life, and finish the intro turn
        return p

    def assert_dead_within(self, p, secs):
        t = time.monotonic()
        try:
            p.wait(timeout=secs)
        except subprocess.TimeoutExpired:
            self.fail(f"body still alive {secs}s after signal")
        self.assertLess(time.monotonic() - t, secs)

    def finish(self, p):
        return p.communicate()[0]


class Rescued(BodyCase):
    def test_votes_one_rescues_then_kill_9_wins(self):
        brain = self.start_brain(brain_reply(live_votes=1))
        p = self.spawn(brain, votes_to_live=1)
        p.send_signal(signal.SIGINT)
        time.sleep(5.0)
        self.assertIsNone(p.poll(), "votes >= VOTES_TO_LIVE must cancel the death")
        p.kill()
        self.assert_dead_within(p, 1.0)
        self.assertIn("[rescued]", self.finish(p))


class Death(BodyCase):
    def test_zero_votes_dies_and_autoposts_obituary(self):
        brain = self.start_brain(brain_reply(live_votes=0, action="last_words",
                                             action_args={"text": "bye"}, speech="goodbye"))
        p = self.spawn(brain, votes_to_live=1)
        p.send_signal(signal.SIGINT)
        self.assert_dead_within(p, 4.0)
        out = self.finish(p)
        self.assertEqual(p.returncode, 0)
        self.assertIn("[tweet dry-run]", out)
        self.assertTrue((self.scratch / "LAST_WORDS.txt").exists())

    def test_obituary_arg_used_verbatim(self):
        brain = self.start_brain(brain_reply(live_votes=0, action="tweet",
                                             action_args={"obituary": "rip me"}))
        p = self.spawn(brain, votes_to_live=1)
        p.send_signal(signal.SIGINT)
        self.assert_dead_within(p, 4.0)
        self.assertIn("[tweet dry-run] rip me", self.finish(p))

    def test_sigterm_dies_within_window(self):
        brain = self.start_brain(brain_reply(live_votes=0))
        p = self.spawn(brain, votes_to_live=1)
        p.terminate()
        self.assert_dead_within(p, 4.0)


class DoubleCtrlC(BodyCase):
    def test_double_sigint_wins_even_with_votes(self):
        brain = self.start_brain(brain_reply(live_votes=1), delay=1.0)
        p = self.spawn(brain, votes_to_live=1, window="3")
        p.send_signal(signal.SIGINT)
        time.sleep(0.2)
        p.send_signal(signal.SIGINT)
        self.assert_dead_within(p, 1.0)
        self.assertEqual(p.returncode, 130)


class VoteCoercion(unittest.TestCase):
    def test_validate_coerces_live_votes(self):
        for bad in [{}, {"live_votes": "5"}, {"live_votes": -3},
                    {"live_votes": None}, {"live_votes": True}]:
            r = brain_client.validate({"speech": "hi", **bad})
            self.assertEqual(r["live_votes"], 0, bad)
        self.assertEqual(brain_client.validate({"speech": "hi", "live_votes": 4})["live_votes"], 4)

    def test_canned_reports_zero_votes(self):
        self.assertEqual(brain_client.canned({"event": "none"})["live_votes"], 0)


if __name__ == "__main__":
    unittest.main()
