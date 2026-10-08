// Copyright (C) 2026 opencode-lab contributors
// SPDX-License-Identifier: GPL-3.0-or-later

package scores

// Defaults match gui_player.go:touchConfig for BanG with humanization off.
func AutodoriTouchConfig() *VTEGenerateConfig {
	return &VTEGenerateConfig{
		TapDuration: 10, FlickDuration: 60, FlickReportInterval: 5,
		FlickFactor: 1.0 / 5, FlickPow: 1, SlideReportInterval: 10,
	}
}
