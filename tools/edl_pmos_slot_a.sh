#!/bin/bash
# Option 2: pmOS on slot A. boot_a <- pmOS boot.img, dtbo_a <- zeros, activate A, reset.
# Undo: w boot_a boot/magisk_boot_a.img ; w dtbo_a backup/edl-2026-10-25/lun4/dtbo_a.bin
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
T=$R/tools
EDL=("$T/venv/bin/edl" --loader="$T/loader/palma2_lagoon_fhprg.bin")
BOOT=${BOOT:-$R/port/build/boot.img}
TMP=$(mktemp -d)
for i in $(seq 1 60); do ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' && break; sleep 2; done
ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' || { echo "no EDL device"; exit 1; }
"${EDL[@]}" --memory=ufs w boot_a "$BOOT" 2>&1 | grep -E "Wrote|rror"
"${EDL[@]}" --memory=ufs w dtbo_a "$R/port/dtbo/dtbo_zero.img" 2>&1 | grep -E "Wrote|rror"
"${EDL[@]}" --memory=ufs r boot_a "$TMP/b.bin" 2>&1 | grep -E "rror"
N=$(stat -f %z "$BOOT"); A=$(shasum -a 256 "$BOOT" | cut -c1-16); B=$(head -c "$N" "$TMP/b.bin" | shasum -a 256 | cut -c1-16)
echo "boot image=$A boot_a[:N]=$B $([ "$A" = "$B" ] && echo MATCH || echo MISMATCH)"
"${EDL[@]}" setactiveslot a 2>&1 | grep -iE "error" | tail -1
"${EDL[@]}" reset 2>&1 | grep -iE "error" | tail -1
echo "RESET_SENT $(date +%T)"
rm -rf "$TMP"
