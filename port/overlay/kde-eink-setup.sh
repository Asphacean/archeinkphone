#!/bin/sh
# Boox Palma 2: tune Plasma (Mobile) for e-ink. Run as the session user.
# Every DRM commit becomes a TCON refresh (panel driver commit trigger), so kill anything that animates or blinks.
set -e
w() { kwriteconfig6 "$@"; }
w --file kdeglobals --group KDE --key AnimationDurationFactor 0
w --file kdeglobals --group General --key ColorScheme BreezeLight
w --file kdeglobals --group KDE --key LookAndFeelPackage org.kde.breeze.desktop
w --file kdeglobals --group KDE --key CursorBlinkRate 0          # Qt text cursors (QStyleHints)
w --file kwinrc --group Compositing --key AnimationSpeed 0
w --file kwinrc --group Plugins --key blurEnabled false
w --file kwinrc --group Plugins --key contrastEnabled false
w --file kwinrc --group Plugins --key slidingpopupsEnabled false
w --file kwinrc --group Plugins --key fadingpopupsEnabled false
w --file kwinrc --group Plugins --key scaleEnabled false
w --file kwinrc --group Plugins --key kwin4_effect_fadeEnabled false
w --file kwinrc --group Plugins --key kwin4_effect_scaleEnabled false
w --file plasmarc --group Theme --key name default   # "default" follows the colour scheme; breeze-light hard-codes white status-bar text
w --file konsolerc --group "Desktop Entry" --key DefaultProfile EInk.profile
mkdir -p ~/.local/share/konsole
cat > ~/.local/share/konsole/EInk.profile <<'P'
[Appearance]
ColorScheme=BlackOnWhite
Font=Monospace,11,-1,5,50,0,0,0,0,0
[Cursor Options]
BlinkingCursorEnabled=false
[General]
Name=EInk
Parent=FALLBACK/
[Scrolling]
ScrollBarPosition=2
P
w --file kscreenlockerrc --group Daemon --key LockOnStart false   # pmOS default true: dark lock screen at every login
w --file kscreenlockerrc --group Daemon --key Autolock false
w --file kscreenlockerrc --group Daemon --key LockOnResume false
echo "kde e-ink settings applied"


# high-contrast colour scheme (port/overlay/EInk.colors, made by mk_eink_colors.py from BreezeLight)
mkdir -p ~/.local/share/color-schemes && cp EInk.colors ~/.local/share/color-schemes/ && plasma-apply-colorscheme EInk

# heavier/larger UI fonts
sh eink-fonts.sh

# wallpaper: white with black bars under status/nav. Folio app labels are hard-coded "white" in QML compiled into the
# plugin; folio-black.so = plasma-mobile 6.8.1 folio.so with those strings byte-patched to "black" (unit strings + qrc
# sources). Loaded from ~/.local via QT_PLUGIN_PATH, so a plasma-mobile upgrade needs a re-patch (offsets differ).
mkdir -p ~/.local/lib/qt6/plugins/plasma/applets ~/.config/environment.d
cp folio-black.so ~/.local/lib/qt6/plugins/plasma/applets/org.kde.plasma.mobile.homescreen.folio.so
echo "QT_PLUGIN_PATH=$HOME/.local/lib/qt6/plugins:/usr/lib/qt6/plugins" > ~/.config/environment.d/palma-plugins.conf
cp eink-wallpaper.png ~/ && plasma-apply-wallpaperimage ~/eink-wallpaper.png

# e-ink UI rules (flat, no shadows/translucency/animation, solid outlines): Breeze widget + decoration
kwriteconfig6 --file breezerc --group Style --key AnimationsEnabled false
kwriteconfig6 --file breezerc --group Style --key MenuOpacity 100
kwriteconfig6 --file breezerc --group Common --key ShadowSize ShadowNone
kwriteconfig6 --file breezerc --group Common --key OutlineIntensity OutlineHigh
kwriteconfig6 --file kwinrc --group Plugins --key translucencyEnabled false
kwriteconfig6 --file kwinrc --group Plugins --key dimscreenEnabled false

# power button handled by palma-sleep.service (sleep clock + s2idle), so powerdevil does nothing
for g in AC Battery LowBattery; do kwriteconfig6 --file powerdevilrc --group $g --group SuspendAndShutdown --key PowerButtonAction 0; done

# global contrast curve: ICC profile with a VCGT S-curve (tools/mk_contrast_icc.py), applied by KWin to the whole output
python3 mk_contrast_icc.py ~/eink-contrast.icc 1.6 0.08 0.92 && kscreen-doctor output.1.iccprofile.$HOME/eink-contrast.icc output.1.colorProfileSource.ICC

# haptics: default feedbackd theme uses 7 ms @0.2 for keys, too short for the AW86938 LRA
sudo install -m644 onyx,palma2.json /usr/share/feedbackd/themes/onyx,palma2.json
