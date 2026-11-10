/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Physical press/release verified on SI-2806-HFD-0.85-V01, 2026-11-08.
 * The supplier's dedicated P1.17 routine does not describe this switch.
 * Row 14 drives C9; column 0 senses B14, high while pressed. */
#define F75_WHEEL_ROW 14
#define F75_WHEEL_COL 0
#define F75_WHEEL_DRIVE_PORT 0x40048000
#define F75_WHEEL_DRIVE_MASK 0x00000200
#define F75_WHEEL_SENSE_PORT 0x40046000
#define F75_WHEEL_SENSE_MASK 0x00004000
