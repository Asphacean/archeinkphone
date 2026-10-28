# Palma 2 display bring-up (milestone: static GC16 frame) — derived facts, risks, procedure

## From the stock kernel (analysis/decomp_str, dtbo fragment@69/70, recon/root/{dmesg,sysfs_vals,live.dts})
- GPIO polarity = DT flags of stock `lfcpnx@0` (driver stores `active = !(flags&1)`): 30V_EN tlmm97 and 12V_CORE_EN tlmm58
  active-high; RESET tlmm122, STANDBY tlmm96, PROGRAMN tlmm38, INITN tlmm9 active-low; DONE tlmm8 active-high. Pinctrl: gpio, 2 mA, no bias.
- Power-on (`lfe5u_power_ctrl(1)`, 1 ms = `__const_udelay(0x418958)`): vdd1v8 L5A=1.8 V on -> 1 ms -> RESET asserted (low),
  PROGRAMN released (high), STANDBY released (high), 30V_EN=1 -> 1 ms -> (2.5 V slot, absent) 1 ms -> 12V_CORE_EN=1 -> 1 ms ->
  vdd1v2 L3E=1.2 V on (takes the absent "1.2 V IO" GPIO slot; stock regulator_enable there) -> 3 ms -> RESET released -> 3 ms.
  `lfe5u_probe`: +100 ms, then `lfe5u_config_done_wait`: poll DONE every 50 ms, 20x; on DONE re-check after 5 ms, +100 ms settle.
  Timeout -> `lfe5u_load_fw`: PROGRAMN low 50 ms, high, wait again, 2 retries. Stock dmesg: DONE on the first poll (~0.26 s).
  The stock first power cycle was only for SPI work (chip id, usercode, AES key check, QPI flash) and was followed by a 10 ms
  power-cycle; mainline skips SPI entirely (bitstream self-loads from the FPGA's own flash, encrypted). INITN unused.
- Power-off (`lfe5u_power_ctrl(0)`): RESET low, 1 ms, 30V off, 2 ms, vdd1v2 off, 1 ms, 12V_CORE off, 1 ms, vdd1v8 off, STANDBY+PROGRAMN low.
- DSI panel (live `qcom,mdss_dsi_rm69299_visionox_amoled_video`, name is a leftover): video mode, 4 lanes (lane_map_0123), RGB888,
  non_burst_sync_event, h-sync-pulse 0, EOT appended, BLLP/EOF-BLLP power stop, lp11-init, no force-clock-lane-hs; 1648x824,
  hfp 40 hsw 20 hbp 40, vfp 10 vsw 2 vbp 6, 60 Hz -> 88.35 MHz; on = DCS 0x11 then 255 ms in HS mode (no 0x29); off = DCS 0x10 + 150 ms;
  reset = PM6150L GPIO9 raw 1/0/1 x 10 ms (pinctrl output-low at rest -> DT GPIO_ACTIVE_LOW); 139 x 70 mm (landscape scanout, TCON rotates).
- I2C 0x34 (QUP SE7 = mainline i2c7): 2-byte writes `[reg, data]`, SMBus read-byte works (`lfe5u_ctrl_get_vcom`). Registers from the
  live `dump_reg` (overrides PLAN.md's 0x03/0x04 guess): 0x01 GC_FULL_MODE, 0x02 AUTO_MODE_CTRL, 0x04 A2_FRAME_NUM, 0x05 CONTRAST,
  0x06 DISPLAY_MODE (0..4 | clean<<4; 4 adds 10 ms), 0x07 UI_MODE_SET, 0x08 VCOM (= vcom-50, vcom in [50,305]; 200 -> 0x96),
  0x0a/0x0b FILTER_P1/P2, 0x0c/0x0d A2_THRESHOLD_WHITE/BLACK, 0x0e DEBOUNCE_ENABLE, 0x10 DEBOUNCE_PARM, 0x11 DEBOUNCE_THRESHOLD,
  0x20 PM_STATE, 0x21 WF_SEND_STATE, 0x22 FLG_STATE, 0x23 ERROR. Table index 0 is cmd 0xe0 (version?); 0x03/0x09/0x0f are invalid.
  Stock I2C probe: VCOM (only if known) then `[0x07, 0x20]` + 50 ms. VCOM=200 comes from Android userspace (sysfs), not DT/cmdline.
- Frame protocol: before kickoff pixel (0,0) = R 0x07, G mode, B marker (ABGR8888 bytes 0..2, `sde_plane_set_fb_marker`); after the
  vblank `onyx_tcon_cmd_triger` waits 500 us, zeroes the 3 bytes, then `onyx_tcon_send_cmd` writes I2C `[0x07, mode]` (no marker).
  mode: 0x01 GC16 full, 0x10 GC16 partial, 0x15 GC16 regal partial, 0x03 GL16, 0x12 DU, 0x20 sync (only after resume, `_resume_ll`).

## What lives where
- `port/pmaports/kernel/0002-drm-panel-onyx-palma2.patch` (applies to v7.2.0-sm6350, checkpatch clean): `panel-onyx-palma2-tcon.c`
  does rails + GPIO sequence at probe (FPGA stays on, like stock), DONE wait with PROGRAMN retry (timeout only warns), panel reset,
  DCS 0x11/0x10 via `mipi_dsi_multi_context`, fixed mode. `fpga-*-gpios` are optional as a set: drop them from the DT node to
  sequence from user space (`palma_epd_test.py --fpga-power`). Flags: `MIPI_DSI_MODE_VIDEO | MIPI_DSI_CLOCK_NON_CONTINUOUS`.
- `port/sm6350-onyx-palma2.dts` (compiles with the tag's includes): &mdss/&mdss_dsi0 (vdda L22A)/&mdss_dsi0_phy (vdds L18A) as FP4,
  &gpi_dma1, &i2c7 with driverless `tcon@34` (`onyx,lfe5u-tcon`), tlmm `fpga_tcon_default` state.
- `tools/palma_epd_test.py` (stdlib): `--dump` register map, VCOM + sync, test pattern via /dev/fb0, command pixel by colour
  channel (R/G/B offsets from fb_var), I2C trigger, state read-back; `--fpga-power` via GPIO cdev v2 ioctls.

## Open questions / risks
- Command pixel channel order: stock writes memory bytes 0..2 of an ABGR8888 buffer; fbdev gives XRGB8888, so the tool maps by
  colour channel (R=0x07) assuming the TCON parses DSI RGB components. If nothing refreshes, retry with `--cmd-order bgr`.
- Clock lane: stock lacks force-clock-lane-hs, so NON_CONTINUOUS is used; if the FPGA DSI RX needs a continuous HS clock, drop the flag.
- PHY timings: stock used explicit `0x200808 0x24230808 0x5020400`, t-clk-pre 0x31 / post 0x0e; mainline computes its own (unverified).
- `prepare_prev_first` puts the host in LP-11 before 0x11; stock did DSI init ~6 s after FPGA power, same order here (FPGA at panel probe).
- Unknown whether PM6150L GPIO9 reaches the TCON board; replicated anyway. DISPLAY_MODE/GC_FULL_MODE/AUTO_MODE_CTRL semantics
  unknown beyond names (idle 0/0/3), untouched. First-frame behaviour without a 0x20 sync frame is an assumption (stock cold boot has none).
- fbcon draws into /dev/fb0 (cursor, text) and would clobber pixel (0,0): unbind it before testing.
- SPI2 (FPGA sysCONFIG port, tlmm 45/46/56/57) is not described; pins stay in bootloader state. Fine for self-boot.
## Kernel config (`config-postmarketos-qcom-sm6350.aarch64`; could not be fetched here -> verify on winpc)
Needed: `CONFIG_DRM_MSM` (+`_DSI`, `_DPU`), `CONFIG_REGULATOR_QCOM_REFGEN` (mdss_dsi0 refgen-supply), `CONFIG_DRM_FBDEV_EMULATION=y`
(+`CONFIG_DRM_CLIENT_DEFAULT_FBDEV=y` on >= 6.14), `CONFIG_I2C_CHARDEV`, `CONFIG_I2C_QCOM_GENI`, `CONFIG_QCOM_GPI_DMA`, `CONFIG_GPIO_CDEV=y`,
`CONFIG_PINCTRL_SM6350`, `CONFIG_PINCTRL_QCOM_SPMI_PMIC`. NEW and mandatory: `CONFIG_DRM_PANEL_ONYX_PALMA2_TCON=m` must be added to the
config file (olddefconfig drops unknown symbols); add 0002 to `source=`/`sha512sums` of the APKBUILD like 0001.

## Test procedure (device, root, after flashing the new boot.img)
1. `dmesg | grep -iE 'palma2|dsi|FPGA|panel'` -> no "FPGA DONE timeout"; `ls /sys/class/drm` shows card0-DSI-1; `/dev/fb0` exists.
2. `echo 0 > /sys/class/vtconsole/vtcon1/bind; modprobe i2c-dev` (if module). `python3 tools/palma_epd_test.py --selftest` (any host).
3. `python3 tools/palma_epd_test.py --dump` -> readable registers (no I/O error) prove I2C + FPGA alive; VCOM/ERROR values are informative.
4. `python3 tools/palma_epd_test.py` -> VCOM 200, sync, ramp pattern, GC16 full. Expect a 16-step gray ramp with a black frame.
5. Then `--pattern white --marker 2`, `--mode gc16-partial --marker 3`; on failure: `--cmd-order bgr`, re-read `--dump` (0x22/0x23),
   `cat /sys/kernel/debug/dri/0/state`, and `modetest -M msm` to confirm the 1648x824 mode is active.

## Findings 26.10 (clean-boot tests)
- Panel module (panel_onyx_palma2_tcon) is loaded from the rootfs by udev at boot, not by the initramfs (boot-r4-device.img initramfs carries only evdev + usb gadget modules), so /etc/modprobe.d/palma2-panel.conf options apply at boot. The file must contain BOTH lines: `blacklist panel_onyx_palma2_tcon` and `options panel_onyx_palma2_tcon dsi_flags_override=0x1`. On 26.10 the options line was missing and the module came up with default flags.
- NEVER rmmod the panel module: rmmod oopses in drm_self_refresh_helper_entry_work (NULL deref via drm_atomic_commit_alloc). Afterwards DRM re-binds with DSI-1 "disabled", `fbcon_init: detected unhandled fb_set_par error, error code -16`, ssh becomes sluggish. Flags must be right at first load (modprobe.d or kernel cmdline `panel_onyx_palma2_tcon.dsi_flags_override=...`).
- Clean boot with flags=0x1 (MIPI_DSI_MODE_VIDEO only, continuous clock): DSI-1 enabled/connected, mode "1648x824" 60 88350 1648 1688 1708 1748 824 834 836 842 (matches stock porches). Clocks: dsi0_pll_bit_clk 530.1 MHz, byte 66.2625 MHz, pclk 88.35 MHz, esc 19.2 MHz.
- BUT `dsi_err_worker: status=7` (TIMEOUT|DLN0_PHY|FIFO, sometimes status=5) still fires every frame (~60/s, ratelimited). The earlier conclusion "continuous clock removes the errors" was wrong: it was observed on a DRM wedged by rmmod cycles.
- dsi_fifo_status() flags FIFO for ANY non-zero FIFO_STATUS (bit 12 DLN0_LP_FIFO_EMPTY is normally set), so the FIFO bit in status=7 may be a side effect. Real triggers are TIMEOUT_STATUS and DLN0_PHY_ERR (ESC/SYNC_ESC/CONTROL/CONTENTION_LP0/LP1 = LP-mode errors on data lane 0).
- Ramp test (palma_epd_test.py, GC16 full, marker) on clean boot: TCON registers readable, VCOM 0x96, UI_MODE_SET writes accepted, but PM_STATE/WF_SEND_STATE/FLG_STATE/ERROR all stay 0x00 (stock idle PM_STATE is also 0). Screen result pending from user.
- DPMS cycle via `/sys/class/graphics/fb0/blank` (1 -> I2C `[0x07,0x20]` -> 0): errors stop while blanked and resume after unblank; no change in TCON state. The later loss of ping/ssh was NOT a device hang but the Tailscale static route on the Mac (see the section below); pstore was empty after reboot. The DPMS cycle is safe and useful: it restarts the DSI link without rmmod.
- Stock DTBO panel node (analysis/dtb/dtbo/01_...v11.dts lines 17-78): no qcom,mdss-dsi-panel-clockrate (bit clock = pclk*24/4 = 530.1 Mbps, same as mainline); lane_map_0123; non_burst_sync_event; h-sync-pulse 0; tx-eot-append; bllp + bllp-eof power mode; lp11-init; on/off command state dsi_hs_mode; t-clk-post 0x0e; t-clk-pre 0x31; phy-timings <0x200808 0x24230808 0x5020400> = CMN_TIMING_CTRL_0..11 = 00 20 08 08 24 23 08 08 05 02 04 00. Mainline 7nm PHY computes its own; compare with tools/palma_dsi_errs.py output.
- Regulators with panel up: l16a 832 mV, l18a 792 mV (dsi phy vdds + usb), l22a 1.08 V (dsi vdda; stock L22A range 1.08-1.304 V), l3e 1.2 V, l5a 1.8 V, refgen on. Stock constraints for L16A/L18A are identical to ours.
- Next: run `tools/palma_dsi_errs.py` (devmem snapshot of DSI0 ctrl/PHY error registers with error IRQ masked for a window) to see which exact bits fire. Candidates: PHY timings (force stock values), lane-0 LP contention from the FPGA RX, t-clk-pre/post.
- WARN trace appears in palma2_tcon_probe at module load (~54 s uptime on 26.10 boot); text not yet captured. Grab with `dmesg | grep -B5 -A25 'palma2_tcon_probe'` on next boot.

## Findings 26.10 (later): PHY timings, next build
- /dev/mem is absent (CONFIG_DEVMEM unset in r5) -> tools/palma_dsi_errs.py cannot run on r5; r6 config enables DEVMEM (+STRICT, no IO_STRICT).
- The mainline PHY driver for sm6350 is the **10nm** one (`dsi_10nm_phy_enable`, `msm_dsi_dphy_timing_calc_v3`), not 7nm. With
  `drm.debug=0x2` + DPMS cycle the computed timings print as: clk_pre 36, clk_post 11, clk_zero 19, clk_trail 6, clk_prepare 5,
  hs_exit 31, hs_zero 30, hs_prepare 5, hs_trail 5, hs_rqst 3, ta_go 3?, ta_sure 0, ta_get 4 (bclk 66.2625 MHz, pclk 88.35 MHz).
  10nm TIMING_CTRL_0..11 layout = halfbyte_en, clk_zero, clk_prepare, clk_trail, hs_exit, hs_zero, hs_prepare, hs_trail, hs_rqst,
  ta_go|(ta_sure<<3), ta_get, 0. Stock DTBO bytes 00 20 08 08 24 23 08 08 05 02 04 00 -> clk_zero 32, clk_prepare 8, clk_trail 8,
  hs_exit 36, hs_zero 35, hs_prepare 8, hs_trail 8, hs_rqst 5, ta_go 2, ta_get 4; t-clk-pre 0x31 (49), post 0x0e (14).
  Every stock value is ~1.5x longer than mainline's spec-minimum -> hypothesis: the FPGA D-PHY RX needs the longer HS entry/exit
  (one LP<->HS transition per frame in this video mode = one error per frame).
- r6 = pkgrel 6: 0003-drm-msm-dsi-palma2-diagnostics.patch (dsi_err_worker prints raw CLK/FIFO/ACK/TIMEOUT/STATUS0/DLN0 regs;
  runtime knobs `/sys/module/msm/parameters/phy_timings` = 12 hex bytes "00,20,08,08,24,23,08,08,05,02,04,00", `phy_clk_pre`,
  `phy_clk_post`, applied at every PHY enable -> set them, then DPMS cycle `/sys/class/graphics/fb0/blank` 1/0), plus L22A min 1.2 V
  (stock DSI vdda-1p2; mainline left it at 1.08 V) in 0001. Pipeline: apk -> device `apk add --allow-untrusted` -> boot-deploy
  regenerates /boot/boot.img (sha of /boot/boot.img == flashed boot-r4-device.img, so this is the canonical image) -> EDL flash boot_a.
- Mac-side gotcha: with Tailscale on, a static route `172.16.42/24 via <lan-ip> (en6)` appears and the device becomes
  unreachable over IPv4 although it is alive (IPv6 link-local still works: `ping6 ff02::1%en10`). ~/.ssh/config `Host palma`
  now has `BindInterface en10`; scripts that use raw 172.16.42.1 (push_rootfs.py, telnet) still need Tailscale off.

## Findings 26.10 (evening): link clean, TCON protocol, bootloader

- r6 raw error registers: every error IRQ showed TIMEOUT_STATUS=0x1 (HS_TX_TIMEOUT), FIFO_STATUS 0xcccc1019/0xdddd1019 (VIDEO_MDP_FIFO over+underflow, all 4 lane HS FIFOs over/underflow), DLN0_PHY_ERR=0x89888/0x88888.
- HS_TIMER_CTRL hw default 0x0000ffff (65535 x byte clk ~1 ms) is shorter than one full-frame HS burst (~16 ms, HS porches, LP only in BLLP) -> HS TX timeout every frame.
- Writing HS_TIMER_CTRL=0x000fffff (resolution 0xf) removed the timeouts. Clearing BLLP power stop (VID_CFG0 0x9130 -> 0x0130) removed all remaining error IRQs.
- Later measurements: 0 errors in every link variant (clock continuous/non-continuous, BLLP LP on/off) once the timer is fixed.
- DLN0_PHY_ERR 0x88888 (all lane-3 LP error bits) is a constant, not clearable with W1C -> red herring.
- Stock PHY timings (00 20 08 08 24 23 08 08 05 02 04 00, clk_pre 49/post 14) applied via msm.phy_timings + DPMS cycle: no effect on TCON.
- Tools: tools/palma_dsi_errs.py (devmem snapshot + accumulate, needs CONFIG_DEVMEM, maps 0xae94000 with 0x2000 and PHY at +0x400).
- Tools: tools/palma_dsi_reg.py (r/w DSI0 ctrl regs: 0xc VID_CFG0, 0xa8 LANE_CTRL, 0xb8 HS_TIMER_CTRL, 0xbc TIMEOUT_STATUS, 0x8 FIFO_STATUS).
- Patch 0004-drm-msm-dsi-palma2-hs-timer-bllp.patch adds msm.dsi_hs_timer (default 0x000fffff, applied at enable) and msm.dsi_bllp_hs (bool) knobs.
- DCS commands in video mode time out: "[drm:dsi_cmds2buf_tx] *ERROR* wait for video done timed out" -> ENTER_SLEEP on DPMS off fails with -110, then "Skipping prepare of already prepared panel" on unblank.
- VIDEO_DONE IRQ never fires (cause unknown, not display-blocking).
- TCON: STANDBY (tlmm96) low -> PM_STATE bit0=1 within 300 ms (asleep), high -> 0. Polarity confirmed, high = awake.
- TCON: RESET (tlmm122) pulse resets the TCON (VCOM reg back to 0xce default).
- TCON: PROGRAMN pulse reconfigures the FPGA, DONE after ~55 ms.
- Full I2C map: only 0x01,0x02,0x04..0x08,0x0a..0x0e,0x10,0x11,0x20..0x25 exist; every other register reads 0x5a. Nothing changes with DSI link on/off.
- Marker-pixel protocol (R=0x07, G=mode, B=marker at pixel (0,0), then I2C [0x07,mode]) never produced any register change in ~20 timing/order/mode variants: rgb/bgr order, sync pair first, I2C before/during/after the marked frames, DU/partial/sync modes, after RESET/STANDBY/PROGRAMN pulses.
- I2C-only commands DO produce activity:
  - [0x06]=0x10 (DISPLAY_MODE clean) -> PM_STATE 0->4 (56 ms)->6 (82 ms), FLG_STATE 0x14 then 1.
  - [0x01]=0x01 or 0x11 (GC_FULL_MODE) -> PM_STATE 4->6, FLG_STATE 8 for ~1.2 s, then FLG 1, PM 4->0. Looks like a full GC16 power/refresh cycle.
  - WF_SEND_STATE stayed 0 in all cases.
  - Screen result pending from the user.
- Bootloader (XBL FV -> DisplayDxe, panel "onyx_dsi_tcon_video" id 0x29, Panel_tcon_vid.xml; scratch copies under the session scratchpad bl/):
  - Same timings 1648x824 fp40/bp40/sw20, 10/6/2, 60 Hz, RGB888, 4 lanes.
  - TrafficMode=1 (non-burst sync event), LP in BLLP and BLLP-EOF, default lane map, no marker pixel.
  - Init DCS: 39 FE 00 | 39 C2 08 | 39 35 00 | 39 51 FF | 05 11 | 150 ms | 05 29 | 50 ms.
  - Term: 28, 50 ms, 10, 150 ms.
  - Probe: rails on, reset 1-0-1 (10 ms), 350 ms, read chip id, I2C [0x01,0x11], 2 s.
  - Splash refresh: blit logo to the DSI framebuffer, 30 ms, I2C [0x02,0x02], [0x06,0x01], 500 ms.
  - Lfe5u cfg: i2c bus 8 (qupv3 se7), addr 0x34, gpios reset 122 / standby 96 / program 38 / done 8 / 30v 97 / 12v core 58, vdd1p8 LDO5A, vddio LDO22A.
- Key inference: the stock kernel runs with continuous splash and never sends its own DCS on-command, so the FPGA has always been initialised by the bootloader sequence including 0x29 (display on). Mainline sent only 0x11.
- r7 (pkgrel 7): panel driver prepare() now replays the bootloader sequence; unprepare() sends 28 / 50 ms / 10 / 150 ms.
- Pipeline unchanged: apk -> device apk add -> /boot/boot.img -> EDL boot_a.

## Android live reference (26.10, recon/android-20261026-1447)
- No root over adb (Magisk su missing, adbd production) -> no /dev/mem, no debugfs; only /sys/class/ebc/dump_reg (world-readable).
- After cold boot dump_reg returns 0x95 for every register until a screen off/on cycle; after resume values are real (VCOM 0x96).
- Idle: 01=0 02=3 06=0 07=0x15 (last cmd GC16 regal partial) 20=0 21=0 22=1 23=0.
- Every refresh (swipe/tap), polled at 30 ms: 21 WF_SEND_STATE 0->8 (sometimes 2->0x0a) first, then 20 PM_STATE 0->4,
  22 FLG_STATE 1->0x18, ~370-500 ms, back to 20=0 21=0 22=1. PM_STATE never 6 on normal updates.
- Linux I2C-only cycles looked different: PM 4->6, FLG 8 (or 5/0x14), WF_SEND_STATE always 0 -> TCON ran an internal
  full/clean cycle on its (empty/white) buffer; it never reached WF_SEND_STATE!=0, i.e. never accepted DSI frame data.
  So the gate is: TCON must see the marker/frame over DSI (WF_SEND_STATE=8) -- the DSI RX side still rejects our stream.
- Root on Android: Magisk su at /debug_ramdisk/su (not in PATH). No debugfs/devmem; registers read with tools/palmareg/
  (header-free .ko: struct module 0x340 B, init@0x170, exit@0x310, CRCs + vermagic from /vendor/lib/modules; insmod returns
  -EAGAIN after dumping). Dump: recon/android-20261026-1447/regdump_android.txt(.map). Stock DSI0: CTRL 0x1f3, VID_CFG0 0x9130, LANE_CTRL 0x01000000,
  **LANE_SWAP_CTRL 0x1** (mainline 0), HS_TIMER_CTRL 0x0003fd08, CLKOUT 0xe31, EOT 1, ERR_INT_MASK0 0x13f03b1f, PHY timing
  00 20 08 08 24 23 08 08 05 02 04 00, PHY CMN_LANE_CFG0/1 0x21/0x84 (same as mainline).
- Trace (recon/android-20261026-1447/trace_refresh2.txt, tracefs i2c+sde_evtlog): during updates the kernel writes I2C [07 15] (GC16 regal partial)
  once per frame, ~0.5 ms after the vblank IRQ that follows each kickoff (one kickoff per frame, ~16.7 ms). Occasional
  [11 ff] [04 00] [10 0a] + read 0x10 (A2/debounce setup). Compare with tools/palma_regdump.py on pmOS.
- pmOS vs Android full diff (recon/regdump_pmos.map): matched at runtime LANE_SWAP_CTRL=1, LANE_CTRL non-continuous,
  CLKOUT 0xe31, stock PHY timings, HS_TIMER 0x3fd08, INTF_CONFIG2/DATA_HCTL off, pclk via by_2 (CLK_CFG0 0x31, CLK_CFG1 0x21).
  Remaining diffs: PLL frac div + SSC enabled on Android (PLL base 0xae94a00: FRAC_DIV_START_LOW/MID 0xde/0x62, SSC_* set,
  SSC_CONTROL 0x2), Android error-mask 0x13f03b1f vs 0x13ff3be0, MISR enabled on Android. DPU DMA0 SRC0_ADDR = stolenfb
  iova 0x2000, stride 6656 -> fbdev buffer is what is scanned. Per-frame Android protocol (marker + [07 15] each frame) in all
  6 byte orders: no TCON reaction. Open lead: pmOS FIFO_STATUS shows 0xdddd10xx (all 4 lanes HS FIFO empty+over+underflow)
  every 200 ms even with zero error IRQs; Android dump showed 0x1010 but its mask lets these raise IRQs (cleared by ISR),
  so verify on Android with a clear-then-read module before trusting this lead. CRC debugfs on crtc-0 wedges the link
  (CLK_STATUS 0x4343, MDP FIFO overflow) -> avoid.
- **Lead confirmed (26.10 16:30)**: Android FIFO_STATUS clear-then-sample (tools/palmareg/palmafifo.c, recon/android-*/fifo_android.txt):
  lanes only EMPTY|FULL (acc 0x33331010), never OVERFLOW/UNDERFLOW. pmOS: 0xdddd10xx = EMPTY|OVERFLOW|UNDERFLOW on all
  4 lanes every 200 ms -> HS lane FIFOs overrun/underrun, frame data corrupted -> TCON never decodes marker/frames.
  Next: compare dispcc (byte/byte_intf/pclk dividers) — Android dump recon/android-*/dispcc_android.txt.map (0xaf00000+0x2000).
- DPU diff (recon/android-*/dpudump_android.txt.map vs recon/dpudump_pmos.map): **MDP top INTR_STATUS pmOS 0x0c000000 =
  INTF_1_UNDERRUN (bit26) + INTF_1_VSYNC; Android 0x08000100 = VSYNC only.** -> DPU fetch underrun on pmOS, INTF emits
  underflow colour / starves DSI (DSI MDP FIFO over/underflow, lane FIFO under/overflow). Android scans with DMA2
  (AB24, unpack 0x03010002, SRC_FORMAT 0x237ff, fb at iova 0xfee00000), pmOS DMA0 (XR24). Timing/INTF otherwise equal.
  Next: raise DPU core clock / interconnect bandwidth (debugfs dri/0/core_perf: perf_mode=2 fixed, fix_core_clk_rate,
  fix_core_ib_vote/ab_vote) and check whether INTF_1_UNDERRUN and the DSI FIFO flags disappear.
- Follow-up 16:45 (clean r7 boot): INTF_1_UNDERRUN NOT present in 200 ms samples (earlier hit was likely from experiments);
  DSI FIFO acc still 0xffff1019 with fbcon bound/unbound and with all Android link settings. DSI PLL VCO identical
  (Android 1059.71 MHz with SSC, pmOS 1060.20 MHz), dispcc dividers identical, lanes in HS 97.8% of the time (LANE_STATUS
  0x1f00; 0x1f1f during BLLP). Writing Android values to INTF 0x8c/0x1c4: no change. DSI video MISR (0xa4=0x10100,
  sig @0x140) reads 0xffffffff on pmOS (Android a51f137a) -> MISR not capturing here; unexplained.
  Open: why DSI MDP FIFO (bits 0/3) and lane HS FIFOs over/underflow on pmOS but not on Android with identical
  DSI/INTF/clock registers. Remaining differences: source pipe DMA0 XR24 vs DMA2 AB24 (+fetch/QoS), PLL SSC,
  DSI ERR_INT_MASK0, CMD DMA/TRIG_CTRL bits, mainline vs downstream enable ordering.
- r8 (pkgrel 8: 0005 PLL SSC knob msm.pll_ssc=Y, DT data-lanes <3 0 1 2>): SSC active (SSC_CONTROL 0x2 = stock), but
  data-lanes <3 0 1 2> gives LANE_SWAP_CTRL=3, not 1 -> for the stock value use data-lanes <1 2 3 0> (mainline maps the
  other way). Runtime swap=1 on r8 + SSC + stock PHY timings + HS timer: DSI FIFO acc still 0xdddd1011, TCON no reaction
  (Android protocol and I2C-only GC16). Display work paused here (26.10 evening).
- CORRECTION (26.10 evening): "VIDEO_DONE never fires on pmOS" was a measurement error. INTR_CTRL bit16 only latches
  while MASK_VIDEO_DONE (bit17) is set; with the mask on, ~60 VIDEO_DONE IRQs/s arrive -> the DSI video engine completes
  frames normally. r9 (0006: forced-clock soft reset, PHY_SW_RESET 0x01000001, video engine enabled 400 ms after host
  enable, data-lanes <1 2 3 0> -> LANE_SWAP 1) was built on that wrong premise; result: FIFO acc still 0xffff1019, no TCON
  reaction. The DSI FIFO over/underflow flags themselves are real and still unexplained.
- Next experiment: boot-r9-splash.img = r9 + cmdline "initcall_blacklist=msm_drm_register clk_ignore_unused
  pd_ignore_unused regulator_ignore_unused" to keep the bootloader's DSI/DPU pipeline (splash fb at 0xa0000000) running and
  compare its FIFO flags / TCON behaviour.
- **Stock enable trace** (tools/palmareg/palmatrace.c: 14 s register-change sampler gated on MDSS GDSC+AHB, plus
  sde_hw_util_log_mask + drm.debug=0x2 for SDE writes; recon/android-20261026-1447/trace_enable_{dsi,sde}.txt): DSI enable order on screen-on:
  PHY_RESET 0x01000001 (0.58 ms), PHY CMN/timing + lane cfg, PLL program, CTRL=0x1f1 (no video), VID_CFG0, timings, TRIG_CTRL
  0x80000004, MISR 0x10100, LANE_SWAP 1, HS_TIMER 0x3fd08, CLKOUT 0xe31, EOT 1, ERR mask, CLK_CTRL 0x23f, TIMING_FLUSH 1,
  PLL SSC/frac, RESET reg 0x1c00->0, TIMING_FLUSH 0, PHY CLK_CFG1 0x21 + RBUF_CTRL 1, then **52 ms later CTRL=0x1f3**.
  SDE side: INTF timing written once, INTF_CONFIG2/DATA_HCTL 0, **INTF_PROG_FETCH_START 0x1637d5 (line 833 = vtotal-9)**,
  INTF_CONFIG 0x80800000, CTL_INTF_ACTIVE 2, CTL_FLUSH, INTF_TIMING_ENGINE_EN 1, then per-frame CTL_FLUSH 0x1020040.
  Mainline programs PROG_FETCH_START 0x163101 (line 832 = vtotal-vfp) -> fetch one line earlier. Test that next.
- r10 boot (17:45): stock PROG_FETCH_START (0x1637d5 and later lines) + CONFIG2/DATA_HCTL=0 via devmem+CTL flush: FIFO
  unchanged (0xdddd1011). Stock trace during scrolling: CTRL stays 0x1f3, no INTF/DSI re-enable, only CTL_FLUSH 0x1020040.
- PHY lane state regs LN+0x78/+0x7c (undocumented): HS = 0xc0|0x00/0x5f, LP-11 = 0xc2|0xf2/0x2f. With r9 knobs on
  (dsi_vid_delay_ms=400, dsi_ds_reset=Y) the lanes stay in LP-11 forever (LANE_STATUS 0x1f1f) -> r9's late video enable is
  broken; set msm.dsi_vid_delay_ms=0 dsi_ds_reset=N (then DPMS cycle) to get HS back (97.7% HS). Every r9/r10 TCON test
  before that was run with no HS video at all.
- 26.10 late: lane HS FIFO over/underflow (FIFO_STATUS 0xffff1019) persists with the DSI internal test pattern generator
  (TPG_CTRL 0x31/0x21, no MDP data) -> problem sits between DSI controller and PHY (byte clock domain), NOT in DPU/INTF.
  Copying stock VBIF shareability (0x170/0x174=0) and stock DMA2 QoS/OT values: no change.
  msm.dsi_ds_reset=Y alone (forced-clock soft reset + PHY_SW_RESET 0x01000001 in mainline order) leaves lanes in LP-11
  (LANE_STATUS 0x1f1f) -> keep N. Next: measure real byte/pixel/esc clock frequencies with the GCC/dispcc debug mux on
  both systems (Android via palmareg-style module) to find a byte-clock/PHY-clock mismatch.
- debugcc (linux-msm/debugcc, static aarch64 build in scratch, copy on device /home/user/debugcc, `-p sm6350 <clk>`):
  pmOS measured byte0 66.095 MHz, byte0_intf 33.048, pclk0 88.129, esc0 19.198, mdp 200.0 -> exact 4:3 byte:pclk, -0.25 %
  from nominal = SSC down-spread average, consistent. Clearing TRIG_DMA/CMD_DMA_CTRL/DMA_LEN, stock TRIG_CTRL and
  ERR_INT_MASK0: FIFO flags unchanged. modprobe.d now also sets msm dsi_vid_delay_ms=0 dsi_ds_reset=N (r9 knobs off).
  TODO next Android visit: run debugcc there for the same clocks; sample FIFO_STATUS with TPG enabled on stock.
- NOTE: `msm` is built-in, so `options msm ...` in modprobe.d never applied; set these on the kernel cmdline instead.
  boot-r10-knobs.img = r10 + cmdline `msm.dsi_vid_delay_ms=0 msm.dsi_ds_reset=0 msm.dsi_hs_timer=0x3fd08 msm.phy_timings=...
  msm.phy_clk_pre=49 msm.phy_clk_post=14`. 0006 patch defaults changed to 0/false for the next build.
- boot-r10-knobs.img flashed (cmdline knobs verified in /proc/cmdline). Observation: on the FIRST enable after boot the
  INTF runs (59.96 fps) and CTRL=0x1f3 but all DSI lanes stay in LP-11 (LANE_STATUS 0x1f1f, FIFO 0xdddd1011 = lane flags
  only); after one DPMS cycle (fb0/blank 1 then 0) lanes go HS 97.7 % and FIFO shows 0xffff1019 (MDP over/underflow added).
  So mainline's first link bring-up after boot does not transmit at all; the DPMS re-enable path does. Compare the two
  enable paths (msm_dsi_host_power_on/enable ordering vs bridge pre_enable after a disable) next session.

## 26.10 (evening) — corrections, new leads

- **"First enable after boot leaves LP-11" is WRONG as a rule.** On the 15:23 boot the panel was enabled by fbcon at 17.3 s
  (udev modprobe) and the INTF ran from then on with no DPMS; lanes were HS. mdss_gdsc total_idle_time=0 -> the GDSC never
  collapsed since the bootloader, so bootloader register residue survives (explains LANE_CTRL 0x11000000: mainline never
  writes LANE_CTRL when MIPI_DSI_CLOCK_NON_CONTINUOUS is set; the bootloader's CLKLN_HS_FORCE_REQUEST bit stays).
- **The LP-11 lock-up is intermittent per enable** (cycles.py: 8 DPMS cycles): NOM corner 8/8 HS (+1 LP-11 earlier),
  LOW_SVS 6/8 HS. Any single-shot "knob X leaves lanes in LP-11" conclusion from earlier (dsi_ds_reset, dsi_vid_delay_ms=400)
  is unreliable. Once stuck, nothing short of a full DPMS cycle recovers it: CTRL 0/0x1f1/0x1f3, PHY LANE_CTRL0 0/0x1f,
  CLK_CTRL rewrite, video off/on, RBUF off/soft-reset/RBUF on (with or without global clk gating) all leave 0x1f0f.
  A controller soft reset (REG_DSI_RESET 1->0) on a running link reliably *produces* the stuck state (resync.py A: 2/2).
- Live register diff vs Android (recon/regdump_pmos_live.map vs regdump_android.txt.map), after fixing my +4 offset mistake:
  DSI ctrl: only CMD_DMA_CTRL/DMA_BASE/DMA_LEN leftovers, TRIG_CTRL bit12, MISR, LANE_CTRL bit28, ERR mask, INTR_CTRL
  (hw default extra bits) differ. PHY: CLK_CFG0/1 = 0x61/0x20 (pclk = bit_clk/6) vs 0x31/0x21 (by_2/3) — same 88.35 MHz,
  tested before, no effect. PLL: FRAC_DIV_START 0x00/0x70 vs 0xde/0x62 = SSC centre 0.047 % apart, negligible. All other
  PHY/PLL/lane/dispcc registers identical. DLN0_PHY_ERR 0x89888 identical on Android (lane-3 LP bits are a constant).
- Stock panel DT (analysis/dtb/dtbo/01_*.dts, node with onyx,tcon-mode-support): on-command is only `05 11` (exit sleep,
  255 ms) in **dsi_hs_mode**; off = `05 10` 150 ms; t-clk-pre 0x31, t-clk-post 0x0e, lane_map_0123, bllp + eof-bllp
  power mode. The FE/C2/35/51/29 sequence is bootloader-only.
- **Stock DSI PHY vdda-0p9 is the MX level rail with min corner NOM (256)** (analysis/dtb/boot/01_*Lagoon_SoC.dts
  mdss_dsi_phy0: vdda-0p9-supply = pm6350_s5_level, supply-min-voltage 0x100). On pmOS MX/CX sit at LOW_SVS (64): the DSI
  host votes via its OPP (66 MHz byte clk -> low_svs) and the PHY node votes nothing. Runtime test via DPU perf debugfs
  (`echo 448000000 > /sys/kernel/debug/dri/0/debug/core_perf/fix_core_clk_rate; echo 2 > perf_mode`, then a DPMS cycle)
  -> mdp 448 MHz, cx/mx = 256. Result: lane FIFO flags unchanged (0xffff1019), TCON still WF_SEND_STATE=0; only the
  LP-11 lock-up rate looked lower (weak statistics). Proper fix would be `power-domains = <&rpmhpd SM6350_MX>` +
  `required-opps = <&rpmhpd_opp_nom>` on the PHY node; not done yet.
- Also: vreg_l18a (our vdds) is forced to 792 mV at boot by the regulator core ("Setting 788000-1049000uV", rpmh returns
  -ENOTRECOVERABLE). Irrelevant now (stock PHY supply is MX, not an LDO), but L16A/L18A ranges should match stock.
- Boot-time noise: three "DSI PLL(0) lock failed" at 12.2 s come from clk_disable_unused (CLK_OPS_PARENT_ENABLE on the
  dispcc RCGs prepares the PLL with the PHY unpowered) and the WARN "dsi0_pll_bit_clk: Zero divisor" at first enable is the
  CCF recalculating through CLK_CFG0=0 before the PLL is programmed. Both harmless.
- **Ordering difference, now patched (0008-drm-msm-dsi-10nm-late-rbuf.patch, `msm.late_rbuf=1`)**: stock enables the PHY
  global clock (CLK_CFG1 bit5) + resync FIFO (RBUF_CTRL=1) only after CTRL=0x1f1/timings/soft reset, ~52 ms before
  VID_MODE_EN. Mainline does both inside dsi_pll_10nm_vco_prepare(), before the controller is set up. late_rbuf moves them
  to msm_dsi_host_power_on() right after dsi_ctrl_enable(); combine with `msm.dsi_vid_delay_ms=50`. Both params are
  0644 -> can be toggled at runtime, effective on the next DPMS cycle. r11 = r10 + 0008 (pkgrel 11).

### 26.10 late evening — r11/r12 results, frame-boundary analysis, research
- **r11 (0008 v1: global clk + RBUF deferred until after dsi_ctrl_enable) is unusable**: with the PHY global clock off
  the dispcc byte0/pclk0 RCGs cannot update, link_clk_enable fails, the enable path unwinds (PHY/ctrl left powered off,
  DPU "vblank timeout"), and a later register poke hung the SoC. Never gate CLK_CFG1 bit5 before the dispcc clocks are on.
- **r12 (0008 v2: only RBUF_CTRL deferred, `msm.late_rbuf`)**: no measurable effect. cycles.py (DPMS cycles, lanes HS vs
  LP-11): late_rbuf=0 2/6, =1 4/6, then 0/4 — noise. FIFO flags identical (ffff1019).
- **The LP-11 lock-up is decided at enable time and is not recoverable by register pokes.** Tried on a stuck link:
  TIMING_FLUSH, LANE_CTRL bit28/bit24 changes, CTRL 0/0x1f1/0x1f3, PHY LANE_CTRL0 0/0x1f, CLK_CTRL rewrite, video
  off/on, RBUF off/on, soft reset with/without global clk, CTRL.ENABLE=0 + RESET + 0x1f3 (V1/V2/V4). V1/V2/V4 bring the
  lanes to HS but it is a ghost: MISR stays 0xffffffff (no frames processed), FIFO 0x5555xxxx, and the link collapses to
  LP-11 again within ~6 s. Any LANE_CTRL write on a running link also kills the video engine (lanes drop to LP-11).
- **dsi_vid_delay_ms** (video engine enabled N ms after host enable, i.e. after the INTF started): 50 ms 0/6, 400 ms 1/6,
  1000 ms 1/4 (last one sampled too early) — no better than 0 ms. HS blanking (`msm.dsi_bllp_hs=1`, VID_CFG0 0x130):
  **0/5, never HS** — with LP blanking the engine gets a new HS attempt every frame, with HS blanking only one.
- **MX/CX at NOM** (DPU perf debugfs `fix_core_clk_rate=448000000`, `perf_mode=2`): 8/8 HS + 1 LP-11, FIFO flags and
  TCON (WF_SEND_STATE) unchanged. Stock DT: DSI PHY vdda-0p9 = MX level rail, min corner NOM. refgen regulator is enabled
  (PWRDWN_CTRL5=1, kona-style). vreg_l18a forced to 792 mV by the regulator core (irrelevant: PHY analog is on MX).
- **TCON held in RESET** (tlmm122 low): lock-ups still happen (1/6), FIFO flags identical, DLN0_PHY_ERR 0x88888 identical ->
  everything below is SoC-side; the receiver plays no role in the flags or the lock-up.
- **Frame-position of the FIFO flags** (fifoline.py: clear at INTF frame start, record INTF LINE_COUNT at first
  appearance): lane OVF + MDP OVF/UDF at lines 1-3 (frame start), lane UDF at lines 833-835 (end of active / entry into
  the LP vertical blanking). So the errors are per-frame boundary events (LP<->HS transitions), not a continuous rate
  mismatch. Clock frequencies (debugcc) are identical in HS and stuck states; PLL status regs identical.
- The earlier "DSI TPG excludes the DPU" conclusion is unreliable: with TPG_CTRL written live the video MISR did not change,
  i.e. the generator never took effect. The command-DMA re-fire theory (TRIG_DMA=1 + BLOCK_DMA_WITHIN_FRAME) is dead:
  CMD_DMA_DONE count is 0 per 0.5 s. DCS commands already go out in HS (xfer_prepare clears LOW_POWER for non-LPM msgs).
- First boot after flash had mdss_gdsc never collapsed -> LANE_CTRL kept the bootloader's bit28 (continuous clock) and
  the first enable was HS; FIFO flags identical in continuous and non-continuous clock mode.
- Web research (subagent, see port/research/boox_tcon_research.md): no Onyx GPL source anywhere; palma2pro-eos
  (SM7225, same panel/TCON family) documents the *software-EPDC* variant (457x835 packed DSI timing) — ours is the
  hardware-TCON (htcon) variant, protocol undocumented. Lattice DSI Rx IP: no LP escape/ULPS/BTA support, LP-11->HS
  entry only, sync-pulse/sync-event supported, VSYNC/HSYNC widths static in the bitstream, LP blanking gap must exceed
  the Rx FIFO drain time. => never send LP commands or BTA to the TCON; our DCS go in HS already.
- **r13 = r12 + 0009 runtime knobs** (`msm.dsi_cmd_block`, `msm.dsi_vid_on_at` 0/1/2, `msm.dsi_pre_vid_ms`,
  `msm.dsi_post_vid_ms`) to test: no DCS at all; video engine on in bridge enable (after INTF start, true INTF-first);
  settle time between host power-on and video enable (before INTF).

### 26.10 night — BREAKTHROUGH: DSI/PHY/TCON work with the DSI test pattern generator
- r13 knob matrix (dsi_cmd_block, dsi_vid_on_at=1, pre/post delays, Android pclk divider path, dsi_ds_reset, DPMS
  off-time): every configuration is a ~50 % coin flip for the LP-11 lock-up and FIFO flags never change. Dead end.
- **DSI TPG, armed BEFORE the enable** (tpg2.py: TEST_PATTERN_GEN_VIDEO_INIT_VAL=0xff, TPG_MAIN_CONTROL=BIT(8)
  checkered, TPG_VIDEO_CONFIG=0x7 (24bpp RGB), TEST_PATTERN_GEN_CTRL=0x31, then a DPMS cycle; the generator only latches
  when the video engine starts, which is why the earlier live TPG test showed nothing): link comes up with
  **FIFO_STATUS 0x33331010 = Android's clean signature**, no OVF/UDF at any line, MISR stable (0x4f75c13a).
  => DSI controller, PHY, PLL, clocks and timing are fine. The frame-boundary over/underflows come from the
  **DPU INTF -> DSI pixel delivery**.
- **TCON accepts the TPG frames**: with the TPG link up, I2C [0x07,0x01] gives WF_SEND_STATE 0->8, PM_STATE 0->4->6,
  FLG 0x10 -> back, exactly the stock refresh signature (first time ever on pmOS); [0x07,0x12] (DU) likewise.
  No marker pixel needed for this; the TCON latched the DSI frame into its memory and ran a waveform. So the TCON
  protocol as we understand it (frame over DSI + I2C UI_MODE_SET) is correct; only the DPU-generated stream is rejected.
- Remaining INTF differences vs stock (INTF_1 at 0xae6b800): CONFIG2 0x10 (DATA_HCTL_EN) vs 0, DISPLAY_DATA_HCTL
  0x06ab003c vs 0, PROG_FETCH_START 0x163101 vs 0x1637d5, +0x1c4 0x200 vs 0xa00. All earlier "live" tests of these were
  invalid for the same reason as the TPG one: the DSI video engine latches the MDP interface behaviour at start.
  r14 = r13 + 0010 (`msm.dpu_intf_ovr="off=val,..."` applied after setup_timing_engine and setup_prg_fetch, before the
  timing engine enable) to test them at enable time. MDP TOP 0x2b0/0x2c8 (0x1000) are SSPP clock-status bits
  (DMA0 on pmOS vs DMA2 on Android), not a config difference.
- Scripts: /home/user/tpg2.py (arm TPG + cycle), tpgtcon.py (TPG + I2C triggers + TCON poll), fifoline.py (first INTF
  line per FIFO flag), cycles.py / cycles2.py (DPMS series, HS count), unstick*.py, resync.py, statecmp.py, misrstab.py.
- **Photo confirmation**: recon/photos/20261026-tpg-checkerboard-first-dsi-image.jpg — the TCON rendered the DSI TPG
  checkerboard (GC16 via I2C [0x07,0x01]) on the e-ink panel. First image ever displayed over DSI on pmOS.

## 26.10 night — ROOT CAUSE FOUND: INTF programmable fetch start one line too early
- r14 override matrix (intfovr.py, `msm.dpu_intf_ovr`): DATA_HCTL off -> no change (4/4 HS but FIFO ffff1019);
  **INTF_PROG_FETCH_START = stock 0x1637d5 (line 833 + 1 px) instead of mainline 0x163101 (line 832 + 1 px) ->
  FIFO 0x33331010, zero over/underflow at any line, 4/4 HS, no LP-11 lock-ups.** +0x1c4 is a status register
  (0x200/0x600/0xa00 depending on state), not a config.
- Mechanism: mainline programmable_fetch_get_num_lines() with prog_fetch_lines_worst_case=24, vbp+vsw=8, vfp=10 takes the
  "entire vfp" branch -> fetch starts exactly at vtotal-vfp = line 832 = first line after the active region. On this
  platform (DPU 6.4 + DSI 6G v2.4.1 video mode) that corrupts the end of the active frame (lane FIFO underflow at line
  833) and the start of the next one (overflow at lines 1-3); stock fetches from line 833 (vfp-1). Fix: 0011 patch,
  `msm.dpu_prog_fetch_adj` (default -1 line) in dpu_encoder_phys_vid.c programmable_fetch_config(); r15.
- **TCON accepts real framebuffer frames now**: palma_epd_test.py ramp + GC16 -> PM 6 / WF_SEND 8 / FLG 0x10, and the
  16-step ramp is on the e-ink (recon/photos/20261026-fb-ramp-first-real-frame.jpg). Console text + I2C [0x07,0x01]
  refresh also works. First real image through the whole pmOS display stack.
- Lessons: (1) the DSI video engine latches MDP-interface behaviour (TPG, prog fetch, INTF config) at start -> any such
  change must be tested through a full DPMS cycle, never live; (2) the LP-11 lock-up was a *symptom* of the same fetch
  timing, not a separate PHY problem; (3) stock register parity must include DPU encoder-side registers written at
  enable time (INTF_PROG_FETCH_START differed by exactly one line and was dismissed after an invalid live test).
- Next: per-frame/commit TCON trigger in the panel driver (stock: marker pixel + I2C [0x07, mode] after each frame),
  fbcon/KDE integration, then drop the diagnostic knobs that match stock anyway (phy_timings, hs_timer, clk_pre/post).
- Photo: recon/photos/20261026-fbcon-text-on-eink.jpg — fbcon text (uname/date) rendered on the e-ink via GC16.
- **r15 confirmed** (0011 built in, no runtime overrides): PROG_FETCH_START 0x1637d5 at boot, FIFO 0x33331010, 8/8 DPMS
  cycles HS. Panel blacklist removed from /etc/modprobe.d/palma2-panel.conf (module autoloads at boot).
- **Auto-refresh daemon** (port/overlay/epd_autorefresh.py -> /usr/local/bin, epd-autorefresh.service enabled): crc32-polls
  /dev/fb0 every 150 ms, waits for the fb to settle, then I2C [0x07, DU 0x12] (GC16 0x01 every 20th update); VCOM 200 +
  sync at start. fbcon output now appears on the e-ink by itself. Interim solution until the panel driver gets a
  per-commit trigger (marker pixel + I2C) and proper waveform selection.
- Console inverted to black-on-white via DECSCNM (printf '[?5h' > /dev/tty1) in epd-autorefresh.service ExecStartPre.

### TCON update modes & timing (26.10, modetime*.py / modeprobe.py, full screen 1648x824, DISPLAY_MODE 0x06 = 0)
| UI_MODE_SET 0x07 | duration | note |
|---|---|---|
| 0x01 GC16 / 0x03 GL16 / 0x10 GC16-partial / 0x15 GC16-regal / 0x11 / 0x13 / 0x30 / 0x31 | ~0.49-0.51 s | 16-level |
| 0x12 DU | ~0.32 s | 2-level |
| 0x02 | ~0.31 s | DU-like |
| 0x16..0x1a | ~0.41 s | GL/GLR-like variants |
| **0x04 / 0x14** | **~0.19-0.20 s** | A2-like fast 1-bit (visual check pending) |
| 0x06 | 1.3 s | probably full clean |
| 0x20 sync, 0x21, 0x22 | no update | control |
- Update duration is independent of the changed area (200x200 DU = full-screen DU = 320 ms): waveform-bound.
- **Overlapping updates are supported**: a second DU 100 ms after the first ran concurrently (WF_SEND_STATE is a slot
  bitmask: 8 -> 4 -> 0xc), total 548 ms instead of 640. So a per-commit trigger without waiting for idle is the right
  model (what stock does with [0x07,0x15] every frame).
- DISPLAY_MODE 0x06 values 1/3/4 are NOT speed presets: 1 and 3 leave the TCON in a non-idle state (no refresh), 4 starts
  an endless ~400 ms refresh loop. 2 behaves like 0 but without WF_SEND_STATE reporting. Keep 0.
- Daemon v2 (port/overlay/epd_autorefresh.py): no idle wait, 50 ms poll, 60 ms settle, >=90 ms between commands, DU by
  default (`--a2` -> 0x14), GC16 every 24th update or 4 s after a burst. Theoretical: ~5 Hz with 0x14, ~3 Hz with DU per
  region, regions overlap.

## 27.10 — обновление консоли и чистка ручек

- Полный флеш каждые 2–5 с при «ничего не происходит» = мигающий курсор fbcon (5 изменений fb/с → DU на каждое, GC16 каждое 24-е). Демон v3 (`port/overlay/epd_autorefresh.py`): `fbcon/cursor_blink=0`, детект по `/dev/vcsa` (21 КБ, 0.04 мс) каждые 100 мс + полный fb раз в секунду (чтение 5 МБ uncached scanout ≈ 5–25 мс, поэтому не чаще), GC16 только по простою 3 с после ≥8 частичных или принудительно на 48-м. Проверка `tconmon.py` (poll 0x20/0x21): простой — тишина; одна строка — один DU (~0.27 с); пачка — DU'ы + один GC16 через 3 с.
- Ручки не нужны: 9 DPMS-циклов на r21 с mainline PHY-таймингами (ошибка парсера «bad byte 0» = override полностью пропущен, clk_pre/post тоже), `dsi_hs_timer=0` (HW default) и `pll_ssc=N` — все HS, FIFO чист, `dsi_err_worker` 0. Нужен только patch 0011 (prog fetch −1 строка). 0003–0010 → `port/pmaports/kernel/attic/`.
- Ядро r22: 0001, 0002 (панель; политика GC16 как у демона: `refresh_gc_min=8`, `refresh_gc_hard=48`, `refresh_gc_idle_ms=3000`, GC16 после пачки по таймеру, а не на первом коммите после простоя), 0011, 0012 (без diag always-on), 0013. Cmdline без `msm.*`. 0007 (`mdss_gdsc` ALWAYS_ON) снят непроверенным.
