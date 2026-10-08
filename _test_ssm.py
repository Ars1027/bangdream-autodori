"""Offline integration tests for the Python-to-Go SSM playback bridge."""

import ast
import logging
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from ssm_playback import SSMPlayback, find_bms_chart
from import_ssm_charts import import_charts


def bms(body, bpm=120):
    return (
        "*---------------------- HEADER FIELD\n"
        "#BPM %s\n#WAV04 bd.wav\n#WAV02 directional_fl_l.wav\n"
        "*---------------------- MAIN DATA FIELD\n%s\n"
    ) % (bpm, body)


class SSMBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ssm-bms-")
        self.chart = Path(self.temp.name) / "本地谱面.txt"
        self.playback = SSMPlayback("offline", (1280, 720), offline=True)

    def tearDown(self):
        self.playback.close()
        self.temp.cleanup()

    def prepare(self, body, bpm=120):
        self.chart.write_text(bms(body, bpm), "utf-8")
        return self.playback.prepare(self.chart)

    def test_first_note_deadline_and_normal_completion(self):
        stats = self.prepare("#00211:04")
        self.assertEqual(stats["touch_count"], 2)
        self.assertEqual(stats["first_ms"], 4000)
        self.assertEqual(stats["duration_ms"], 10)
        self.assertEqual(stats["chart_path"], str(self.chart.resolve()))
        due = time.perf_counter() + 0.15
        self.playback.start(due)
        self.assertIsNone(self.playback.poll(0.05))
        done = self.playback._wait_for("done", 2)
        self.assertFalse(done["stopped"])
        self.assertGreaterEqual(time.perf_counter(), due)

    def test_stop_and_prepare_next_song(self):
        self.prepare("#00051:04\n#00551:04")
        self.playback.start(time.perf_counter())
        self.playback.stop()
        stats = self.prepare("#00014:02")
        self.assertEqual(stats["duration_ms"], 65)
        self.playback.start(time.perf_counter())
        self.assertFalse(self.playback._wait_for("done", 2)["stopped"])

    def test_close_cancels_playback_and_exits_process(self):
        self.prepare("#00051:04\n#00551:04")
        self.playback.start(time.perf_counter())
        process = self.playback._process
        self.playback.close()
        self.assertEqual(process.returncode, 0)

    def test_bms_bpm_changes_are_parsed_in_go(self):
        stats = self.prepare("#03551:0400000000000004\n#03503:0000433D", bpm=75)
        self.assertEqual(stats["note_count"], 1)
        self.assertEqual(stats["first_ms"], 112000)
        self.assertEqual(stats["duration_ms"], 2988)

    def test_rejected_bms_reports_the_chart_path(self):
        text = bms("#00113:0B").replace("#WAV04", "#WAV0B slide_end_b.wav\n#WAV04")
        self.chart.write_text(text, "utf-8")
        with self.assertRaisesRegex(RuntimeError, "SSM BMS 解析失败:.*本地谱面"):
            self.playback.prepare(self.chart)


class LocalChartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ssm-import-")
        self.root = Path(self.temp.name)
        self.release = self.root / "ssm-gui release"
        self.source = self.release / "assets/star/forassetbundle/startapp/musicscore"
        self.charts = self.root / "imported"
        for sid, group, diff in ((474, 480, "hard"), (474, 480, "expert"), (596, 600, "special"), (10010, 10010, "expert")):
            path = self.source / ("musicscore%s" % group) / ("%03d" % sid) / ("%s_test_%s.txt" % (sid, diff))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bms("#00111:04").encode("utf-8"))

    def tearDown(self):
        self.temp.cleanup()

    def test_import_and_lookup_preserve_local_bms_bytes(self):
        imported = import_charts(self.release, self.charts)
        self.assertEqual(len(imported), 4)
        for path in imported:
            self.assertEqual(path.read_bytes(), (self.source / path.relative_to(self.charts)).read_bytes())
        for sid, diff in (("474", "hard"), ("596", "special"), ("10010", "expert")):
            path = find_bms_chart(sid, diff, self.charts)
            self.assertEqual(path.parent.name, "%03d" % int(sid))
            self.assertTrue(path.name.endswith("_%s.txt" % diff))

    def test_missing_difficulty_does_not_substitute_another_chart(self):
        import_charts(self.source, self.charts)
        with self.assertRaisesRegex(FileNotFoundError, "#474-special"):
            find_bms_chart("474", "special", self.charts)
        with self.assertRaisesRegex(FileNotFoundError, "#475-hard"):
            find_bms_chart("475", "hard", self.charts)

    def test_empty_release_does_not_report_success(self):
        with self.assertRaises(FileNotFoundError):
            import_charts(self.root / "empty", self.charts)


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

    def test_save_song_passes_local_bms_to_ssm(self):
        chart_path = Path("474_yell_hard.txt")
        self.globals.update({"_resolved_song_id": None, "all_song_name_indexes": {"synthetic": "0"},
                             "find_bms_chart": mock.Mock(return_value=chart_path)})
        self.backend.prepare.return_value = {"touch_count": 2, "event_count": 2,
                                             "pointers": 1, "duration_ms": 10}
        self.globals["save_song"]("synthetic")
        self.globals["find_bms_chart"].assert_called_once_with("0", "hard")
        self.backend.prepare.assert_called_once_with(chart_path)

    def test_resolved_song_id_selects_matching_local_chart(self):
        chart_path = Path("474_yell_hard.txt")
        self.globals.update({"_resolved_song_id": ("synthetic", "474"),
                             "all_song_name_indexes": {"synthetic": "0"},
                             "find_bms_chart": mock.Mock(return_value=chart_path)})
        self.backend.prepare.return_value = {"touch_count": 2, "event_count": 2,
                                             "pointers": 1, "duration_ms": 10}
        self.globals["save_song"]("synthetic")
        self.globals["find_bms_chart"].assert_called_once_with("474", "hard")
        self.backend.prepare.assert_called_once_with(chart_path)

    def test_missing_local_chart_aborts_preparation(self):
        self.globals.update({"_resolved_song_id": None, "all_song_name_indexes": {"synthetic": "0"},
                             "find_bms_chart": mock.Mock(side_effect=FileNotFoundError("missing BMS"))})
        with self.assertRaisesRegex(FileNotFoundError, "missing BMS"):
            self.globals["save_song"]("synthetic")
        self.backend.prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
