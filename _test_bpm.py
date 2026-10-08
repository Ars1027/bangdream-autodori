"""Offline BPM timing regression tests. Run with: python _test_bpm.py."""

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


class BPMTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # chart/api create a database and cache during import; isolate both.
        cls.workspace = tempfile.TemporaryDirectory()
        previous_cwd = Path.cwd()
        try:
            os.chdir(cls.workspace.name)
            Path("data").mkdir()
            import chart

            cls.chart_module = chart
        finally:
            os.chdir(previous_cwd)

    @classmethod
    def tearDownClass(cls):
        cls.chart_module.PlayRecord._meta.database.close()
        cls.chart_module.BestdoriAPI._cache.close()
        cls.workspace.cleanup()

    def build(self, notes):
        with mock.patch.object(
            self.chart_module.BestdoriAPI,
            "get_chart",
            return_value=copy.deepcopy(notes),
        ):
            return self.chart_module.Chart(("0", "hard"), "bpm-regression")

    def test_yell_long_crosses_two_later_bpm_changes(self):
        # YELL HARD: the old parser releases this tail 187.326 ms early.
        chart = self.build([
            {"type": "BPM", "bpm": 75, "beat": 0},
            {"type": "Long", "connections": [
                {"lane": 6, "beat": 140},
                {"lane": 6, "beat": 143.5},
            ]},
            {"type": "BPM", "bpm": 67, "beat": 142},
            {"type": "BPM", "bpm": 61, "beat": 143},
        ])
        head, tail = chart._chart_data[1]["connections"]
        self.assertAlmostEqual(head["time"], 112000.0)
        self.assertAlmostEqual(tail["time"], 114987.325666748, places=6)

    def test_slide_times_include_changes_after_its_head(self):
        chart = self.build([
            {"type": "BPM", "bpm": 120, "beat": 0},
            {"type": "Slide", "connections": [
                {"lane": 1, "beat": 1},
                {"lane": 2, "beat": 3, "hidden": True},
                {"lane": 4, "beat": 5, "flick": True},
            ]},
            {"type": "BPM", "bpm": 60, "beat": 2},
            {"type": "BPM", "bpm": 240, "beat": 4},
        ])
        connections = chart._chart_data[1]["connections"]
        self.assertEqual([c["time"] for c in connections], [500, 2000, 3250])
        self.assertEqual(connections[0]["checkpoint_index"], 0)
        self.assertNotIn("checkpoint_index", connections[1])
        self.assertEqual(connections[2]["checkpoint_index"], 1)
        self.assertTrue(connections[2]["flick"])

    def test_bpm_timeline_is_sorted_without_reordering_notes(self):
        notes = [
            {"type": "BPM", "bpm": 60, "beat": 4},
            {"type": "BPM", "bpm": 240, "beat": 2},
            {"type": "Single", "lane": 0, "beat": 5},
            {"type": "BPM", "bpm": 120, "beat": 0},
        ]
        chart = self.build(notes)
        self.assertEqual(chart._bpms, [(120, 0), (240, 2), (60, 4)])
        self.assertEqual(chart._chart_data[2]["time"], 2500)
        self.assertEqual(
            [n["type"] for n in chart._chart_data], [n["type"] for n in notes]
        )

    def test_single_and_directional_at_bpm_boundary(self):
        chart = self.build([
            {"type": "BPM", "bpm": 120, "beat": 0},
            {"type": "Single", "lane": 1, "beat": 2},
            {"type": "Directional", "lane": 2, "beat": 3,
             "width": 1, "direction": "Right"},
            {"type": "BPM", "bpm": 60, "beat": 2},
        ])
        self.assertEqual(chart._chart_data[1]["time"], 1000)
        self.assertEqual(chart._chart_data[2]["time"], 2000)
        self.assertEqual(chart._chart_data[1]["index"], 0)
        self.assertEqual(chart._chart_data[2]["checkpoint_index"], 1)

    def test_constant_bpm_keeps_times_and_checkpoint_indices(self):
        chart = self.build([
            {"type": "BPM", "bpm": 120, "beat": 0},
            {"type": "Single", "lane": 1, "beat": 1},
            {"type": "Directional", "lane": 2, "beat": 2,
             "width": 1, "direction": "Right"},
            {"type": "Slide", "connections": [
                {"lane": 1, "beat": 3},
                {"lane": 2, "beat": 3.5, "hidden": True},
                {"lane": 4, "beat": 4},
            ]},
            {"type": "Long", "connections": [
                {"lane": 6, "beat": 5}, {"lane": 6, "beat": 6},
            ]},
        ])
        single, directional, slide, long = chart._chart_data[1:]
        checkpoints = [single, directional, *slide["connections"], *long["connections"]]
        self.assertEqual(
            [c["time"] for c in checkpoints], [500, 1000, 1500, 1750, 2000, 2500, 3000]
        )
        self.assertEqual(
            [c.get("checkpoint_index") for c in checkpoints], [0, 1, 2, None, 3, 4, 5]
        )
        self.assertEqual([n["index"] for n in chart._chart_data[1:]], [0, 1, 2, 3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
