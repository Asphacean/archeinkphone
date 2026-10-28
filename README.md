# archeinkphone — native Linux on the Boox Palma 2

postmarketOS + mainline Linux port for the **Onyx Boox Palma 2** (Qualcomm SM6350 "lagoon", 6.13" e-ink panel driven by a
Lattice CertusPro-NX FPGA TCON over MIPI DSI).

Status, findings and the running log are in [`PLAN.md`](PLAN.md) (Russian).

| Path | What |
|---|---|
| `port/sm6350-onyx-palma2.dts` | device tree |
| `port/pmaports/` | kernel patches (e-ink TCON panel driver, DPU tweaks, charger) and the `device-onyx-palma2` package |
| `port/overlay/` | userspace: e-ink refresh profiles, front light, contrast, sleep, Plasma Mobile / Phosh / Sxmo configs |
| `port/research/`, `port/*.md`, `recon/` | hardware and reverse-engineering notes |
| `tools/` | EDL flashing / backup, register dump and TCON helpers |

No vendor firmware, stock partition images or decompiled vendor code are included: extract them from your own device
(see `tools/edl_backup.sh`). EDL tooling is [bkerler/edl](https://github.com/bkerler/edl) (clone into `tools/edl`);
the firehose programmer is device-specific and not redistributed.

Flashing replaces the stock boot image; keep a full EDL backup first. No warranty.
