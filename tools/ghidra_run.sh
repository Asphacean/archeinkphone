#!/bin/bash
# Import vmlinux.elf once (project analysis/ghidra), then decompile Onyx display driver functions to analysis/decomp/.
set -eu
T=$(cd "$(dirname "$0")/.." && pwd)/tools; A=$(cd "$(dirname "$0")/.." && pwd)/analysis
export JAVA_HOME=/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home; export PATH=$JAVA_HOME/bin:$PATH
HL=$(ls $(cd "$(dirname "$0")/.." && pwd)/tools/ghidra/ghidra_*/support/analyzeHeadless | head -1)
mkdir -p "$A/ghidra" "$A/decomp"
if [ ! -d "$A/ghidra/palma2.rep" ]; then
  "$HL" "$A/ghidra" palma2 -import "$A/vmlinux.elf" -processor AARCH64:LE:64:v8A -loader ElfLoader \
    -noanalysis -scriptPath "$T" \
    -postScript GhidraDecomp.java '^(lfe5u_|onyx_tcon_|onyx_epdc_|epdc_|dsi_panel_is_tcon|get_tcon_display_addr|is_regal_waveform|get_waveform_(mode_index|type|position)|__setup_tcon_pmic)' "$A/decomp"
else
  "$HL" "$A/ghidra" palma2 -process vmlinux.elf -noanalysis -scriptPath "$T" \
    -postScript GhidraDecomp.java "${1:-^(lfe5u_|onyx_tcon_)}" "$A/decomp"
fi
ls "$A/decomp" | wc -l
