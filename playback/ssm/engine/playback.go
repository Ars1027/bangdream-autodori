// Copyright (C) 2026 hj6hki123
// SPDX-License-Identifier: GPL-3.0-or-later

// playEvents is copied verbatim from ssm-gui/gui/playback.go.
package engine

import (
	"context"
	"github.com/kvarenzn/ssm/common"
	"github.com/kvarenzn/ssm/controllers"
	"time"
)

type preparedSong struct {
	controller controllers.Controller
	events     []common.ViscousEventItem
	stop       chan struct{}
	offset     chan int
}

func Play(ctx context.Context, ctrl controllers.Controller, events []common.ViscousEventItem, start time.Time) {
	playEvents(ctx, &preparedSong{
		controller: ctrl, events: events,
		stop: make(chan struct{}), offset: make(chan int, 32),
	}, start)
}

func playEvents(ctx context.Context, song *preparedSong, start time.Time) {
	for i := 0; i < len(song.events); {
		select {
		case <-song.stop:
			return
		case <-ctx.Done():
			return
		default:
		}
		select {
		case delta := <-song.offset:
			start = start.Add(time.Duration(-delta) * time.Millisecond)
		default:
		}

		event := song.events[i]
		remaining := event.Timestamp - time.Since(start).Milliseconds()
		switch {
		case remaining <= 0:
			song.controller.Send(event.Data)
			i++
		case remaining > 10:
			// Sleep until shortly before the event, staying interruptible.
			select {
			case <-song.stop:
				return
			case <-ctx.Done():
				return
			case <-time.After(time.Duration(remaining-5) * time.Millisecond):
			}
		case remaining > 4:
			time.Sleep(time.Millisecond)
		}
	}
}
