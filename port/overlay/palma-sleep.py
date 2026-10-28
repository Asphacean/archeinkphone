#!/usr/bin/env python3
"""Palma 2 sleep mode (root daemon). Power key: front light off, sleep clock on screen, then s2idle with an RTC
alarm at every minute boundary; each RTC wake lets the clock repaint (GC16 every 15 min) and goes back to sleep.
Power key again: clock closed, light restored, session locked. The key device is grabbed, so the shell never sees it."""
import fcntl, glob, os, select, struct, subprocess, time
USER, UID = 'user', 10000
ENV = ['env', f'XDG_RUNTIME_DIR=/run/user/{UID}', 'WAYLAND_DISPLAY=wayland-1', f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{UID}/bus', 'QT_QPA_PLATFORM=wayland']
NOW = '/sys/module/panel_onyx_palma2_tcon/parameters/refresh_now'
KEY_POWER, SETTLE, GC_EVERY = 116, 2.0, 15

def evdev(name):
    return next(f'/dev/input/{os.path.basename(e)}' for e in glob.glob('/sys/class/input/event*') if open(e + '/device/name').read().strip() == name)

def presses(fd, timeout):
    """True if a power key press arrives within timeout (drains the queue)."""
    hit = False
    while select.select([fd], [], [], timeout)[0]:
        for i in range(0, len(buf := os.read(fd, 24 * 64)), 24):
            _, _, t, c, v = struct.unpack('llHHi', buf[i:i + 24])
            hit |= t == 1 and c == KEY_POWER and v == 1
        timeout = 0
    return hit

def full_refresh():
    try:
        with open(NOW, 'w') as f: f.write('1')
    except OSError: pass

def suspend_until_next_minute():
    t = time.time()
    open('/sys/class/rtc/rtc0/wakealarm', 'w').write('0')
    open('/sys/class/rtc/rtc0/wakealarm', 'w').write('+%d' % max(2, int(60 - t % 60) + 1))
    try: open('/sys/power/state', 'w').write('freeze')
    except OSError: time.sleep(1)   # a pending wakeup aborted the suspend

def sleep_mode(fd):
    light = subprocess.run(['/usr/local/bin/palma-light'], capture_output=True, text=True).stdout.split()
    subprocess.run(['/usr/bin/python3', '/usr/local/bin/palma_frontlight.py', '0'], capture_output=True)
    clock = subprocess.Popen(['runuser', '-u', USER, '--'] + ENV + ['/usr/lib/qt6/bin/qmlscene', '/usr/local/share/palma2/sleepclock.qml'])
    time.sleep(SETTLE); full_refresh(); time.sleep(SETTLE)
    n = 0
    while True:
        suspend_until_next_minute()
        if presses(fd, SETTLE):                        # woken by the power key (or pressed right after)
            break
        n += 1
        if n % GC_EVERY == 0:
            full_refresh(); time.sleep(1)
    clock.terminate()
    if len(light) == 2: subprocess.run(['/usr/local/bin/palma-light', 'apply'], capture_output=True)
    subprocess.run(['loginctl', 'lock-sessions'])
    time.sleep(0.5); full_refresh()

def main():
    fd = os.open(evdev('pm8941_pwrkey'), os.O_RDONLY)
    fcntl.ioctl(fd, 0x40044590, 1)                   # EVIOCGRAB: KWin/powerdevil/the shell must not see the key
    while True:
        if presses(fd, None):
            sleep_mode(fd)
            presses(fd, 0.5)                           # swallow key bounce

if __name__ == '__main__':
    main()
