#!/bin/sh
# Heavier, slightly larger UI fonts for e-ink: Noto Sans SemiBold (600), one point up from the Breeze defaults (10/8).
w() { kwriteconfig6 --file kdeglobals --group General --key "$1" "$2"; }
w font                 "Noto Sans,11,-1,5,600,0,0,0,0,0,0,0,0,0,0,1"
w menuFont             "Noto Sans,11,-1,5,600,0,0,0,0,0,0,0,0,0,0,1"
w toolBarFont          "Noto Sans,11,-1,5,600,0,0,0,0,0,0,0,0,0,0,1"
w smallestReadableFont "Noto Sans,9,-1,5,600,0,0,0,0,0,0,0,0,0,0,1"
w fixed                "Hack,11,-1,5,600,0,0,0,0,0,0,0,0,0,0,1"
kwriteconfig6 --file kdeglobals --group WM --key activeFont "Noto Sans,11,-1,5,700,0,0,0,0,0,0,0,0,0,0,1"
