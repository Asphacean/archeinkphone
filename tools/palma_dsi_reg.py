#!/usr/bin/env python3
"""Read/write MSM DSI0 controller registers on the Palma 2 via /dev/mem (root).
usage: palma_dsi_reg.py r OFFSET | w OFFSET VALUE   (offsets as in dsi.xml, e.g. 0xb8 = HS_TIMER_CTRL)"""
import mmap, os, struct, sys
BASE, SHIFT = 0xae94000, 4
fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x1000, offset=BASE)
off = SHIFT + int(sys.argv[2], 0)
if sys.argv[1] == 'w':
    m[off:off + 4] = struct.pack('<I', int(sys.argv[3], 0))
print('0x%03x = 0x%08x' % (int(sys.argv[2], 0), struct.unpack('<I', m[off:off + 4])[0]))
