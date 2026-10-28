# Boox TCON / DSI — web research (26.10.2026, subagent report, condensed)

Legend: [fetched] read directly; [search-hit] seen in listing only; [derived] inference.

## Bottom line
1. No Onyx GPL kernel source exists publicly for any Boox device (GitHub code search for lfe5u_ctrl_send_cmd,
   onyx_tcon_parse_cmd, onyx_tcon_cmd_queue, lfe5u_write_reg, "onyx,lfe5u", lfe5u_sync_tcon, onyx_tcon_triger: nothing).
   onyx-intl org = apps only. help.boox.com "Violation of GPL" thread unanswered for years.
2. Most useful: spavikevik/palma2pro-eos — Palma 2 Pro (SM7225 lagoon, same ED061KC1 1648x824 panel, same
   lfcpnx100_tcon_fw_* CertusPro-NX TCON) bring-up with a confidence-tagged TCON/panel ABI document. Onyx has TWO TCON
   modes; which one you are in changes what the DSI frame must contain.
3. Nobody documents the hardware-TCON (I2C 0x34, WF_SEND_STATE) command protocol. No "marker pixel / embedded command"
   documentation exists. Must be captured from the stock device.

## 1. spavikevik/palma2pro-eos [fetched] https://github.com/spavikevik/palma2pro-eos
Files: docs/19-tcon-panel-abi.md, 07-epd-hardware.md, 06-kernel.md, 11-epd-update-path.md, 03-ebc-api.md, 21-own-kernel.md.
- TCON node mxo1300@40, compatible "onyx,mxo", I2C 0x40 (ours 0x34 = different product/bitstream), fw-product-id 0x81;
  GPIOs program_enable/init/done = Lattice PROGRAMN/INITN/DONE; rails fpga_12v_core_en(gpio6), fpga_25v_en(48),
  fpga_30v_en(100), reset_gpio 139 active-low; regulators vsys 3.0 V, vddi2c 1.8 V, vdd1v8in, vdd3vin, vdd1v2in.
- eink-timings: ED061KC1 1648x824, sdclk 40 MHz, margins L/R/U/D 11/21/5/4, hsync_len 17, vsync_len 2, panel_width 16,
  kernel_init_mode_disable = 1 (kernel never paints at probe; userspace drives the screen).
- TPS65185 @0x68: pwr_seq0/1/2 = 0xe1/0x30/0x33, upseq0 0xe4, dwnseq0 0x1e, max_wait 0x18, delay_3v3_highv 3,
  VCOM range -4.325..-0.5 V.
- Kernel config (IKCONFIG): FB_ONYX_SOFTWARE_EPDC=y, ONYX_EPDC_SEND_MODE_VIDEO=y, ONYX_EPDC_TCON_TYPE_LCDIF=y,
  DISPLAY_BUF_PIXEL_FORMAT_RGBA=y, PANEL_DATA_CTRL_END_SWAP=y, INIT_WAVE_FIRMWARE=y; EXTRA_FIRMWARE = waveform +
  mxo/mxo{1300,4300}_nvcm_8x.ied (9) + lfcpnx/lfcpnx100_tcon_fw_{99,9e,9f,a2,a5,a7}.bin (6), all inside the Image.
- Key DSI fact (docs/19 §2, docs/11): "The DSI link timing is not the panel resolution. card0-DSI-1 1648x824
  dsi_rm69299_visionox_amoled_cmd dummy panel 'primary'; card0-DSI-2 457x835 dsi_epdc_cmd = the real EPD. The epdc
  panel's DSI timing is 457x835 because the link feeds the FPGA TCON in a packed format; the TCON drives 1648x824."
  dmesg: dsi_display_dev_probe(): boot_disp[qcom,mdss_dsi_epdc_cmd] ... "epdc panle is SECONDARY dsi".
  SurfaceFlinger logs hasHwTcon: 0 -> kernel does waveform work in software (SWEpdcManager).
  Only identified FPGA I2C traffic: lfe5u_ctrl_send_cmd 2-byte {cmd,data}: 0x7210 -> cmd 0x10 CMD_TCON_DEBOUNCE_PARM (10),
  0x7211 -> cmd 0x11 CMD_TCON_DEBOUNCE_THRESHOLD (128). Function keeps the lfe5u name on CertusPro-NX.
- Bitstreams inside the Image found by Lattice sync word FFFFBDB3 (6 occurrences, region ~0x17f0000-0x1a90000).
- [derived] 457x835 decodes as an i.MX-LCDIF-style raw source-driver frame: 835 = 824+5+4+2; 457 = 1648/4 (412) +
  (11+21+17-4) (45). Storytel RK3128 log confirms the formula (1024x758 -> ldl 256, xres_lcd_data 302, yres 769).
  In TCON_TYPE_LCDIF / software-EPDC mode the DSI "image" is not a picture: 24-bit DSI pixel = 4 panel pixels x 2-bit
  waveform data + control bits; panel blanking carried as pixels; FPGA = DSI->parallel pass-through.

## 2. vendor.onyx.htcon = "has hardware TCON" [fetched]
- hbmartin/onyx-android-sdk SystemPropertiesUtil.java: "vendor.onyx.htcon" -> hasHTCon(). Note Air 4C (lito) getprop:
  [vendor.onyx.htcon]: [true]. Palma 2 Pro: hasHwTcon: 0.
- Onyx ships both an SoC-side software EPDC (FPGA = dumb LCDIF bridge) and a hardware TCON (FPGA holds waveform/LUT,
  HWEpdcManager). Our register set (DISPLAY_MODE, UI_MODE_SET, VCOM, PM_STATE, WF_SEND_STATE, FLG_STATE, ERROR) and the
  onyx_tcon_cmd_queue/triger/get_tcon_display_addr/set_upd_scheme symbols are the htcon path; 1648x824 RGB888 DSI =
  plain images into a TCON with its own frame memory. Protocol undocumented.

## 3. Leaked Onyx kernel .config [fetched]
https://github.com/tautcony/leaf5-ghostlock/blob/1aa2db1d5b2b17eee243ab0031965e56ac29c886/leaf5/raw/kernel_config.txt
(SDM662 = SM6115/SM4250, panel ONYX_EINK_ES133TT3_2200x1650). Lines 3551-3598: FB_ONYX_SOFTWARE_EPDC, EPDC_MFD_REGISTER,
SEND_MODE_VIDEO, DISPLAY_BUF_PIXEL_FORMAT_RGBA, PANEL_DATA_CTRL_END_SWAP, FIRMWARE_WAVEFORM_KERNEL, TCON_TYPE_LCDIF,
EPDC_SEGMENT, USE_MIPI_SDM662, SDM662_PERF, WAVEFORM_VENDOR_DIR="onyxconfig", FB_MSM_MDSS_EPDC_PANEL_PERF,
TC358762_MIPI2DBI, MXO_MIPI2DBI, LFE5U_MIPI2DBI; MFD/REGULATOR/SENSORS_TPS6518X. [derived] Onyx models every TCON
(TC358762 real DSI->DPI/DBI bridge, MachXO, ECP5, CertusPro-NX) as a "MIPI2DBI" bridge = Lattice reference bridge class.

## 4. Storytel Reader (Boox-made, RK3128) [fetched]
- https://github.com/ntherning/StorytelReaderMods/blob/389b3b22b45c67369ae35d26fd1bfbc9658bee44/dumps/gen2/bootlog —
  only public stock dmesg of the Onyx EPDC driver (ONYX_EPDC_DEBUG_PRINTK): timing formula, upd_scheme = 2, waveform
  parse (mode_num=8, temp_num=14, gray_num=32), "not ready!! -- skip magic[N]" until waveform loads, set_temp 24.
- https://github.com/hsw/onyx-rc2-ebc/blob/99ce0fbaa96741a66aabe50f5d877596111bdb7f/driver/other-controllers.md —
  software EPDC (onyx,sepdc): 128 LUT slots, onyx_epdc_merge_upd, per-update magic markers, /dev/ebc ioctl 0x7000+n (34).

## 5. cloudrumbles/boox-gocolor7-linux [fetched commit page]
https://github.com/cloudrumbles/boox-gocolor7-linux — mainline 6.18 for Go Color 7 Gen II = SM6350 (same SoC). Commits:
apps-smmu/tlmm diagnostics, "iommu/qcom: preserve boot streams without firmware state", audio/battery thermal, venus.
No display/DSI/TCON work. Worth contacting; the iommu patch may matter for DSI bring-up.

## 6. Lattice DSI receiver constraints [fetched both PDFs]
(a) FPGA-IPUG-02081-2.1 CSI-2/DSI D-PHY Rx IP User Guide (Jan 2024; CrossLink-NX/CertusPro-NX):
https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/5873/FPGA-IPUG-02081-2-1-CSI2-DSI-DPHY-Rx-IP-User-Guide.pdf
- Supports continuous and non-continuous clock; all DSI video modes (sync pulses, sync events, burst).
- §8.3 Limitations: "Escape Mode, ULPS, and Bus Turnaround sequences are not yet supported." §2.6: the Global
  Operations Controller only supports LP-11 -> LP-01 -> LP-00 -> HS0 -> HS0/1 -> LP11. => cannot receive LP (LPDT/escape)
  DCS commands, cannot answer BTA/reads; only HS packets decoded.
- §2.5.2: LP blanking interval between HS transactions must be long enough for the FIFO to empty, otherwise the word
  aligner misses the SoT of the next stream. §8.1 continuous-clock design: clk_byte_fr_i from clk_byte_hs_o, RX FIFO OFF
  (recommended with Soft D-PHY + continuous HS clock); ping-pong FIFO recommended for DSI with LP blanking.
- Hard D-PHY timing: continuous clock needs T_HS-EXIT + T_LPX >= 8*T_clk_byte + 3*T_sync_clk; non-continuous needs
  T_CLK-POST + T_LPX >= ...
- Packet parser: rxcsr_dropnull_i=0 -> null/blanking packets assert lp_en; lp_av_en_o only for the configured ref_dt_i
  (pixel data type must be exactly what the bitstream expects, e.g. 0x3E RGB888).
(b) FPGA-RD-02238 v1.2 "MIPI DSI/CSI-2 to Parallel Bridge for CertusPro-NX"
https://www.latticesemi.com/view_document?document_id=53358 (design page:
https://www.latticesemi.com/products/designsoftwareandip/intellectualproperty/referencedesigns/referencedesigns05/mipidsicsi2toparallelbridge
source ZIP document_id=53354):
- 80 Mb/s..1.5 Gb/s; 1/2/4 lanes; continuous and non-continuous clock; RGB888/RGB666; non-burst sync pulses and
  non-burst sync events (burst not listed); dedicated EoTp. Known limitations: only RGB888/RGB666 data types; no command
  mode / DCS forwarding. Default build: RX 4 lanes, Gear 8, Soft D-PHY in continuous clock mode (CertusPro-NX has no
  hard D-PHY; LFCPNX-100 = Onyx's lfcpnx100). LP_BLANKING directive enables LP during vertical blanking, else HS blanking.
- vsync_o goes high/low on VSYNC start/end short packets; in sync-events mode the end packets are absent and
  VSYNC_WIDTH/HSYNC_WIDTH are static design parameters that must match the Byte-to-Pixel settings.

## 7. Firmware package tooling [fetched README]
https://github.com/Hagb/decryptBooxUpdateUpx — DeBooxUpx.py <model> update.upx update.zip, AES key/IV per model in
BooxKeys.csv (Palma, Page, Go6, Leaf*; no Palma2 row seen — verify). payload.bin -> payload-dumper-go -> boot.img.
Also gist winstonma/41305920ec95aa1ec2c7b4227ab7e9f0 "Onyx Boox Image Extractor" [search-hit].

## 8. Negative results
XDA / MobileRead / pmOS wiki / GitLab / LKML / dri-devel: nothing on Boox DSI-TCON bring-up. KOReader
android-luajit-launcher#250 (Nova 2) is Java-level only. Kongpob-R/epaperdisplaylauncher mentions onyx_epdc [search-hit].

## Implications for our sequence
1. Confirm TCON mode on stock: getprop vendor.onyx.htcon; zcat /proc/config.gz | grep -E 'ONYX_EPDC|MIPI2DBI|SOFTWARE_EPDC';
   epdc panel node width/height in the DTBO. 1648x824 RGB888 + WF_SEND_STATE registers => htcon variant [derived].
2. In htcon mode the DSI frame is only a buffer write; the update is triggered over I2C after the frame has landed.
   Capture the stock per-update I2C transaction (ftrace/kprobe on lfe5u_write_reg / lfe5u_ctrl_send_cmd /
   onyx_tcon_triger, or a logic analyser on SDA/SCL) during one refresh — the missing protocol.
3. Lattice-side constraints: DCS/generic packets in HS only, never LP; no reads/BTA; prefer continuous HS clock (reference
   default) — non-continuous works only if the bitstream has the LP<->HS clock-lane detector; sync-pulse or sync-event
   only; with sync-event the hsync/vsync widths must equal stock exactly; keep HS blanking unless stock used LP blanking
   (then the LP gap must exceed the FIFO drain time, do not shrink porches); pixel data type RGB888 (0x3E) VC0; EoTp fine.
4. Palma 2 Pro register details (0x40, onyx,mxo, product 0x81) are a different product/bitstream — only its structure
   transfers (2-byte cmd/data messages, PROGRAMN/INITN/DONE handshake, TPS65185 sequencing).
5. Contacts: spavikevik/palma2pro-eos (same panel/TCON family, kernel-Image blob map), cloudrumbles/boox-gocolor7-linux
   (SM6350 mainline, no display).

Local copies: scratchpad dl/ of session 09b25588 (palma2pro docs, leaf5 kconfig, Storytel bootlog, hsw doc, ipug02081.txt,
rd02238.txt, rd02238.pdf) — copy into recon/ if needed.
