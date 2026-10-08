// Copyright (C) 2024, 2025 kvarenzn
// SPDX-License-Identifier: GPL-3.0-or-later

package controllers

// The upstream interface is in hid.go; this build uses the ADB backend.
type Controller interface {
	Send(data []byte)
}
