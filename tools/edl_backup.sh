#!/bin/bash
# Read-only EDL dump of all partitions except userdata. Reversible: `edl reset` returns to Android.
set -u
T=$(cd "$(dirname "$0")/.." && pwd)/tools
EDL="$T/venv/bin/edl --loader=$T/loader/palma2_lagoon_fhprg.bin --memory=ufs"
OUT=$(cd "$(dirname "$0")/.." && pwd)/backup/edl-$(date +%Y-%m-%d)
mkdir -p "$OUT"; cd "$OUT"
df -h "$HOME" | tail -1
adb reboot edl
for i in $(seq 1 60); do
  ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' && break   # 0x9008
  sleep 2
done
ioreg -p IOUSB -l -w0 | grep -E '"USB Product Name"|idProduct' | grep -B1 36872
$EDL printgpt | tee gpt.txt
$EDL rl "$OUT" --skip=userdata 2>&1 | tee rl.log | grep -vE 'Progress|^\s*$' | tail -40
ls -la "$OUT" | head -80; du -sh "$OUT"
$EDL reset
