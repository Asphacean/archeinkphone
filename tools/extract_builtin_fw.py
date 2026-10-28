#!/usr/bin/env python3
"""Extract CONFIG_EXTRA_FIRMWARE blobs from a vmlinux ELF (built by vmlinux-to-elf).
Walks the .builtin_fw table between __start_builtin_fw/__end_builtin_fw: {name*, data*, size}.
Usage: extract_builtin_fw.py vmlinux.elf outdir"""
import sys, os, struct
from elftools.elf.elffile import ELFFile

path, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
f = open(path, 'rb'); elf = ELFFile(f)
segs = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
def v2o(v):
    for s in segs:
        if s['p_vaddr'] <= v < s['p_vaddr'] + s['p_filesz']:
            return v - s['p_vaddr'] + s['p_offset']
    raise ValueError(hex(v))
def rd(v, n): f.seek(v2o(v)); return f.read(n)
def cstr(v):
    b = rd(v, 256); return b.split(b'\0', 1)[0].decode()
syms = {}
for sec in elf.iter_sections():
    if sec.header['sh_type'] == 'SHT_SYMTAB':
        for s in sec.iter_symbols(): syms[s.name] = s['st_value']
start, end = syms['__start_builtin_fw'], syms['__end_builtin_fw']
print(f'.builtin_fw: {hex(start)}..{hex(end)} = {(end-start)//24} entries')
for v in range(start, end, 24):
    name_p, data_p, size = struct.unpack('<QQQ', rd(v, 24))
    name = cstr(name_p); dst = os.path.join(out, name.replace('/', '_'))
    open(dst, 'wb').write(rd(data_p, size))
    print(f'{name:45s} {size:9d} bytes @ {hex(data_p)} -> {dst}')
