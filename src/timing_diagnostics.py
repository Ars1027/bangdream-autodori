"""Store host and device timing after a song, away from the input hot path."""

import csv
import datetime
from pathlib import Path


FIELDS = (
    "batch",
    "action_start",
    "action_end",
    "elapsed_ms",
    "wait_ms",
    "margin_ms",
    "publish_ms",
    "life_check_ms",
    "sleep_requested_ms",
    "sleep_actual_ms",
    "sleep_overshoot_ms",
    "next_prepare_ms",
    "next_publish_gap_ms",
    "next_pub_minus_nominal_wait_ms",
)

SLOW_MS = 10.0

DEVICE_FIELDS = (
    "command_index", "batch", "expected_command", "actual_command",
    "match_status", "mapping_valid", "action_index", "note_index",
    "chart_time_ms", "device_start_ms", "device_end_ms", "device_cost_ms",
    "device_gap_ms", "commit_command_index", "commit_chart_min_ms",
    "commit_chart_max_ms", "device_relative_ms", "chart_relative_min_ms",
    "chart_relative_max_ms", "drift_min_ms", "drift_max_ms",
)


def save_report(rows, song_id, difficulty, output_dir=Path("debug")):
    """Write one CSV per play and return its path and outlier counts.

    ``next_pub_minus_nominal_wait_ms`` compares host publish times with the
    previous batch's sum of wait commands. It is a clue, not a measurement of
    server queue underflow: minitouch command execution also consumes time.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = output_dir / f"timing-{stamp}-{song_id}-{difficulty}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    def slow_count(field):
        return sum((row.get(field) or 0) >= SLOW_MS for row in rows)

    return path, {
        "batches": len(rows),
        "oversleep": slow_count("sleep_overshoot_ms"),
        "prepare": slow_count("next_prepare_ms"),
        "publish": slow_count("publish_ms"),
        "nominal_gap": slow_count("next_pub_minus_nominal_wait_ms"),
        "max_oversleep_ms": max(
            (row["sleep_overshoot_ms"] for row in rows), default=0.0
        ),
        "max_prepare_ms": max(
            (row.get("next_prepare_ms") or 0.0 for row in rows), default=0.0
        ),
    }


def build_device_report(sent_batches, commands, actions, events):
    """Match the exact sent sequence; derive drift only from its valid prefix.

    ``sent_batches`` contains (batch, published_text, command_start, command_end).
    Device callback timestamps use milliseconds, as in the existing offset loop.
    Commit end times describe submission to Android, not game judgements. Each
    timeline has its own origin; no host/device clock subtraction is performed.
    """
    expected = []
    invalid_batches = 0
    for batch, content, start, end in sent_batches:
        lines = content.splitlines()
        # publish() adds one c which is absent from Chart._commands.
        mapped = commands[start:end] + [{"command": "c", "action": None}]
        valid = lines == [entry["command"] for entry in mapped]
        invalid_batches += not valid
        for i, command in enumerate(lines):
            action_index = mapped[i]["action"] if valid else None
            action = actions[action_index] if action_index is not None else {}
            expected.append({
                "batch": batch, "expected_command": command,
                "mapping_valid": valid, "action_index": action_index,
                "note_index": action.get("note"),
                "chart_time_ms": action.get("time"),
            })

    matched = 0
    for planned, event in zip(expected, events):
        if planned["expected_command"] != event.cmd.strip():
            break
        matched += 1
    first_mismatch = (
        matched + 1 if matched < max(len(expected), len(events)) else None
    )
    rows = []
    pending = []
    mapping_ok = True
    origin = None
    drifts = []
    for i in range(max(len(expected), len(events))):
        row = {"command_index": i + 1}
        planned = expected[i] if i < len(expected) else None
        event = events[i] if i < len(events) else None
        if planned is not None:
            row.update(planned)
            mapping_ok = mapping_ok and planned["mapping_valid"]
        if event is not None:
            row.update({
                "actual_command": event.cmd,
                "device_start_ms": event.start_time,
                "device_end_ms": event.end_time,
                "device_cost_ms": event.cost,
                "device_gap_ms": (
                    event.start_time - events[i - 1].end_time if i else None
                ),
            })
        row["match_status"] = (
            "extra" if planned is None else
            "missing" if event is None else
            "matched" if i < matched else
            "mismatch" if i == matched else "unmatched"
        )
        rows.append(row)
        if i >= matched or not mapping_ok:
            continue
        command_type = planned["expected_command"].split()[0]
        if command_type in ("d", "m", "u"):
            pending.append(row)
        elif command_type == "c" and pending:
            times = [entry["chart_time_ms"] for entry in pending]
            if any(value is None for value in times):
                mapping_ok = False
                pending.clear()
                continue
            low, high = min(times), max(times)
            if origin is None:
                origin = (event.end_time, low)
            device_relative = event.end_time - origin[0]
            relative_low, relative_high = low - origin[1], high - origin[1]
            drift = (device_relative - relative_high,
                     device_relative - relative_low)
            row.update({
                "commit_command_index": i + 1,
                "commit_chart_min_ms": low, "commit_chart_max_ms": high,
                "device_relative_ms": device_relative,
                "chart_relative_min_ms": relative_low,
                "chart_relative_max_ms": relative_high,
                "drift_min_ms": drift[0], "drift_max_ms": drift[1],
            })
            for entry in pending:
                entry["commit_command_index"] = i + 1
            pending.clear()
            drifts.append(drift)

    return rows, {
        "expected": len(expected), "received": len(events), "matched": matched,
        "first_mismatch": first_mismatch, "invalid_batches": invalid_batches,
        "commits": len(drifts),
        "min_drift_ms": min((d[0] for d in drifts), default=None),
        "max_drift_ms": max((d[1] for d in drifts), default=None),
        "last_drift_min_ms": drifts[-1][0] if drifts else None,
        "last_drift_max_ms": drifts[-1][1] if drifts else None,
    }


def save_device_report(sent_batches, commands, actions, events, song_id,
                       difficulty, output_dir=Path("debug")):
    """Save raw callbacks even when matching is incomplete or inconsistent."""
    rows, stats = build_device_report(sent_batches, commands, actions, events)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = output_dir / f"device-timing-{stamp}-{song_id}-{difficulty}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=DEVICE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path, stats
