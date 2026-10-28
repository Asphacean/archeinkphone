#!/bin/bash
# Capture a live TCON refresh on stock Android (Magisk root) via adb: polls /sys/class/ebc/dump_reg
# at ~20 ms for N seconds while the user triggers screen updates; also dumps DSI/clk info.
# usage: tools/android_tcon_capture.sh [seconds]   (output: recon/android-<date>/)
set -u
SECS=${1:-15}
OUT=$(cd "$(dirname "$0")/.." && pwd)/recon/android-$(date +%Y%m%d-%H%M)
mkdir -p "$OUT"
A="adb shell su -c"
adb wait-for-device
$A id > "$OUT/id.txt" 2>&1
$A 'cat /sys/class/ebc/dump_reg' > "$OUT/dump_reg_idle.txt" 2>&1
$A 'ls -la /dev/mem /sys/kernel/debug/ 2>&1; ls /sys/kernel/debug/msm_drm /sys/kernel/debug/dri/0 2>&1' > "$OUT/debugfs.txt" 2>&1
$A 'cat /sys/kernel/debug/clk/clk_summary' 2>/dev/null | grep -iE "dsi|mdss|disp_cc" > "$OUT/clk_dsi.txt"
$A 'cat /proc/interrupts' > "$OUT/interrupts.txt" 2>&1
echo "polling dump_reg for $SECS s -- trigger a refresh on the device now (touch/scroll/power button)"
$A "end=\$((\$(date +%s)+$SECS)); while [ \$(date +%s) -lt \$end ]; do echo \"== \$(date +%s.%N)\"; cat /sys/class/ebc/dump_reg | grep -E 'cmd\[0x(20|21|22|23|1|2|6|7)\]'; usleep 20000; done" > "$OUT/dump_reg_poll.txt" 2>&1
$A 'dmesg' > "$OUT/dmesg.txt" 2>&1
# distinct register states over the poll (compressed view)
python3 - "$OUT/dump_reg_poll.txt" <<'PY'
import re, sys
cur = {}; prev = None; t0 = None
for line in open(sys.argv[1]):
    if line.startswith('== '):
        if cur:
            key = tuple(sorted(cur.items()))
            if key != prev:
                print('%7.3f s %s' % (ts - t0, ' '.join('%s=%s' % kv for kv in key))); prev = key
        ts = float(line[3:]); t0 = t0 or ts; cur = {}
    else:
        m = re.search(r'cmd\[(0x[0-9a-f]+)\] value\[(0x[0-9a-f]+)\]', line)
        if m: cur[m.group(1)] = m.group(2)
PY
echo "saved to $OUT"
