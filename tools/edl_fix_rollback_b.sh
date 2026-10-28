#!/bin/bash
# Slot B anti-rollback fix: copy slot A's vbmeta_system (newer rollback index) to vbmeta_system_b,
# then write pmOS boot.img to boot_b, verify, activate slot B, reset. Backups: backup/edl-2026-10-25/lun4/*_b.bin
set -u
T=$(cd "$(dirname "$0")/.." && pwd)/tools
BK=$(cd "$(dirname "$0")/.." && pwd)/backup/edl-2026-10-25/lun4
EDL=("$T/venv/bin/edl" --loader="$T/loader/palma2_lagoon_fhprg.bin")
BOOT=${BOOT:-$(cd "$(dirname "$0")/.." && pwd)/port/build/boot.img}
TMP=$(mktemp -d)
for i in $(seq 1 60); do ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' && break; sleep 2; done
ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' || { echo "no EDL device"; exit 1; }
"${EDL[@]}" --memory=ufs w vbmeta_system_b "$BK/vbmeta_system_a.bin" 2>&1 | grep -E "Wrote|rror"
"${EDL[@]}" --memory=ufs r vbmeta_system_b "$TMP/vsb.bin" 2>&1 | grep -E "rror"
cmp "$BK/vbmeta_system_a.bin" "$TMP/vsb.bin" && echo "vbmeta_system_b verified (== slot A copy)"
"${EDL[@]}" --memory=ufs w boot_b "$BOOT" 2>&1 | grep -E "Wrote|rror"
"${EDL[@]}" --memory=ufs r boot_b "$TMP/boot_b.bin" 2>&1 | grep -E "rror"
N=$(stat -f %z "$BOOT"); A=$(shasum -a 256 "$BOOT" | cut -c1-16); B=$(head -c "$N" "$TMP/boot_b.bin" | shasum -a 256 | cut -c1-16)
echo "boot image=$A boot_b[:N]=$B $([ "$A" = "$B" ] && echo MATCH || echo MISMATCH)"
if [ "$A" = "$B" ]; then
  "${EDL[@]}" setactiveslot b 2>&1 | grep -iE "error" | tail -1
  "${EDL[@]}" reset 2>&1 | grep -iE "error" | tail -1
  echo "RESET_SENT $(date +%T)"
fi
rm -rf "$TMP"
