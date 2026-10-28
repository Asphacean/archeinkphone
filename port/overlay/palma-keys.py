#!/usr/bin/env python3
"""Palma 2 side buttons: the left "smart" button (gpio-keys KEY_PROG1 148, gpio123 needs the DT pull-up) forces a full GC16 redraw.
Grabs gpio-keys and re-emits every other key (volume up) through a uinput clone."""
import fcntl, glob, os, struct
KEYS, NOW = (148,), '/sys/module/panel_onyx_palma2_tcon/parameters/refresh_now'
dev = next(f'/dev/input/{os.path.basename(e)}' for e in glob.glob('/sys/class/input/event*') if open(e + '/device/name').read().strip() == 'gpio-keys')
def forwarder():
    """uinput clone for the keys we pass on (volume up), so only the smart key is swallowed."""
    u = os.open('/dev/uinput', os.O_WRONLY)
    fcntl.ioctl(u, 0x40045564, 1); fcntl.ioctl(u, 0x40045565, 115)     # EV_KEY, KEY_VOLUMEUP
    os.write(u, struct.pack('80sHHHHi', b'palma-keys', 0x19, 1, 1, 1, 0) + bytes(64 * 4 * 4))
    fcntl.ioctl(u, 0x5501)
    return u

out = forwarder()
with open(dev, 'rb') as f:
    fcntl.ioctl(f, 0x40044590, 1)   # EVIOCGRAB: the shell treats the smart key as typing and pops up the on-screen keyboard
    while True:
        ev = f.read(24)
        _, _, t, c, v = struct.unpack('llHHi', ev)
        if t == 1 and v == 1:
            print('key', c, flush=True)
        if t == 1 and c in KEYS:
            if v == 1:
                try:
                    with open(NOW, 'w') as n: n.write('1')
                except OSError as e: print('refresh_now:', e, flush=True)
            continue
        os.write(out, ev)                # everything else (volume up, SYN) goes on unchanged
