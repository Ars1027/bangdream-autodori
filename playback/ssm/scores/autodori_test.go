// Copyright (C) 2026 opencode-lab contributors
// SPDX-License-Identifier: GPL-3.0-or-later

package scores

import (
	"github.com/kvarenzn/ssm/common"
	"testing"
)

func generated(t *testing.T, notes []TimedNote) common.RawVirtualEvents {
	t.Helper()
	chart, err := FromAutodori(notes)
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := GenerateHumanizedTouchEvent(AutodoriTouchConfig(), HumanizeConfig{GreatOffsetMs: 10}, chart)
	return raw
}

func TestAutodoriLongEndAndSimultaneousTap(t *testing.T) {
	raw := generated(t, []TimedNote{
		{Type: "Long", Connections: []Connection{{Time: 0, Lane: 1}, {Time: 1000, Lane: 1}}},
		{Type: "Single", Time: 1000, Lane: 4},
	})
	var longPointer, tapPointer int
	var moved, released bool
	for _, item := range raw {
		for _, e := range item.Events {
			if item.Timestamp == 0 && e.Action == common.TouchDown {
				longPointer = e.PointerID
			}
			if item.Timestamp == 1000 && e.Action == common.TouchDown {
				tapPointer = e.PointerID
			}
			if item.Timestamp == 1000 && e.PointerID == longPointer && e.Action == common.TouchMove {
				moved = true
			}
			if item.Timestamp == 1001 && e.PointerID == longPointer && e.Action == common.TouchUp {
				released = true
			}
		}
	}
	if !moved || !released {
		t.Fatal("long must move to its endpoint, then release 1 ms later")
	}
	if longPointer == tapPointer {
		t.Fatal("a tap at the long endpoint must use a different pointer")
	}
}

func TestAutodoriTouchingTapIntervalsConflict(t *testing.T) {
	raw := generated(t, []TimedNote{{Type: "Single", Time: 0, Lane: 0}, {Type: "Single", Time: 10, Lane: 1}})
	var pointers []int
	for _, item := range raw {
		for _, e := range item.Events {
			if e.Action == common.TouchDown {
				pointers = append(pointers, e.PointerID)
			}
		}
	}
	if len(pointers) != 2 || pointers[0] == pointers[1] {
		t.Fatalf("shared endpoints require distinct pointers: %v", pointers)
	}
}

func TestAutodoriSixSimultaneousNotes(t *testing.T) {
	var notes []TimedNote
	for lane := 0; lane < 6; lane++ {
		notes = append(notes, TimedNote{Type: "Single", Time: 500, Lane: float64(lane)})
	}
	raw := generated(t, notes)
	down := map[int]bool{}
	for _, e := range raw[0].Events {
		if e.Action == common.TouchDown {
			down[e.PointerID] = true
		}
	}
	if len(down) != 6 {
		t.Fatalf("six simultaneous taps lost a pointer: %v", down)
	}
}

func TestAutodoriSlideZeroLengthAndHiddenGeometry(t *testing.T) {
	raw := generated(t, []TimedNote{{Type: "Slide", Connections: []Connection{
		{Time: 0, Lane: 0}, {Time: 500, Lane: 2}, {Time: 500, Lane: 3}, {Time: 1000, Lane: 6, Flick: true},
	}}})
	var at500 []float64
	var lastUp int64
	for _, item := range raw {
		for _, e := range item.Events {
			if (item.Timestamp == 500 || item.Timestamp == 501) && e.Action == common.TouchMove {
				at500 = append(at500, e.X)
			}
			if e.Action == common.TouchUp {
				lastUp = item.Timestamp
			}
		}
	}
	if len(at500) != 2 || at500[0] != 2.0/6 || at500[1] != 3.0/6 {
		t.Fatalf("SSM must preserve same-time geometry with adjacent 1 ms timestamps: %v", at500)
	}
	if lastUp != 1065 {
		t.Fatalf("SSM flick must release after 60+5 ms, got %d", lastUp)
	}
}
