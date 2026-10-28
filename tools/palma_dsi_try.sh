#!/bin/bash
# Try DSI mode-flag variants of the panel module without reflashing: palma_dsi_try.sh <flags-hex> [lanes]
# Flags: VIDEO=0x1 BURST=0x2 SYNC_PULSE=0x4 HSE=0x10 NO_EOT=0x200 CLOCK_NON_CONTINUOUS=0x400 LPM=0x800
F=${1:-0x1}; L=${2:-0}
ssh palma "echo palma | sudo -S -p '' sh -c '
echo 0 > /sys/class/vtconsole/vtcon1/bind 2>/dev/null
rmmod panel_onyx_palma2_tcon 2>/dev/null; sleep 1; dmesg -C
modprobe panel-onyx-palma2-tcon dsi_flags_override=$F dsi_lanes_override=$L; sleep 6
echo \"flags=$F lanes=$L dsi_err lines in 6s: \$(dmesg | grep -c dsi_err_worker)\"; dmesg | grep -E \"palma2|tcon|DONE|error|fail\" | grep -v dsi_err | cut -c1-120 | head -6
echo 0 > /sys/class/vtconsole/vtcon1/bind 2>/dev/null
python3 /home/user/palma_epd_test.py 2>&1 | tail -2
'" 2>&1
