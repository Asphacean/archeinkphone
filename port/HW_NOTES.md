# Palma 2 secondary HW notes (power / wireless / firmware)
Fragment: port/dts-fragments/onyx-palma2-power-wireless.dtsi (unbuilt, untested). FP4 ref: port/ref/sm7225-fairphone-fp4.dts.
Stock evidence: recon/root/live.dts, recon/root/dmesg.txt, recon/getprop.txt.

## 1. Battery / charger / fuel gauge (pm7250b)
- Stock (live.dts 7865-8135): fuel gauge `pm7250b_qg` = `qcom,qpnp-qg` (qgauge@4800, sdam@b100, io-channels bat_therm 0x4a, bat_id 0x4b);
  charger `pm7250b_charger` = `qcom,qpnp-smb5` (+ smb1396 div2 charge pumps @I2C 0x34/0x35, smb1398 @0x36). Vendor-only drivers.
- Battery profile (live.dts 19320): "7381805_Onyx_Note6_3950mAh_PM7250B", max 4.45 V, fastchg 2000 mA, batt-id 68k, beta 3440, term 150 mA.
  (sub-node name says 4030mAh, type string says 3950mAh: capacity unresolved.)
- Mainline: FP4 has NO charger/fg node, only pm7250b_typec/vbus (FP4 L935-982, comment "without charger driver"). Kernel has no qpnp-qg/smb5
  driver (qcom_pmi8998_charger = smb2, qcom_fg = pmi8998 FG gen3; neither is compatible per my knowledge, NOT verified online).
  => capacity readout and charge status are NOT achievable by DT alone. Options: port QG driver (large), or read vph/vbat via pm7250b ADC
  (vbat_sns@0x84 / vph_pwr@0x83 exist in stock, add if needed) and estimate SoC from voltage in userspace.
- Charging itself: stock dmesg shows PMIC hardware APSD works (SDP detected); hardware charging should proceed with default PMIC settings,
  but JEITA/termination are vendor-driver-controlled -> do not leave unattended on mainline until verified.
- Fragment adds: pm7250b ADC channels (4d charger_skin_therm, 4f conn_therm from FP4; 4a bat_therm, 4b bat_id from stock) and a simple-battery
  stub with stock numbers (4.45 V, 2 A, 150 mA). The 4b mapping to ADC5_AMUX_GPIO2_100K_PU is GUESSED from the number; verify header value.

## 1b. pmk8350 ADC ("no channels defined")
- Fix = FP4 L1003-1017 (xo_therm channel@644, PMK8350_ADC7_AMUX_THM1_100K_PU) + adc_tm xo-therm@0 (L984-993). Stock pmk8350_vadc has
  die_temp@603, ref_gnd@600, xo_therm@644, vref_1p25@601 -> same. Confirmed. die_temp channel added optional (header constant PMK8350_ADC7_DIE_TEMP
  is assumed to exist; drop if dtc complains). FP4 thermal-zones (xo-thermal etc.) not copied; add after sensors work.
- pm6150l adc (FP4 L761-897: msm_therm, rear-cam, pa0/pa1 etc.) is board-specific to FP4; NOT copied, Palma 2 stock pm6150l channels not mapped.

## 2. WiFi / Bluetooth
- Stock: `qca,wcn3990` bluetooth node (live.dts 9234), `qcom,icnss@18800000` WLAN (15406), `qca_cld3_wlan.ko` (qcom CLD3 vendor driver),
  btfm slimbus codec "wcn3990". Reserved mem wlan_fw_region@8b500000 (2 MB) = same as sm6350.dtsi wifi/wlan_fw_mem. "bt-chip-pwd not provided" => no BT enable GPIO.
- FP4 uses WCN3988 (WCN399x family): ath10k-snoc `&wifi` (FP4 L1263-1270) + `uart1` bluetooth `qcom,wcn3988-bt` (L1186-1207). Same chip family,
  same SoC, same uart1 (stock serial@884000, wake IRQ GPIO64, sw-ctrl GPIO69 = FP4 values). So the FP4 nodes are copied verbatim.
  CONFIRMED: family/buses/GPIOs. GUESSED: supply rail mapping (stock regulator phandles 0x19-0x1c,0xba,0xbb were not resolved to rail names),
  and 3988 vs 3990 variant (try `qcom,wcn3990-bt` if hci_qca fails to match; firmware crnv/apnv file naming tells which).
- Kernel config: CONFIG_ATH10K, ATH10K_SNOC, BT_HCIUART, BT_HCIUART_QCA, SERIAL_QCOM_GENI, QCOM_Q6V5_MSS/ADSP/PAS(mss, wcss not needed). Check recon/config.gz is stock only.
- Firmware: ath10k wants `ath10k/WCN3990/hw1.0/{firmware-5.bin,board-2.bin}` (linux-firmware; board data for Palma 2 NOT in linux-firmware;
  stock has bdwlan.* + wlanmdsp.mbn in modem_a image/). ath10k WCN3990 runs on modem-side firmware wlanmdsp.mbn: FP4 pmOS ships
  `qcom/sm7225/fairphone4/wlanmdsp.mbn` and ath10k `firmware-name` is not needed; `qcom,calibration-variant` selects board-2.bin entry.
  Needs a board-2.bin built from Palma 2 bdwlan.bin (ath10k-bdencoder), else expect "board data not found".
- BT firmware: hci_qca loads `qca/crnv32.bin|apnv...` and `crbtfw*.tlv` names; stock has apbtfw10/11.tlv, apnv10/11.bin, crbtfw11/20/21.tlv, crnv11.bin
  in bluetooth_a. Linux-firmware qca/ has generic crbtfw21.tlv/crnv21.bin; the board-specific NV may need copying.

## 3. Remoteproc firmware (stock partitions in backup/edl-2026-10-25/lun4, listable with 7z)
- FP4 paths: adsp.mbn, cdsp.mbn, modem.mbn, ipa_fws.mbn, a615_zap.mbn under `qcom/sm7225/fairphone4/` (FP4 L292,595,757,714,612).
  Palma 2 DTS fragment uses `qcom/sm6350/onyx/palma2/*` (invented install dir, change as preferred).
- modem_a.bin (FAT, /vendor/firmware_mnt, image/): modem.mdt+modem.b00..b20 (21), adsp.mdt+b00..b33, cdsp.mdt+b*, venus.mdt, npu.mdt,
  wlanmdsp.mbn, bdwlan.*/regdb.bin, qwes/rtic/widevine.mbn, *.jsn. => ADSP/CDSP/MPSS firmware can be taken from here (dated 2024-08-20).
- dsp_a.bin (ext4, /vendor/dsp): adsp/ cdsp/ dirs (FastRPC userspace libs, NOT remoteproc images).
- bluetooth_a.bin (FAT, /vendor/bt_firmware): apbtfw/crbtfw .tlv, apnv/crnv .bin.
- qupfw_a (0x14000) = QUP firmware, not needed on mainline-tz setups unless GENI fails to load.
- NOT found: ipa_fws, a615_zap.* in modem_a (stock loads a615_zap.mdt/.b02 via ueventd => lives in /vendor/firmware inside super.bin).
  super.bin (6 GB sparse/raw dynamic partition) not unpacked: no lpunpack/simg2img here. Unverified.
- Convert split mdt+bNN to .mbn: `pil-squasher adsp.mbn adsp.mdt` (needs all bNN beside the .mdt). Mainline needs signature-valid blobs; stock
  ones are signed for this device, so OK. Bootloader orange / secure boot interplay with TZ loading is untested.
- Stock reserved memory (adsp 0x88d00000.., cdsp 0x86f00000 size 0x1e00000, wlan_fw 0x8b500000) matches SM6350 layout; FP4's sm6350.dtsi reservations
  should be correct but check mpss/ipa regions against live.dts reserved-memory.

## Open items
1. Port or stub QG fuel gauge; 2. resolve stock supply phandles; 3. extract vendor/ from super.bin for a615_zap + ipa_fws;
4. build board-2.bin; 5. verify ADC5 header constant for bat_id.
