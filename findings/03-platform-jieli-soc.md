[<< Index](Findings.md)

## 4. Platform Identification — JieLi SoC

### 4.1 The decisive evidence

Every `.fw` file ends with a 64-byte trailer whose final magic is the ASCII string **`JL_FW`**:

```
00000030  3d 9a 13 92 65 36 73 42  00 00 00 00 00 00 00 00
00000040  4a 4c 5f 46 57 00 00 00  00 00 00 00 00 00 00 00   |JL_FW...........|
```

`JL` = **JieLi** (杰理). Corroborating evidence:

- The unpacked updater contains the class names `jl_fw::package`, `jl_format_ufw`, `jl_crypto::decode_key`, `jl_key::getMappingKey`.
- The decrypted bootloader contains JieLi SDK-specific symbols: `jlfs_check_all_head`, `jlfs_dual_bank_check`, `uboot_zone`, `isd_config.ini`.
- The `@JLUA` string appears in the USB descriptor area.
- The hardware spec (240 MHz + BT 5.1 BR/EDR/BLE + integrated flash) matches the **AC69xx / AD69xx** family.

### 4.2 Why this matters enormously

JieLi chips are the silicon inside countless cheap TWS earbuds, MP3 players and BT speakers. As a result there is a **substantial existing open-source RE ecosystem** — most importantly `kagaimiq`'s toolchain, which already implements the cipher, the CRCs, and the USB bootloader protocol. We are not starting from zero.

### 4.3 CPU architecture

**CONFIRMED BY HARDWARE READ:** the chip reports as **`BR23`**, which `jl-uboot-tool` maps to the **AC635N / AC695N series**. This supersedes the earlier AC69xx/AD69xx guess — AC695N is in that family, so the guess was close.

These parts use JieLi's in-house **`pi32`** core (a MIPS-like/proprietary 32-bit RISC ISA). This remains the main obstacle to full static analysis — Ghidra/IDA have no stock `pi32` processor module. Community SLEIGH definitions exist in varying states of completeness.

Knowing it is specifically **BR23/AC635N/AC695N** is a significant narrowing: it is a very common TWS-earbud/BT-audio part, so SDK headers, memory maps and community notes for it are comparatively easy to find.

---

*[<< Index](Findings.md)*
