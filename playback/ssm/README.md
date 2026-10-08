# Vendored SSM playback core

Source: [hj6hki123/ssm-gui](https://github.com/hj6hki123/ssm-gui/tree/061d1b880e42b57698be35e9a4a841a44a684fef), commit `061d1b880e42b57698be35e9a4a841a44a684fef`.

The original copyright and SPDX headers are preserved. This code is GPL-3.0-or-later; see LICENSE.

## Directly reused

- `scores/bms.go`: the BanG local BMS parser, including complete BPM timing, holds, slide geometry and directional flick merging. It is byte-identical to SSM GUI v3.7.0's parser.
- `scores/generate.go`, `humanize.go`: the GUI's touch generation pipeline, with timing/position jitter and Great mode disabled.
- `scores/colorize.go`, `dsatur.go`, `graph.go`: conflict detection and pointer allocation.
- `common/events.go`, `stage/bang.go`: virtual events and BanG judge-line coordinates.
- `adb/`, `controllers/scrcpy.go`, `scrcpy_gui.go`: the ADB client, scrcpy connection, 32-byte touch encoding, GUI preprocessing and touch reset.
- `engine/playback.go`: `playEvents` copied verbatim from upstream `gui/playback.go`.
- Supporting `config/`, `locale/`, `log/`, `utils/` and upstream humanization tests.

## Integration changes

- `scores/autodori.go` retains the BanG GUI's default touch parameters. The timed Bestdori adapter has been removed; `cmd/autodori/` reads the BMS file directly and calls the unchanged SSM `ParseBMS`. The SUS parser is not included.
- `controllers/autodori.go` adapts landscape emulator dimensions to SSM's portrait device config. `controller.go` contains the upstream interface normally declared in `hid.go`; this build uses ADB.
- `cmd/autodori/` exposes prepare/play/stop/close over stdin/stdout JSON. Prepare accepts an absolute `chart_path`; the first-note deadline crosses the process boundary once, and the song then uses SSM's Go monotonic scheduler.
- Optional FFmpeg decoding is removed from `scrcpy.go` and `scrcpy_gui.go`. The video payload is discarded as in SSM's default mode; autodori continues to capture frames through emulator IPC.

Build from the project root with `python build_ssm.py`, using Go 1.25 or later. CGO is disabled. The generated executable belongs in `assets/ssm/` and is included by `build.py` when packaging.
