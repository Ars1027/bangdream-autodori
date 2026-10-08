// Copyright (C) 2026 opencode-lab contributors
// SPDX-License-Identifier: GPL-3.0-or-later

package scores

import (
	"math"
	"testing"

	"github.com/kvarenzn/ssm/common"
)

func TestBMSHoldCrossesLaterBPMChanges(t *testing.T) {
	// YELL's hold at beats 140..143.5 crosses BPM 67 at 142 and BPM 61 at 143.
	// Put its note line before the tempo line to verify the complete BPM table.
	chart := ParseBMS(`*---------------------- HEADER FIELD
#BPM 75
#WAV04 bd.wav
*---------------------- MAIN DATA FIELD
#03551:0400000000000004
#03503:0000433D
`)
	if len(chart) != 1 || !chart[0].isSlide() {
		t.Fatalf("expected one hold, got %v", chart)
	}
	wantEnd := 142*60.0/75 + 60.0/67 + 0.5*60.0/61
	if math.Abs(chart[0].start()-112) > 1e-9 || math.Abs(chart[0].seconds-wantEnd) > 1e-9 {
		t.Fatalf("hold times: %.9f..%.9f, want 112..%.9f", chart[0].start(), chart[0].seconds, wantEnd)
	}
	var lastUp int64
	for _, item := range generated(t, chart) {
		for _, event := range item.Events {
			if event.Action == common.TouchUp {
				lastUp = item.Timestamp
			}
		}
	}
	if lastUp != 114988 {
		t.Fatalf("hold must release after the correct BPM-integrated endpoint: %d", lastUp)
	}
}

func TestBMSDirectionalFlicksMergeAdjacentLanes(t *testing.T) {
	chart := ParseBMS(`*---------------------- HEADER FIELD
#BPM 120
#WAV01 directional_fl_r.wav
#WAV02 directional_fl_l.wav
*---------------------- MAIN DATA FIELD
#00111:01
#00112:01
#00114:02
#00115:02
`)
	if len(chart) != 2 {
		t.Fatalf("adjacent directional lanes must merge into two flicks, got %d", len(chart))
	}
	found := map[float64]float64{}
	for _, note := range chart {
		if note.kind() != flickNote || math.Abs(note.seconds-2) > 1e-9 {
			t.Fatalf("unexpected directional note: %+v", note)
		}
		found[note.track] = note.direction
	}
	right, hasRight := found[1.0/6]
	left, hasLeft := found[5.0/6]
	if len(found) != 2 || !hasRight || !hasLeft || right != 0 || left != math.Pi {
		t.Fatalf("right flick starts at lane 1, left at lane 5: %v", found)
	}
}
