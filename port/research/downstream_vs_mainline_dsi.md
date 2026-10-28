# Downstream (msm-4.19 techpack/display, lagoon) vs mainline v7.2 drm/msm: DSI video-mode bring-up

Sources compared:
- Downstream: LineageOS/android_kernel_fairphone_sm7225 (FP4 = SM7225 = lagoon), `techpack/display/msm/{dsi,sde}`, `techpack/display/pll/dsi_pll_10nm.c`.
  Cross-checked against the STOCK Boox vmlinux (analysis/vmlinux.elf, objdump) for the functions that matter:
  `dsi_ctrl_hw_cmn_phy_sw_reset`, `_set_video_timing`, `_video_engine_setup`, `_ctrl_en`, `_soft_reset` are byte-for-byte the FP4 code
  (PHY_SW_RESET=0x01000001, HS_TIMER=0x3FD08, MISR_VIDEO_CTRL=0x10100, TIMING_FLUSH=1 @0x1E4, TIMING_DB_MODE=0 @0x1E8,
  CLK_CTRL force value 0x200B3F). Stock `sde_hw_intf_setup_timing_engine` (decomp_str) = FP4 code (INTF_CONFIG2=0, DATA_HCTL=0 for DSI).
- Mainline: sm6350-mainline/linux tag v7.2.0-sm6350: dsi/dsi_host.c, dsi/dsi_manager.c, dsi/phy/dsi_phy_10nm.c, disp/dpu1/*.
- Register offsets below are DSI0 physical offsets (downstream numbering; mainline 6G xml is -4 but ctrl_base is shifted +4, so same physical).
  SM6350: DSI0 ctrl 0xAE94000, PHY cmn 0xAE94400, PHY lanes 0xAE94600, PLL 0xAE94900, INTF_1 0xAE6A800.

## 1. Downstream sequence (dsi_display_prepare -> dsi_display_enable -> SDE kickoff)

1. Core clocks on (mdp/ahb/iface).
2. `dsi_ctrl_hw_cmn_phy_sw_reset`: 0x12C = BIT(24)|BIT(0) (0x01000001), 1 ms, 0x12C = 0, 100 us.
3. `dsi_phy_hw_v3_0_enable`: wait REFGEN; CMN_CTRL_0=0x60; PLL_CNTRL=0; RBUF_CTRL=0; GLBL_CTRL=0x10; VREG_CTRL=0x59;
   LANE_CFG0/1=0x21/0x84; TIMING_CTRL_0..11; CMN_CTRL_0=0x7f(|0x1f); LANE_CTRL0=0x1f; CTRL_2=0x40; CLK_CFG1=src<<2;
   lane settings: LPTX_STR=0x55, LPRX=0 (lane0: 0x03), PIN_SWAP=0, HSTX_STR=0x88, LN_CFG0..3 from DT (clk lane CFG3=0x80),
   OFFSET_TOP/BOT=0, TX_DCTRL={0,0,0,0x04,0x01}. **No 0x05->0x04 freeze toggle on lane 3.**
4. Clock source set (byte/pixel RCG parents -> PLL).
5. `dsi_ctrl_host_init`: lane map; `host_setup` (TRIG_CTRL w/o TE bit unless ext-TE, T_CLK_PRE_EXTEND @0x180, CLKOUT_TIMING, EOT,
   **CLK_CTRL=0x23F**, DSI_CTRL |= clk lane BIT8 + data lanes, *no* DSI_EN);
   `video_engine_setup` (VIDEO_MODE_CTRL @0x10, VIDEO_MODE_DATA_CTRL @0x20, **TIMING_DB_MODE @0x1E8 = 0**);
   `set_video_timing` (ACTIVE_H/V, TOTAL, HSYNC, VSYNC, VSYNC_VPOS, HS_TIMER=0x3FD08, MISR_VIDEO_CTRL=0x10100, **TIMING_FLUSH @0x1E4 = 1**);
   status IRQs; error IRQs (INT_CTRL BIT25, ERR_INT_MASK0 from 0x7FFF3BFF).
6. `dsi_ctrl_set_host_engine_state(ON)` -> `ctrl_en`: CLK_CTRL |= 0x200B3F (force-on dynamic clocks), DSI_CTRL |= DSI_EN, CLK_CTRL restored.
   (DSI_EN is set BEFORE link clocks.)
7. Link clocks on (esc, byte, byte_intf, pixel). PLL: bias on (CMN_CTRL_0 BIT5, PLL_SYSTEM_MUXES=0xc0), CLK_CFG1[1:0]=cached mux,
   PLL_CNTRL=1, lock, CLK_CFG1 BIT5 (global clk), **RBUF_CTRL=1**.  (Mainline does the same, incl. RBUF=1 after lock.)
8. `dsi_ctrl_hw_cmn_soft_reset` (link clocks running): DSI_CTRL &= ~7; **CLK_CTRL |= 0x200B3F**; 0x118=1; 1 us; 0x118=0; CLK_CTRL restored; DSI_CTRL restored.
9. Panel prepare (reset GPIO; lp11-init: link is LP11 by now).
10. `dsi_display_enable`: **panel ON commands first (DCS 0x11, 255 ms) with VIDEO_MODE_EN=0**, then `video_engine_en` (DSI_CTRL |= BIT1).
11. SDE: setup_timing_engine (INTF regs, CONFIG2=0, DATA_HCTL=0), CTL intf cfg, prog fetch; first kickoff: CTL flush, then
    INTF_TIMING_ENGINE_EN=1 in `handle_post_kickoff` (Boox: only if !sde_video_continue_mode && !vid_enable_timing; Boox also has
    `sde_hw_intf_enable_timing_engine_tcon` that toggles TG for e-ink frame sending).

## 2. Mainline sequence (dsi_mgr_bridge_pre_enable)

1. `msm_dsi_host_reset_phy`: 0x12C = **0x1 only** (no BIT24), 1 ms, 0, 100 us.
2. `dsi_10nm_phy_enable`: same as downstream except TX_DCTRL(3) **0x05 then 0x04** (no OLD_TIMINGS quirk for sm6350); VREG from tuning (0x59 default).
3. `msm_dsi_phy_pll_restore_state` (CLK_CFG0, CLK_CFG1[1:0], OUTDIV, vco_set_rate).
4. `msm_dsi_host_power_on`: link clk set_rate + enable (PLL lock, RBUF=1);
   `dsi_timing_setup` (ACTIVE_H/V, TOTAL, HSYNC, VSYNC_HPOS=0, VSYNC_VPOS) — **never writes HS_TIMER_CTRL (0xBC), MISR_VIDEO_CTRL, TIMING_DB_MODE or TIMING_FLUSH**;
   `dsi_sw_reset`: clear DSI_EN, **CLK_CTRL=0x23F (no BIT8/11/21 dynamic force-on)**, 0x118=1, msleep(20), 0x118=0, restore;
   `dsi_ctrl_enable`: VID_CFG0, VID_CFG1=0, CMD_DMA_CTRL, TRIG_CTRL (**TE bit + BLOCK_DMA_WITHIN_FRAME**, not set downstream),
   CLKOUT_TIMING, T_CLK_PRE_EXTEND, EOT, ERR_INT_MASK0=0x13ff3fe0, CLK_CTRL=0x23F, LANE_SWAP, LANE_CTRL, DSI_CTRL=EN|CLK|lanes.
5. `msm_dsi_host_enable` -> `dsi_op_mode_config`: **VID_MODE_EN set immediately in pre_enable**, i.e. before/while the panel
   driver sends its ON commands (depends on panel prepare_prev_first), unlike downstream which sends ON cmds with VID engine off.
6. DPU: setup_timing_engine writes **INTF_CONFIG2 = DATA_HCTL_EN (BIT4)** and **DISPLAY_DATA_HCTL = (hstart+width-1)<<16 | hstart**
   for DPU>=5; downstream/stock write 0 / 0. TG enabled after first CTL flush (same as downstream).

## 3. Candidate writes to replicate (ranked)

| # | Write (phys addr) | Downstream location | Why it may fix VIDEO_MDP_FIFO + DLn HS FIFO over+underflow |
|---|---|---|---|
| 1 | Soft reset with dynamic clocks forced: `CLK_CTRL(0xAE9411C) |= 0x200B3F` (BIT8,9,11,21 on top of 0x23F) around `SOFT_RESET(0xAE94118)=1/0`, and likewise around setting DSI_EN | dsi_ctrl_hw_cmn.c `dsi_ctrl_hw_cmn_soft_reset`, `dsi_ctrl_hw_cmn_ctrl_en` (`DSI_CTRL_DYNAMIC_FORCE_ON`); stock vmlinux confirms 0x200B3F | Simultaneous overflow AND underflow on the MDP FIFO and all 4 lane FIFOs every frame = async FIFO pointers out of sync, not a rate problem. Mainline resets with only 0x23F, so byte/pclk dynamic-gated domains may not see the reset. Write-only/self-clearing: not visible in dumps. |
| 2 | Runtime recovery test (devmem, no rebuild): DSI_CTRL &= ~BIT1; DSI_CTRL &= ~(BIT0|BIT1); 0x11C=0x100A00; 0x118=1; 0x118=0; 0x11C=0 (then put back 0x23F); DSI_CTRL = old & ~BIT1; PHY `CMN_LANE_CTRL3 (0xAE944A4)=0x1F` until `LANE_STATUS1 (0xAE944F8)==0x1F`, then 0; wait until INTF line count is in active region; DSI_CTRL |= BIT1; clear FIFO_STATUS (0xAE9400C W1C) | dsi_display.c `dsi_display_handle_fifo_overflow` -> `dsi_ctrl_hw_cmn_ctrl_reset` + `dsi_phy_hw_v3_0_lane_reset` (applies to ctrl >= 2.2.1, lagoon 2.4) | This is Qualcomm's own fix for exactly this error on video mode. If FIFO_STATUS stays clean afterwards, root cause is enable ordering/reset, and #1/#3 are the permanent fix. |
| 3 | Order: send panel ON cmds with VID_MODE_EN=0, then set DSI_CTRL BIT1 (video engine) only after, just before the first INTF kickoff | dsi_display.c `dsi_display_enable` (dsi_panel_enable then `dsi_display_vid_engine_enable`) | Mainline sets VID_MODE_EN in bridge pre_enable; DMA cmds + 255 ms wait with video engine armed but no MDP stream may desync the engine. Move `msm_dsi_host_enable()` to bridge enable / after panel enable, or set panel `prepare_prev_first` and check order. |
| 4 | `TIMING_DB_MODE (0xAE941E8)=0` then after timing writes `TIMING_FLUSH (0xAE941E4)=1` | dsi_ctrl_hw_cmn.c `video_engine_setup`, `set_video_timing` (stock confirmed) | Mainline never touches them. If DB mode is on, readback shows shadow timings (dumps "match") while the active engine uses stale/reset timings -> over/underflow every line. Read 0x1E8 on mainline first; cheap to test with devmem (write 0 / flush 1). |
| 5 | `INTF_CONFIG2 (0xAE6A860)=0`, `INTF_DISPLAY_DATA_HCTL (0xAE6A864)=0`, `ACTIVE_DATA_HCTL (0xAE6A868)=0` | sde_hw_intf.c `sde_hw_intf_setup_timing_engine` (stock decomp line 128-130) | Mainline sets DATA_HCTL_EN + data window (DPU>=5). Stock runs with it off. Verify those 3 regs live (likely not in the "INTF timing" dump) and force 0 via devmem while TG is off, or patch dpu_hw_intf for INTF_DSI. |
| 6 | `DSI_PHY_SW_RESET (0xAE9412C)=0x01000001`, 1 ms, 0 | dsi_ctrl_hw_cmn.c `dsi_ctrl_hw_cmn_phy_sw_reset` (stock confirmed 0x1000001) | BIT24 undocumented in mainline (writes only BIT0); likely resets an extra PHY/ctrl-side datapath (resync) block. One-line patch in `msm_dsi_host_reset_phy`. |
| 7 | PHY `LN_TX_DCTRL(3) (0xAE94600+3*0x80+0x2C)=0x04` only, no 0x05 pulse | dsi_phy_hw_v3_0.c `lane_settings` | Mainline toggles "freeze I/O" on clock lane; downstream 4.19 never does. Low probability; try with `DSI_PHY_10NM_QUIRK_OLD_TIMINGS`-like path but keeping 0x04. |
| 8 | `TRIG_CTRL (0xAE94080)` without BIT31 (TE) and without BLOCK_DMA_WITHIN_FRAME; `HS_TIMER_CTRL=0x3FD08`; `MISR_VIDEO_CTRL=0x10100` | `dsi_setup_trigger_controls`, `set_video_timing` | Only affect cmd DMA / timers; include for parity. Compare TRIG_CTRL live. |

Not different (verified): PHY lane cfg / strength / LPRX (DT <0 0 0 0 0x80> = clk lane CFG3 0x80, [55 03 ...] = LPTX 0x55, lane0 LPRX 0x03,
regulator-settings unused on v3.0), LANE_CFG0/1 0x21/0x84, PLL init/commit values, RBUF_CTRL=1 after lock, programmable fetch math,
INTF polarity (0 for DSI in both). `dsi_ctrl_hw_22_config_clk_gating` (DISP_CC_MISC_CMD) is only used for idle/cmd-mode gating, off by default.

Also check live: PHY CMN_CLK_CFG0/CLK_CFG1 (0xAE94410/0xAE94414) stock vs mainline (pclk mux bits [1:0]), and Boox stock's TG behaviour
(`vid_enable_timing`, `sde_video_continue_mode`): stock may run the INTF TG only during frame transfers.
