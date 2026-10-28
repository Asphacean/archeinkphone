# Speaker silent on mainline: stock vs. mainline audio diff

Date: 2026-10-27. This was read-only research. Nothing ran on the device.

Sources used:
- stock `audio_wcd937x.ko` and other modules, extracted from vendor_a (super.bin) and disassembled
- stock vmlinux (`analysis/vmlinux.elf`), decompiled with Ghidra (the aw87xxx driver is built into the kernel)
- `recon/android-audio/mix_play.txt`, `recon/root/live.dts`, `mixer_paths_lagoonqrd.xml`
- mainline v7.2 `wcd937x.c`, `wcd937x-sdw.c`, `wcd-clsh-v2.c`, `lpass-rx-macro.c` and `soundwire/qcom.c`

## TL;DR: most likely cause

**Mainline wcd937x does not put the LO (AUX) SoundWire port into the stream unless the `LO Switch` kcontrol is on.**

- Stock does this automatically. `wcd937x_enable_rx3` PRE_PMU calls `wcd937x_set_port_params(…, 0x0e /*LO*/)` and then `swr_connect_port`.
- In mainline, `RX3` / `CLS_H_PORT` have no port logic. Ports are only added by the `HPHL/HPHR/LO/CLSH PA/DSD_* Switch` controls. Those call `wcd937x_connect_port()`, which sets `port_config[].ch_mask`.
- `wcd937x_sdw_hw_params()` skips every port whose `ch_mask == 0`.
- So with `LO Switch` off, DAPM powers the whole AUX chain and the stream "plays" without errors (the HPHL port we enabled keeps the stream valid). But slave port 4 / master port 4 never carries the INT2 PDM data, and AUX outputs silence. `LO Switch` was not in the list of things already tried.

Stock also connects the **CLSH port** (master/slave port 2) during speaker playback. In stock `wcd937x_enable_clsh`, the port is connected when `hph_mode ∈ {1,2,4,5}`. Stock sets mixer `RX HPH Mode` = `CLS_AB`, which is text index 4. The put handler stores the index raw, so it lands in the internal enum as `CLS_H_LOHIFI` (the "CLS_H_INVALID" text entry shifts the enum by one). Mainline has the same text/enum quirk.

### Proposed mixer sequence (set BEFORE opening the PCM; ports are latched at hw_params)

```
amixer -c0 cset name='RX HPH Mode' CLS_AB          # same as stock (internally CLS_H_LOHIFI)
amixer -c0 cset name='LO Switch' on                # <-- the missing piece (SWR port 4, ch 0x1)
amixer -c0 cset name='CLSH PA Switch' on           # stock streams CLSH port 2 in this mode
amixer -c0 cset name='HPHL Switch' off             # port 1 not used for speaker on stock
amixer -c0 cset name='RX_MACRO RX2 MUX' AIF2_PB
amixer -c0 cset name='RX INT2_1 MIX1 INP0' RX2
amixer -c0 cset name='AUX_RDAC Switch' on
amixer -c0 cset name='RX_RX2 Digital Volume' 84    # 0 dB; check that it is not 0 (=-84 dB)
amixer -c0 cset name='AUX_HPF Switch' on           # stock: "AUX_HPF Enable On"
# + MultiMedia1 -> RX_CODEC_DMA_RX_1 routing, FSA2275 gpio90=0/gpio47=0, AW87390 "Music" profile
```

Fallback if class-H mode misbehaves: `RX HPH Mode` = `CLS_H_LP`. That selects real CLS_AB (enum 3), which needs no CLSH port data. Mainline AUX POST_PMU then sets `RX_SUPPLIES` bit 1, the same as stock does for CLS_AB.

Ignore `SpkrMono WSA_RDAC` / `SpkrMono BOOST Switch` from mixer_paths. These controls **do not exist** on the stock card (they are absent from the 2658-control dump), so the HAL skips them. They are leftovers from the QRD WSA881x path.

## Q2: SoundWire port mapping (verified)

Stock `rx_swr_master` (0x3210000, `qcom,swr-num-ports = 5`), `qcom,swr-port-mapping` triples `<port type ch_mask>`:
`(1,HPH_L,1) (1,HPH_R,2) (2,CLSH,1) (3,COMP_L,1) (3,COMP_R,2) (4,LO,1) (5,DSD_L,1) (5,DSD_R,2)`.
Stock slave `qcom,rx_swr_ch_map`: LO = slave port idx 3, so slave port 4, ch 0x1. CLSH = slave port 2, ch 0x1.

Our DT has `qcom,rx-port-mapping = <1 2 3 4 5>` and `qcom,rx-channel-mapping = <1 2 1 1 2 1 1 2>`. Both **match** stock. Mainline `wcd937x_sdw_rx_ch_info` puts LO on `WCD937X_LO_PORT` (4), BIT(0). Mapping is correct. Only the enable (the `LO Switch`) is missing.

Our master port params for port 4 are SI=0x03, off1=0x01, off2=0, the rest 0xff. These match the stock 4.8 MHz table layout (kodiak-derived). The `din-ports (0) / dout-ports (5) mismatch` messages are cosmetic: `qcom.c` uses the DT value, and stock also declares 5 ports.

## Q1: wcd937x AUX register sequence, stock vs. mainline

| Step | Stock audio_wcd937x.ko | Mainline wcd937x.c |
|---|---|---|
| RX3 PRE_PMU | connect LO port (type 0x0e) | nothing (needs `LO Switch`) |
| CLS_H_PORT supply | `wcd937x_enable_clsh`: connect CLSH port if mode ∈ {1,2,4,5} | no event (needs `CLSH PA Switch`) |
| AUX DAC PRE_PMU | rx_clk_enable; 0x3408 b2; 0x3409 b2; 0x344F b0; clsh PRE_DAC AUX | same **plus `AUX_AUXPA (0x3128)` bit 4 = 1** (stock never writes bit 4) |
| AUX PA PRE_PMU | `swr_slvdev_datapath_control(on)`; 0x3467 mask 0x05 = 0x05 | PDM_WD_CTL2 EN/TIMEOUT/HOLD_OFF (equivalent) |
| AUX PA POST_PMU | sleep 1 ms; if mode 3/6 (CLS_AB/CLS_AB_HIFI): 0x3008 b1; bolero RX_MUTE event (unmute RX3); irq on | sleep; same b1 condition; **plus 0x3008 b6 and b7 = 1**; irq on |
| AUX PA POST_PMD | sleep 2 ms; clsh POST_PA AUX; 0x3467 &= ~5 | similar |
| codec init (`wcd937x_init_reg`) | 0x3103, 0x312A, 0x3029, 0x3001, 0x30E2, 0x306B/E, 0x3071 | same register set in `wcd937x_io_init` |

Secondary suspects, only if `LO Switch` alone does not help. These are guesses:
- mainline extra write `AUX_AUXPA` bit 4
- `ANA_RX_SUPPLIES` (0x3008) bits 6/7

To test, clear them by hand during playback through the regmap debugfs of the wcd937x component (or with a 2-line patch that drops them) and compare.

## Q4: rx-macro INT2 on lagoon

- Mainline rx-macro uses the same register layout for codec versions 1.0 through 2.1, and the INT2 path regs are identical. The sm8250 fallback (v1.0) is fine for the RX path.
- The interpolator is unmuted in mainline by `rx_macro_digital_mute()` (DAI mute_stream). Stock does it through the bolero `RX_MUTE` event from `wcd937x_codec_enable_aux_pa`. The two are functionally equivalent, provided `RX_MACRO RX2 MUX`=AIF2_PB has set `active_ch_mask` for AIF2.
- Diagnostic during playback: `CDC_RX_RX2_RX_PATH_CTL` bit 4 (PGA mute) must be 0.
- Stock state during playback:
  - `RX_COMP1/2 Switch` Off
  - `RX INT2_1 VBAT` Off
  - `AUX_HPF Enable` On
  - `RX_EAR Mode` OFF
  - `RX_HPH_PWR_MODE` ULP
  - `EAR PA GAIN` G_6_DB, which only touches 0x300B mask 0x7C (EAR compander gain), not AUX
- `RX_RX2 Digital Volume` reads 334 in the stock dump, which is out of range. It is probably a downstream readout artefact. Use 84 (0 dB).

## Q3: ONYX_AW_SpkrL_MODE (stock PA control)

Call chain: `onyx_soc_aw87xxx_mode_set` (in wcd937x.ko) → `onyx_snd_codec_mode_set` (function pointer) → `aw87xxx_mode_set_v230(dev_index, val)`.

What `aw87xxx_mode_set_v230` does with `val`:
- low nibble selects the profile: 0 Off, 1 **Music**, 2 Voice, 3 Fm, 4 Receiver
- bits 4–6 hold the gain offset, stored as `gain = 12 ± n`; 0 means 12, printed only
- it then calls `aw87xxx_update_profile` → `aw87xxx_power_on` → `aw_dev_default_pwr_on`:
  - `aw_dev_hw_pwr_ctrl`: no hwen GPIO in DT, so it is a no-op
  - `aw_dev_reg_update`: writes the ACF register list
  - optionally writes reg 0x05 if the profile requests it

There are no extra writes outside the ACF and nothing tied to stream timing: the HAL applies it with the mixer path, before the stream starts. Rails come from `onyx_aw_dev_regulator_ctrl`: vcc = pm6350_l5, vdd = "onyx-vsys" (gpio33). Our DT already hogs gpio33 high, and chip id and SYSCTRL read back the same as stock. **Conclusion: the PA is not the problem.**

## Suggested permanent fix

Put the sequence above in the UCM `EnableSequence` for the Speaker device, with `LO Switch` and `CLSH PA Switch` before the PCM opens. Disable them in `DisableSequence`. No DT or kernel change is required.

Optional kernel nicety (upstreamable): give `RX3` / `CLS_H_PORT` events that call `wcd937x_connect_port()` like stock, so DAPM handles the ports automatically.

## Follow-up 2026-10-27: device test still silent (LO + CLSH PA on), register dump review

### The rx-macro dump is from the wrong window
For codec versions ≤ 2.1 (our sm8250 data), mainline uses `rxn_reg_stride = 0x80` and `rxn_reg_stride2 = 0xc`. **INT2 lives at 0x0500–0x054C**, not at 0x0Bxx.
- 0x0A00–0x0AFF is the sidetone IIR block. `a24/aa4` = IIR0/1 `GAIN_B8`/`_CTL`-area defaults, and `a2c/aac` = IIR `COEF/CTL` defaults.
- `b40/b50 = 0x04` are `CDC_RX_SIDETONE_SRC0/1_ST_SRC_PATH_CTL` (reset value, 48 k rate field).
- So the dump says nothing about INT2. It does not show that INT2 is off.

Registers to read during playback, with the values expected if INT2 is running:

| reg | name | expect |
|---|---|---|
| 0x0100 | CLK_RST_CTRL_MCLK_CONTROL | bit0 = 1 |
| 0x0104 | CLK_RST_CTRL_FS_CNT_CONTROL | bit0 = 1 |
| 0x0108 | CLK_RST_CTRL_SWR_CONTROL | bit0 = 1 (SWR clk to the master) |
| 0x0190 | INP_MUX_RX_INT2_CFG0 | low nibble 0x3 (= RX2) |
| 0x0500 | RX2_RX_PATH_CTL | 0x24: bit5 CLK_EN = 1, bit4 PGA mute = 0, rate 0x4 |
| 0x0504 | RX2_RX_PATH_CFG0 | CLSH_EN and DLY_Z_EN set |
| 0x0514 | RX2_RX_VOL_CTL | 0x00 (0 dB) |
| 0x054C | RX2_RX_PATH_DSM_CTL | bit0 = 1 |

Why INT2 can stay muted or unclocked even though DAPM shows "RX INT2_1 INTERP" On:
- `rx_macro_enable_interp_clk()` only sets PGA mute = 1 and DSM clk.
- `CLK_EN` (bit5) and the unmute are written in `rx_macro_digital_mute()` (the DAI `mute_stream`). They are applied only to interpolators whose INT2 mux nibble matches a port in `active_ch_mask[dai->id]`.
- `active_ch_mask` is filled by `rx_macro_mux_put` (`RX_MACRO RX2 MUX` = AIF2_PB) and is keyed by the DAI that the card actually uses.
- If the DAI link resolves to a different rx-macro DAI id, or the mux was set before the macro probed, INT2 stays at 0x0500 = 0x10 (muted, no clock).
- This is exactly what 0x0500 will show.

`RX_EAR Mode` only touches INT0 (`RX0_RX_PATH_CFG1` EAR_SEL and the HPH class-H V_PA). It has no effect on INT2. INT2 has no kcontrol besides `AUX_HPF Switch` and the `RX INT2*` muxes and volumes.

### wcd937x dump decode (0x3000–0x313F)
| reg | val | meaning |
|---|---|---|
| 3008 ANA_RX_SUPPLIES | 0xC3 | bits 0, 1 + AUX bits 6/7 set: the AUX PA POST_PMU ran |
| 3009 ANA_HPH | 0xAC | **bit7 = HPHL PA enabled.** The HPHL path is still powered. Stock never has HPH and AUX on together. Set `HPHL_RDAC Switch` = 0 |
| 300B EAR_COMPANDER_CTL | 0x42 | EAR gain field, not used by AUX |
| 3128 AUX_AUXPA | 0x90 | AUX PA enabled (bit7) + the mainline-only bit4 |
| 3129 LDORXTX_MODE | 0x0C | default |
| others | | MBHC, micbias, bias and HPH timers. Defaults, or from the TX path |

Analog AUX is up. What is missing is evidence that PDM data reaches it. Read next:
- wcd937x **0x3400–0x3470**. Expect:
  - `0x3408` ANA_CLK_CTL bits 0, 1, 2
  - `0x3409` DIG_CLK_CTL bits 2, 3
  - `0x340F` CDC_RX2_CTL bit6 = 0
  - `0x344F` AUX_GAIN_CTL bit0 = 1
  - `0x3467` PDM_WD_CTL2 bits 0, 2
- SoundWire:
  - `/sys/kernel/debug/soundwire/master-*/qualcomm-sdw/qualcomm-registers`: master DP4 / DP2 port enable
  - the slave's `registers` file under `/sys/kernel/debug/soundwire/master-*/sdw:*`: DP4 ChannelEn (0x420 / 0x430) must be 0x01 in the active bank, and DP2 likewise

### Next actions (no writable regmap needed)
1. Set `HPHL_RDAC Switch` = 0 (with `HPHL Switch` = 0) so only the AUX chain is powered, as on stock.
2. Read the registers listed above. Interpretation:
   - **0x0500 shows bit4 = 1 or bit5 = 0:** the rx-macro mute/clock is never released. The fix is a kernel patch. Force an unmute and `CLK_EN` for INT2 in `rx_macro_enable_interp_clk` POST_PMU, or debug why `active_ch_mask[AIF2_PB]` is empty: print it in `rx_macro_digital_mute`.
   - **0x0500 = 0x24 but slave DP4 ChannelEn = 0:** a SoundWire stream or port problem.
   - **Both OK:** look at `AUX_AUXPA` bit4 and the RX_SUPPLIES bits 6/7 (guess).

## 2026-10-27 evening: ruled out, new lead
- Clean AUX-only run (HPH never enabled): wcd937x 0x3408=07, 0x3409=0c, AUX PA on, slave+master DP4 ch1 enabled with matching SI=3/off1=1. Still silent.
- Clearing mainline-only AUX_AUXPA b4 and RX_SUPPLIES b6/7 live (SWR debugfs write: `command`=0 write / 1 read) changes nothing. RX HPH Mode ULP/CLS_AB/NORMAL/HIFI: nothing.
- Mainline bug noted: RX1/RX2 POST_PMD call rx_clk_disable while AUX still active (shared, non-refcounted) -> kills ANA_CLK b0/1.
- **Lead:** our rxmacro voted TX_CORE_MCLK/TX_CORE_NPL (copied from sm8250). Stock bolero rx_core_clk/rx_npl_clk = AFE 0x30e/0x30f = RX_CORE_MCLK/RX_CORE_NPL_MCLK. Fixed in DT -> boot-r36-audio6.img.
- Stock also writes `qcom,rx_mclk_mode_muxsel` 0x033240d8 (tx: 0x033220d8) = 1 after core clk enable (bolero-clk-rsc dev_up_gfmux). Mainline never does; reads 0 on our device. Test live via /dev/mem (`~/mux.py 0x033240d8 1`).
- Capture (DMIC0 via TX DEC2) gives I/O error, independent of tx muxsel.
