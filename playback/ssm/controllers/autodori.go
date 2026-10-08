// Copyright (C) 2026 opencode-lab contributors
// SPDX-License-Identifier: GPL-3.0-or-later

package controllers

import (
	"github.com/kvarenzn/ssm/common"
	"github.com/kvarenzn/ssm/config"
	"github.com/kvarenzn/ssm/stage"
)

// Capture and scrcpy metadata are both landscape; SSM stores device dimensions
// in portrait order in its config. ADB touch coordinates need no rotation.
func (c *ScrcpyController) AutodoriEvents(raw common.RawVirtualEvents, width, height int) []common.ViscousEventItem {
	return c.PreprocessGUI(raw, false, &config.DeviceConfig{
		Width: height, Height: width,
	}, stage.BanGJudgeLinePos)
}

// Used by offline protocol tests without an Android device.
func NewOfflineScrcpy(width, height int) *ScrcpyController {
	return &ScrcpyController{width: width, height: height}
}
