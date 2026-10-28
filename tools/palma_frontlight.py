#!/usr/bin/env python3
"""Boox Palma 2 front light (TI LM3630A @0x38 on i2c10 / 990000.i2c), registers as mainline lm3630a_bl.
usage: palma_frontlight.py <percent> [warm_percent]   (0 = off; banks A/B = warm/white, both = percent by default)
       palma_frontlight.py --level BR CT             (stock 33x33 tables: BR 0..32 brightness, CT 0 white (bank B) .. 32 warm (bank A))
Raw mode uses full-scale current code 0x0a; --level takes BRT and current per bank from the stock tables."""
import fcntl, glob, json, os, sys
TABLES = '/usr/local/share/palma2/frontlight-tables.json'
CTRL, CONFIG, BOOST, BRT_A, BRT_B, I_A, I_B, FILTER = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x50
SLEEP, LEDA_LINEAR, LEDB_LINEAR, I_FULL = 0x80, 0x14, 0x0A, 0x0A

def bus():
    for d in glob.glob('/sys/bus/i2c/devices/i2c-*'):
        if '990000' in os.path.realpath(d): return '/dev/' + os.path.basename(d)
    sys.exit('i2c10 (990000.i2c) not found: needs DTB with &i2c10 enabled')

def main():
    fd = os.open(bus(), os.O_RDWR); fcntl.ioctl(fd, 0x0706, 0x38)   # I2C_SLAVE_FORCE: the DT node has no driver
    w = lambda r, v: os.write(fd, bytes([r, v]))
    if sys.argv[1] == '--level':
        br, ct = (max(0, min(32, int(x))) for x in sys.argv[2:4]); t = json.load(open(TABLES))
        ba, bb, ca, cb = (t[k][ct][br] for k in ('ba', 'bb', 'ca', 'cb'))
        if not (ba or bb):
            w(BRT_A, 0); w(BRT_B, 0); w(CTRL, SLEEP); print('front light off'); return
        # as stock Android (reg_dump 27.10): CONFIG 0x18 = feedback on both banks (0 leaves bank B dark),
        # boost 0x7c, on/off and run ramps 0x09, exponential mapping (no LINEAR bits) the tables are made for
        w(FILTER, 0x03); w(CONFIG, 0x18); w(BOOST, 0x7c); w(0x07, 0x09); w(0x08, 0x09); w(I_A, ca); w(I_B, cb)
        w(CTRL, 0x06); w(BRT_A, ba); w(BRT_B, bb)
        print('front light br %d ct %d: A %#x/%#x B %#x/%#x' % (br, ct, ba, ca, bb, cb)); return
    cold = max(0, min(100, int(sys.argv[1]))); warm = max(0, min(100, int(sys.argv[2]))) if len(sys.argv) > 2 else cold
    if cold == 0 and warm == 0:
        w(BRT_A, 0); w(BRT_B, 0); w(CTRL, SLEEP); print('front light off'); return
    w(FILTER, 0x03); w(CONFIG, 0x00); w(BOOST, 0x38); w(I_A, I_FULL); w(I_B, I_FULL)
    w(CTRL, LEDA_LINEAR | LEDB_LINEAR)
    w(BRT_A, round(cold * 255 / 100)); w(BRT_B, round(warm * 255 / 100))
    os.write(fd, bytes([0x0B])); fault = os.read(fd, 1)[0]
    print('front light cold %d%% warm %d%% (fault reg %#x)' % (cold, warm, fault))

if __name__ == '__main__':
    main()
