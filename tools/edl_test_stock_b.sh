#!/bin/bash
# Option 1: restore slot B to stock from backup (boot_b, dtbo_b, vbmeta_system_b), activate B, reset.
set -u
T=$(cd "$(dirname "$0")/.." && pwd)/tools
BK=$(cd "$(dirname "$0")/.." && pwd)/backup/edl-2026-10-25/lun4
EDL=("$T/venv/bin/edl" --loader="$T/loader/palma2_lagoon_fhprg.bin")
for i in $(seq 1 60); do ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' && break; sleep 2; done
ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' || { echo "no EDL device"; exit 1; }
for p in boot_b dtbo_b vbmeta_system_b; do
  "${EDL[@]}" --memory=ufs w $p "$BK/$p.bin" 2>&1 | grep -E "Wrote|rror"
done
"${EDL[@]}" setactiveslot b 2>&1 | grep -iE "error" | tail -1
"${EDL[@]}" reset 2>&1 | grep -iE "error" | tail -1
echo "RESET_SENT $(date +%T)"
