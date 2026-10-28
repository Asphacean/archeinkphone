#!/usr/bin/env python3
"""pmOS twin of tools/palmareg/palmadpu.ko: dump DPU top/CTL/DMA SSPP/LM/PP/INTF_1 + DSI0 via /dev/mem ('addr value')."""
import mmap, os, struct
R = [(0x0ae01000, 0x500), (0x0ae02000, 0x800), (0x0ae25000, 0x200), (0x0ae27000, 0x200), (0x0ae29000, 0x200),
     (0x0ae45000, 0x320), (0x0ae46000, 0x320), (0x0ae71000, 0x100), (0x0ae71800, 0x100), (0x0ae6b800, 0x2c0), (0x0ae94000, 0x1000)]
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
for base, ln in R:
    pg = base & ~0xfff; m = mmap.mmap(fd, (base - pg + ln + 0xfff) & ~0xfff, mmap.MAP_SHARED, mmap.PROT_READ, offset=pg)
    for o in range(0, ln, 4): print('%08x %08x' % (base + o, struct.unpack('<I', m[base - pg + o:base - pg + o + 4])[0]))
