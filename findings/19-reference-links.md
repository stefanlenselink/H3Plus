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

### Official SDK, toolchain and packagers (added 2026-09-30, see [Ch. 24](24-jieli-ecosystem-sdk-toolchain.md))

| Resource | Why it matters |
|---|---|
| <https://github.com/JieLi-IC/fw-AC63_BT_SDK> | ⭐ **The right SDK** — `cpu/br23` = AC635N: registers (`br23.h` SFCENC), `isd_config_rule.c` (our config's generator), btstack/btctrler libs with 1拖2 multipoint APIs, AC635N datasheets in `doc/`. |
| <https://github.com/JieLi-IC/fw-AC630N_BT_SDK> | Older SDK — `cpu/bd29` only (q32s core). Wrong architecture for us; kept for contrast. |
| Official Linux toolchain (JieLi download, `jieli-linux-toolchains-*`) | LLVM 4.0.1 clang/ld/objdump with **pi32v2 (`-mcpu=r3`) backend** — validated our disassembler; raw-image disassembly recipe in [Ch. 24 §24.5](24-jieli-ecosystem-sdk-toolchain.md#245-official-toolchain--our-disassembler-validated-byte-exactly). |
| Official post-build tools (`jieli-linux-post-build-tools-*`) | `ufw_maker`, `fw_add`, `isd_download`, `packres`, `fat_comm` — produced the `.ufw` table decode that closed the ch. 04 open question. |
| <https://github.com/kagaimiq/fw-Bootloader> | Open reimplementation + AA55 upgrade-protocol spec (cmds `0xC0`–`0xCA` incl. `EX_KEY`). |
| <https://github.com/kagaimiq/jl-misctools> | `fwunpack_newfw.py` (parses our firmware end-to-end; its `app.bin` ≡ our `app_dec.bin[0x100:]`), `keyfgen.py`, `recrypt.py`, `mkbfu.py`, `jltech/cipher.py` (byte-identical to our two ciphers). |
| <https://kagaimiq.github.io/jielie/datafmt/newfw.html> | The "New Firmware Format" spec page — flash header, JLFS lists, `app_dir_head` → VA `0x1E00000`, VM/BTIF/EXIF/key_mac layout. |
| <https://kagaimiq.github.io/jielie/cpu/pi32v2.html> | pi32v2 opcode tables + **ELF machine 0xF1 (241)** + SFR list. |
| <https://blog.quarkslab.com/reverse-engineering-a-jieli-bt-firmware.html> | Quarkslab's JieLi BT firmware teardown — the methodology inspiration; Ghidra module at <https://github.com/quarkslab/ghidra-jieli>. |

### Open pi32v2 ISA reference & open toolchain (added 2026-11-10, see [Ch. 34](34-pi32v2-isa-open-reference.md))

| Resource | Why it matters |
|---|---|
| <https://github.com/jvitkauskas/pi32v2-isa> | ⭐ **The open pi32v2 ISA.** `isa/pi32v2.toml` — 1,165 instruction forms, every one confirmed against the JieLi toolchain oracle, 1,079 hardware-confirmed on AC791N (same `-mcpu=r3` as our BR23). Table + docs are **CC0-1.0**, code MIT-0. Pure-Python assembler/linker/objdump proven byte-identical to JieLi's; `python3 -m pi32v2isa disasm <hex>`; oracle protocol (`docs/ORACLE.md`) + gap list (`docs/GAPS.md`). Cross-validates every core encoding this project hand-derived; closes our `???` holes (hw divide, 32-bit stack ld/st, 6-byte `FF00–0xFFEF` branches, predication blocks, psr flags). Used by `tools/isa_xcheck.py` and `pi32dis.py --upstream`. |
| <https://github.com/jvitkauskas/pi32v2-llvm> | Open LLVM 23.1.5 target for pi32v2 (branch `pi32v2`): clang/ld.lld/llvm-mc/objdump, static Linux releases `pi32v2-23.1.5-5`, `-mcpu generic\|r3\|ac791n`; reads JieLi's LLVM-4.0.1 SDK bitcode (4,898/4,900 objects); `tools/dropin` replicates the `/opt/jieli` layout so SDK Makefiles build unchanged. The open replacement for the closed compiler on the ch. 25 compile route / ch. 28 SDK rebuild. |
| <https://github.com/jvitkauskas/m-bootloader> | Same author; open AC79/BR23 bootloader project — its `docs/SPEC.md` §10.1 (mask-ROM USB download mode) is the basis of pi32v2-isa's hardware RAM-runner harness, conceptually parallel to our `jl_hidboot.py` HID path (ch. 32). |

### Architecture / disassembly

- `pi32` (JieLi proprietary 32-bit core) — search for community Ghidra SLEIGH definitions; completeness varies. The `jielie` repo above is the best starting reference. **Since 2026-09-30 we also have the official LLVM objdump backend (§24.5) — the ground truth for pi32v2 decoding.**

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
