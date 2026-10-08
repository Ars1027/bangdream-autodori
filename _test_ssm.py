"""Offline integration tests for the Python-to-Go SSM playback bridge."""

import ast
import logging
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from ssm_playback import SSMPlayback


class SSMBridgeTests(unittest.TestCase):
    def setUp(self):
        self.playback = SSMPlayback("offline", (1280, 720), offline=True)

    def tearDown(self):
        self.playback.close()

    def test_first_note_deadline_and_normal_completion(self):
        stats = self.playback.prepare([{"type": "Single", "time": 4000, "lane": 1}])
        self.assertEqual(stats["touch_count"], 2)
        self.assertEqual(stats["first_ms"], 4000)
        self.assertEqual(stats["duration_ms"], 10)
        due = time.perf_counter() + 0.15
        self.playback.start(due)
        self.assertIsNone(self.playback.poll(0.05))
        done = self.playback._wait_for("done", 2)
        self.assertFalse(done["stopped"])
        self.assertGreaterEqual(time.perf_counter(), due)

    def test_stop_and_prepare_next_song(self):
        self.playback.prepare([{"type": "Long", "connections": [
            {"time": 0, "lane": 1}, {"time": 10000, "lane": 1},
        ]}])
        self.playback.start(time.perf_counter())
        self.playback.stop()
        stats = self.playback.prepare([{"type": "Directional", "time": 0,
                                       "lane": 4, "width": 1, "direction": "Left"}])
        self.assertEqual(stats["duration_ms"], 65)
        self.playback.start(time.perf_counter())
        self.assertFalse(self.playback._wait_for("done", 2)["stopped"])

    def test_close_cancels_playback_and_exits_process(self):
        self.playback.prepare([{"type": "Long", "connections": [
            {"time": 0, "lane": 1}, {"time": 10000, "lane": 1},
        ]}])
        self.playback.start(time.perf_counter())
        process = self.playback._process
        self.playback.close()
        self.assertEqual(process.returncode, 0)


class AutodoriFlowTests(unittest.TestCase):
    def setUp(self):
        # Load the production callers without running module-level API/MAA setup.
        source = Path(__file__).resolve().parent / "src" / "autodori.py"
        functions = [node for node in ast.parse(source.read_text("utf-8")).body
                     if isinstance(node, ast.FunctionDef) and node.name in {"save_song", "play_song"}]
        self.backend = mock.Mock(stats={"touch_count": 2})
        self.clock = mock.Mock()
        self.clock.perf_counter.side_effect = [0, 1.1, 1.2]
        self.globals = {
            "logging": logging, "time": self.clock, "current_playback": self.backend,
            "current_song_name": "synthetic", "current_song_id": "0", "DIFFICULTY": "hard",
            "PHOTOGATE_LATENCY": 46, "_reload_photogate": mock.Mock(),
            "wait_first_note": mock.Mock(return_value=42.046),
            "_life_exhausted_on_screen": mock.Mock(return_value="no_match"),
            "LifeExhaustedDetected": type("LifeExhaustedDetected", (Exception,), {}),
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), self.globals)

    def test_play_passes_deadline_and_preserves_no_match_life_check(self):
        self.backend.poll.side_effect = [None, {"event": "done", "stopped": False}]
        self.globals["play_song"](object())
        self.backend.start.assert_called_once_with(42.046)
        self.backend.stop.assert_not_called()
        self.globals["_life_exhausted_on_screen"].assert_called_once()

    def test_life_exhaustion_stops_go_playback(self):
        self.backend.poll.return_value = None
        self.globals["_life_exhausted_on_screen"].return_value = "hit"
        with self.assertRaises(self.globals["LifeExhaustedDetected"]):
            self.globals["play_song"](object())
        self.backend.stop.assert_called_once()

    def test_save_song_uses_ssm_instead_of_old_touch_compiler(self):
        chart = mock.Mock(_chart_data=[{"type": "Single", "time": 0, "lane": 1}])
        self.globals.update({"_resolved_song_id": None, "all_song_name_indexes": {"synthetic": "0"},
                             "Chart": mock.Mock(return_value=chart)})
        self.backend.prepare.return_value = {"touch_count": 2, "event_count": 2,
                                             "pointers": 1, "duration_ms": 10}
        self.globals["save_song"]("synthetic")
        self.backend.prepare.assert_called_once_with(chart._chart_data)
        chart.notes_to_actions.assert_not_called()
        chart.actions_to_MNTcmd.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
