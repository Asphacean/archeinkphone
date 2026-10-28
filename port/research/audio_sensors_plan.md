# Palma 2: audio + accelerometer bring-up plan (pmOS edge, linux-postmarketos-qcom-sm6350 7.2)

Status: research only. Nothing flashed, no kernel patches changed. Evidence is cited as
`file:line` or log excerpt. Anything marked **GUESS** has not been verified.

Sources: `recon/root/live.dts` (stock DT), `recon/android-20261026-1447/dmesg_root.txt`,
`port/firmware/stock/modem_a/image/adsp.*` (string scan), and kernel tarball
`linux-v7.2.0-sm6350.tar.gz` plus pmaports (`device-fairphone-fp4`,
`firmware-fairphone-fp4`, `alsa-ucm-conf-qcom-sm6350`, `msm-firmware-loader`) on winpc.

---

## 0. Shared prerequisite: ADSP up (needed by both audio and sensors)

Both audio and sensors run on the ADSP. SM6350 has no separate SLPI: the SSC sensors
run in the ADSP "sensors PD".

What we already have:
- `sm6350.dtsi` `adsp: remoteproc@3000000` (`qcom,sm6350-adsp-pas`). It carries the full
  APR tree (q6core, q6afe+q6afecc+q6usbdai, q6asm, q6adm/routing) and an ADSP `fastrpc`
  node with compute-cb 3/4/5. All of it is disabled only because `&adsp` is disabled.
- Firmware is already on the device in `/lib/firmware/qcom/sm6350/onyx/palma2/`
  (adsp.mdt + b00..b33). For pd-mapper, **the `.jsn` files must also be there**:
  `adspr.jsn`, `adsps.jsn`, `adspua.jsn` (from `port/firmware/stock/modem_a/image/`).
  The in-kernel pd-mapper (`CONFIG_QCOM_PD_MAPPER=m`) reads them next to the firmware.
  Without them, the `avs/audio` and sensors PDs never come up.
- Kernel config: `QCOM_Q6V5_PAS=m`, `QCOM_APR=m`, `QCOM_FASTRPC=m`, `SND_SOC_QDSP6=m`,
  `QCOM_PD_MAPPER=m` are already set.

DT (board file):
```dts
&adsp {
	firmware-name = "qcom/sm6350/onyx/palma2/adsp.mdt";  /* mdt+split bNN works, as mpss does */
	status = "okay";
};
/* cdsp is not needed for audio or sensors. Leave it disabled. */
```
Stock firmware is APR/Elite (it has the q6asm/q6afe channel `apr_audio_svc` and
`qcom,msm-pcm-*`), not AudioReach. That matches FP4, so use the **q6asm/q6afe/q6adm
(APR)** stack, not q6apm/q6prm.

Checks after boot: `remoteproc*/state = running` for adsp; dmesg shows
`q6core ... ready` / `apr ... adsp` services; `/dev/fastrpc-adsp` exists.
Effort: about 0.5 day. Risk: low (same blob family as FP4).

---

## 1. Audio

### 1.1 Stock hardware path (facts)

| Item | Evidence |
|---|---|
| Sound card `lito-lagoonqrd-snd-card`, `qcom,kona-asoc-snd` | live.dts 22985 ff |
| Internal codec: **bolero (LPASS digital) + WCD937x** (`wcd937x-codec` status ok, `wcd938x-codec` disabled) | live.dts 22750–22935 |
| `qcom,wsa-max-devs = <0>`: **WSA883x not used** (nodes exist but are inert) | live.dts sound node |
| Speaker PA: **Awinic AW87390** (analog-input class-K PA), one working instance at real addr **0x58** on `i2c@990000` (bus 3). DT nodes sit at 0x78/0x79 with `onyx,real-i2c-reg` 0x58/0x59. The **0x59 one fails probe → the speaker is mono** | dmesg: `[3-0078] ... set i2c_addr:0x58`, `product=[aw87390] profile=[Music/Voice/Fm/Receiver/Off]`, `[3-0079] pa init failed` |
| PA firmware: `awinic/aw87xxx_acf.bin` (ACF v0.0.0.1, profiles Music/Voice/Fm/Receiver/Off) | dmesg 10.316 |
| PA supplies: vcc = `pm6350_l2` (0x2cf), vdd = fixed `onyx-vsys` (already hogged in our DTS) | live.dts 7426–7460, 15660 |
| Analog switch **FSA2275** under Onyx control in the wcd937x node: mute gpio **47**, sel gpio **90** | live.dts 22771/22773 → pinctrl `audio_switch_mute_enable`/`audio_switch_headset_enable` |
| WCD937x reset: **gpio83** | `wcd938x_reset_active` pins gpio83 |
| WCD937x supplies: vddio/rxtx = `pm6150a_l10` (L10E, 0x19), buck = `pm6350_l13` (L13A), micbias = `pm6150a_bob` | phandle resolution |
| SoundWire: RX master @0x3210000 irq SPI **297** (0x129), TX master @0x3230000 irq SPI **296** (0x128, wake via PDC 0x90); version 1.5.1 | live.dts rx/tx_swr_master |
| WCD937x SDW slaves: RX `0x1170224` (unique id 4), TX `0x1170223` (unique id 3) | live.dts |
| LPI pins: tx_swr clk gpio0, data gpio1/2/14; rx_swr clk gpio3, data gpio4/5 (lpass_tlmm) | live.dts *_swr_*_active |
| USB-C analog audio: `fsa4480@42` on the same i2c@990000 bus (en pin gpio85), `qcom,msm-mbhc-usbc-audio-supported` | live.dts 7417, sound node |
| i2c@990000 = mainline **`&i2c10`** (our frontlight lm3630a@38 is on it too) | stock bus listing + our DTS |

Path, interpreted: `q6afe RX_CODEC_DMA_RX_0 → rx-macro → SoundWire RX → WCD937x (HPH or
AUX) → FSA2275 (sel) → AW87390 IN → speaker`.
**GUESS**: which WCD937x output feeds the PA (HPHL/HPHR vs AUX/EAR), and the FSA2275
polarity (sel=1 → speaker or → USB-C). Confirm from stock `vendor/etc/mixer_paths*.xml`
(see 1.5), or empirically by toggling gpio90/47.

### 1.2 Mainline driver availability (7.2 tree)

| Block | Driver | Status |
|---|---|---|
| AW87390 | `sound/soc/codecs/aw87390.c` (`awinic,aw87390`), DAPM `IN → SPK PA → OUT`, firmware **`aw87390_acf.bin`** (shares the aw88395 ACF parser) | exists. **CONFIG_SND_SOC_AW87390 not set** |
| WCD937x | `wcd937x.c` + `wcd937x-sdw.c` (`qcom,wcd9370-codec`/`wcd9375-codec`, sdw `sdw20217010a00`) | exists. **CONFIG_SND_SOC_WCD937X_SDW not set** |
| rx/tx/va macro | `lpass-{rx,tx,va}-macro.c`. **No sm6350 compatible** (sm8250, sm6115, sc7280, 8450…) | need sm6350 compat or fallback |
| SoundWire | `drivers/soundwire/qcom.c` `qcom,soundwire-v1.5.1` | `SOUNDWIRE_QCOM=m` ok |
| LPI pinctrl | `qcom,sm6350-lpass-lpi-pinctrl` (`lpass_tlmm` already in sm6350.dtsi; funcs `swr_rx_clk/data`, `swr_tx_clk/data`) | ok, `=m` |
| Machine | `sound/soc/qcom/sm8250.c` (handles q6afe CODEC_DMA + sdw prepare; FP4 uses `fairphone,fp4-sndcard` here) | `SND_SOC_SM8250=m` ok |
| FSA2275 | no driver. Model it with `simple-audio-mux` (sel) plus a `simple-audio-amplifier` or gpio hog (mute) | `SIMPLE_MUX`/`SIMPLE_AMPLIFIER` **not set** |
| FSA4480 | `drivers/usb/typec/mux/fsa4480.c` (`fcs,fsa4480`) | **not set**, and Type-C isn't wired up anyway |
| sm6350.dtsi | **has no rx/tx/va macro, SoundWire or WCD nodes** (only the APR tree, lpass_tlmm and an empty `sound {}`) | must add |

FP4 is not a full template for this. Its speaker is I2S (QUIN MI2S → aw882xx smart PAs)
and it uses no macros or WCD. The template for the macro/SoundWire part is
**sm8250.dtsi + qrb5165-rb5** (APR + q6afecc clocks + macros + swr v1.5.1, the same
generation as lagoon's bolero). The template for the WCD937x node is **qcm6490-idp.dts**.

### 1.3 Ordered steps

**A1. Kernel config** (`config-postmarketos-qcom-sm6350.aarch64`, proposal):
```
CONFIG_SND_SOC_AW87390=m
CONFIG_SND_SOC_WCD937X_SDW=m      # pulls SND_SOC_WCD937X
CONFIG_SND_SOC_SIMPLE_MUX=m
CONFIG_SND_SOC_SIMPLE_AMPLIFIER=m
# later, for USB-C analog: CONFIG_TYPEC_MUX_FSA4480=m
```

**A2. Kernel patch: macro compatibles** (small, about 20 lines). Add
`qcom,sm6350-lpass-{rx,tx,va}-macro`:
- rx/tx: same data as sm8250 (clocks mclk/npl/macro/dcodec/fsgen).
- va: **don't reuse `sm8250_va_data`**. It hard-codes `LPASS_CODEC_VERSION_1_0`. Add
  `sm6350_va_data = { .has_swr_master = false, .has_npl_clk = false, .version = 0 }` so
  `va_macro_set_lpass_codec_version()` reads CORE_ID from hardware.
  **GUESS**: lagoon bolero reports 1.x/2.0. Log what it detects on first boot. Stock
  va-macro has no SoundWire child, hence `has_swr_master=false`.
- Alternative with no C patch for the first test: `compatible = "qcom,sm8250-lpass-*-macro"`
  in the board DT. Fine for bring-up; replace with a proper sm6350 compat before upstreaming.

**A3. DT: add macros + SoundWire to the board DTS** (or a new `sm6350.dtsi` patch),
modelled on sm8250.dtsi. Proposed:
```dts
&soc {	/* or as a dtsi patch under soc@0 */
	rxmacro: codec@3200000 {
		compatible = "qcom,sm6350-lpass-rx-macro";   /* fallback: sm8250 */
		reg = <0 0x03200000 0 0x1000>;
		pinctrl-0 = <&rx_swr_active>; pinctrl-names = "default";
		clocks = <&q6afecc LPASS_CLK_ID_TX_CORE_MCLK LPASS_CLK_ATTRIBUTE_COUPLE_NO>,
			 <&q6afecc LPASS_CLK_ID_TX_CORE_NPL_MCLK LPASS_CLK_ATTRIBUTE_COUPLE_NO>,
			 <&q6afecc LPASS_HW_MACRO_VOTE LPASS_CLK_ATTRIBUTE_COUPLE_NO>,
			 <&q6afecc LPASS_HW_DCODEC_VOTE LPASS_CLK_ATTRIBUTE_COUPLE_NO>,
			 <&vamacro>;
		clock-names = "mclk", "npl", "macro", "dcodec", "fsgen";
		#clock-cells = <0>; clock-output-names = "mclk";
		#sound-dai-cells = <1>;
	};
	swr_rx: soundwire@3210000 {
		compatible = "qcom,soundwire-v1.5.1";
		reg = <0 0x03210000 0 0x2000>;
		interrupts = <GIC_SPI 297 IRQ_TYPE_LEVEL_HIGH>;   /* stock 0x129; sm8250 uses 298 */
		clocks = <&rxmacro>; clock-names = "iface";
		label = "RX";
		qcom,din-ports = <0>; qcom,dout-ports = <5>;
		/* qcom,ports-*: start from sc7280.dtsi swr0 (tuned for WCD937x/938x RX) */
		#sound-dai-cells = <1>; #address-cells = <2>; #size-cells = <0>;
	};
	txmacro: codec@3220000 { /* like rxmacro, compatible …tx-macro, pinctrl tx_swr_active */ };
	swr_tx: soundwire@3230000 {
		compatible = "qcom,soundwire-v1.5.1";
		reg = <0 0x03230000 0 0x2000>;
		interrupts = <GIC_SPI 296 IRQ_TYPE_LEVEL_HIGH>;   /* stock 0x128 */
		interrupt-names = "core";
		clocks = <&txmacro>; clock-names = "iface"; label = "TX";
		qcom,din-ports = <5>; qcom,dout-ports = <0>;
		/* qcom,ports-*: from sc7280.dtsi swr1 */
		#sound-dai-cells = <1>; #address-cells = <2>; #size-cells = <0>;
	};
	vamacro: codec@3370000 {
		compatible = "qcom,sm6350-lpass-va-macro";
		reg = <0 0x03370000 0 0x1000>;
		clocks = <&q6afecc LPASS_CLK_ID_TX_CORE_MCLK LPASS_CLK_ATTRIBUTE_COUPLE_NO>,
			 <&q6afecc LPASS_HW_MACRO_VOTE LPASS_CLK_ATTRIBUTE_COUPLE_NO>,
			 <&q6afecc LPASS_HW_DCODEC_VOTE LPASS_CLK_ATTRIBUTE_COUPLE_NO>;
		clock-names = "mclk", "macro", "dcodec";
		#clock-cells = <0>; clock-output-names = "fsgen";
		#sound-dai-cells = <1>;
	};
};

&lpass_tlmm {
	rx_swr_active: rx-swr-active-state {
		clk-pins  { pins = "gpio3";          function = "swr_rx_clk";  drive-strength = <2>; slew-rate = <1>; bias-disable; };
		data-pins { pins = "gpio4", "gpio5"; function = "swr_rx_data"; drive-strength = <2>; slew-rate = <1>; bias-bus-hold; };
	};
	tx_swr_active: tx-swr-active-state {
		clk-pins  { pins = "gpio0";                   function = "swr_tx_clk";  drive-strength = <2>; slew-rate = <1>; bias-disable; };
		data-pins { pins = "gpio1", "gpio2", "gpio14"; function = "swr_tx_data"; drive-strength = <2>; slew-rate = <1>; bias-bus-hold; };
	};
};
```
The `qcom,ports-*` arrays are the main risk. The SoundWire master fails or plays noise
when they are wrong. Copy them from sc7280 (WCD937x is used with those on qcm6490-idp).
Cross-check against stock `qcom,swr-port-mapping` (RX: 5 ports, TX: 5 ports).

**A4. DT: WCD937x + SDW slaves** (template: qcm6490-idp.dts):
```dts
/ {
	wcd937x: audio-codec {
		compatible = "qcom,wcd9370-codec";   /* GUESS 9370 vs 9375: driver reads chip id; 9375 adds TX ADC3 */
		pinctrl-0 = <&wcd_reset_n>; pinctrl-names = "default";
		reset-gpios = <&tlmm 83 GPIO_ACTIVE_LOW>;
		vdd-buck-supply     = <&vreg_l13a>;   /* stock cdc-vdd-buck = pm6350_l13 */
		vdd-rxtx-supply     = <&vreg_l10e>;   /* pm6150a_l10 1.8 V */
		vdd-px-supply       = <&vreg_l10e>;
		vdd-mic-bias-supply = <&vreg_bob>;
		qcom,micbias1-microvolt = <1800000>;
		qcom,micbias2-microvolt = <1800000>;
		qcom,micbias3-microvolt = <1800000>;
		qcom,micbias4-microvolt = <1800000>;
		qcom,rx-device = <&wcd937x_rx>;
		qcom,tx-device = <&wcd937x_tx>;
		#sound-dai-cells = <1>;
	};
};
&swr_rx {
	status = "okay";
	wcd937x_rx: codec@0,4 {
		compatible = "sdw20217010a00"; reg = <0 4>;
		qcom,rx-port-mapping = <1 2 3 4 5>;
		qcom,rx-channel-mapping = /bits/ 8 <1 2 1 1 2 1 1 2>;
	};
};
&swr_tx {
	status = "okay";
	wcd937x_tx: codec@0,3 {
		compatible = "sdw20217010a00"; reg = <0 3>;
		qcom,tx-port-mapping = <1 1 2 3>;   /* idp; stock lagoon tx map may shift by one, verify */
		qcom,tx-channel-mapping = /bits/ 8 <1 2 1 1 2 3 3 4 1 2 3 4>;
	};
};
```
Check the regulator labels against our `apps_rsc` blocks (L13A, L10E, BOB). L10E is
already used for Wi-Fi, which is fine because it is shared.

**A5. DT: AW87390 + FSA2275 + card**:
```dts
&i2c10 {
	speaker_amp: audio-codec@58 {
		compatible = "awinic,aw87390";
		reg = <0x58>;
		awinic,audio-channel = <0>;
		#sound-dai-cells = <0>;
		sound-name-prefix = "Speaker";
		/* vcc = pm6350_l2 must be on: add regulator-always-on to vreg_l2a, or a small
		 * driver patch for vdd-supply (the rgds variant already handles vdd) */
	};
	/* 0x59 (second PA) failed on stock too: leave it out */
};

/ {
	audio_sel: audio-switch-sel {           /* FSA2275 sel, gpio90 (GUESS polarity) */
		compatible = "simple-audio-mux";
		mux-gpios = <&tlmm 90 GPIO_ACTIVE_HIGH>;
		state-labels = "USB", "Speaker";    /* GUESS order */
		sound-name-prefix = "Out Switch";
	};
	audio_mute: audio-switch-mute {          /* FSA2275 mute, gpio47 */
		compatible = "simple-audio-amplifier";
		enable-gpios = <&tlmm 47 GPIO_ACTIVE_HIGH>;   /* GUESS: stock pinctrl drives it high = unmuted */
		sound-name-prefix = "Out Mute";
	};
};

&q6asmdai { dai@0 { reg = <MSM_FRONTEND_DAI_MULTIMEDIA1>; }; dai@1 { reg = <MSM_FRONTEND_DAI_MULTIMEDIA2>; }; };

&sound {
	compatible = "qcom,sm8250-sndcard";      /* or add "onyx,palma2-sndcard" to sm8250.c (1 line) */
	model = "Onyx Palma 2";
	aux-devs = <&speaker_amp>, <&audio_sel>, <&audio_mute>;
	audio-routing =
		"Speaker IN", "HPHL",   /* GUESS: or "AUX" / "EAR" – check mixer_paths */
		"Speaker", "Speaker OUT";
	mm1-dai-link { link-name = "MultiMedia1"; cpu { sound-dai = <&q6asmdai MSM_FRONTEND_DAI_MULTIMEDIA1>; }; };
	mm2-dai-link { link-name = "MultiMedia2"; cpu { sound-dai = <&q6asmdai MSM_FRONTEND_DAI_MULTIMEDIA2>; }; };
	wcd-playback-dai-link {
		link-name = "WCD Playback";
		cpu      { sound-dai = <&q6afedai RX_CODEC_DMA_RX_0>; };
		codec    { sound-dai = <&wcd937x 0>, <&swr_rx 0>, <&rxmacro 0>; };
		platform { sound-dai = <&q6routing>; };
	};
	wcd-capture-dai-link {                    /* only if a mic exists (GUESS: AMIC via WCD937x) */
		link-name = "WCD Capture";
		cpu      { sound-dai = <&q6afedai TX_CODEC_DMA_TX_3>; };
		codec    { sound-dai = <&wcd937x 1>, <&swr_tx 0>, <&txmacro 0>; };
		platform { sound-dai = <&q6routing>; };
	};
};
```
Note that `sm8250.c` routes CODEC_DMA links through `qcom_snd_sdw_*`, so the
stream setup is already handled.

**A6. Firmware for the PA.** The driver wants `aw87390_acf.bin`; stock has
`awinic/aw87xxx_acf.bin` in `/vendor/firmware` (**not** in our `port/firmware/stock/` yet).
Install it as `/lib/firmware/aw87390_acf.bin` (root, no subdir). Mainline
`aw88395_dev_load_acf_check` accepts ACF hdr v1, and the stock file parsed as
"v_0_0_0_1" → **probably compatible (GUESS)**. If the parse fails, fall back to the
anbernic-style hard-coded register init (patch).

**A7. UCM.** `alsa-ucm-conf-qcom-sm6350` (sm6350-mainline) only covers FP4 and Sony.
Write a device UCM `ucm2/Qualcomm/sm6350/OnyxPalma2/HiFi.conf` + `ucm2/conf.d/sm8250/Onyx Palma 2.conf`
(the card driver name is "sm8250" unless we add our own compatible). Minimal Speaker
EnableSequence (control names to be verified with `amixer -c0 contents`):
```
cset "name='MultiMedia1 Mixer RX_CODEC_DMA_RX_0' 1"
cset "name='RX_CODEC_DMA_RX_0 Audio Mixer MultiMedia1' 1"
cset "name='RX_MACRO RX0 MUX' AIF1_PB"
cset "name='RX INT0_1 MIX1 INP0' RX0"
cset "name='RX INT0 DEM MUX' CLSH_DSM_OUT"
cset "name='HPHL_RDAC Switch' 1"
cset "name='HPHL Switch' 1"
cset "name='HPHL Volume' 18"
cset "name='Out Switch Mux' Speaker"
cset "name='Speaker AW87390 Profile Set' Music"
```
Add a wireplumber `52-onyx-palma2.conf` that forces `S16LE`/`S32LE` (like FP4) if q6asm
rejects the default format.

**A8. USB-C audio**
- *Digital* USB-C dongles: `snd-usb-audio` is already `=m`. This works once dwc3 can be
  a host. **Blocker:** our `usb_1_dwc3` is gadget-only ("stage 1"). It needs a
  role switch from the PMIC Type-C block (`CONFIG_TYPEC_QCOM_PMIC=y` is set; pm7250b
  typec node + `usb-role-switch`). This is independent of the ADSP and is the cheapest
  USB-C audio win.
- *Analog* USB-C headset (FSA4480 + WCD937x MBHC + Type-C audio-accessory mode):
  `TYPEC_MUX_FSA4480` plus `mode-switch`/`orientation-switch` wiring to the pm7250b
  typec port, plus `qcom,mbhc-*` in wcd937x. Defer: high effort and rarely used on an
  e-reader.
  FSA4480 node for later: `&i2c10 { typec-mux@42 { compatible = "fcs,fsa4480"; reg = <0x42>; vcc-supply = <&vreg_l2a>; mode-switch; orientation-switch; ... }; }`, enable pin gpio85 (active-low, `fsa_usbc_ana_en_n`).

### 1.4 Blockers and risks (audio)
1. sm6350 bolero/macros: no upstream support. sm8250 compatibles are a guess. Watch for
   va codec version and differing register defaults. *Medium risk.*
2. SoundWire port parameters for WCD937x on v1.5.1. *Medium risk, the most likely time sink.*
3. The output that feeds the PA and the FSA2275 polarity are unknown → need stock
   `mixer_paths*.xml`. *Low risk once the file is extracted.*
4. AW87390 ACF compatibility of the stock blob. *Low–medium risk.*
5. q6afe needs `CODEC_DMA` support in the stock ADSP. That is fine: stock uses
   `msm-dai-cdc-dma-dev.45104` (=RX_CODEC_DMA_RX_0).

Effort: ADSP 0.5 d + DT/config 1–2 d + SoundWire/macro debug 2–5 d + UCM 0.5–1 d
≈ **4–8 working days** for the speaker. USB-C digital audio follows from the Type-C
role-switch work (1–2 d). USB-C analog: +3–5 d (defer).

### 1.5 Stock files to extract (audio)
From `vendor_a` (super image, via `out/eink-research/mk.sh` + debugfs/7z, or from the
device's untouched vendor partition):
- `/vendor/firmware/awinic/aw87xxx_acf.bin` → `aw87390_acf.bin` (**required**)
- `/vendor/etc/mixer_paths*.xml` (lagoon QRD/onyx variant): **required to resolve
  the GUESSes** (PA source output, FSA2275 GPIO use is in the Onyx kernel driver, but
  mixer_paths shows the WCD path for "speaker")
- `/vendor/etc/audio_platform_info*.xml` (optional, for the backend ↔ device mapping)
- ACDB (`/vendor/etc/acdbdata/`) is **not** needed. Mainline q6asm/afe run without
  calibration, and FP4 strips acdb too.

---

## 2. Accelerometer / orientation

### 2.1 Facts
- Stock Android DT has **no accelerometer on any AP I2C bus**. The sensor HAL is
  `vendor.sensors` (QTI SEE), and `fastrpc` has `qcom,fastrpc-adsp-sensors-pdr`
  (live.dts 9256–9258) → sensors are **SSC on the ADSP sensors PD**, behind the ADSP's
  own QUP. Linux can't reach the chip directly. (`qcom,qmi-sensors` in live.dts is
  the *thermal* QMI TS, unrelated.)
- ADSP image (`adsp.b*`) contains only two physical-sensor drivers: **`sns_lsm6dst`**
  (ST LSM6DST 6-axis IMU, accel+gyro) and **`sns_stk3x3x`** (Sensortek ALS/prox),
  plus registry keys `lsm6dst_0_platform.{orient,placement,accel.fac_cal,...}`.
  The QTI reference build ships dozens of drivers, so this trimmed list points to an
  OEM-customised image → **accelerometer = ST LSM6DST** (strong inference, confirm via
  registry JSON). Whether stk3x3x is physically fitted is a **GUESS** (e-reader, likely not).
- FP4 (same SoC/firmware family) uses exactly the planned stack:
  `hexagonrpcd` (adsp sensorspd) + `libssc` + `iio-sensor-proxy` (ssc backend), plus a
  udev `ACCEL_MOUNT_MATRIX` on `fastrpc-*`. The FP4 device package depends on
  `hexagonrpcd>=0.3.2-r3`. The firmware package installs `hexagonfs/` to
  `/usr/share/qcom/sm7225/Fairphone/fp4/` (with `acdb/` and `dsp/` removed).

→ **Path: hexagonrpcd + libssc + iio-sensor-proxy, as on FP4.** The kernel
`st_lsm6dsx` driver (`IIO_ST_LSM6DSX`, not set) does not help, because the bus is
SSC-owned.

### 2.2 Ordered steps
**S1.** ADSP up (section 0) with `adsps.jsn` present (sensors PD service locator)
and the fastrpc node enabled (comes with `&adsp`). Check that `/dev/fastrpc-adsp` and
`/dev/fastrpc-adsp-secure` exist.

**S2. hexagonfs tree** at `/usr/share/qcom/sm6350/Onyx/palma2/` (the hexagonrpcd
convention is `SOC/Vendor/device`):
```
sensors/config/           <- /vendor/etc/sensors/config/*.json   (lagoon_lsm6dst_0.json, lagoon_stk3x3x_0.json?, sns_*.json …)
sensors/registry/registry <- /mnt/vendor/persist/sensors/registry/registry/  (persist partition)
sensors/sns_reg.conf      <- /vendor/etc/sensors/sns_reg_config
socinfo/                  <- as in the FP4 package (static copy of /sys/devices/soc0 fields hexagonrpcd serves)
```
Plus `/vendor/etc/sensors/hals.conf` for reference only.
`sensors/registry` must come from **persist** (factory accel calibration, placement).
That partition is in the iCloud EDL backup (lun0), not in `backup/` locally. It is
small, so extract it alone (or read it from the device's untouched persist partition, ro).

**S3. Packages** (Alpine/pmOS edge): `hexagonrpcd`, `hexagonrpcd-openrc` or the
`msm-firmware-loader-hexagonrpcd-systemd` units, `libssc`, `iio-sensor-proxy`
(pmOS builds it with the ssc backend), `qrtr`/`pd-mapper` (already present for the modem).
Service: `hexagonrpcd -f /dev/fastrpc-adsp -d adsp -s -R /usr/share/qcom/sm6350/Onyx/palma2`
(the `-s` = sensors PD variant, cf. `hexagonrpcd-adsp-sensorspd.service`).
Also run the rootpd instance (without `-s`) if the sensors PD needs it to attach (FP4 runs both).

**S4. Mount matrix** udev rule (device package), placeholder:
```
SUBSYSTEM=="misc", KERNEL=="fastrpc-*", ENV{ACCEL_MOUNT_MATRIX}+="1, 0, 0; 0, 1, 0; 0, 0, 1"
```
Then fix it empirically with `ssccli`/`monitor-sensor`: hold the device portrait, which
should read +9.8 on Y. Note that libssc already applies the registry `placement`,
so the matrix may stay identity (FP4 needs -1,-1,-1).

**S5. Verify**: `ssccli -s accelerometer` (from libssc) → `monitor-sensor` shows
"Accelerometer orientation changed: normal" → the compositor rotates. For e-ink, decide
whether auto-rotate is wanted at all.

### 2.3 Blockers and risks (sensors)
1. Registry and config files are not yet extracted (vendor + **persist**). *Required, low risk.*
2. hexagonrpcd may ask for files not provided (logs show missing paths). Add them
   iteratively. FP4 shows SM6350 needs no `dsp/` skel libs. *Low–medium risk.*
3. OEM ADSP image: the sensors PD may expect Onyx-specific registry paths. The
   registry keys seen are standard (`lsm6dst_0_platform.*`). *Low risk.*
4. If ADSP audio PD and sensors PD both work on FP4 with the same firmware family,
   no kernel work is expected. *Kernel risk: very low.*

Effort: **1–3 working days** (mostly file extraction + hexagonrpcd iteration).
Can be done **before** audio, since it only needs `&adsp` enabled.

---

## 3. Recommended order
1. `&adsp` okay + copy `adsp*.jsn` → verify ADSP/APR/fastrpc (0.5 d).
2. Extract from stock: vendor `etc/sensors/**`, `etc/mixer_paths*.xml`,
   `firmware/awinic/aw87xxx_acf.bin`; persist `sensors/registry/**`. Put them under
   `port/firmware/stock/vendor_a/…` and `port/firmware/stock/persist/…`.
3. Sensors: hexagonfs tree + hexagonrpcd + libssc + iio-sensor-proxy (1–3 d).
4. Audio: config (A1) → macro compat (A2) → macros/SoundWire DT (A3) → WCD937x (A4)
   → `amixer` path test to HPH/AUX with the PA forced on → card + AW87390 + mux (A5/A6)
   → UCM (A7) (4–8 d).
5. Later: Type-C role switch (USB host → USB audio dongles), then FSA4480 analog (deferred).

Packaging: add a `firmware-onyx-palma2` package with subpackages `-adsp` (mdt/bNN + jsn),
`-audio` (aw87390_acf.bin) and `-hexagonfs`, following `firmware-fairphone-fp4`. The
device package then depends on `hexagonrpcd`, `alsa-ucm-conf` (own UCM) and ships the
`81-libssc-onyx-palma2.rules` udev rule.
