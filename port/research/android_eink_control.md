# Stock Boox Android (Palma 2, SM6350): how the e-ink display is controlled

Date: 2026-10-27. Method: read-only static analysis. Sources: the decompiled stock kernel (`analysis/decomp_str/*.c`, `analysis/vmlinux.elf`),
`system_a`/`system_ext_a`/`vendor_a` from `backup/edl-2026-10-25/lun0/super.bin` (LP metadata parsed, ext4 read with debugfs),
`framework.jar`/`framework-res.apk` (custom dex disassembler, see "Tools"), `/system/bin/surfaceflinger` (objdump plus string xrefs),
the `onyxconfig` partition (MMKV store) and the Android dmesg capture `recon/android-20261026-1447/dmesg_root.txt`.
Labels: **[fact]** = read directly from code, data or logs. **[infer]** = consistent with several pieces of evidence. **[guess]** = plausible, not verified.

## 0. TL;DR

* The control chain is: app/`com.onyx` settings, then `android.onyx.optimization` (EAC = "E-ink App Config", runs inside
  framework/system_server), then a Binder transaction (`ViewUpdateHelper`, codes 0xFF00xx/0x1000xx) to **SurfaceFlinger** (Onyx-patched,
  `HWEpdcManager`), then two paths into the kernel:
  1. **per frame**: a list of `upd_data` regions (waveform_mode, update_mode, marker, flags) goes through HWC (`libsdedrm`) as the DRM plane
     properties `EPDC_UPDATE_CNT` and `EPDC_UPDATE_PARMS_ADDR`. The kernel (`onyx_tcon_send_cmd`) turns each region into one TCON I2C write
     (`UI_MODE_SET` 0x07 `[mode, marker]`, or `AUTO_MODE_CTRL`/`GC_FULL_MODE` in fast mode).
  2. **mode/parameter changes**: SurfaceFlinger opens `/dev/ebc` and issues ioctls (`SET_EBC_UPDATE_SCHEME` 0x7006, A2 frame number 0x7024,
     debounce 0x7210/0x7211, a2 type 0x720f, `SEND_UPDATE` 0x700c and others).
* **Most "picture" settings are not TCON registers.** Contrast, B/W mono level, dither, gamma, "enhance", text bolding, anti-aliasing,
  icon/image EAC and DPI are all done in software: in the SurfaceFlinger GPU composition shader or in the app's Canvas/hwui hooks.
  Stock Android **never writes** TCON `CONTRAST` (0x05), `FILTER_P1/P2` (0x0a/0x0b), `A2_THRESHOLD_*` (0x0c/0x0d) or `DEBOUNCE_ENABLE` (0x0e).
  These registers keep their power-on defaults.
* What the TCON gets from Android: refresh waveform per update (REGAL 0x15 for normal partial updates, GC16 0x01 for full, DU 0x12, GL16 0x03),
  fast mode (`DISPLAY_MODE=1` plus `AUTO_MODE_CTRL` A2/DU, with `A2_FRAME_NUM` = "turbo" 0..6), anti-flicker (`DEBOUNCE_PARM` 0x10 = 0..32,
  default 10), `DEBOUNCE_THRESHOLD` 0x11 (0xff), `VCOM` (0x08 = vcom-50, Palma: 200 gives 0x96), and sync/sleep `UI_MODE 0x20`.
* Per-app profiles are JSON blobs in MMKV `/onyxconfig/mmkv/onyx_config` (partition `onyxconfig`, sda9), key `eac_app_<pkg>`.
  Device defaults come from `framework-res.apk` `res/raw/eac.json`, `palma2_eac.json`, `palma2_systemui.json` and `palma2_config.json`.

## 1. Kernel interface (`lfe5u_i2c` driver, misc device `/dev/ebc`, class `/sys/class/ebc`)

### 1.1 TCON register table (`cmd_operand_list`/`cmd_string_list` in vmlinux) [fact]
Index, then register, operand length, then name. Writes are I2C `[reg, data...]`. Reads use SMBus read-byte.

| idx | reg | len | name | live value (Android, `dump_reg`) | who writes it in stock |
|---|---|---|---|---|---|
| 0 | 0xe0 | 3 | (unnamed, 3-byte cmd) | - | only via sysfs `update` [guess: debug] |
| 1 | 0x01 | 1 | GC_FULL_MODE | 0x00 | kernel on full refresh (see 1.4) |
| 2 | 0x02 | 1 | AUTO_MODE_CTRL | 0x03 | kernel in fast mode (scheme 4) |
| 3 | 0x04 | 1 | A2_FRAME_NUM | 0x00 | SF via ioctl 0x7024 = "turbo" |
| 4 | 0x05 | 1 | CONTRAST | 0x00 | **never** (ioctl 0x7205 exists, unused) |
| 5 | 0x06 | 1 | DISPLAY_MODE | 0x00 | kernel `onyx_tcon_set_display_mode` (scheme) |
| 6 | 0x07 | 1 (+marker) | UI_MODE_SET | - | kernel per update |
| 7 | 0x08 | 1 | VCOM | 0x96 | kernel (sysfs `vcom_value`, probe/resume) |
| 8 | 0x0a | 1 | FILTER_P1 | 0x20 | **never** (ioctl 0x720e unused) |
| 9 | 0x0b | 1 | FILTER_P2 | 0x20 | **never** |
| 10 | 0x0c | 1 | A2_THRESHOLD_WHITE | 0xff | **never** (ioctl 0x720c unused) |
| 11 | 0x0d | 1 | A2_THRESHOLD_BLACK | 0x00 | **never** |
| 12 | 0x0e | 1 | DEBOUNCE_ENABLE | 0x00 | **never** (ioctl 0x720d unused) |
| 13 | 0x10 | 1 | DEBOUNCE_PARM | 0x04 idle / 0x0a after SF start | SF ioctl 0x7210 = antiFlicker |
| 14 | 0x11 | 1 | DEBOUNCE_THRESHOLD | 0xff | SF ioctl 0x7211 (0x80 once at boot, then 0xff) |
| 15-18 | 0x20-0x23 | 1 | PM_STATE, WF_SEND_STATE, FLG_STATE, ERROR | 0 | read-only status |

"Never" means: no ioctl number 0x7202-0x720e appears as an immediate in surfaceflinger, any /system, /system_ext or /vendor ELF,
and none of these registers shows up in Android dmesg. [fact for SF/dmesg; infer for "nobody"]

Suspend/resume (`lfe5u_ctrl_reg_backup/restore`) [fact]: reads and restores exactly 6 registers: 0x02, 0x04, 0x05, 0x06 (masked 0x0f, so the clean bit is dropped), 0x10, 0x11.
VCOM is re-written in `lfe5u_resume_late_work_func`.

### 1.2 ioctls on `/dev/ebc` (`ebc_ioctl`, arg = `int*` unless noted) [fact]

| ioctl | name (from logs) | action |
|---|---|---|
| 0x7002 | GET_EBC_DRIVER_SN | copies `"ONYX_TCON_DRIVER_VERSION_1.00"` (0x1e bytes) |
| 0x7006 | SET_EBC_UPDATE_SCHEME | `onyx_tcon_set_upd_scheme(v,1,0)`; see 1.3. v low nibble = scheme, bits 4..7 = clean flag |
| 0x7008 | (waiting_for_all_lut_free) | not implemented (log only) |
| 0x7009 | get | always returns 1 |
| 0x700a | set | stores int at lfe5u+0x94 [guess: power-down delay, unused on htcon] |
| 0x700b | SET_EBC_FORCE_WAVEFORM | "not achieve" |
| 0x700c | SET_EBC_SEND_UPDATE | arg = 0x28-byte `upd_data` (below). See 1.4 |
| 0x700e | set clear colour | `_clear_color_val` used by flag 0x10000 (clear screen) |
| 0x701d | extbuf sync with fb | copy current fb to extbuf |
| 0x701f | SET_EBC_EXTBUF_SYNC_FB_ENABLE | 1/0 |
| 0x7021 | get cfa_mode | returns DT `cfa_mode` (0 on Palma 2) |
| 0x7024 | set a2_cut_frame_num | 0..6, writes **A2_FRAME_NUM (0x04)**, stored at +0xa4 |
| 0x7025 | ? | if arg<4: clears field +0x98 [unknown] |
| 0x7026 | enable/disable cfa mode | bool at +0x8c |
| 0x7027 | clean screen | v>=0: `DISPLAY_MODE = cur_display_mode + v*16` (clean bit); v<0: `GC_FULL_MODE = v-1` |
| 0x7028 | get a2_cut_frame_num | |
| 0x7202 | AUTO_MODE_CTRL | writes `v - ((v&0xf) > 2)` (waveform id 4 gives 3, 5 gives 4) |
| 0x7204 | A2_FRAME_NUM | raw |
| 0x7205 | CONTRAST | raw (unused by stock userspace) |
| 0x7206 | DISPLAY_MODE | raw |
| 0x720c | A2 thresholds | low byte goes to 0x0c WHITE, next byte to 0x0d BLACK |
| 0x720d | DEBOUNCE_ENABLE | raw |
| 0x720e | FILTER | low byte goes to 0x0a P1, next byte to 0x0b P2 |
| 0x720f | a2_mode_type | 0/1, only if DT `epdc-a2-enhance-enable`; stored at +0xac (used in fast mode, 1.4) |
| 0x7210 | DEBOUNCE_PARM | raw (reg 0x10) |
| 0x7211 | DEBOUNCE_THRESHOLD | raw (reg 0x11) |
| 0x7302 / 0x7310 | read AUTO_MODE_CTRL / DEBOUNCE_PARM | returns byte |
| others (0x7203, 0x7207-0x720b, 0x700f, 0x7010, 0x7016, 0x701e, 0x7022, 0x7029) | | no-op / -EINVAL (SF still calls some of them, leftovers from the software-EPDC variant) |

`ebc_mmap` maps the handwriting ION buffer (pen fast path, `UPDATE_SCHEME_HANDWRITE`).

`upd_data` (0x28 bytes, mxcfb-like) [fact for offsets, infer for names]:
`{ u32 top, left, width, height; u32 waveform_mode; u32 update_mode /*1=full*/; u32 update_marker; u32 temp; u32 flags; u32 pad; }`.
Waveform ids come from `android.onyx.ViewUpdateHelper` (Freescale numbering): INIT 0, DU 1, GC16 2, GC4 3, ANIM(A2) 4, AUTO 5, REAGL 6,
DU4 8, REAGL_PLUS 9, GCC16 11, DEEP_GC16 12. Flags: 0x10000 = clear screen with clear colour, 0x20000 = delayed extbuf show,
0x40000 = HANDWRITE (also `EPDC_FLAG_HANDWRITE_GU` 0x80000), 0x200000 = disable DRM around the update, 0x400000 = no-regal,
bits 0xf0 = full-refresh variant selector, 0x2000000 bit 5 of byte 0x22 = shutdown image.

### 1.3 Update schemes (`onyx_tcon_set_upd_scheme`) [fact]
Values come from `ViewUpdateHelper.SCHEME_*`. 1 is treated as 2.

| scheme | Android meaning | kernel action |
|---|---|---|
| 2 (1) | SCHEME_NORMAL (and KEYBOARD) | `DISPLAY_MODE=0`; per-update UI_MODE path |
| 3 | SCHEME_SCRIBBLE (pen) | DSI video timing **off** (`onyx_android_refreash_enable(0)`), `DISPLAY_MODE=4` (+10 ms), handwriting buffer path |
| 4 | SCHEME_APPLICATION_ANIMATION (= app "fast mode") | `DISPLAY_MODE=1`; per-update writes go to `AUTO_MODE_CTRL`, not UI_MODE |
| 5 | SCHEME_SYSTEM_ANIMATION | `DISPLAY_MODE=2` |

`DISPLAY_MODE` byte = `mode | clean<<4` (clean comes from the upper nibble of the scheme value or from ioctl 0x7027).

### 1.4 Per-update waveform mapping (`onyx_tcon_send_cmd`; normalisation: wf 0xc/0xff become 2, 0xf becomes 2+full, 0x10 becomes 5) [fact]
UI_MODE write = I2C `[0x07, mode, marker & 0xff]` (3 bytes: the second operand byte is the update marker).

**Normal schemes (not 4):**
| upd_data | TCON write |
|---|---|
| wf DU(1) | UI_MODE 0x12 (DU) |
| wf AUTO(5) | UI_MODE 0x03 (GL16) |
| wf GC16(2), partial, flags&0xf0==0 | **UI_MODE 0x15 (REGAL)** if DT `epdc-gu-regal-enable` (Palma 2: yes) and !(flags&0x400000), else 0x10 (partial GU) |
| wf GC16(2), full (update_mode=1), flags&0xf0==0 | UI_MODE 0x01 (GC16 full) |
| wf GC16(2), full, flags&0xf0 = n | `GC_FULL_MODE (0x01) = table[(n>>4)-1]`, table = {1,0,7,2,7,7,7,3} (flags 0x10 gives 1, 0x20 gives 0, 0x40 gives 2, 0x80 gives 3, others 7) [meaning of values: guess, full-refresh waveform variants] |
| other wf (A2 4, REAGL 6, ...) | ignored ("ui mode dont support waveform_mode") |

The Android dmesg confirms this: in HD mode almost every update is `UI_MODE 0x??15` (REGAL, marker in the high byte), and full refreshes are `0x??01`.

**Fast scheme 4:** UI_MODE is not sent (the TCON runs autonomously in `DISPLAY_MODE=1`):
* wf A2(4): `AUTO_MODE_CTRL = 3`, or **4** when `a2_mode_type==1` (SF always sets 1, so the log shows `0x02 <- 0x04`).
* wf DU(1): `AUTO_MODE_CTRL = 1`.
* wf GC16 full: `GC_FULL_MODE = table[...]` (log: data 0x0, i.e. flags 0x20).
* Repeats of the same wf are filtered.

**SEND_UPDATE ioctl 0x700c** (explicit refresh from SF, e.g. `fullRefreshScreen`/`applyGCOnce`) [fact]:
update_mode=1 with wf 2 gives `GC_FULL_MODE=7`; wf 1 gives 5; wf 4 gives 4; wf 2 (partial) or 0xff gives 6. Flag 0x10000 means fill the extbuf
with the clear colour and show it (whiteClear). Flag 0x40000 goes to the handwriting submit.

### 1.5 sysfs `/sys/class/ebc/*` [fact]
`chipid` (r), `version` (r, "TCONB-0x6a9f9a09-encry"), `dump_reg` (r: all 18 regs), `vcom_value` (rw: `lfe5u_ctrl_set_vcom(v)`,
v in [50,305], reg = v-50; optionally persisted to the `splash` partition header "VCOM" + 2 bytes + checksum when DT `vcom_spiflash_save`, N on Palma),
`power` (w: 1/0 for FPGA rails and GPIOs), `sleep` (w: 1 = `lfe5u_sleep_in`, 0 = `sleep_out`), `update` (w: raw `send_cmd_ext`, value = `reg | data<<8 ...`),
`scheme` (w: `onyx_tcon_set_upd_scheme_ext(v)`, forced), `a2_mode_type` (w: 0/1), `verity`, `verity_repeat`, `verity_fw` (r: FPGA bitstream check),
`erase` (r!: erases FPGA config flash, **dangerous**), `reset` (w 1: reload FPGA firmware), `overlay` (w: SPI CS), `force_update_fw`,
`extbuf_test`, `aes_key`, `otp`.

### 1.6 DT knobs (`lfe5u_i2c@34` in the dtbo) [fact]
`epdc-a2-enhance-enable` (allows a2_mode_type), `epdc-gu-regal-enable` (partial GU becomes REGAL 0x15), `epdc-vcom-workaround-enable`
(absent on Palma 2; for product ids 0x97/0x99 it shifts VCOM by ±50), `cfa_mode` (absent, so 0 = mono panel). dmesg:
`cfa_mode[0] a2_enhance[1] gu_regal[1] vcom_workaround[0]`.

## 2. Userspace

### 2.1 Components [fact]
* **`android.onyx.optimization.*`** in `framework.jar`: `OECService` / `EACSystemServerManager` (system_server side), `TabletEACRefreshImpl`,
  `TabletEACDisplayImpl`, `EACScrollRefreshManager`, `EpdEventListener` (pipe `/dev/onyx/listener`, which carries input and top-activity events
  from SF/system to the service), `EInkHelper` (app side).
* **`android.onyx.ViewUpdateHelper`**: the only bridge to SurfaceFlinger (`transactData(code, Parcel)` on the `SurfaceComposer` binder).
  Codes: APPLY_APP_SCOPE_UPDATE 0xFF0004, CLEAR_APP_SCOPE_UPDATE 0x100040, SET_EPD_TURBO 0x100055, SET_ANTI_FLICKER 0x100073,
  DEBOUNCER 0xFF0064, SET_GC_REFRESH_INTERVAL 0x100052, USE_GC_FOR_NEW_SURFACE 0x100051, APPLY_GC_ONCE 0xFF0026, REFRESH_SCREEN 0xFF0001,
  REPAINT_EVERY_THING 0xFF0014, APPLY_GAMMA_CORRECTION 0xFF000F, APPLY_MONO_LEVEL 0xFF0063, ENABLE_DITHER 0x100074, SET_DITHER_THRESHOLD 0x100080,
  ENABLE_ENHANCE 0x100081, SET_ENHANCE_STRATEGY 0x100079, ENABLE_REGAL 0xFF002A, SET_VCOM 0xFF0028, SET_APPLICATION_DISPLAY_SCHEME 0xFF0015,
  WHITE_CLEAR 0x100057, BYPASS* (pen/animation bypass), and others (the full list is in `out/eink-research/vuh.smali`).
* **SurfaceFlinger** (`/system/bin/surfaceflinger`, classes `HWEpdcManager`/`SWEpdcManager`/`EpdcSchemaManager`/`EpdcWrapper`): owns
  `/dev/ebc`, builds `hwc_epdc_llist` per frame, runs the debouncer, GC counter and the gamma/mono/dither shaders.
* **HWC** (`vendor.qti.hardware.display.composer-service`, `libsdmcore`, `libsdedrm`): passes the region list as plane props
  `EPDC_UPDATE_CNT` / `EPDC_UPDATE_PARMS_ADDR` (log: `update_to_display[...] marker waveform_mode update_mode Rect flags`).
* UI: package **`com.onyx`** (`/system/priv-app/kcb-release`: launcher, settings, "App optimization"/E-Ink Center pages) and
  **`com.onyx.floatingbutton`** (Navball/quick refresh-mode switcher) [infer from package names; the UI code was not decompiled].

### 2.2 Storage of profiles [fact]
* MMKV file `/onyxconfig/mmkv/onyx_config` (+ `.crc`), partition `onyxconfig` (sda9, ext4). The path comes from `DeviceConfig.systemConfigPrefix`
  ("/onyxconfig/" in `res/raw/config.json`) plus "eac_config"/"eac_system" ids.
  * `eac_app_<pkg>`: JSON `EACAppConfig` (example in 2.3). `eac_default_app_config<pkg>`: shipped default per known app.
  * `eac_extra_config_enable`=1, `eac_extra_refresh_mode`=0, `eac_extra_turbo`=0, `eac_extra_gc_after_scrolling`=1,
    `eac_extra_gc_after_scrolling_delay_time`=1500 ms, `gc_after_scrolling_refresh_mode`=2 (system-wide "EACDeviceExtraConfig").
  * `eac_theme_<pkg>@theme_type_N`, `eac_onyx_app_theme_1..3`, `eac_color_type_1..3`, `eac_dpi_type_1..3`: presets.
* `/onyxconfig/com.android.vcom` = "200" (factory VCOM, pushed to `/sys/class/ebc/vcom_value`; the path comes from `palma2_config.json` `vcomPath`).
* Device defaults: `framework-res.apk res/raw/`: `eac.json` (colour/BW/DPI presets: BW `gamma` 30/80/30, `monoLevel` 10, DPI 0/350/350),
  `palma2_eac.json` (`enhanceDelta` 90, `enhanceThreshold` 2, `disableEnhanceThreshold` 10, `ditherThreshold` 128),
  `palma2_systemui.json` (refresh modes, below), `palma2_config.json`.

### 2.3 Per-app profile schema (`EACAppConfig`, actual JSON from the device; defaults from the constructors) [fact]
```
pkgName, enable, supportEAC,
globalActivityConfig / activityConfigMap{cls -> EACActivityConfig}:
  refreshConfig:  updateMode (0 NORMAL,1 DU,2 A2,3 REGAL,4 X,5 REGAL_PLUS; default 0),
                  refreshModeIndex ("refresh_mode_1..4", overrides updateMode/turbo via systemui.json),
                  turbo 0..6 (default 0), antiFlicker 0..32 (default 10), gcInterval 0..50 (default 20 = full GC every N updates),
                  animationDuration ms (debounce, e.g. 50), useGCForNewSurface (false), supportRegal
  displayConfig:  contrast 0..100 (default EACConfig.contrastDefault=0; example app 30), monoLevel 0..175 (default 10; SF gets +80),
                  bwMode 0/1, ditherThreshold 0..255 (128 dev / 255), enhance (true), cfa* (colour panels only)
  paintConfig:    textBold, textEACType (0 off,1 half,2 normal,3 double stroke width), antiAlisingType (0 ignore,1 force off,2 force on),
                  fillEAC/fillContrast/fillBrightness, iconEAC/iconContrast/iconBrightness/iconThreshold, imgEAC/imgGamma (60),
                  ditherBitmap, quantBits (3)
  noteConfig (screen-note pen), scrollRefreshDelay (1000), disableScrollAnim
dpiConfig{dpi 350}, globalCSSConfig{fontBold,fontColor,fontSize 100,customCSS} (WebView), keyboardConfig{pageKeyMode},
rotationConfig, extraConfig{forceFullScreen, usePageKeyAsVolumeKey,...}, autoFreeze/autoStart/network (not display related)
```

### 2.4 Refresh modes on Palma 2 (`palma2_systemui.json`) and what they become [fact, unless marked]
| UI entry | refresh_mode | updateMode | turbo | SF/EAC action | TCON result |
|---|---|---|---|---|---|
| "HD"-class high quality, title REGAL_PLUS | refresh_mode_1 | 5 REGAL_PLUS | 0 | `clearAppScopeUpdate`; debouncer on; transient REGAL_PLUS (wf 9) after touch/key up | partial updates as UI_MODE 0x15 REGAL; GC16 every `gcInterval` |
| "HD" (default for system apps) | refresh_mode_4 | 0 NORMAL | 0 | `clearAppScopeUpdate`, debouncer on | UI_MODE 0x15 REGAL (wf GC16 partial), 0x01 full |
| "Speed"/NEW_SPEED (fast) | refresh_mode_3 | 2 A2 | 2 | `applyAppScopeUpdate(pkg, 0x904 = A2|dither|Y1)`, ioctl 0x7024(2), scheme 4 | `A2_FRAME_NUM=2`, `DISPLAY_MODE=1`, `AUTO_MODE_CTRL=4` (A2 enhanced), GC_FULL on demand |
| (other modes, not offered on Palma 2) DU 1, X 4, REGAL 3 | | | | `toEpdMode`: DU gives 0x901, X gives 0x1000004 (A2 + ONYX_AUTO), REGAL gives 6 | DU: AUTO_MODE_CTRL 1 |

`refreshConfig` (shown to user apps) = [mode_1, mode_4, mode_3]; system apps get [mode_4, mode_3]. Legacy values migrate {0 to 0, 1..4 to 2}.
Switching into fast mode in dmesg (fact): `DEBOUNCE_THRESHOLD 0xff`, `a2_mode_new 1`, `A2_FRAME_NUM 2`, scheme 4 / `DISPLAY_MODE 1`,
`DEBOUNCE_PARM 0x0a` (verified by reading back 0x7310), then `AUTO_MODE_CTRL 4` per A2 frame. Leaving it: same sequence with scheme 2 /
`DISPLAY_MODE 0` / `A2_FRAME_NUM 0`.

Option meanings and mapping to hardware:
* **turbo (0..6)**: fast-mode speed level, mapped to **A2_FRAME_NUM (0x04)** via ioctl 0x7024 [infer: same range 0..6, observed turbo=2 gives reg 2].
  Likely "fewer A2 frames = faster, more ghosting" [guess].
* **antiFlicker (0..32, default 10)**: `SET_ANTI_FLICKER`, then SF `### AF %d`, ioctl 0x7210, then **DEBOUNCE_PARM (0x10)**, read back to verify [fact].
* **DEBOUNCE_THRESHOLD (0x11)**: SF writes 0xff on every app switch, 0x80 once at boot [fact; semantics guess: pixel-change threshold of the TCON's debounce/auto detector].
* **gcInterval (0..50, default 20)**: SF counts partial updates and injects a full GC16 every N (the "full refresh every N pages/updates" knob) [infer: passed as the 5th arg of `debouncer()`].
* **animationDuration / debouncer**: SF delays/merges updates (short delay = animationDuration, long = clamp(3x, 400..1200 ms)), then issues one clean refresh [infer from EACUtils].
* **useGCForNewSurface**: full GC16 when a new window appears ("### full gc for new surface") [fact: SF strings].
* **gc_after_scrolling (1500 ms)**: GC after scrolling ends [fact: keys; behaviour infer].
* **contrast (0..100)**: **gamma correction in the SF shader** (`applyGammaCorrection(enable=contrast>0, contrast)`), not TCON CONTRAST [fact].
* **monoLevel / bwMode** ("dark colour enhancement"/BW threshold): SF shader `color.r >= monoLevel ? 1.0 : color.r` with monoLevel = level+80 (0 = off) [fact].
* **ditherThreshold / enableDither**: SF ordered-dither shader (`ditherTable`, 14x14) [fact].
* **enhance** (+ palma2 `enhanceDelta 90`, `enhanceThreshold 2`, `disableEnhanceThreshold 10`): SF "EnhanceStrategy" (`set EST, delta %d ms, ET %d min, DT %d min`),
  reset on pokeUserActivity [fact for plumbing; semantics guess: temporary extra contrast/clean refresh after idle].
* **textBold / textEACType / antiAlisingType / icon*/img***: done inside the app process (hwui/Canvas hooks, `OnyxEACCanvasImpl`); no kernel involvement [fact for location].
* **DPI**: Android density override per app (350 default) [fact].
* **Manual full refresh** (button / `REFRESH_SCREEN` key): `ViewUpdateHelper.refreshScreen`/`applyGCOnce`, then SF, then ioctl 0x700c with update_mode=1 wf=2, giving `GC_FULL_MODE=7` [infer: the 0x700c path is the only one that writes 7].

## 3. Global defaults at boot [fact unless marked]
1. Kernel probe: parse DT; if cmdline `vcom=` was given, write VCOM (not on Palma: no `vcom=`); vcom_workaround off; then `UI_MODE 0x20` (sync).
   `lfe5u_flash_vcom_sync` reconciles VCOM between TCON SPI flash and the fs copy (default "125" if never set).
2. Android pushes VCOM 200 (from `/onyxconfig/com.android.vcom`) to `/sys/class/ebc/vcom_value`, so the register reads 0x96 [infer: the reg is 0x96 on Android
   but 0xce after a TCON reset in our tests, so something in userspace writes it].
3. SurfaceFlinger at start: `DEBOUNCE_THRESHOLD 0x80` (once), first full GC16 (`UI_MODE 0x01`, marker 0x31 in the log).
4. On every top-app change: `DEBOUNCE_THRESHOLD 0xff`, `a2_mode_type 1`, `A2_FRAME_NUM = turbo` (0), `DEBOUNCE_PARM = antiFlicker` (10).
5. Untouched TCON defaults: AUTO_MODE_CTRL 3, CONTRAST 0, FILTER_P1/P2 0x20/0x20, A2_THRESHOLD W/B 0xff/0x00, DEBOUNCE_ENABLE 0, DISPLAY_MODE 0, GC_FULL_MODE 0.
6. Suspend: regs 0x02/0x04/0x05/0x06/0x10/0x11 are backed up and restored, VCOM is re-set, and `UI_MODE 0x20` syncs after resume.

## 4. Proposed mapping for postmarketOS/KDE (ordered by value to an e-ink reader user)

| # | Feature | Where | How |
|---|---|---|---|
| 1 | VCOM 200 at init/resume (TCON reset leaves 0xce, which gives a wrong grey level and ghosting) | **kernel** | write reg 0x08 = vcom-50 at probe/resume; module param `vcom=200` + sysfs `vcom` (range 50..305) |
| 2 | REGAL for partial updates, GC16 for full (stock "HD") | **kernel** | default partial = UI_MODE 0x15 (not 0x10), full = 0x01; include the update marker as the 3rd I2C byte `[0x07, mode, marker]` |
| 3 | Periodic full refresh every N partial updates (gcInterval, default 20) + manual full refresh | **kernel** (counter, sysfs `gc_interval`) + KWin/daemon hotkey | full = UI_MODE 0x01; sysfs `refresh=full` trigger |
| 4 | Fast mode (A2/DU) per app/window, turbo 0..6 | **kernel** sysfs/ioctl `scheme` (2 normal / 4 fast) + `a2_frames` (reg 0x04) + `a2_type`; **userspace daemon** (KWin script/plugin on active-window change) picks the profile | enter: 0x11=0xff, 0x04=turbo, 0x06=1, per frame 0x02=4 (A2) or 1 (DU); leave: 0x06=0, 0x04=0, then one GC16 |
| 5 | Anti-flicker (DEBOUNCE_PARM 0..32, default 10), DEBOUNCE_THRESHOLD 0xff | **kernel** sysfs/module param; daemon may vary it per app | regs 0x10/0x11, restore on resume |
| 6 | Debounce/merge of updates (animation delay 50 ms, long delay 400-1200 ms) and GC after scrolling (1500 ms) | **KWin** (compositor knows damage) or kernel-side timer [kernel simpler, KWin better] | |
| 7 | Contrast (gamma), BW/mono threshold (dark enhancement), dither | **KWin effect** (GLSL shader, same formulas: gamma, `r >= level+80`, ordered dither) per window | not TCON regs; TCON CONTRAST 0x05 could be exposed as an experiment knob only |
| 8 | Per-app profiles | **userspace daemon** + config file (e.g. `~/.config/palma-eink.json`, reuse the EAC field names: updateMode/turbo/antiFlicker/gcInterval/contrast/monoLevel/dpi) | import stock JSON from MMKV `eac_app_*` if desired |
| 9 | Text bold / anti-aliasing / DPI per app | **userspace** (Qt/KDE scale factor, fontconfig `embolden`/`antialias` rules per app, env vars at launch) | |
| 10 | Pen fast path (scheme 3, DSI video off, handwriting buffer) | later, kernel | needs DISPLAY_MODE 4 semantics |

Expose as experimental sysfs but do not default (stock never uses them): CONTRAST 0x05, FILTER 0x0a/0x0b, A2_THRESHOLD 0x0c/0x0d, DEBOUNCE_ENABLE 0x0e.
Do NOT expose `erase`/`reset`/`force_update_fw` equivalents.

## Tools / artefacts (scratch, `out/eink-research/`)
`lp.py` (LP super metadata), `mk.sh` (dd logical partition, then image), `dexdis.py` (minimal dex disassembler: `--class`, `--strings`),
`rd.py` (vmlinux table dump), `resolve.py` (objdump + string xref), `fw_onyx.smali` (all `android.onyx.*` classes), `vuh.smali`
(ViewUpdateHelper), `res/res/raw/*.json` (device configs), `x/` (extracted jars/apks/libs/surfaceflinger, `x/onyx_config.mmkv`).
Images were deleted after extraction (disk 97% full). Rebuild with `mk.sh` + extents from `lp.py`.
Not done: decompiling the `com.onyx` UI APK (UI labels/strings), the full SF debouncer/GC logic, and the exact `GC_FULL_MODE` value semantics.
