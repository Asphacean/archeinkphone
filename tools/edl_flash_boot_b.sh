#!/bin/bash
# Write $BOOT to boot_b via EDL, verify by read-back, keep dtbo_b zeroed, set slot B active, reset.
set -u
T=$(cd "$(dirname "$0")/.." && pwd)/tools
EDL=("$T/venv/bin/edl" --loader="$T/loader/palma2_lagoon_fhprg.bin")
BOOT=${BOOT:?set BOOT=<image>}
TMP=$(mktemp -d)
for i in $(seq 1 60); do ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' && break; sleep 2; done
ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' || { echo "no EDL device"; exit 1; }
"${EDL[@]}" --memory=ufs w boot_b "$BOOT" 2>&1 | grep -E "Wrote|rror"
"${EDL[@]}" --memory=ufs r boot_b "$TMP/boot_b.bin" 2>&1 | grep -E "Dumped|rror"
N=$(stat -f %z "$BOOT"); A=$(shasum -a 256 "$BOOT" | cut -c1-16); B=$(head -c "$N" "$TMP/boot_b.bin" | shasum -a 256 | cut -c1-16)
echo "image=$A boot_b[:N]=$B $([ "$A" = "$B" ] && echo MATCH || echo MISMATCH)"
if [ "$A" = "$B" ]; then
  "${EDL[@]}" setactiveslot b 2>&1 | grep -iE "error|slot" | tail -2
  "${EDL[@]}" reset 2>&1 | grep -iE "error" | tail -1
  echo "RESET_SENT $(date +%T)"
fi
rm -rf "$TMP"
