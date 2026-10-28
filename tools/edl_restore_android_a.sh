#!/bin/bash
# Undo option 2: Magisk boot_a + stock dtbo_a, activate A, reset.
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
T=$R/tools
EDL=("$T/venv/bin/edl" --loader="$T/loader/palma2_lagoon_fhprg.bin")
for i in $(seq 1 60); do ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' && break; sleep 2; done
"${EDL[@]}" --memory=ufs w boot_a "$R/boot/magisk_boot_a.img" 2>&1 | grep -E "Wrote|rror"
"${EDL[@]}" --memory=ufs w dtbo_a "$R/backup/edl-2026-10-25/lun4/dtbo_a.bin" 2>&1 | grep -E "Wrote|rror"
"${EDL[@]}" setactiveslot a 2>&1 | grep -iE "error" | tail -1
"${EDL[@]}" reset 2>&1 | grep -iE "error" | tail -1
echo "RESET_SENT $(date +%T)"
