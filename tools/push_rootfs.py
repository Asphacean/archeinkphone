#!/usr/bin/env python3
"""Stream the pmOS root image into the rawdump partition (/dev/sda7) of the Palma 2 over the
pmOS initramfs USB network (telnet 172.16.42.1 + nc), verify sha256, resize the fs, fix fstab."""
import socket, time, subprocess, hashlib, sys, os
IMG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'port/build/onyx-palma2-root.img')
DEV = '/dev/sda7'; HOST = '172.16.42.1'; PORT = 9000
size = os.path.getsize(IMG)
sha = hashlib.sha256(open(IMG, 'rb').read()).hexdigest()
s = socket.create_connection((HOST, 23), 5); s.settimeout(2)
def rd(t=2):
    out = b''; end = time.time() + t
    while time.time() < end:
        try:
            b = s.recv(65536)
            if not b: break
            out += b
        except socket.timeout: break
    return out
def sh(cmd, t=3):
    s.sendall((cmd + "\n").encode()); return rd(t).decode(errors='replace').replace('\x1b[6n', '')
rd(2)
print(sh(f"grep PARTNAME /sys/block/sda/sda7/uevent; blockdev --getsize64 {DEV}"))
print(sh("pkill nc; pkill dd; sleep 1; pgrep -a nc; pgrep -a dd; echo cleaned", 3))
sh(f"(sleep 3600 | nc -l -p {PORT} | dd of={DEV} bs=4M 2>/tmp/dd.log; echo DD_EXIT=$? >> /tmp/dd.log) </dev/null >/dev/null 2>&1 &", 1)
time.sleep(2)
t0 = time.time()
r = subprocess.run(f"nc -w 10 {HOST} {PORT} < {IMG}", shell=True)
print(f"sent {size} bytes in {time.time()-t0:.0f}s, nc rc={r.returncode}")
for _ in range(60):
    o = sh("cat /tmp/dd.log", 2)
    if 'DD_EXIT' in o: break
    time.sleep(2)
print(o); sh("sync", 5)
print("verifying on device (sha256 of %d bytes)..." % size)
out = sh(f"head -c {size} {DEV} | sha256sum", 240)
print(out); ok = sha[:16] in out
print("SHA256 MATCH" if ok else f"SHA256 MISMATCH (expected {sha[:16]})")
if ok:
    print(sh(f"e2fsck -f -y {DEV} 2>&1 | tail -2; resize2fs {DEV} 2>&1 | tail -2", 60))
    print(sh(f"mkdir -p /mnt/r && mount {DEV} /mnt/r && cat /mnt/r/etc/fstab && df -h /mnt/r | tail -1", 5))
    print(sh("sed -i -E 's|^([^#].*pmOS_boot.*)$|#\\1|; s|^([^#].*[[:space:]]/boot[[:space:]].*)$|#\\1|' /mnt/r/etc/fstab; echo ---; cat /mnt/r/etc/fstab; umount /mnt/r; sync; echo DONE", 5))
