#!/usr/bin/env python3
"""Boox Palma 2 (pmOS): refresh the e-ink TCON whenever /dev/fb0 changes.
ponytail: polling + whole-fb compare; replace with an fbdev-damage hook in the panel driver later."""
import fcntl, glob, mmap, os, sys, time
FB, VCS, VCOM, POLL, SETTLE, MIN_GAP = '/dev/fb0', '/dev/vcsa', 200, 0.1, 0.06, 0.09
FB_EVERY = 1.0   # reading the 5.4 MB uncached scanout costs ~25 ms, so compare the 21 KB console snapshot (/dev/vcsa) per poll and the fb only once a second
GC_MIN, GC_HARD, GC_IDLE = 8, 48, 3.0   # GC16 when idle after >=GC_MIN partial updates, or forced at GC_HARD
# TCON UI_MODE_SET codes measured 26.10: GC16 0x01 ~0.5 s, DU 0x12 ~0.32 s, 0x04/0x14 ~0.19 s (A2-like, 1-bit).
# The TCON runs overlapping updates (WF_SEND_STATE is a slot bitmask), so no need to wait for idle.
FAST, GC16 = (0x14 if '--a2' in sys.argv else 0x12), 0x01
I2C_SLAVE = 0x0703

def find_i2c():
    for p in glob.glob('/sys/bus/i2c/devices/i2c-*/of_node/name'):
        d = os.path.dirname(os.path.dirname(p))
        try:
            if os.readlink(d).find('984000') >= 0 or '984000' in os.path.realpath(d): return '/dev/' + os.path.basename(d)
        except OSError: pass
    return '/dev/i2c-0'

class Tcon:
    def __init__(self, dev):
        self.fd = os.open(dev, os.O_RDWR); fcntl.ioctl(self.fd, I2C_SLAVE, 0x34)
    def write(self, reg, val): os.write(self.fd, bytes([reg, val]))
    def read(self, reg): os.write(self.fd, bytes([reg])); return os.read(self.fd, 1)[0]
    def busy(self): return self.read(0x20) != 0 or self.read(0x21) != 0
    def wait_idle(self, t=2.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < t:
            if not self.busy(): return True
            time.sleep(0.02)
        return False

def main():
    tcon = Tcon(sys.argv[1] if len(sys.argv) > 1 else find_i2c())
    tcon.write(0x08, VCOM - 50); time.sleep(0.01); tcon.write(0x07, 0x20); time.sleep(0.05)
    try: open('/sys/class/graphics/fbcon/cursor_blink', 'w').write('0')   # blinking cursor = 5 fb changes/s
    except OSError: pass
    fd = os.open(FB, os.O_RDONLY)
    fb = mmap.mmap(fd, 1648 * 824 * 4, mmap.MAP_SHARED, mmap.PROT_READ)
    try: vcs = os.open(VCS, os.O_RDONLY)
    except OSError: vcs = None
    vlen = len(os.pread(vcs, 1 << 20, 0)) + 64 if vcs is not None else 0
    snap = (lambda: os.pread(vcs, vlen, 0)) if vcs is not None else (lambda: b'')
    last_v, last_f = snap(), fb[:]; t_f = time.monotonic()
    n = 0; t_last = 0.0      # n = partial updates since last GC16
    tcon.write(0x07, GC16); tcon.wait_idle()
    while True:
        time.sleep(POLL)
        now = time.monotonic(); changed = snap() != last_v
        if not changed and now - t_f >= FB_EVERY:
            f = fb[:]; changed = f != last_f; last_f = f; t_f = now
        if not changed:
            if n >= GC_MIN and now - t_last > GC_IDLE:
                tcon.write(0x07, GC16); n = 0; t_last = now
            continue
        time.sleep(SETTLE)                                     # short settle only
        gap = MIN_GAP - (time.monotonic() - t_last)
        if gap > 0: time.sleep(gap)
        n += 1
        if n >= GC_HARD: tcon.write(0x07, GC16); n = 0
        else: tcon.write(0x07, FAST)
        last_v, last_f = snap(), fb[:]; t_last = t_f = time.monotonic()

if __name__ == '__main__':
    main()
