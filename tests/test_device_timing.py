"""Offline checks for matching device callbacks to submitted touch commands."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from minitouchpy import CommandBuilder
from timing_diagnostics import build_device_report, save_device_report


def fixture():
    actions = [
        {"index": 0, "note": 4, "time": 200.0},
        {"index": 1, "note": 4, "time": 300.0},
    ]
    builder = CommandBuilder()
    commands = [
        {"command": builder.down(1, 100, 200, 1), "action": 0},
        {"command": builder.commit(), "action": None},
        {"command": builder.wait(100), "action": None},
        {"command": builder.up(1), "action": 1},
        {"command": builder.commit(), "action": None},
    ]
    sent = []
    content = builder.publish(SimpleNamespace(send=sent.append), block=False)
    assert sent == [content]
    return [(1, content, 0, len(commands))], commands, actions


def callbacks(lines, origin=10000.0, delay_at=None):
    events = []
    now = origin
    for i, line in enumerate(lines):
        now += (delay_at or {}).get(i, 0)
        start = now
        if line.startswith("w "):
            now += int(line.split()[1])
        events.append(SimpleNamespace(
            cmd=line, start_time=start, end_time=now, cost=now - start,
        ))
    return events


class DeviceTimingTests(unittest.TestCase):
    def setUp(self):
        self.batches, self.commands, self.actions = fixture()
        self.lines = self.batches[0][1].splitlines()
        self.events = callbacks(self.lines)

    def report(self, events=None, batches=None):
        return build_device_report(
            self.batches if batches is None else batches,
            self.commands, self.actions,
            self.events if events is None else events,
        )

    def test_normal_sequence_includes_implicit_empty_commit(self):
        rows, stats = self.report()
        self.assertEqual(len(self.commands) + 1, stats["expected"])
        self.assertEqual(stats["expected"], stats["matched"])
        self.assertIsNone(stats["first_mismatch"])
        self.assertEqual(2, stats["commits"])
        self.assertEqual(0, stats["last_drift_max_ms"])
        self.assertEqual(4, rows[0]["note_index"])
        self.assertEqual(2, rows[0]["commit_command_index"])
        self.assertNotIn("drift_max_ms", rows[-1])
        self.assertEqual(100, rows[2]["device_cost_ms"])

    def test_injected_device_gap_is_retained_as_drift(self):
        rows, stats = self.report(callbacks(self.lines, delay_at={3: 12}))
        self.assertEqual(12, rows[3]["device_gap_ms"])
        self.assertEqual(12, stats["last_drift_min_ms"])
        self.assertEqual(12, stats["last_drift_max_ms"])

    def test_clock_origins_do_not_affect_relative_drift(self):
        _, original = self.report()
        _, shifted = self.report(callbacks(self.lines, origin=90000000))
        self.assertEqual(original, shifted)

    def test_multiple_chart_times_in_one_commit_keep_range(self):
        commands = [
            {"command": "d 1 100 200 1", "action": 0},
            {"command": "m 1 120 200 1", "action": 1},
        ]
        actions = [{"time": 200, "note": 1}, {"time": 200.5, "note": 1}]
        content = "d 1 100 200 1\nm 1 120 200 1\nc\n"
        rows, stats = build_device_report(
            [(1, content, 0, 2)], commands, actions, callbacks(content.splitlines()),
        )
        self.assertEqual(1, stats["commits"])
        self.assertEqual(200, rows[-1]["commit_chart_min_ms"])
        self.assertEqual(200.5, rows[-1]["commit_chart_max_ms"])
        self.assertEqual((-0.5, 0),
                         (rows[-1]["drift_min_ms"], rows[-1]["drift_max_ms"]))

    def test_missing_callback_stops_matching_without_resync(self):
        events = self.events[:2] + self.events[3:]
        rows, stats = self.report(events)
        self.assertEqual(2, stats["matched"])
        self.assertEqual(3, stats["first_mismatch"])
        self.assertEqual(1, stats["commits"])
        self.assertEqual("mismatch", rows[2]["match_status"])
        self.assertEqual("missing", rows[-1]["match_status"])
        self.assertTrue(all("drift_max_ms" not in r for r in rows[2:]))

    def test_duplicate_callback_stops_at_first_difference(self):
        rows, stats = self.report(self.events[:2] + [self.events[1]] + self.events[2:])
        self.assertEqual(2, stats["matched"])
        self.assertEqual(1, stats["commits"])
        self.assertEqual("extra", rows[-1]["match_status"])
        self.assertTrue(all("drift_max_ms" not in r for r in rows[2:]))

    def test_mismatched_command_preserves_raw_event(self):
        events = callbacks(self.lines)
        events[3].cmd = "u 2"
        rows, stats = self.report(events)
        self.assertEqual(4, stats["first_mismatch"])
        self.assertEqual("u 2", rows[3]["actual_command"])
        self.assertEqual("u 1", rows[3]["expected_command"])
        self.assertEqual(1, stats["commits"])

    def test_absent_and_trailing_extra_callbacks_are_explicit(self):
        rows, stats = self.report([])
        self.assertEqual(0, stats["commits"])
        self.assertIsNone(stats["last_drift_min_ms"])
        self.assertTrue(all(r["match_status"] == "missing" for r in rows))
        rows, stats = self.report(self.events + callbacks(["c"], origin=10100))
        self.assertEqual(7, stats["received"])
        self.assertEqual(7, stats["first_mismatch"])
        self.assertEqual("extra", rows[-1]["match_status"])
        self.assertNotIn("drift_max_ms", rows[-1])

    def test_repeated_commands_across_batches_keep_action_mapping(self):
        commands = self.commands + self.commands
        actions = self.actions + [{**a, "time": a["time"] + 100} for a in self.actions]
        commands = [dict(c) for c in commands]
        for c in commands[len(self.commands):]:
            if c["action"] is not None:
                c["action"] += 2
        batches = self.batches + [(2, self.batches[0][1], 5, 10)]
        rows, stats = build_device_report(
            batches, commands, actions, callbacks(self.lines * 2),
        )
        self.assertIsNone(stats["first_mismatch"])
        self.assertEqual(2, rows[6]["batch"])
        self.assertEqual(2, rows[6]["action_index"])
        self.assertEqual(4, stats["commits"])
        self.assertEqual(0, stats["last_drift_max_ms"])

    def test_invalid_sent_mapping_keeps_raw_data_without_drift(self):
        rows, stats = self.report(batches=[(1, self.batches[0][1], 0, 4)])
        self.assertEqual(1, stats["invalid_batches"])
        self.assertEqual(0, stats["commits"])
        self.assertEqual(len(self.events), stats["matched"])
        self.assertEqual(self.events[0].cmd, rows[0]["actual_command"])
        self.assertFalse(rows[0]["mapping_valid"])

    def test_csv_export_preserves_expected_and_raw_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path, stats = save_device_report(
                self.batches, self.commands, self.actions, self.events[:-1],
                "243", "hard", Path(directory),
            )
            with path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(6, len(rows))
            self.assertEqual("10000.0", rows[0]["device_start_ms"])
            self.assertEqual("missing", rows[-1]["match_status"])
            self.assertEqual(6, stats["first_mismatch"])


if __name__ == "__main__":
    unittest.main()
