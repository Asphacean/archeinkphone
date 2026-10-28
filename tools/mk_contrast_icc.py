#!/usr/bin/env python3
"""ICC v2 display profile = sRGB + a VCGT contrast curve, for KWin (applies vcgt to the whole output).
usage: mk_contrast_icc.py OUT.icc [STRENGTH] [BLACK] [WHITE]
  STRENGTH  S-curve steepness around mid-grey, 1.0 = identity (default 1.6)
  BLACK/WHITE  input levels clipped to pure black/white (default 0.08 / 0.92)"""
import math, struct, sys

def s15(v): return struct.pack('>i', round(v * 65536))
def xyz(x, y, z): return b'XYZ \0\0\0\0' + s15(x) + s15(y) + s15(z)
def curve(x, k, lo, hi):
    t = min(1.0, max(0.0, (x - lo) / (hi - lo)))
    if k == 1.0: return t
    f = lambda u: 1 / (1 + math.exp(-k * 4 * (u - 0.5)))      # logistic, normalised to 0..1
    return (f(t) - f(0)) / (f(1) - f(0))

def profile(k, lo, hi, name):
    desc = name.encode() + b'\0'
    tags = [
        (b'desc', b'desc\0\0\0\0' + struct.pack('>I', len(desc)) + desc + b'\0' * 8 + b'\0' * 3 + b'\0' * 67),
        (b'cprt', b'text\0\0\0\0public domain\0'),
        (b'wtpt', xyz(0.9642, 1.0, 0.8249)),
        (b'rXYZ', xyz(0.4361, 0.2225, 0.0139)),
        (b'gXYZ', xyz(0.3851, 0.7169, 0.0971)),
        (b'bXYZ', xyz(0.1431, 0.0606, 0.7141)),
    ]
    trc = b'curv\0\0\0\0' + struct.pack('>IH', 1, 0x0233) + b'\0\0'            # gamma 2.2
    tags += [(b'rTRC', trc), (b'gTRC', trc), (b'bTRC', trc)]
    table = b''.join(struct.pack('>H', round(curve(i / 255, k, lo, hi) * 65535)) for i in range(256))
    tags.append((b'vcgt', b'vcgt\0\0\0\0' + struct.pack('>IHHH', 0, 3, 256, 2) + table * 3))
    off, body, ents = 128 + 4 + 12 * len(tags), b'', b''
    for sig, data in tags:
        data += b'\0' * (-len(data) % 4)
        ents += sig + struct.pack('>II', off + len(body), len(data))
        body += data
    size = off + len(body)
    hdr = struct.pack('>I4sI4s4s4s', size, b'\0' * 4, 0x02100000, b'mntr', b'RGB ', b'XYZ ') + b'\0' * 12 + b'acsp' + b'\0' * 24 \
        + b'\0' * 4 + s15(0.9642) + s15(1.0) + s15(0.8249) + b'\0' * 48
    assert len(hdr) == 128
    return hdr + struct.pack('>I', len(tags)) + ents + body

if __name__ == '__main__':
    a = sys.argv[1:]
    k, lo, hi = float(a[1]) if len(a) > 1 else 1.6, float(a[2]) if len(a) > 2 else 0.08, float(a[3]) if len(a) > 3 else 0.92
    open(a[0], 'wb').write(profile(k, lo, hi, 'Palma2 e-ink contrast %.2f %.2f-%.2f' % (k, lo, hi)))
    assert abs(curve(0.5, k, lo, hi) - 0.5) < 1e-9 and curve(lo, k, lo, hi) == 0 and curve(hi, k, lo, hi) == 1   # self-check
