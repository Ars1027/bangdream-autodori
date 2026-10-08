// Copyright (C) 2026 opencode-lab contributors
// SPDX-License-Identifier: GPL-3.0-or-later

package scores

import "fmt"

// TimedNote adapts autodori's existing Bestdori parser to the SSM note model.
// Time remains the v1.2.7 parser's milliseconds; BPM parsing is not changed.
type TimedNote struct {
	Type        string       `json:"type"`
	Time        float64      `json:"time"`
	Lane        float64      `json:"lane"`
	Flick       bool         `json:"flick"`
	Direction   string       `json:"direction"`
	Connections []Connection `json:"connections"`
}

type Connection struct {
	Time      float64 `json:"time"`
	Lane      float64 `json:"lane"`
	Flick     bool    `json:"flick"`
	Direction string  `json:"direction"`
}

func flickDirection(direction string) int {
	switch direction {
	case "Left":
		return 180
	case "Right":
		return 0
	default:
		return 90
	}
}

func FromAutodori(notes []TimedNote) (Chart, error) {
	chart := Chart{}
	for i, note := range notes {
		switch note.Type {
		case "BPM", "System":
			continue
		case "Single", "Directional":
			chart = append(chart, newStar(note.Time/1000, note.Lane/6, 1.0/6).
				markAsTap().flickToIfOk(note.Flick || note.Type == "Directional", flickDirection(note.Direction)))
		case "Long", "Slide":
			if len(note.Connections) < 2 {
				return nil, fmt.Errorf("note %d: %s needs at least two connections", i, note.Type)
			}
			head := note.Connections[0]
			previousTime := head.Time
			tail := newStar(head.Time/1000, head.Lane/6, 1.0/6).markAsTap().markAsHead()
			for _, connection := range note.Connections[1:] {
				if connection.Time < previousTime {
					return nil, fmt.Errorf("note %d: connections run backwards", i)
				}
				tail = newStar(connection.Time/1000, connection.Lane/6, 1.0/6).chainsAfter(tail)
				previousTime = connection.Time
			}
			last := note.Connections[len(note.Connections)-1]
			chart = append(chart, tail.markAsEnd().flickToIfOk(last.Flick, flickDirection(last.Direction)))
		default:
			return nil, fmt.Errorf("note %d: unsupported type %q", i, note.Type)
		}
	}
	return chart, nil
}

// Defaults match gui_player.go:touchConfig for BanG with humanization off.
func AutodoriTouchConfig() *VTEGenerateConfig {
	return &VTEGenerateConfig{
		TapDuration: 10, FlickDuration: 60, FlickReportInterval: 5,
		FlickFactor: 1.0 / 5, FlickPow: 1, SlideReportInterval: 10,
	}
}
