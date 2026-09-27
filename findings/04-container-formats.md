[<< Index](Findings.md)

## 5. Container Formats

### 5.1 `.bin` header (offsets `0x00–0x3F`)

Byte-identical across **all 12** BIN files:

```
00000000  b3 69 bf 1d 30 2e 30 31  f0 31 ac 67 cc ad ff 68  |.i..0.01.1.g...h|
00000010  58 31 32 33 34 35 36 37  38 ff ff ff ff ff ff ff  |X12345678.......|
00000020  1e 5a 6e c5 bf 3e 7c f8  e0 84 a3 67 ce bd 5b 97  |.Zn..>|....g..[.|
00000030  7a 7c 53 17 a5 ad 45 21  f3 6d 13 d9 b3 67 cf 9f  |z|S...E!.m...g..|
```

Interpretation:

| Offset | Len | Value | Meaning |
|---|---|---|---|
| `0x00` | 4 | `b3 69 bf 1d` | Magic |
| `0x04` | 4 | `"0.01"` | Format version string (ASCII) |
| `0x08` | 8 | `f0 31 ac 67 cc ad ff 68` | Unknown (possibly CRC / chip ID) |
| `0x10` | 9 | `"X12345678"` | **Key string** — matches the `ENCRYPT NUMBER` field in `updata.exe` |
| `0x19` | 7 | `FF` × 7 | Padding to `0x20` |
| `0x20` | 32 | ciphertext | Start of encrypted region |

The `X12345678` string is the single most important lead for the app-region crypto — it is almost certainly the input to `jl_crypto::decode_key` / `jl_key::byteArrayDataToKey`, producing the 16-bit chipkey.

### 5.2 `.fw` package

```
┌──────────────────────────────┐ 0x00000
│ Package header (0x400 bytes) │   bytes 0-3 = per-version checksum
│                              │   bytes 8+  = identical across versions
├──────────────────────────────┤ 0x00400
│                              │
│ Payload — identical to .bin  │   .fw offset = .bin offset + 0x400
│                              │
├──────────────────────────────┤ EOF-0x40
│ 64-byte trailer, ends JL_FW  │   identical across all versions
└──────────────────────────────┘ EOF
```

**Proof of the `0x400` offset:** the bootloader banner `******************BootLoader*****************` appears at `0x41E0` in the decrypted `.fw` and at `0x3DE0` in the decrypted `.bin`. Difference = exactly `0x400`. Independently confirmed by the LFSR phase difference: `32591 − 31567 = 1024 = 0x400`.

### 5.3 The `ufw` file table — NOT YET LOCATED

Expected members, per symbols in the updater:

```
isd_config.ini      uboot.boot          uboot.part
uboot_head.part     uboot_data.part     app.bin
```

Plus flags/tokens: `UBOOT_HEAD_ALIGN`, `TRIPLE_UBOOT`, `uboot1.00`, `uboot2.00`, `AU_KEY`, `V2_AU_KEY`, `AC4600 New Key`, `AC104N`, `EXTRA_CFG_PARAM/SERIAL_SEND_KEY`.

**Attempt made:** decrypted `.fw` bytes `0x000–0x200` using phase 31567 and hexdumped. Result showed **no ASCII filenames and no table structure**. Worse, the output itself contains LFSR-like runs (`34 68 f1 e2 c4 88 10 01 23 46 8c 18`, `83 06 0c`, `11 03 06 2d`), which is the classic signature of **double-XOR** — i.e. we applied keystream to a region that either was already plaintext or uses a different phase.

**Conclusion:** the package header at `0x000–0x3FF` is *not* covered by the same continuous keystream as the payload. It is either plaintext, separately encrypted, or the table lives elsewhere. The symbol **`jl_fw::hasTailInfo`** hints that metadata may be stored in the **trailer**, not the header — this is the most promising next lead.

---

*[<< Index](Findings.md)*
