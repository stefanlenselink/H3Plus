[<< Index](Findings.md)

## 15. Reference Links

### Core JieLi reverse-engineering ecosystem (kagaimiq)

| Repo | Why it matters |
|---|---|
| <https://github.com/kagaimiq/jl-uboot-tool> | **The most important one.** Implements the USB/UART bootloader protocol, `jltech/cipher.py` (the ENC cipher), `jltech/crc.py`, `jltech/uboot.py`. Can dump and write raw flash, and read the chipkey. |
| <https://github.com/kagaimiq/jl-misctools> | Firmware/package utilities — check here first for an existing `ufw` unpacker. |
| <https://github.com/kagaimiq/jielie> | Chip documentation, memory maps, `pi32` architecture notes. **This repo solved the app region.** |

### The documents that broke the app-region cipher

| Document | Contribution |
|---|---|
| <https://github.com/kagaimiq/jielie/blob/main/periph/sfc.md> | ⭐ **The key.** Describes the ENC block between cache and flash, the 32-byte cache-line scrambling granularity, and the formula `key = key ^ (addr >> 2)`. |
| <https://github.com/kagaimiq/jielie/blob/main/periph/enc.md> | The ENC block registers, including `UNENC_ADR[H\|L]` which define a pass-through (unencrypted) area. |
| <https://github.com/kagaimiq/jielie/blob/main/periph/icache.md> | icache layout: BR23+ data @ `0xF8000`, tag @ `0xFC000`, 128 sets × 4 ways × 32 bytes. Confirms the 32-byte line size. |
| <https://github.com/kagaimiq/jielie/blob/main/chips/br23/memmap.md> | BR23 memory map (RAM0/RAM1, peripherals, SFC mapping at `0x1000000`). |

### Architecture / disassembly

- `pi32` (JieLi proprietary 32-bit core) — search for community Ghidra SLEIGH definitions; completeness varies. The `jielie` repo above is the best starting reference.

### Tools used

| Tool | Link |
|---|---|
| UPX (unpacking `Update App.exe`) | <https://github.com/upx/upx> |
| ILSpy (for `TIDRadioCPS.exe`) | <https://github.com/icsharpcode/ILSpy> |
| dnSpyEx (alternative .NET decompiler/debugger) | <https://github.com/dnSpyEx/dnSpy> |
| Ghidra (for `pi32` bootloader) | <https://github.com/NationalSecurityAgency/ghidra> |
| crcmod (used by jl-uboot-tool) | <https://pypi.org/project/crcmod/> |

### Related amateur-radio RE projects (for context/inspiration)

| Project | Link |
|---|---|
| chirp (codeplug programming, many radios) | <https://chirpmyradio.com/> |
| OpenGD77 (custom firmware precedent) | <https://github.com/rogerclarkmelbourne/OpenGD77> |
| OpenRTX (multi-radio open firmware) | <https://openrtx.org/> |

### Vendor

- TIDRADIO official site: <https://www.tidradio.com/>
- Firmware update server (partial string found): `https://fmup.g...` — full host not yet recovered.

---

*[<< Index](Findings.md)*
