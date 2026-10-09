"""Store per-batch host timing after a song, away from the input hot path."""

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
