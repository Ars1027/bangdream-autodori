// Copyright (C) 2026 opencode-lab contributors
// SPDX-License-Identifier: GPL-3.0-or-later

package controllers

import (
	"encoding/binary"
	"github.com/kvarenzn/ssm/common"
	"testing"
)

func TestAutodoriLandscapeScrcpyPacket(t *testing.T) {
	c := NewOfflineScrcpy(1280, 720)
	events := c.AutodoriEvents(common.RawVirtualEvents{{Timestamp: 500, Events: []*common.VirtualTouchEvent{
		{PointerID: 2, Action: common.TouchDown, X: 0, Y: 0},
	}}}, 1280, 720)
	b := events[0].Data
	if len(b) != 32 || b[0] != 2 || b[1] != 0 {
		t.Fatalf("invalid scrcpy touch: %x", b)
	}
	if binary.BigEndian.Uint64(b[2:]) != 2 {
		t.Fatal("pointer id changed")
	}
	if binary.BigEndian.Uint32(b[10:]) != 197 || binary.BigEndian.Uint32(b[14:]) != 591 {
		t.Fatal("SSM judge-line mapping changed")
	}
	if binary.BigEndian.Uint16(b[18:]) != 1280 || binary.BigEndian.Uint16(b[20:]) != 720 {
		t.Fatal("landscape dimensions swapped")
	}
}
