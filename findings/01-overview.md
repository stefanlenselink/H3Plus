[<< Index](Findings.md)

## 1. Executive Summary

**Question asked:** *Is it possible to reverse engineer the firmware or make changes to the existing firmware?*

**Answer: Yes.** The device is built on a **JieLi (杰理 / Zhuhai Jieli Technology)** Bluetooth SoC, a platform with a mature open-source reverse-engineering ecosystem. The firmware's outer encryption layer is a **16-bit LFSR stream cipher that is cryptographically trivial and has been fully broken** in this session.

Concrete progress:

| Milestone | Status |
|---|---|
| Identify SoC vendor | ✅ JieLi, via `JL_FW` magic |
| **Confirm exact chip** | ✅ **BR23 = AC635N/AC695N series** (read from hardware) |
| **Recover chip key** | ✅ **`0xF181`** (read from hardware; key is burned, not blank) |
| **Dump device flash** | ✅ 1 MB SPI NOR, ID `0x856014` on SPI0 |
| **Confirm flash == package** | ✅ Byte-identical to `TD-H3-PlusV1.0.50.bin` except 32 bytes |
| Identify cipher | ✅ JieLi "ENC" LFSR, poly `0x1021` |
| Recover key/phase | ✅ Phase 32591 (`.bin`), 31567 (`.fw`) |
| Decrypt bootloader (`0x0000–0x4FFF`) | ✅ Readable strings + code |
| Map `.bin` vs `.fw` relationship | ✅ `.fw` = 0x400 header + same payload + 64B trailer |
| Unpack official JieLi updater | ✅ UPX-unpacked, symbols extracted |
| Extract flashing protocol strings | ✅ From `updata.exe` |
| **Locate settings/VM area** | ✅ `0xC9000`+, **plaintext**, BT names readable |
| **Decrypt app region (`0x5000`+)** | ✅ **SOLVED — SFC/ENC hardware scrambler, key `0xF181`** |
| **Confirm BT mic (HFP) support** | ✅ **Already present in firmware** — see [§9A](08-bluetooth-1-discovery-and-whitelist.md#9a-bluetooth-hfp--microphone-support--confirmed) |
| **⭐ Radio key → transmit from a generic BT headset mic** | ✅ **HARDWARE-CONFIRMED on PF1 and PF2** (5-byte patch) — see [§9A.44](13-bluetooth-6-key-remap-milestones.md#9a44--milestone-a-radio-key-transmits-the-bt-headset-mic--hardware-confirmed) |
| **⭐ Main PTT → transmit from BT headset mic, radio mic when BT is off** | ✅ **HARDWARE-CONFIRMED** (3-byte patch, `--PTT=BT-PTT`) — see [§9A.46](13-bluetooth-6-key-remap-milestones.md#9a46-main-ptt-as-the-bt-mic-ptt--hardware-confirmed) |
| PF menu options "PTT" (radio mic) / "BT PTT", configurable mapping | 🔶 Built, untested (`--PTT2=` / `--OD-PTT=`, **all 12 pairs of distinct actions** via direct body rewrite) — see [§9A.47](13-bluetooth-6-key-remap-milestones.md#9a47-pf-menu-options-ptt-and-bt-ptt---pf-menu-and-new-tool-defaults), [§9A.48](13-bluetooth-6-key-remap-milestones.md#9a48-configurable---pf-menu-mapping-both--ptt--btptt--swap), [§9A.49](13-bluetooth-6-key-remap-milestones.md#9a49-end-user-cli-redesign---bluetooth-mode---ptt---ptt2---od-ptt), [§9A.50](13-bluetooth-6-key-remap-milestones.md#9a50-direct-body-rewrite-all-12---ptt2----od-ptt-pairs) |
| Parse `ufw` file table | 🔶 Not located yet |
| Decompile CPS (`.NET`) | ❌ Not started |

**Key enabling discovery for patching:** the app-region encryption is **position-deterministic** — identical plaintext at an identical offset produces identical ciphertext, with no chaining or nonce. This is proven by a 57.7% byte-identical diff between v1.0.44 and v1.0.45 including a **22,863-byte contiguous identical run**. Targeted binary patching is therefore viable even without full key recovery.

**Second key discovery (hardware):** the on-device flash is a **byte-for-byte copy of the distributed `.bin` file**. There is no additional on-chip transform applied at write time, so everything learned from the files applies directly to the hardware — and vice versa. See [§12A](16-flashing-and-hardware-dump.md#12a-hardware-flash-dump--confirmed-facts).

**Third key discovery — the app region is broken.** It is descrambled by the **SFC ENC hardware block** using a per-32-byte-cache-line LFSR reseeded with `chipkey ^ (addr >> 2)`. With `chipkey = 0xF181` the whole app decrypts. See [§9](07-app-region-solved.md#9-the-app-region--solved).

---

## 2. Target Device

**TIDRADIO H3 Plus** handheld transceiver.

| Attribute | Value | Source |
|---|---|---|
| **SoC** | **JieLi BR23 — AC635N / AC695N series** | ✅ read from hardware |
| **SoC chip key** | **`0xF181`** (burned) | ✅ read from hardware |
| **RF transceiver** | **Beken BK4819** | CPS symbols `DEBUG_BK4819_*`, `BK4819CfgDT` |
| CPU | 240 MHz, `pi32` core | vendor spec + JieLi arch |
| **Internal flash** | **1 MiB SPI NOR on SPI0, JEDEC ID `0x856014`** | ✅ read from hardware |
| External storage | 128 Mb (16 MB SPI flash) — *not located in the dump* | vendor spec |
| Bluetooth | 5.1 — BR/EDR + BLE (both names provisioned) | ✅ VM area `0x0C9000` |
| Programming | USB Type-C (also Kenwood 2-pin via CH340) | — |
| Firmware upgrade | Web-based (WebUSB/WebSerial) + desktop tooling | — |
| TX/RX bands | 136–173.975 MHz, 350–399.975 MHz, 400–469.975 MHz, 470–529 MHz | vendor spec |
| Variants | GMRS, HAM, "Normal" | CPS `.td` templates |

> **The Beken BK4819 is a major find.** It is the exact RF transceiver used in the **Quansheng UV-K5**, which has a large, mature open-source firmware community. All BK4819 register documentation, band/PA/squelch/modulation tricks and DSP techniques from that ecosystem apply directly to the H3 Plus's radio front-end. See [§15](19-reference-links.md#15-reference-links).

The GMRS / HAM / Normal split is served by the **same firmware image** with different codeplug templates (see [§11.3](15-official-tooling.md#113-tidradiocpsexe--net-cps)). This strongly implies band restrictions are **configuration-driven, not code-driven** — the cheapest route to unlocking TX coverage is the codeplug, not the firmware.

Firmware 1.0.45 release notes mention **"long-press 8 in standby to enter USB upgrade mode"** — a useful recovery entry point.

---

*[<< Index](Findings.md)*
