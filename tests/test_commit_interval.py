"""Command interval budgeting checked against actual published touch streams."""

import sys
import unittest
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chart import Chart
from timing_diagnostics import build_device_report


def make_chart(actions):
    chart = Chart.__new__(Chart)
    chart.actions = [{**action, "index": i} for i, action in enumerate(actions)]
    chart._commands = []
    chart.actions_to_cmd_index = 0
    chart._a2c_offset = 0.0
    chart._a2c_rounded_loss = 0.0
    return chart


def taps(count):
    actions = []
    for i in range(count):
        time = i * 100.0
        actions.extend([
            {"type": "down", "finger": 1, "note": i, "time": time,
             "pos": (100, 200)},
            {"type": "wait", "time": time, "length": 50.0},
            {"type": "up", "finger": 1, "note": i, "time": time + 50},
            {"type": "wait", "time": time + 50, "length": 50.0},
        ])
    return actions


def publish_all(chart, interval, size=100, device_interval=None):
    sent = []
    batches = []
    events = []
    now = 10000.0
    cursor = 0

    def send(content):
        nonlocal now
        sent.append(content)
        for command in content.splitlines():
            now += interval if device_interval is None else device_interval
            start = now
            if command.startswith("w "):
                now += int(command.split()[1])
            events.append(SimpleNamespace(cmd=command, start_time=start,
                                          end_time=now, cost=now - start))

    while chart.actions_to_cmd_index < len(chart.actions):
        chart.actions_to_MNTcmd((1280, 720), 0, {"interval": interval}, size)
        end = len(chart._commands)
        content = chart.command_builder.publish(SimpleNamespace(send=send))
        batches.append((len(batches) + 1, content, cursor, end))
        cursor = end
    return sent, batches, events


class CommitIntervalTests(unittest.TestCase):
    def assert_budget_matches_wire(self, chart, sent, interval):
        lines = [line for content in sent for line in content.splitlines()]
        nominal = sum(a["length"] for a in chart.actions if a["type"] == "wait")
        sent_wait = sum(int(line.split()[1]) for line in lines if line.startswith("w "))
        # Wait reduction plus unused timing/rounding credit accounts for wire cost.
        budget = nominal - sent_wait + chart._a2c_offset + chart._a2c_rounded_loss
        self.assertAlmostEqual(len(lines) * interval, budget, places=7)

    def test_regular_and_implicit_commits_are_budgeted(self):
        chart = make_chart(taps(2))
        sent, _, _ = publish_all(chart, 0.02)
        self.assertEqual(5, sum(line == "c" for line in sent[0].splitlines()))
        self.assert_budget_matches_wire(chart, sent, 0.02)

    def test_rounding_omits_waits_without_interval_charge(self):
        chart = make_chart([
            {"type": "down", "finger": 1, "note": 0, "time": 0,
             "pos": (100, 200)},
            {"type": "wait", "time": 0, "length": 0.1},
            {"type": "wait", "time": 0.1, "length": 0.1},
        ])
        sent, _, _ = publish_all(chart, 0.02)
        self.assertEqual("d 1 100 200 1\nc\n", sent[0])
        self.assert_budget_matches_wire(chart, sent, 0.02)

    def test_empty_batch_still_budgets_publish_commit(self):
        chart = make_chart([])
        chart.actions_to_MNTcmd((1280, 720), 0, {"interval": 0.02})
        sent = []
        content = chart.command_builder.publish(SimpleNamespace(send=sent.append))
        self.assertEqual("c\n", content)
        self.assertEqual([], chart._commands)
        self.assertAlmostEqual(0.02, chart._a2c_offset)

    def test_budget_carries_across_batch_boundaries(self):
        for size in (1, 3, 7, 100):
            with self.subTest(size=size):
                chart = make_chart(taps(60))
                sent, _, _ = publish_all(chart, 0.02, size=size)
                self.assert_budget_matches_wire(chart, sent, 0.02)
                self.assertTrue(all(int(line.split()[1]) > 0
                                    for content in sent for line in content.splitlines()
                                    if line.startswith("w ")))

    def test_five_minute_stream_has_no_accumulating_commit_drift(self):
        chart = make_chart(taps(3000))
        sent, batches, events = publish_all(chart, 0.012)
        rows, stats = build_device_report(batches, chart._commands, chart.actions, events)
        self.assertIsNone(stats["first_mismatch"])
        self.assertEqual(0, stats["invalid_batches"])
        self.assertEqual(6000, stats["commits"])
        self.assertLess(max(abs(r["drift_min_ms"]) for r in rows
                            if "drift_min_ms" in r), 1.0)
        self.assertLess(abs(stats["last_drift_max_ms"]), 1.0)
        self.assert_budget_matches_wire(chart, sent, 0.012)

    def test_zero_interval_preserves_exact_wire_commands(self):
        chart = make_chart([
            {"type": "down", "finger": 2, "note": 3, "time": 0,
             "pos": (100, 200)},
            {"type": "wait", "time": 0, "length": 10},
            {"type": "move", "finger": 2, "note": 3, "time": 10,
             "to": (120, 200)},
            {"type": "wait", "time": 10, "length": 10},
            {"type": "up", "finger": 2, "note": 3, "time": 20},
        ])
        sent, _, _ = publish_all(chart, 0)
        self.assertEqual(["d 2 100 200 1\nc\nw 10\nm 2 120 200 1\nc\nw 10\nu 2\nc\n"], sent)
        self.assertEqual([0, 2, 4], [c["action"] for c in chart._commands
                                    if c["action"] is not None])


if __name__ == "__main__":
    unittest.main()
