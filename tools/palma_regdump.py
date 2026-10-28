#!/usr/bin/env python3
"""pmOS twin of tools/palmareg (stock Android dump module): dump DSI0 ctrl/PHY/PLL, DPU INTF_1 and MDP top
via /dev/mem in the same 'addr value' map format as recon/android-*/regdump_android.txt.map. Root."""
import mmap, os, struct, sys
REGIONS = [(0x0ae94000, 0x1000), (0x0ae6b800, 0x300), (0x0ae01000, 0x500)]
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
for base, ln in REGIONS:
    pg = base & ~0xfff; m = mmap.mmap(fd, (base - pg + ln + 0xfff) & ~0xfff, mmap.MAP_SHARED, mmap.PROT_READ, offset=pg)
    for o in range(0, ln, 4):
        print('%08x %08x' % (base + o, struct.unpack('<I', m[base - pg + o:base - pg + o + 4])[0]))
