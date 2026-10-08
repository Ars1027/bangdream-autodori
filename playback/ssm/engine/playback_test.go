// Copyright (C) 2026 opencode-lab contributors
// SPDX-License-Identifier: GPL-3.0-or-later

package engine

import (
	"context"
	"github.com/kvarenzn/ssm/common"
	"testing"
	"time"
)

type capture struct{ times []time.Time }

func (c *capture) Send([]byte) {
	c.times = append(c.times, time.Now())
	if len(c.times) == 1 {
		time.Sleep(60 * time.Millisecond)
	}
}

func TestSchedulerCatchesUpAfterSendStall(t *testing.T) {
	ctrl := &capture{}
	Play(context.Background(), ctrl, []common.ViscousEventItem{{Timestamp: 0}, {Timestamp: 10}, {Timestamp: 20}}, time.Now())
	if len(ctrl.times) != 3 {
		t.Fatalf("lost events: %v", ctrl.times)
	}
	// Both deadlines have passed after the first send stalls; dispatch them
	// together instead of inserting their relative waits after the stall.
	if ctrl.times[2].Sub(ctrl.times[1]) > 5*time.Millisecond {
		t.Fatal("scheduler accumulated relative wait after the send stall")
	}
}

func TestSchedulerCancellationInterruptsLongWait(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	ctrl := &capture{}
	go func() { Play(ctx, ctrl, []common.ViscousEventItem{{Timestamp: 10000}}, time.Now()); close(done) }()
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("cancel did not interrupt the pending touch")
	}
	if len(ctrl.times) != 0 {
		t.Fatal("touch sent after cancel")
	}
}
