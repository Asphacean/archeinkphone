#!/usr/bin/env python3
"""Poke TCON registers on the live system: palma_tcon_reg.py [REG VAL ...] [--gc]; no args = dump. The panel driver owns 0x34, hence I2C_SLAVE_FORCE."""
import fcntl, glob, os, sys, time
dev = next((('/dev/' + os.path.basename(d)) for d in glob.glob('/sys/bus/i2c/devices/i2c-*') if '984000' in os.path.realpath(d)), '/dev/i2c-0')
fd = os.open(dev, os.O_RDWR); fcntl.ioctl(fd, 0x0706, 0x34)
def rd(r): os.write(fd, bytes([r])); return os.read(fd, 1)[0]
a = [x for x in sys.argv[1:] if x != '--gc']
for r, v in zip(a[::2], a[1::2]): os.write(fd, bytes([int(r, 0), int(v, 0)])); time.sleep(0.01)
if '--gc' in sys.argv: os.write(fd, bytes([0x07, 0x01]))
print(' '.join('%02x=%02x' % (r, rd(r)) for r in (1, 2, 4, 5, 6, 8, 0x0a, 0x0b, 0x0c, 0x0d)))
