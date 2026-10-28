#!/bin/bash
# Compile a Palma 2 DTS against the sparse kernel tree (v7.2.0-sm6350) on the Mac: build_dtb.sh in.dts out.dtb
set -eu
K=${KSRC:?path to the sm6350-mainline kernel tree}
clang -E -nostdinc -I "$K/include" -I "$K/arch/arm64/boot/dts" -I "$K/arch/arm64/boot/dts/qcom" -undef -D__DTS__ -x assembler-with-cpp "$1" -o "$2.pre.dts"
dtc -I dts -O dtb -i "$K/arch/arm64/boot/dts/qcom" -o "$2" "$2.pre.dts" 2>&1 | grep -vE "Warning \((unit_address_vs_reg|simple_bus_reg|avoid_unnecessary_addr_size|unique_unit_address|graph_|interrupt_provider|spi_bus_bridge|i2c_bus_reg)\)" || true
rm -f "$2.pre.dts"; ls -la "$2" | awk '{print $5, $9}'
