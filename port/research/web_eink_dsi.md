# Web research: Onyx FPGA-over-DSI e-ink TCON, msm DSI FIFO errors, e-ink-over-DSI in mainline

Date: 2026-10-26. Web only, no devices touched. Sources are linked inline. "Not found" means I searched and nothing turned up, not that nothing exists.

## 1. Others bringing up Onyx/Boox with the FPGA "TCON" (lfe5u / lfcpnx / TCONB)

**Nothing public found.** No GitHub repo, XDA thread, pmOS wiki page or mailing-list post mentions `lfe5u`, `lfcpnx`, `TCONB`, "onyx tcon" or a CertusPro-NX used as an e-ink TCON. Searches for CertusPro-NX together with e-ink/e-paper returned only Lattice datasheets.

What does exist:
- **cloudrumbles/boox-gocolor7-linux**: "Kernel.org Linux 6.18 downstream for the Onyx Boox Go Color 7 Gen II", created 2026-08 by "Shahriyyah". The commits touch `arch/arm64/boot/dts/qcom/sm6350.dtsi` (venus, apps-smmu), so the **Go Color 7 Gen II is also SM6350**. There are 4 Boox commits: apps-smmu/tlmm diagnostics, "iommu/qcom: preserve boot streams without firmware state", audio/battery thermal (wcd937x, soundwire, adc5), and venus. **None touch display, DSI or a TCON.** The same user mirrors zephray's Caster EPDC, so they may be heading toward e-ink. They are worth contacting, and their SMMU "preserve boot streams" patch may matter for the same SoC.
  https://github.com/cloudrumbles/boox-gocolor7-linux
- **ONYX-BOOK/android_kernel_boox_sm6115** (branch boox13, 2026-08): this is an F(x)tec pro1x-based LineageOS tree with "Porting onyx boox" commits. The display changes are LCD ESD/`lcd_info` hacks, with focaltech ft8201ab TDDI touch, gt1x and pn7160. **It looks like an LCD ODM device, not e-ink. Not relevant.**
  https://github.com/ONYX-BOOK/android_kernel_boox_sm6115
- **Onyx GPL sources:** I found no Qualcomm-era kernel release. Onyx's GitHub (onyx-intl) holds only 2013-era apps and the BOOX60/ak98 kernels. Onyx has publicly declined GPL source requests:
  https://github.com/onyx-intl, https://en.wikipedia.org/wiki/Onyx_Boox, https://www.mobileread.com/forums/showthread.php?t=277431
- Other Boox Linux items are userspace only: jdkruzr/BooxPalma2RootGuide (EDL root), leath-dub/vboox (input over adb), and hsw/onyx-rc2-ebc / onyx-rc2-waveform (RK3026 EBC from an old Boox, useful only for waveform format).
  https://github.com/jdkruzr/BooxPalma2RootGuide, https://github.com/leath-dub/vboox
- SM6350 mainline reference: terraceonhigh/xperia-pmos (Xperia 10 III) reports mainline pmOS on SM6350 (shared FP4 tree). https://github.com/terraceonhigh/xperia-pmos

## 2. msm DSI FIFO overflow/underflow in video mode: known causes and fixes

### 2a. Mainline DSI clock and timing changes in 2026 (check whether your 7.2 tree has these)

| Change | Status | Relevance |
|---|---|---|
| `ac47870fd795` "drm/msm/dsi: fix hdisplay calculation when programming dsi registers" (Pengyu Luo, 2026-02). Reworked bytes-per-pclk to bits-per-pclk in `dsi_timing_setup()`. | Broke CMD/widebus panels and was dropped from stable. https://ratatoskr.run/stable/2026/03/7136439/t | Touches `dsi_timing_setup()` for **all** video-mode panels, so diff the resulting DSI_ACTIVE_H/TOTAL against Android (you say these already match). |
| `2d51cfb77daa` "drm/msm/dsi: fix bits_per_pclk" plus CMD-mode restore. Marijn: "Restore widebus…" | In mainline 2026-03-25. https://ratatoskr.run/dri-devel/2026/03/3446121/t, https://ratatoskr.run/linux-arm-msm/2026/03/3454278/t | DSC/widebus only. Non-DSC uses 24 bits/pclk. |
| "drm/msm/dpu: fix video mode DSC INTF timing width calculation" v3 | 2026-03 thread. Tester got "FIFO errors and no display" until the INTF width matched the downstream `data_width`. https://ratatoskr.run/lkml/2026/03/3471013/t | Shows that **an INTF-vs-DSI width/timing mismatch produces exactly these FIFO errors**. DSC only, though. |
| `6cd33b6f4155` "drm/msm/dsi: round 6G byte clock rate to the PLL-achievable value" (Kavan Smith) | Applied to msm-fixes 2026-07-12, so **probably in 7.2**. https://lkml.iu.edu/2607.1/09429.html, https://ratatoskr.run/dri-devel/2026/07/17220914/t | Rounds the **byte clk only** to the PLL-achievable rate. pclk is set separately. |
| Revert of 6cd33b6f4155 (Krzysztof Kozlowski) and the alternative "round the byte clock rate after reparenting to the PHY PLL" (Dmitry Baryshkov), 2026-09-03 | Posted. The first broke DSI 6G v2.9 (SM8650/8750) with "Failed to set rate pixel clk, -22". https://ratatoskr.run/lkml/2026/09/17504052/t, http://www.mail-archive.com/freedreno@lists.freedesktop.org/msg46766.html | Baryshkov's version also derives **byte_intf from the rounded byte rate** (`byte_intf_clk_div_2`). |
| Konrad Dybcio "DSI byte clock setting fixup" (dispcc glymur/kaanapali/milos/sm4450/sa8775p) | Applied to the clk tree 2026-03-10. https://ratatoskr.run/linux-arm-msm/2026/03/3440023/t | Bug: byte0_div (byte_intf) and byte0 both had CLK_SET_RATE_PARENT and fought over byte0_clk_src. SM6350 is not in the series (see 2b). |

Older reference points:
- `dsi_err_worker: status=4` (= DSI_ERR_STATE_FIFO) on DSC without widebus. Fixed by the 48-bit bus. https://www.mail-archive.com/freedreno@lists.freedesktop.org/msg30689.html
- `status=c` (DLN0 PHY + FIFO) from autorefresh + START together overloading the DSI (2019 "pp done time out" thread). https://lkml.iu.edu/hypermail/linux/kernel/1911.1/03267.html

**Not found:** any report specific to SM6350, SM7225 or SM6150 of VIDEO_MDP_FIFO plus all-lane HS_FIFO overflow and underflow, and any mainline report of a **non-burst** video panel on the 10nm PHY. The FP4 (SM7225) mainline video panel, `panel-himax-hx83112a`, uses `MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST`. **So non-burst sync-event mode on SM6350 has probably never been exercised upstream.** In non-burst mode the DSI link has no slack: the MDP pclk and the DSI byte clk must be in the exact ratio pclk = byte × lanes × 8 / bpp, which here is byte × 4/3. Any drift makes the MDP FIFO alternate between overflow and underflow every line or frame. Burst mode hides this.

### 2b. Concrete leads from reading the source (mine, unverified on hardware)

1. **SM6350 byte_intf divider is read-only in mainline.** `drivers/clk/qcom/dispcc-sm6350.c` declares `disp_cc_mdss_byte0_div_clk_src` (reg 0x10dc, 2-bit) with `clk_regmap_div_ro_ops`, with no CLK_SET_RATE_PARENT on the divider. sm8250, sc7180, sc7280, sm6115, sdm845 and sm7150 all use rw `clk_regmap_div_ops`. Downstream `dispcc-lagoon.c` is also ro (FP4 msm-4.19 mirror), so both kernels depend on whatever value is in the register. Mainline asks for byte_intf = byte/2 (`byte_intf_clk_div_2 = true` in the 10nm timing calc), but on SM6350 the request cannot change the divider. **Compare dispcc+0x10dc (0x0af010dc) and the `clk_summary` rates of byte0, byte0_intf, pclk0, esc0 and mdp between Android and mainline.** If byte0_intf equals byte0 on mainline but byte0/2 on Android, all-lane HS FIFO overflow/underflow is the expected result. Your register matching covered DSI, PHY, PLL and INTF, not dispcc RCG/MN/div.
   Sources: https://github.com/torvalds/linux/blob/master/drivers/clk/qcom/dispcc-sm6350.c, https://github.com/FairphoneMirrors/android_kernel_fairphone_sm7225/blob/master/drivers/clk/qcom/dispcc-lagoon.c
2. **Check the pclk0 RCG M/N/D (dispcc pclk0 cmd_rcgr) as well**, not just the PLL. Byte is now rounded to the PLL-achievable rate (6cd33b6f4155) while pclk is requested independently. In non-burst mode, pclk/byte must be exactly 4/3.
3. **The Android snapshot is not proof of "no overflow".** Downstream SDE (`techpack/display/msm/dsi/dsi_ctrl.c`) clears error bits in the ISR. It also clears DLNx_HS_FIFO_OVERFLOW on every BTA_DONE. It masks FIFO overflow around every DCS DMA transfer (`dsi_ctrl_mask_overflow()`), during ESD reads, and during PHY sw reset (`dsi_display.c`, which masks DSI_FIFO_OVERFLOW/UNDERFLOW/PLL_UNLOCK). It does still log `"dsi FIFO OVERFLOW error"` / `"dsi FIFO UNDERFLOW error"` when the bits are unmasked. **Grep Android dmesg/SDE evtlog for those strings** before treating Android as clean.
   Source (same SDE generation): https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/lineage-20/techpack/display/msm/dsi/dsi_ctrl.c
4. Mainline `dsi_fifo_status()` writes the status back to clear it and only sets DSI_ERR_STATE_MDP_FIFO_UNDERFLOW for **CMD**_MDP_FIFO_UNDERFLOW. VIDEO_MDP_FIFO bits are only logged as a generic FIFO error. Bits that recur after a W1C clear on every frame point to a real rate mismatch, not leftover startup junk.

## 3. Other e-ink TCONs over MIPI DSI in mainline

**None found.** I found no `drm/panel` or `drm/bridge` driver for an e-paper TCON on a DSI link, either in mainline or posted to dri-devel. Mainline and posted e-paper display work all uses SoC-integrated EPDCs or SPI/USB controllers:
- Rockchip EBC RFC (Samuel Holland, 2022, PineNote; not merged as far as I found). Its design notes still apply: no `drm_simple_display_pipe`, shadow buffers for relative updates, a refresh kthread, and an open question on how userspace selects the waveform. https://lore.kernel.org/all/1790161.aHo8FjPgqx@archbook/T/, https://lkml.iu.edu/hypermail/linux/kernel/2204.1/08394.html
- i.MX6/7 EPDC DRM series (Andreas Kemnade), credited in the EBC cover letter as the first such submission.
- `drm/tiny/repaper` (SPI) and IT8951 (SPI/USB). Neither uses DSI.
- Modos Glider/Caster: the FPGA EPDC accepts MIPI-DSI, LVDS or DVI **as input**, and the host side is a plain video source with mode hints over USB. That matches your topology (host DSI video, then FPGA, then EPD) and is the closest open reference for the FPGA side. https://github.com/Modos-Labs/Glider, https://github.com/Modos-Labs/Caster
- Hisense A5 (SDM439 e-ink phone, DSI e-ink): no mainline or pmOS port found. https://wiki.mobileread.com/wiki/Hisense_A5

Practical implication: a mainline Palma 2 driver would be a `drm_panel` (or bridge) on msm DSI. It runs continuous video mode, injects the pixel-(0,0) command into the plane content (or uses a DPU solid-fill/cursor layer for that pixel), and sends the I2C trigger after vblank. I found no upstream precedent for that pattern.

## Blocked or unreached
- lore.kernel.org and wiki.postmarketos.org (which redirects to wiki.nura.eco) are behind Anubis bot checks, so lore searches went through ratatoskr.run, lkml.iu.edu and mail-archive mirrors instead.
