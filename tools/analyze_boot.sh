#!/bin/bash
# Unpack boot_a + dtbo_a from an EDL dump: kernel -> vmlinux.elf (symbols), built-in firmware, all DTBs -> .dts
set -eu
T=$(cd "$(dirname "$0")/.." && pwd)/tools; PY=$T/venv/bin/python
SRC=${1:?edl backup dir}; OUT=$(cd "$(dirname "$0")/.." && pwd)/analysis
mkdir -p "$OUT"; cd "$OUT"
$PY $T/unpack_bootimg.py --boot_img "$SRC/boot_a.bin" --out boot_a --format info | tee boot_a.info
K=boot_a/kernel
case "$(file -b $K)" in
  *gzip*) gunzip -c $K > kernel.raw ;;
  *LZ4*)  $PY -c "import lz4.frame,sys; sys.stdout.buffer.write(lz4.frame.decompress(open('$K','rb').read()))" > kernel.raw ;;
  *)      cp $K kernel.raw ;;
esac
file kernel.raw; ls -l kernel.raw
$PY -m vmlinux_to_elf kernel.raw vmlinux.elf 2>&1 | tail -3 || $T/venv/bin/vmlinux-to-elf kernel.raw vmlinux.elf 2>&1 | tail -3
$PY $T/extract_builtin_fw.py vmlinux.elf firmware
mkdir -p dtb && $T/venv/bin/extract-dtb kernel.raw -o dtb/kernel >/dev/null 2>&1 || true
[ -f boot_a/dtb ] && $T/venv/bin/extract-dtb boot_a/dtb -o dtb/boot >/dev/null 2>&1 || true
$T/venv/bin/extract-dtb "$SRC/dtbo_a.bin" -o dtb/dtbo >/dev/null 2>&1 || true
for d in $(find dtb -name '*.dtb'); do dtc -q -I dtb -O dts -o "${d%.dtb}.dts" "$d"; done
echo "== DTBs:"; find dtb -name '*.dts' | while read f; do echo "$f: $(grep -m1 'model = ' "$f")"; done
