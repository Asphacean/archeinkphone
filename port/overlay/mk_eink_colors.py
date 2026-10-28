#!/usr/bin/env python3
"""BreezeLight.colors -> EInk.colors: white backgrounds, black text/frames, inverted selection (16-level e-ink)."""
import re, sys
W, B, ALT, DIM = '255,255,255', '0,0,0', '230,230,230', '60,60,60'
out, sec = [], ''
for line in open(sys.argv[1]).read().splitlines():
    line = line.strip()
    if line.startswith("Name["): continue
    m = re.match(r'\[(.*)\]', line)
    if m: sec = m.group(1)
    k, eq, v = line.partition('=')
    if eq and re.fullmatch(r'\d+,\d+,\d+', v):
        inv = sec in ('Colors:Selection', 'Colors:Complementary')   # white on black: selection, and the shell over the (black) wallpaper, whose app labels are hard-coded white
        if k.startswith('Background'): v = B if inv else (ALT if k == 'BackgroundAlternate' else W)
        elif k == 'ForegroundInactive': v = '200,200,200' if inv else DIM
        elif k.startswith('Foreground') or k.startswith('Decoration'): v = W if inv else B
        elif sec == 'WM': v = B if 'Foreground' in k or k.startswith('inactiveForeground') or k.startswith('activeForeground') else W
        line = k + '=' + v
    if k == 'Name': line = 'Name=E-Ink'
    if k == 'ColorScheme': line = 'ColorScheme=EInk'
    if k == 'contrast': line = 'contrast=10'
    out.append(line)
print('\n'.join(out))
