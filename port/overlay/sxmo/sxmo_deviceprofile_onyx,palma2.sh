#!/bin/sh
# Boox Palma 2: e-ink, no modem; ft5x06 reports portrait coords already
export SXMO_NO_MODEM=1
export SXMO_LISGD_INPUT_DEVICE=/dev/input/by-path/platform-988000.i2c-event
export SXMO_VIBRATE_DEV=/dev/input/by-path/platform-880000.i2c-event
