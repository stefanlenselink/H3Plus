[<< Index](Findings.md)

## 12. Flashing & Recovery Paths

Three independent paths exist. Having more than one is what makes this project safe to attempt.

### Path A — USB-C / USB MSC (primary)

- Device enumerates as a **USB Mass Storage volume** in bootloader mode.
- Entered by **long-pressing `8` in standby** (per 1.0.45 release notes).
- Official tool: `Update App.exe -d F -f firmware.fw -r`
- Open tool: **`jl-uboot-tool`** — supports raw flash `read` and `write`, plus chipkey read.

### Path B — Kenwood 2-pin serial via CH340

- Tool: `updata.exe`
- Flashes `.bin` files, requires the `ENCRYPT NUMBER` (`X12345678`).
- Can also reflash UBOOT itself (`checkBoxUpdateUBoot`) — powerful, and the most dangerous option available.

### Path C — Web-based upgrade

- Vendor-provided browser flasher (WebUSB/WebSerial). Same underlying protocol as A.

### Recommended first action on hardware

**Dump the flash before writing anything.** Use `jl-uboot-tool` to read the full flash to a file. That dump is simultaneously:
1. Ground truth for the real on-device memory layout (vs. the packaged image),
2. The source of the real `isd_config.ini`,
3. Your chipkey,
4. Your brick insurance.

**\u2705 This has now been done \u2014 see [\u00a712A](#12a-hardware-flash-dump--confirmed-facts).**

---

## 12A. Hardware Flash Dump — CONFIRMED FACTS

> This section supersedes speculation elsewhere in the document. Everything here was read directly off a physical H3 Plus.

### 12A.1 How it was obtained

Tool: `jl-uboot-tool` (<https://github.com/kagaimiq/jl-uboot-tool>), run on Linux:

```console
$ sudo python3 jluboottool.py
Searching for some JieLi devices..
Found a device: BR23 UBOOT1.00 (1.00) at /dev/sg2
Waiting for [/dev/sg2] try! ok (BR23 UBOOT1.00 1.00)

Chip: BR23 - AC635N/AC695N series
Running loader with argument 0x0001.
The Loader has been successfully installed.

================ Quick info ==================
  ** BR23 (AC635N/AC695N series) **
  >> Chip key: 0xF181 <<
  - Online device:
     ID: 0x856014
     Type: 0x03 (SPI NOR flash on SPI0)
==============================================

=>JL: read 0x00000000 0x100000 dump_internal.bin
Reading: 100%|██████████████████████████| 1.00M/1.00M [00:01<00:00, 648kB/s]
```

The device enumerates as a **SCSI generic device** (`/dev/sg2`) — i.e. USB Mass Storage — and the tool pushes a loader into RAM before flash access works. Output stored at `Dumps/dump_internal.bin` (1,048,576 bytes).

### 12A.2 Confirmed hardware identity

| Property | Value |
|---|---|
| Chip family string | **`BR23`** |
| Marketed part | **AC635N / AC695N series** |
| UBOOT version | `UBOOT1.00` (1.00) |
| **Chip key** | **`0xF181`** — burned, **not** blank |
| Flash device ID | `0x856014` |
| Flash type | `0x03` — SPI NOR on **SPI0** |
| Flash size | `0x100000` = **1 MiB** |

> The `0x14` capacity nibble in JEDEC ID `0x856014` decodes as 2²⁰ = 1 MiB, matching the advertised "1 MB internal storage". The advertised "128 Mb external storage" is **not** this device — it is either a second SPI part on another chip-select or simply marketing for the same die. Worth a follow-up `read` on other CS lines.

### 12A.3 `jl-uboot-tool` shell command set (as built)

```
burnchipkey   erase    exit    memdump   memread    read   write
dump          erasechip        help      memjump    memwrite      reset
```

`dump <address> [<length>]` prints to console (default 256 bytes); `read <addr> <len> <file>` writes to disk.

> ⚠️ `burnchipkey` and `erasechip` are present in this shell. **Never run them.** See [§16](20-risks-and-safety.md#16-risks-and-safety-notes).

### 12A.4 THE BIG RESULT — flash content == distributed `.bin`

Comparing the dump against every packaged image:

| Packaged file | Length | Sampled match |
|---|---|---|
| **`TD-H3-PlusV1.0.50.bin`** | 823,296 | **100.0%** |
| `TID-H3-PlusV1.0.45.bin` | 782,336 | 12.4% |
| `TID-H3-PlusV1.0.44.bin` | 782,336 | 12.4% |
| `TID-H3-PlusV1.0.43.bin` | 778,240 | 12.5% |
| `TID-H3-PlusV1.0.42.bin` | 774,144 | 12.2% |
| `TID-H3-PlusV1.0.41.bin` | 929,792 | 5.1% |
| (older) | — | ~5% |

Exact byte comparison against `TD-H3-PlusV1.0.50.bin`:

```
differing bytes: 31 of 823296
first: 0xc8fe0   last: 0xc8fff
num runs: 2
  0x0c8fe0-0x0c8ff2  (19 bytes)
  0x0c8ff4-0x0c8fff  (12 bytes)
```

**The device's flash is a byte-for-byte copy of the distributed `.bin` file**, except for 32 bytes at the very end of the image. The header matches exactly, including the `X12345678` key string:

```
dump [0x00:0x40] == bin45 [0x00:0x40] == b369bf1d302e3031 f031ac67ccadff68
                                          5831323334353637 38ffffffffffffff ...
```

#### Why this matters

1. **The unit under test is running firmware v1.0.50.**
2. **There is no write-time transform.** What you flash is what sits in flash. Any patched `.bin` lands on the chip verbatim.
3. **Therefore all file-based analysis transfers directly to hardware**, and a hardware dump can be used as ground truth for file-format work.
4. **The app-region encryption is decrypted at *execution* time, not at write time** — i.e. by the chip's hardware engine keyed on the OTP chip key, or by a software decryptor in UBOOT. This finally settles hypothesis 1 in [§9.5](07-app-region-solved.md#90-the-solution).

### 12A.5 Confirmed flash memory map

```
0x000000 ┌────────────────────────────────────────────┐
         │ UBOOT — continuous ENC LFSR, seed 0xFFFF   │  ✅ DECRYPTED
0x005000 ├────────────────────────────────────────────┤
         │ App — SFC/ENC, 32B lines, key 0xF181       │  ✅ DECRYPTED
         │   seed = 0xF181 ^ ((addr-0x5000) >> 2)     │
0x0C8FE0 ├────────────────────────────────────────────┤
         │ 32 B device-specific runtime data          │  ← 0xFF in package
0x0C9000 ├────────────────────────────────────────────┤
         │ JieLi VM / settings area — PLAINTEXT ✅     │
         │ magic 55 AA AA 55                          │
         │ BT names, pairing records, config          │
0x0CA000 ├────────────────────────────────────────────┤
         │ 0xFF erased (unused)                       │
0x100000 └────────────────────────────────────────────┘
```

Dump-wide statistics:

```
whole-file entropy : 6.9841 bits/byte    (lower than package only because of the FF tail)
index of coincid.  : 0.051548
0xFF bytes         : 232,515
low-entropy 4K blocks: 57  — at 0x4000 (3.96), 0xC8000 (4.21), 0xC9000 (1.54),
                              0xCA000+ (0.00 = erased)
repeated 16B blocks : FF×16 → 14,324 ;  00×16 → 8
```

### 12A.6 The 32 device-specific bytes at `0x0C8FE0`

Present on the device, **erased (`0xFF`) in the distributed file**:

```
dump: 04 00 00 00 00 00 00 00 00 00 01 00 00 00 00 00
      03 01 1e ff 0d 21 1c 00 67 de 8f 43 4a be 78 00
bin : ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff
      ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff
```

Written at runtime or at factory test. Candidates: BT MAC / device serial / calibration pointer / boot counter. Being immediately adjacent to the VM area and 32 bytes long (matching the 32-byte alignment signal noted in [§9.3](07-app-region-solved.md#93-historical-the-period-32-red-herring--it-was-not-a-red-herring)) makes it likely a VM header or a first-boot marker.

### 12A.7 The settings / VM area at `0x0C9000` — PLAINTEXT

This region is **not encrypted at all**. Header magic `55 AA AA 55`:

```
000c9000  55 aa aa 55 fb 68 60 00 aa 7c bb 55 1f ef e1 65  |U..U.h`..|.U...e|
000c9010  00 02 54 44 2d 48 33 2d 50 6c 75 73 2d 33 35 31  |..TD-H3-Plus-351|
000c9020  31 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  |1...............|
000c9030  00 00 92 67 00 02 54 44 2d 48 33 2d 50 6c 75 73  |...g..TD-H3-Plus|
000c9040  2d 33 35 31 31 2d 62 6c 65 00 00 00 00 00 00 00  |-3511-ble.......|
000c9050  00 00 00 00 00 00 01 68 60 00 c9 e8 0f 7a 92 d1  |.......h`....z..|
```

**Recovered Bluetooth identity:**

| Offset | Value | Meaning |
|---|---|---|
| `0x0C9012` | `TD-H3-Plus-3511` | **BR/EDR (Classic) device name** |
| `0x0C9036` | `TD-H3-Plus-3511-ble` | **BLE device name** |

Both a Classic **and** a BLE name are provisioned — consistent with the SoC running dual-mode BT 5.1. Each name record is preceded by a 2-byte tag (`00 02`) and a 16-bit item ID (`92 67`, etc.), which is the standard JieLi VM item layout.

Further in, repeating 16-byte high-entropy blobs framed by `ff ff 30 00` / `ff 0f 03 00` and item headers like `a5 51 00 02`, `b4 51 00 02`, `74 51 00 02` are almost certainly **Bluetooth link keys for paired devices** (BT link keys are exactly 16 bytes):

```
000c9280  95 38 01 00 00 00 ff ff 30 00 34 73 e2 4b 5c 74  |.8......0.4s.K\t|
000c9290  6c 5f 6a 53 6d f2 55 7e bc fc 6f 10 55 20 2a 8e  |l_jSm.U~..o.U *.|
```

A recurring `56 10 00` / `11 30 02 07 13` pattern runs through the area — likely a per-item tag/length framing or a timestamp/counter field.

#### Practical significance

The VM area being plaintext means **device configuration can be read and modified without breaking any encryption**. Changing the advertised Bluetooth names, and potentially BT behaviour flags, is a *file edit*, not a firmware patch. This is by far the most accessible modification surface found so far.

### 12A.8 Chip key `0xF181` as a plain LFSR seed — NEGATIVE (but the key was right)

The first hypothesis was that the chip key simply seeds a continuous ENC LFSR across the app region. Tested:

```
baseline (no decryption)  entropy 7.9941   zeros 231
seed 0xF181               entropy 7.9972   zeros 274
seed 0xFFFF               entropy 7.9972   zeros 273
seed 0x81F1 (byteswap)    entropy 7.9974   zeros 247
```

All statistically identical to noise. Additionally:

```
Is 0xF181 on the 0xFFFF LFSR cycle?  →  NO (not found in all 32767 states)
```

> **This result was misleading.** `0xF181` *is* the correct key — the error was assuming a **continuous** keystream. The SFC ENC block reseeds the LFSR **every 32 bytes** with `0xF181 ^ (addr >> 2)`. Once that is done, the region decrypts cleanly. See [§9.0](07-app-region-solved.md#90-the-solution).
>
> The observation that `0xF181` is not on the `0xFFFF` cycle is still true and still relevant: the ENC key is an arbitrary 16-bit seed, and the LFSR's 65536 states split into several cycles. Any seed is valid.

### 12A.9 Running code on the chip (`memread` / `memwrite` / `memjump`)

> **No longer needed for decryption** — [§9.0](07-app-region-solved.md#90-the-solution) solved the app region offline. Retained because these commands remain valuable for live experimentation.

The `jl-uboot-tool` shell exposes **`memread`**, **`memdump`**, **`memwrite`** and **`memjump`**. Useful remaining applications:

- **Verify the decryption** by reading the same region through the SFC map (addresses `0x1000000`+ per the BR23 memory map) and comparing against `work/app_dec.bin`.
- **Dump the ENC/SFCENC registers** (HSB peripherals, `0x01F0200` = SFC, `0x01F0300` = SFCENC on BR25; BR23 is similar) to confirm the key and base-address offset directly.
- **Run small `pi32` payloads** via `memwrite` + `memjump` for live experimentation.

BR23 memory map highlights (from `kagaimiq/jielie`):

```
0x0000000 - 0x002BFFF   176k  RAM0
0x002C000 - 0x002FFFF    16k  RAM1 (non-volatile)
0x00FC000 - 0x00FDBFF     7k  icache tag
0x0100000 - 0x010FFFF    64k  Core peripherals
0x0110000 - 0x0117FFF    32k  MaskROM
0x01E0000 - 0x01EFFFF    64k  LSB peripherals
0x01F0000 - 0x01FFFFF    64k  HSB peripherals  (SFC, SFCENC live here)
0x0800000 - 0x0FFFFFF     8M  PSRAM mapping
0x1000000 - 0x1FFFFFF    16M  SFC (flash) mapping
```

BR23 = **pi32v2** core, 208k SRAM total, 16k icache.

---

*[<< Index](Findings.md)*
