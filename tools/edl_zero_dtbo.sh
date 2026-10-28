#!/bin/bash
# Zero dtbo_b via EDL (ABL then falls back to the DTB appended to the kernel), verify boot_b, activate slot B.
set -u
T=$(cd "$(dirname "$0")/.." && pwd)/tools
P=$(cd "$(dirname "$0")/.." && pwd)/port
EDL=("$T/venv/bin/edl" --loader="$T/loader/palma2_lagoon_fhprg.bin")
BOOT=$P/build/boot.img
ZERO=$P/dtbo/dtbo_zero.img
TMP=$(mktemp -d)
for i in $(seq 1 60); do ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' && break; sleep 2; done
ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' || { echo "no EDL device"; exit 1; }
"${EDL[@]}" --memory=ufs w dtbo_b "$ZERO" 2>&1 | grep -E "Wrote|rror"
"${EDL[@]}" --memory=ufs r boot_b "$TMP/boot_b.bin" 2>&1 | grep -E "Dumped|rror"
"${EDL[@]}" --memory=ufs r dtbo_b "$TMP/dtbo_b.bin" 2>&1 | grep -E "Dumped|rror"
N=$(stat -f %z "$BOOT")
A=$(shasum -a 256 "$BOOT" | cut -c1-16); B=$(head -c "$N" "$TMP/boot_b.bin" | shasum -a 256 | cut -c1-16)
echo "boot.img=$A boot_b[:N]=$B $([ "$A" = "$B" ] && echo MATCH || echo MISMATCH)"
echo "dtbo_b nonzero bytes: $(tr -d '\000' < "$TMP/dtbo_b.bin" | wc -c | tr -d ' ')"
if [ "$A" = "$B" ] && [ "${NOSLOT:-}" = "" ]; then
  "${EDL[@]}" setactiveslot b 2>&1 | grep -viE "capstone|keystone|Using loader|Waiting|detected" | tail -2
  "${EDL[@]}" reset 2>&1 | grep -viE "capstone|keystone|Using loader|Waiting|detected" | tail -1
  echo "RESET_SENT $(date +%T)"
else
  echo "NOT switching slot"
fi
rm -rf "$TMP"
