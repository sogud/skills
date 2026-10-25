#!/usr/bin/env python3
"""No live Herdr mutations or model calls."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import supervise as s


def info(pane, status="idle", seq=1, session="a"):
    return {"pane_id": pane, "terminal_id": "term-" + pane,
            "agent_session": {"value": session}, "agent_status": status,
            "state_change_seq": seq}


class Tests(unittest.TestCase):
    def test_initial_idle_is_not_completion(self):
        w, p = info("w:p2"), info("w:p1")
        watch = s.Watch(w, p, 0)
        for now in (1, 31, 400):
            self.assertIsNone(watch.sample(w, p, now))
        self.assertFalse(watch.started)

    def test_fast_task_detected_by_state_sequence(self):
        w, p = info("w:p2"), info("w:p1")
        watch = s.Watch(w, p, 0)
        finished = info("w:p2", "idle", 3)
        self.assertIsNone(watch.sample(finished, p, 30))
        self.assertEqual(watch.sample(finished, p, 60)["kind"], "review")
        self.assertTrue(watch.delivered(60))

    def test_busy_parent_keeps_notice_then_delivers(self):
        w, p = info("w:p2", "working"), info("w:p1", "working")
        watch = s.Watch(w, p, 0)
        w = info("w:p2", "done", 2)
        self.assertIsNone(watch.sample(w, p, 30))
        self.assertIsNone(watch.sample(w, p, 60))
        self.assertIsNotNone(watch.pending)
        self.assertEqual(watch.sample(w, info("w:p1"), 90)["kind"], "review")

    def test_blocked_parent_is_not_prompted(self):
        w, p = info("w:p2", "blocked"), info("w:p1", "blocked")
        watch = s.Watch(w, p, 0, observe_current=True)
        watch.sample(w, p, 30)
        self.assertIsNone(watch.sample(w, p, 60))
        self.assertEqual(watch.pending["workerStatus"], "blocked")

    def test_transient_idle_does_not_complete(self):
        w, p = info("w:p2", "working"), info("w:p1")
        watch = s.Watch(w, p, 0)
        self.assertIsNone(watch.sample(info("w:p2", "idle", 2), p, 30))
        self.assertIsNone(watch.sample(info("w:p2", "working", 3), p, 60))
        self.assertIsNone(watch.pending)

    def test_inspection_is_rate_limited(self):
        w, p = info("w:p2", "working"), info("w:p1")
        watch = s.Watch(w, p, 0)
        self.assertIsNone(watch.sample(w, p, 299))
        self.assertEqual(watch.sample(w, p, 300)["kind"], "inspection")
        self.assertFalse(watch.delivered(300))
        self.assertIsNone(watch.sample(w, p, 301))
        self.assertEqual(watch.sample(w, p, 600)["kind"], "inspection")

    def test_session_replacement_stops(self):
        w, p = info("w:p2"), info("w:p1")
        watch = s.Watch(w, p, 0)
        with self.assertRaisesRegex(RuntimeError, "session changed"):
            watch.sample(info("w:p2", session="new"), p, 1)
        with self.assertRaisesRegex(RuntimeError, "session changed"):
            watch.sample(w, info("w:p1", session="new"), 1)

    def test_missing_identity_and_same_pane_rejected(self):
        with self.assertRaises(RuntimeError):
            s.identity({"pane_id": "p1"})
        with self.assertRaises(ValueError):
            s.Watch(info("p1"), info("p1"), 0)

    def test_start_preserves_explicit_options(self):
        with tempfile.TemporaryDirectory() as directory:
            a = argparse.Namespace(cwd=Path(directory), name="worker", pane="w:p2",
                                   model="qmodel", yolo=False)
            command = s.start_command(a)
            self.assertEqual(command[command.index("--kind") + 1], "qodercli")
            self.assertEqual(command[command.index("--model") + 1], "qmodel")
            self.assertNotIn("--yolo", command)
            a.yolo = True
            self.assertEqual(s.start_command(a)[-1], "--yolo")
        with self.assertRaises(ValueError):
            s.start_command(a)

    def test_pair_lock_prevents_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = s.acquire(Path(directory), "p2", "p1")
            try:
                with self.assertRaisesRegex(RuntimeError, "already owns"):
                    s.acquire(Path(directory), "p2", "p1")
            finally:
                lock.unlink()

    def run_fake_watch(self, directory, failure=False):
        a = argparse.Namespace(job="test", root=Path(directory), report=Path(directory)/"report.md",
                               worker="worker", parent="parent", background=False,
                               observe_current_terminal=True, inspect_seconds=300,
                               max_seconds=60, poll_seconds=5)
        def read(target):
            return info("p2", "done") if target == "worker" else info("p1")
        def call(*args):
            if failure and args[:2] == ("agent", "prompt"):
                raise RuntimeError("Submission may have reached server")
            return {"type": "agent_prompted"}
        with patch.object(s, "agent", side_effect=read), patch.object(s, "cli", side_effect=call) as mock_cli, \
             patch.object(s.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            if failure:
                with self.assertRaises(RuntimeError):
                    s.watch(a)
            else:
                s.watch(a)
        state = json.loads((Path(directory)/".artifacts/herdr-watch/test.json").read_text())
        calls = [c for c in mock_cli.call_args_list if c.args[:2] == ("agent", "prompt")]
        self.assertEqual(len(calls), 1)
        self.assertFalse(list((Path(directory)/".artifacts/herdr-watch").glob("*.lock")))
        return state

    def test_delivery_success_is_not_task_success(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self.run_fake_watch(directory)
            self.assertEqual(state["status"], "notified")
            self.assertEqual(state["delivery"], "accepted")
            self.assertEqual(state["notifications"], 1)

    def test_ambiguous_delivery_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self.run_fake_watch(directory, failure=True)
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["delivery"], "uncertain-do-not-retry")

    def test_initial_read_failure_is_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            a = argparse.Namespace(job="init-failure", root=Path(directory), report=Path(directory)/"report.md",
                                   worker="worker", parent="parent", background=False,
                                   observe_current_terminal=False, inspect_seconds=300,
                                   max_seconds=60, poll_seconds=5)
            with patch.object(s, "agent", side_effect=RuntimeError("offline")), \
                 patch.object(s, "cli") as notify, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    s.watch(a)
            state = json.loads((Path(directory)/".artifacts/herdr-watch/init-failure.json").read_text())
            self.assertEqual(state["status"], "failed")
            notify.assert_not_called()

    def test_registration_timeout_reaps_only_owned_child(self):
        with tempfile.TemporaryDirectory() as directory:
            child = unittest.mock.Mock(pid=123)
            child.poll.return_value = None
            path = Path(directory)/"state.json"
            s.cancel_registration(child, path, "timeout")
            child.terminate.assert_called_once_with()
            child.wait.assert_called_once_with(timeout=5)
            child.kill.assert_not_called()
            self.assertEqual(json.loads(path.read_text())["status"], "failed")

    def test_delivery_preflight_rechecks_parent(self):
        expected = s.identity(info("p1"))
        with patch.object(s, "agent", return_value=info("p1", "blocked")):
            self.assertFalse(s.parent_ready("parent", expected))
        with patch.object(s, "agent", return_value=info("p1", session="replacement")):
            with self.assertRaisesRegex(RuntimeError, "session changed"):
                s.parent_ready("parent", expected)


if __name__ == "__main__":
    unittest.main()
