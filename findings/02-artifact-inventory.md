[<< Index](Findings.md)

> [!NOTE]
> The folders inventoried below are **not published in this repository** — they list
> the artifacts of the original effort on the author's machine. How to acquire or
> generate each one yourself: [ARTIFACTS.md](../ARTIFACTS.md).

## 3. Artifact Inventory

### 3.1 `BIN/` — Kenwood / CH340 serial flashing images

| File | Size (dec) | Size (hex) |
|---|---|---|
| `TID-H3-PlusV1.0.32.bin` | 897024 | 0xDB000 |
| `TID-H3-PlusV1.033.bin` | 901120 | 0xDC000 |
| `TID-H3-PlusV1.0.35.bin` | 905216 | 0xDD000 |
| `TID-H3-PlusV1.0.37.bin` | 905216 | 0xDD000 |
| `TID-H3-PlusV1.0.39.bin` | 909312 | 0xDE000 |
| `TID-H3-PlusV1.0.41.bin` | 929792 | 0xE3000 |
| `TID-H3-PlusV1.0.42.bin` | 774144 | 0xBD000 |
| `TID-H3-PlusV1.0.42(1).bin` | 774144 | 0xBD000 |
| `TID-H3-PlusV1.0.43.bin` | 778240 | 0xBE000 |
| `TID-H3-PlusV1.0.44.bin` | 782336 | 0xBF000 |
| `TID-H3-PlusV1.0.45.bin` | 782336 | 0xBF000 |
| `TD-H3-PlusV1.0.50.bin` | 823296 | 0xC9000 |

Notes:
- The **drop from 0xE3000 → 0xBD000 between 1.0.41 and 1.0.42** is a large structural change (~152 KB). Worth investigating — possibly a resource/voice-prompt repack or a compression change.
- Note the naming inconsistency: `TID-H3-PlusV1.033.bin` (missing a dot) and `TD-` (not `TID-`) for 1.0.50.
- All files are `0xFF`-padded at the tail (erased-flash filler).
- **All 12 files share byte-identical first 64 bytes.**

### 3.2 `FW/` — USB-C flashing packages

12 files, sizes 827,808 – 1,220,448 bytes. All sizes end in `...f60` except 1.0.50 which is `0xCA1A0`.

Includes a version not present in `BIN/`: **`TID-H3-Plus-1.0.47.fw`**.

Observations:
- Bytes `0x00–0x03` vary per version → looks like a **checksum/CRC**.
- Bytes `0x04–0x07` are near-identical across versions (e.g. `9f 80 8f 1f`).
- Bytes `0x08+` of the header are **identical across all versions**.
- **All 12 files share a byte-identical 64-byte footer** ending with ASCII `JL_FW`.

### 3.3 `work/` — derived artifacts (created by this effort)

| Path | Description |
|---|---|
| `work/UpdateApp_unpacked.exe` | UPX-unpacked JieLi Firmware Upgrade Utility (14,513,568 bytes) |
| `work/Kenwood150/.../updata.exe` | Kenwood serial updater (15,936,000 bytes, not packed) |
| `work/CPS/TIDCPS_20260422/TIDRadioCPS.exe` | .NET CPS (636,416 bytes) |
| `work/decrypted/*.dec` | Decrypted images produced by `tools/jl_decrypt.py` |
| `work/app_region.bin` | Carved `0x5000`→EOF of v1.0.45 (761,856 bytes) |

> `BIN/` and `FW/` are kept pristine — all generated files live under `work/`.

### 3.4 `Dumps/` — hardware reads

| Path | Size | Description |
|---|---|---|
| `Dumps/dump_internal.bin` | 1,048,576 (`0x100000`) | **Full internal SPI NOR dump** from a live H3 Plus running v1.0.50. See [§12A](16-flashing-and-hardware-dump.md#12a-hardware-flash-dump--confirmed-facts). |
| `Dumps/vm_tidmic.bin` | 4,096 | VM area `0xC9000` read with the TIDRADIO PTT button paired. |
| `Dumps/vm_generic.bin` | 4,096 | VM area `0xC9000` read with a Jabra Evolve 65 paired. Diff analysed in [§9A.8](08-bluetooth-1-discovery-and-whitelist.md#9a8-vm-differential-test--negative-and-that-is-informative). |

> This file is irreplaceable brick-insurance for **that specific unit** (it contains its unique BT identity and pairing records). Back it up off-machine.

---

*[<< Index](Findings.md)*
