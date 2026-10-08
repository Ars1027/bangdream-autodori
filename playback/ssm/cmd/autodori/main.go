// Copyright (C) 2026 opencode-lab contributors
// SPDX-License-Identifier: GPL-3.0-or-later

package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"sync"
	"time"

	"github.com/kvarenzn/ssm/adb"
	"github.com/kvarenzn/ssm/common"
	"github.com/kvarenzn/ssm/controllers"
	"github.com/kvarenzn/ssm/engine"
	"github.com/kvarenzn/ssm/scores"
)

type request struct {
	Command        string             `json:"command"`
	Notes          []scores.TimedNote `json:"notes"`
	FirstDueUnixNS int64              `json:"first_due_unix_ns"`
}

var outputMu sync.Mutex

func report(event string, fields map[string]any) {
	if fields == nil {
		fields = map[string]any{}
	}
	fields["event"] = event
	outputMu.Lock()
	defer outputMu.Unlock()
	json.NewEncoder(os.Stdout).Encode(fields)
}

type offlineController struct{}

func (offlineController) Send([]byte) {}

func run() error {
	serial := flag.String("serial", "", "ADB serial selected by MaaFramework")
	server := flag.String("server", "", "scrcpy-server-v3.3.1 path")
	width := flag.Int("width", 1280, "landscape capture width")
	height := flag.Int("height", 720, "landscape capture height")
	offline := flag.Bool("offline", false, "generate and schedule without sending touches")
	flag.Parse()

	var ctrl controllers.Controller
	var scrcpy *controllers.ScrcpyController
	if *offline {
		scrcpy = controllers.NewOfflineScrcpy(*width, *height)
		ctrl = offlineController{}
	} else {
		devices, err := adb.NewDefaultClient().Devices()
		if err != nil {
			return err
		}
		for _, device := range devices {
			if device.Serial() == *serial && device.Authorized() {
				scrcpy = controllers.NewScrcpyController(device)
				break
			}
		}
		if scrcpy == nil {
			return fmt.Errorf("ADB device %q is unavailable or unauthorized", *serial)
		}
		gui := controllers.GUIScrcpy{ScrcpyController: scrcpy}
		defer gui.Close()
		if err := scrcpy.Open(*server, "3.3.1"); err != nil {
			return fmt.Errorf("open SSM scrcpy control: %w", err)
		}
		ctrl = gui
	}
	report("connected", nil)

	var events []common.ViscousEventItem
	var cancel context.CancelFunc
	var finished chan struct{}
	stop := func() {
		if cancel != nil {
			cancel()
			<-finished
			cancel = nil
		}
	}
	defer stop()
	decoder := json.NewDecoder(os.Stdin)
	for {
		var req request
		if err := decoder.Decode(&req); err != nil {
			if err == io.EOF {
				return nil
			}
			return err
		}
		switch req.Command {
		case "prepare":
			stop()
			chart, err := scores.FromAutodori(req.Notes)
			if err != nil {
				return err
			}
			raw, _ := scores.GenerateHumanizedTouchEvent(scores.AutodoriTouchConfig(),
				scores.HumanizeConfig{GreatOffsetMs: 10}, chart)
			if len(raw) == 0 {
				return fmt.Errorf("chart contains no playable notes")
			}
			events = scrcpy.AutodoriEvents(raw, *width, *height)
			count, pointers := 0, 0
			for _, item := range raw {
				count += len(item.Events)
				for _, event := range item.Events {
					pointers = max(pointers, event.PointerID+1)
				}
			}
			if !*offline {
				scrcpy.ResetTouch()
			}
			report("ready", map[string]any{"event_count": len(events), "touch_count": count,
				"pointers": pointers, "first_ms": events[0].Timestamp,
				"duration_ms": events[len(events)-1].Timestamp - events[0].Timestamp})
		case "play":
			stop()
			if len(events) == 0 {
				return fmt.Errorf("play requested before prepare")
			}
			ctx, cancelPlay := context.WithCancel(context.Background())
			cancel = cancelPlay
			finished = make(chan struct{})
			// Unix time transfers only the first-note deadline across the IPC.
			// The complete song then uses Go's monotonic time, exactly as SSM.
			now := time.Now()
			firstDue := now
			if req.FirstDueUnixNS != 0 {
				firstDue = now.Add(time.Duration(req.FirstDueUnixNS - now.UnixNano()))
			}
			start := firstDue.Add(-time.Duration(events[0].Timestamp) * time.Millisecond)
			go func(done chan struct{}, prepared []common.ViscousEventItem) {
				defer close(done)
				engine.Play(ctx, ctrl, prepared, start)
				if !*offline {
					scrcpy.ResetTouch()
				}
				report("done", map[string]any{"stopped": ctx.Err() != nil})
			}(finished, events)
		case "stop":
			stop()
			report("stopped", nil)
		case "close":
			return nil
		default:
			return fmt.Errorf("unknown command %q", req.Command)
		}
	}
}

func main() {
	if err := run(); err != nil {
		report("error", map[string]any{"message": err.Error()})
		os.Exit(1)
	}
}
