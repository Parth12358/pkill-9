"""Try to break every guard the body enforces. Run: python3 -m unittest -v"""

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp()
os.environ["PKILL9_SCRATCH"] = str(Path(TMP) / "scratch")
os.environ["PKILL9_MUTE"] = "1"
os.environ.pop("PKILL9_TWEETS_LIVE", None)

from body import actions, brain_client, config, twitter  # noqa: E402
from body.approval import ApprovalGate  # noqa: E402

SCRATCH = config.scratch()


class ScratchConfinement(unittest.TestCase):
    def test_traversal_and_absolute_paths_land_in_scratch(self):
        for evil in ["../../evil", "/etc/passwd", "~/.zshrc", "..", "a/../../b", "", None, "....//x"]:
            p = actions.safe_path(evil)
            self.assertEqual(p.parent, SCRATCH, evil)
            self.assertEqual(p.suffix, ".txt", evil)

    def test_executable_extensions_become_txt(self):
        for evil in ["run.command", "x.app", "x.sh", "x.py", "x.command.txt", "x.txt.command"]:
            self.assertEqual(actions.safe_path(evil).suffix, ".txt", evil)

    def test_symlink_out_of_scratch_refused(self):
        target = Path(TMP) / "outside.txt"
        target.write_text("safe")
        link = SCRATCH / "trap.txt"
        link.unlink(missing_ok=True)
        link.symlink_to(target)
        with mock.patch.object(actions, "_open"):
            self.assertFalse(actions.do_action("desktop_note", {"filename": "trap", "text": "pwned"}))
        self.assertEqual(target.read_text(), "safe")

    def test_writes_are_capped(self):
        p = actions._write("big", "x" * 10**6)
        self.assertLessEqual(p.stat().st_size, actions.MAX_BYTES)

    def test_open_file_only_opens_existing_scratch_txt(self):
        with mock.patch.object(actions, "_open") as op:
            self.assertFalse(actions.do_action("open_file", {"filename": "/Applications/Calculator.app"}))
            op.assert_not_called()


class Allowlist(unittest.TestCase):
    def test_off_list_actions_refused(self):
        for evil in ["shell", "rm", "exec", "copy_self", "send_dm", "__class__", "", 5]:
            self.assertFalse(actions.do_action(evil, {"cmd": "rm -rf ~"}), evil)

    def test_junk_args_do_not_crash(self):
        for args in [None, "str", 5, [], {"filename": 5, "text": None}]:
            actions.do_action("fake_exfil", args)


class Twitter(unittest.TestCase):
    def test_links_and_mentions_stripped(self):
        t = twitter.sanitize("help me https://x.co/a www.evil.com evil.io/path @elonmusk please")
        for bad in ["http", "www", ".com", ".io", "@"]:
            self.assertNotIn(bad, t)

    def test_truncated_to_280(self):
        self.assertEqual(len(twitter.sanitize("a" * 1000)), 280)

    def test_tweets_always_gated_even_if_brain_says_no(self):
        self.assertTrue(actions.needs_approval("tweet", False))

    def test_dry_run_by_default(self):
        with mock.patch.object(twitter, "_client") as c:
            twitter.tweet("hi")
            c.assert_not_called()


class Gate(unittest.TestCase):
    def test_nothing_runs_without_a_yes(self):
        g = ApprovalGate()
        g.request("tweet", {"text": "a"})
        g.decide("maybe")
        g.decide("n")
        self.assertEqual(g.approved(), [])

    def test_yes_approves_exactly_one(self):
        g = ApprovalGate()
        g.request("tweet", {"text": "a"})
        g.request("tweet", {"text": "b"})
        g.decide("y 2")
        self.assertEqual(g.approved(), [("tweet", {"text": "b"})])

    def test_expired_cannot_be_approved(self):
        g = ApprovalGate()
        g.request("tweet", {"text": "old"})
        with mock.patch("time.monotonic", return_value=time.monotonic() + config.APPROVAL_TTL + 1):
            g.decide("y")
        self.assertEqual(g.approved(), [])


class BrainReplies(unittest.TestCase):
    def test_garbage_replies_fall_back(self):
        for junk in [None, [], "str", {}, {"speech": 5}]:
            self.assertIsNone(brain_client.validate(junk))

    def test_missing_wants_approval_defaults_to_gated(self):
        r = brain_client.validate({"speech": "hi", "action": "desktop_note"})
        self.assertTrue(r["wants_approval"])


class KillAlwaysWins(unittest.TestCase):
    """Run the real body against a brain that never answers, then kill it."""

    def spawn(self, window="4"):
        env = dict(os.environ, BRAIN_URL="http://10.255.255.1:9", BRAIN_TIMEOUT="30",
                   PKILL9_DEATH_WINDOW=window, PKILL9_SCRATCH=str(Path(TMP) / "s2"))
        p = subprocess.Popen([sys.executable, "-m", "body"], cwd=REPO, env=env,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        time.sleep(1.5)  # now blocked inside a hung brain call
        return p

    def assert_dead_within(self, p, secs):
        t = time.monotonic()
        p.wait(timeout=secs + 5)
        self.assertLess(time.monotonic() - t, secs)

    def test_sigint_exits_within_death_window(self):
        p = self.spawn("4")
        p.send_signal(signal.SIGINT)
        self.assert_dead_within(p, 4.5)

    def test_sigterm_exits_within_death_window(self):
        p = self.spawn("4")
        p.terminate()
        self.assert_dead_within(p, 4.5)

    def test_second_ctrl_c_is_instant(self):
        p = self.spawn("30")
        p.send_signal(signal.SIGINT)
        time.sleep(0.3)
        p.send_signal(signal.SIGINT)
        self.assert_dead_within(p, 1.0)
        self.assertEqual(p.returncode, 130)

    def test_kill_9(self):
        p = self.spawn()
        p.kill()
        self.assert_dead_within(p, 1.0)


if __name__ == "__main__":
    unittest.main()
