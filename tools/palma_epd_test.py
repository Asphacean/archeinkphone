#!/usr/bin/env python3
"""Onyx Boox Palma 2 e-ink bring-up: push one static frame through the Lattice TCON on mainline.

Runs on the device as root, stdlib only. Protocol = PLAN.md "Фаза 1b" (stock lfe5u / onyx_tcon):
  * TCON control port = I2C 0x34 on QUP SE7 (i2c@984000); a command is a 2-byte write [reg, data].
  * A frame is plain DSI video 1648x824 (gray, R=G=B). Pixel (0,0) carries the command:
    R = 0x07 (CMD_TCON_UI_MODE_SET), G = mode, B = update marker (sde_plane_set_fb_marker).
    Once that frame has been scanned out the stock driver clears the pixel and sends the same
    mode over I2C [0x07, mode] (onyx_tcon_cmd_triger -> onyx_tcon_send_cmd); the marker is not sent on I2C.
  * modes: 0x01 GC16 full, 0x10 GC16 partial, 0x15 GC16 regal partial, 0x03 GL16, 0x12 DU, 0x20 sync.
Typical: python3 palma_epd_test.py --dump ; python3 palma_epd_test.py ; ... --pattern white --marker 2
"""
import argparse, ctypes as C, fcntl, glob, mmap, os, struct, sys, time

# I2C 0x34 registers: names/numbers from the stock /sys/class/ebc/dump_reg (recon/root/sysfs_vals.txt)
REGS = {0x01: 'GC_FULL_MODE', 0x02: 'AUTO_MODE_CTRL', 0x04: 'A2_FRAME_NUM', 0x05: 'CONTRAST',
        0x06: 'DISPLAY_MODE', 0x07: 'UI_MODE_SET', 0x08: 'VCOM', 0x0a: 'FILTER_P1', 0x0b: 'FILTER_P2',
        0x0c: 'A2_THRESHOLD_WHITE', 0x0d: 'A2_THRESHOLD_BLACK', 0x0e: 'DEBOUNCE_ENABLE',
        0x10: 'DEBOUNCE_PARM', 0x11: 'DEBOUNCE_THRESHOLD', 0x20: 'PM_STATE', 0x21: 'WF_SEND_STATE',
        0x22: 'FLG_STATE', 0x23: 'ERROR'}
MODES = {'gc16': 0x01, 'gc16-partial': 0x10, 'gc16-regal': 0x15, 'gl16': 0x03, 'du': 0x12, 'sync': 0x20}
TCON_ADDR = 0x34
# FPGA sysCONFIG/power pins on tlmm (stock lfcpnx@0): offset, active-low
FPGA_PINS = {'reset': (122, True), 'standby': (96, True), 'programn': (38, True),
             'done': (8, False), 'pwr_30v': (97, False), 'pwr_12v_core': (58, False)}


def ms(n):
    time.sleep(n / 1000)


# ---------------------------------------------------------------- I2C (i2c-dev)
I2C_SLAVE_FORCE, I2C_RDWR, I2C_M_RD = 0x0706, 0x0707, 1


class I2cMsg(C.Structure):
    _fields_ = [('addr', C.c_uint16), ('flags', C.c_uint16), ('len', C.c_uint16), ('buf', C.POINTER(C.c_uint8))]


class I2cRdwr(C.Structure):
    _fields_ = [('msgs', C.POINTER(I2cMsg)), ('nmsgs', C.c_uint32)]


class Tcon:
    def __init__(self, dev):
        self.fd = os.open(dev, os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE_FORCE, TCON_ADDR)   # FORCE: a driverless DT client sits at 0x34

    def write(self, reg, val):                               # lfe5u_i2c_write_reg: [cmd, operand]
        print(f'  i2c -> {REGS.get(reg, "?"):18s} [{reg:#04x}] = {val:#04x}')
        os.write(self.fd, bytes([reg, val & 0xff]))

    def read(self, reg):                                     # smbus read-byte-data (lfe5u_ctrl_get_vcom)
        w, r = (C.c_uint8 * 1)(reg), (C.c_uint8 * 1)()
        msgs = (I2cMsg * 2)(I2cMsg(TCON_ADDR, 0, 1, w), I2cMsg(TCON_ADDR, I2C_M_RD, 1, r))
        fcntl.ioctl(self.fd, I2C_RDWR, I2cRdwr(msgs, 2))
        return r[0]


def find_i2c():
    for d in glob.glob('/sys/bus/i2c/devices/i2c-*'):
        try:
            if os.readlink(d + '/of_node').endswith('i2c@984000'):
                return '/dev/' + os.path.basename(d)
        except OSError:
            pass
    sys.exit('i2c@984000 adapter not found (modprobe i2c-dev? &i2c7 enabled in DT?)')


# ---------------------------------------------------------------- framebuffer (DRM fbdev emulation)
FBIOGET_VSCREENINFO, FBIOGET_FSCREENINFO = 0x4600, 0x4602


class Fb:
    def __init__(self, dev):
        self.fd = os.open(dev, os.O_RDWR)
        v = fcntl.ioctl(self.fd, FBIOGET_VSCREENINFO, bytes(160))
        self.xres, self.yres, _, _, _, _, self.bpp, _ = struct.unpack_from('8I', v, 0)
        self.roff, self.goff, self.boff = (struct.unpack_from('I', v, 32 + 12 * i)[0] for i in range(3))
        toff, tlen = struct.unpack_from('II', v, 68)
        f = fcntl.ioctl(self.fd, FBIOGET_FSCREENINFO, bytes(80))
        smem_len, self.stride = struct.unpack_from('I', f, 24)[0], struct.unpack_from('I', f, 48)[0]
        assert self.bpp == 32, f'need a 32 bpp framebuffer, got {self.bpp}'
        self.alpha = (0xff << toff) if tlen else 0
        self.mem = mmap.mmap(self.fd, smem_len)
        print(f'  fb {self.xres}x{self.yres} {self.bpp}bpp stride {self.stride} '
              f'R@{self.roff} G@{self.goff} B@{self.boff}')

    def px(self, r, g, b):
        return struct.pack('<I', (r << self.roff) | (g << self.goff) | (b << self.boff) | self.alpha)

    def show(self, rows):
        pad = b'\0' * (self.stride - self.xres * 4)
        self.mem.seek(0)
        self.mem.write(b''.join(row + pad for row in rows))

    def cmd_pixel(self, mode, marker, order):                # stock: bytes 0..2 of an ABGR8888 fb = R,G,B
        rgb = (0x07, mode, marker) if order == 'rgb' else (marker, mode, 0x07)
        self.mem[0:4] = self.px(*rgb)

    def clear_cmd_pixel(self):                               # sde_plane_clear_fb_marker: 3 bytes -> 0
        self.mem[0:4] = self.px(0, 0, 0)


def pattern(fb, kind):
    W, H, black, white = fb.xres, fb.yres, fb.px(0, 0, 0), fb.px(255, 255, 255)
    if kind in ('white', 'black'):
        return [(white if kind == 'white' else black) * W] * H
    # ramp: 16 gray bars (0..255 step 17), bottom quarter 64 px checkerboard, 4 px black frame
    bars = b''.join(fb.px(i * 17, i * 17, i * 17) * (W // 16) for i in range(16))
    bars = bars + white * ((W * 4 - len(bars)) // 4)
    checker = b''.join(black if (x // 64) % 2 else white for x in range(W))
    rows = []
    for y in range(H):
        body = checker if y >= H * 3 // 4 else bars
        rows.append(black * W if y < 4 or y >= H - 4 else black * 4 + body[16:-16] + black * 4)
    return rows


# ---------------------------------------------------------------- GPIO cdev v2 (optional FPGA sequencing)
GPIO_GET_CHIPINFO, GPIO_V2_GET_LINE = 0x8044B401, 0xC250B407
GPIO_V2_SET_VALUES, GPIO_V2_GET_VALUES = 0xC010B40F, 0xC010B40E
F_ACTIVE_LOW, F_INPUT, F_OUTPUT = 1 << 1, 1 << 2, 1 << 3


def line_request(offset, flags):                           # struct gpio_v2_line_request, 592 bytes
    return (struct.pack('64I', offset, *[0] * 63) + b'palma_epd'.ljust(32, b'\0')
            + struct.pack('QI5I', flags, 0, *[0] * 5) + bytes(240)      # gpio_v2_line_config
            + struct.pack('II5Ii', 1, 0, *[0] * 5, 0))                  # num_lines, evbuf, pad, fd


class Tlmm:
    """stdlib GPIO via the character device (libgpiod v1/v2 CLI syntax and line holding differ)."""

    def __init__(self, label=b'f100000.pinctrl'):
        for dev in sorted(glob.glob('/dev/gpiochip*')):
            fd = os.open(dev, os.O_RDWR)
            if label in fcntl.ioctl(fd, GPIO_GET_CHIPINFO, bytes(68))[32:64]:
                self.fd, self.lines = fd, {}
                return
            os.close(fd)
        sys.exit(f'no gpiochip labelled {label!r} (CONFIG_GPIO_CDEV?)')

    def line(self, offset, flags):
        res = fcntl.ioctl(self.fd, GPIO_V2_GET_LINE, line_request(offset, flags))
        self.lines[offset] = struct.unpack_from('i', res, 588)[0]   # fd; EBUSY = kernel driver owns it

    def set(self, offset, v):                                  # logical value (active-low handled by flag)
        fcntl.ioctl(self.lines[offset], GPIO_V2_SET_VALUES, struct.pack('QQ', 1 if v else 0, 1))

    def get(self, offset):
        return struct.unpack('QQ', fcntl.ioctl(self.lines[offset], GPIO_V2_GET_VALUES, struct.pack('QQ', 0, 1)))[0] & 1


def fpga_power(t):
    """lfe5u_power_ctrl(1) + lfe5u_config_done_wait (+ lfe5u_load_fw retry), same as the panel driver.
    vdd1v8 (L5A) / vdd1v2 (L3E) are regulators: only the kernel enables them (panel driver does)."""
    for name, (off, low) in FPGA_PINS.items():
        t.line(off, (F_INPUT if name == 'done' else F_OUTPUT) | (F_ACTIVE_LOW if low else 0))
    print('  FPGA: RESET low, PROGRAMN high, STANDBY high, 30V on, 12V_CORE on, RESET high')
    t.set(122, 1); t.set(38, 0); t.set(96, 0); t.set(97, 1); ms(2); t.set(58, 1); ms(4); t.set(122, 0); ms(3)
    ms(100)
    for attempt in range(3):
        for _ in range(20):
            ms(50)
            if t.get(8):
                ms(5)
                if t.get(8):
                    ms(100)
                    print('  FPGA: DONE')
                    return
        if attempt == 2:
            sys.exit('FPGA DONE timeout')
        print('  FPGA: DONE timeout, pulsing PROGRAMN')
        t.set(38, 1); ms(50); t.set(38, 0)


def selftest():
    class F:                                                   # XRGB8888 geometry
        xres, roff, goff, boff, alpha = 4, 16, 8, 0, 0
        px = Fb.px
    assert Fb.px(F, 0x07, 0x01, 0x05) == struct.pack('<I', 0x00070105)
    assert len(line_request(122, F_OUTPUT | F_ACTIVE_LOW)) == 592
    assert 200 - 50 == 0x96                                    # live dump: VCOM reg 0x96 at vcom 200
    assert MODES['gc16'] == 0x01 and MODES['sync'] == 0x20
    print('selftest ok')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--i2c', help='i2c-dev node (default: the adapter of i2c@984000)')
    ap.add_argument('--fb', default='/dev/fb0')
    ap.add_argument('--vcom', type=int, default=200, help='VCOM in -10 mV units; stock onyxconfig = 200 (-2.00 V)')
    ap.add_argument('--mode', default='gc16', help=', '.join(MODES) + ' or a hex byte')
    ap.add_argument('--marker', type=int, default=1, help='update marker, 1..255, change it per frame')
    ap.add_argument('--pattern', default='ramp', choices=['ramp', 'white', 'black'])
    ap.add_argument('--cmd-order', default='rgb', choices=['rgb', 'bgr'],
                    help='which colour channel carries 0x07 (rgb = R, as the stock ABGR8888 byte 0)')
    ap.add_argument('--fpga-power', action='store_true',
                    help='run the FPGA GPIO sequence here (only if the DT panel node has no fpga-*-gpios)')
    ap.add_argument('--no-init', action='store_true', help='skip VCOM + sync (TCON already initialised)')
    ap.add_argument('--dump', action='store_true', help='read the register map and exit')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.fpga_power:
        fpga_power(Tlmm())
    tcon = Tcon(a.i2c or find_i2c())
    if a.dump:
        for reg, name in REGS.items():
            print(f'  {name:18s} [{reg:#04x}] = {tcon.read(reg):#04x}')
        return
    if not a.no_init:
        # lfe5u_ctrl_set_vcom: data = vcom - 50, vcom in [50, 305]; lfe5u_i2c_probe: UI_MODE_SET sync, 50 ms
        assert 50 <= a.vcom <= 305, 'vcom off-limits'
        tcon.write(0x08, a.vcom - 50); ms(10)
        tcon.write(0x07, MODES['sync']); ms(50)
        print(f'  VCOM readback {tcon.read(0x08) + 50}')
    mode = MODES.get(a.mode) or int(a.mode, 0)
    fb = Fb(a.fb)
    fb.show(pattern(fb, a.pattern))
    fb.cmd_pixel(mode, a.marker, a.cmd_order)              # sde_plane_set_fb_marker before kickoff
    ms(60)                                                 # >= 2 frames @60 Hz carry the marker
    fb.clear_cmd_pixel()                                   # onyx_tcon_cmd_triger: clear, then I2C
    tcon.write(0x07, mode)
    ms(200)
    print('  state:', ' '.join(f'{REGS[r]}={tcon.read(r):#04x}' for r in (0x20, 0x21, 0x22, 0x23)))


if __name__ == '__main__':
    main()
