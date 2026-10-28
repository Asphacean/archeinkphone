#!/bin/bash
# Flash pmOS boot.img to slot B via EDL, verify by read-back, switch active slot to B.
# Rollback: tools/edl_flash_pmos.sh rollback  (setactiveslot a; Android on slot A untouched)
set -u
T=$(cd "$(dirname "$0")/.." && pwd)/tools
P=$(cd "$(dirname "$0")/.." && pwd)/port
EDL=("$T/venv/bin/edl" --loader="$T/loader/palma2_lagoon_fhprg.bin")
BOOT=${BOOT:-$P/build/boot.img}
DTBO=$P/dtbo/dtbo_empty.img
TMP=$(mktemp -d)

wait_edl() {
  for i in $(seq 1 60); do
    ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 36872' && return 0
    sleep 2
  done
  echo "no EDL device (9008)"; return 1
}

case "${1:-flash}" in
  rollback)
    wait_edl || exit 1
    "${EDL[@]}" setactiveslot a
    "${EDL[@]}" reset
    ;;
  flash)
    [ -f "$BOOT" ] || { echo "missing $BOOT"; exit 1; }
    wait_edl || exit 1
    "${EDL[@]}" --memory=ufs w boot_b "$BOOT"
    "${EDL[@]}" --memory=ufs w dtbo_b "$DTBO"
    "${EDL[@]}" --memory=ufs r boot_b "$TMP/boot_b.bin"
    "${EDL[@]}" --memory=ufs r dtbo_b "$TMP/dtbo_b.bin"
    cmp -n "$(stat -f %z "$BOOT")" "$BOOT" "$TMP/boot_b.bin" && echo "boot_b verified"
    cmp -n "$(stat -f %z "$DTBO")" "$DTBO" "$TMP/dtbo_b.bin" && echo "dtbo_b verified"
    "${EDL[@]}" setactiveslot b
    "${EDL[@]}" reset
    ;;
esac
rm -rf "$TMP"
