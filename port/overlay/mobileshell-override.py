#!/usr/bin/env python3
"""Shadow org.kde.plasma.private.mobileshell under /usr/local/lib/qml (QML_IMPORT_PATH) with the front light
sliders added to the action drawer. Everything is a symlink to the packaged module except the qmldir (no
'prefer :/', so the .qml files are read from disk) and QuickSettings.qml. Rerun after a plasma-mobile upgrade."""
import os, shutil, sys
SRC, DST = '/usr/lib/qt6/qml/org/kde/plasma/private/mobileshell', '/usr/local/lib/qml/org/kde/plasma/private/mobileshell'
ITEM = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'FrontlightItem.qml') if len(sys.argv) < 2 else sys.argv[1]
shutil.rmtree(DST, ignore_errors=True)
for root, dirs, files in os.walk(SRC):
    rel = os.path.relpath(root, SRC); os.makedirs(os.path.join(DST, rel), exist_ok=True)
    for f in files: os.symlink(os.path.join(root, f), os.path.join(DST, rel, f))
q = os.path.join(DST, 'qmldir'); lines = open(q).read().splitlines(); os.unlink(q)
lines = [l for l in lines if not l.startswith('prefer ')] + ['FrontlightItem 254.0 actiondrawer/private/FrontlightItem.qml']
open(q, 'w').write('\n'.join(lines) + '\n')
shutil.copy(ITEM, os.path.join(DST, 'actiondrawer/private/FrontlightItem.qml'))
qs = os.path.join(DST, 'actiondrawer/private/QuickSettings.qml'); s = open(qs).read(); os.unlink(qs)
anchor = '        // Brightness slider\n'
assert s.count(anchor) == 1, 'QuickSettings.qml changed upstream, update mobileshell-override.py'
s = s.replace(anchor, '''        // Palma 2 front light (mobileshell-override.py)
        FrontlightItem {
            Layout.bottomMargin: Kirigami.Units.smallSpacing * 2
            Layout.leftMargin: Kirigami.Units.smallSpacing
            Layout.rightMargin: Kirigami.Units.smallSpacing
            Layout.fillWidth: true
        }

''' + anchor)
# the stock slider drives KWin's software brightness, which only greys an e-ink screen
s = s.replace('            id: brightnessItem\n', '            id: brightnessItem\n            visible: false\n', 1)
open(qs, 'w').write(s)
print('ok', DST)
