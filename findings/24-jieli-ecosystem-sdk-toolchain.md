[<< Index](Findings.md)

# Ch. 24 — The JieLi Ecosystem: Official SDK, Toolchain, Packagers, Community Tools

*Added 2026-09-30. Sources: the [kagaimiq/jielie site](https://kagaimiq.github.io/jielie/),
the public [fw-AC63_BT_SDK](https://github.com/JieLi-IC/fw-AC63_BT_SDK), the official Linux
pi32v2 toolchain, the official post-build tool bundle, the `fw-Bootloader` project, and the
community [jl-misctools](https://github.com/kagaimiq/jl-misctools). Local checkouts used here:
`../fw-AC63_BT_SDK`, `../fw-AC630N_BT_SDK`, `../fw-Bootloader`,
`../jieli-linux-toolchains-20250324.1`, `../jieli-linux-post-build-tools-20260923.1`,
`../jl-misctools`.*

This chapter consolidates a large external-material sweep. Several of our long-standing open
questions closed during it — most importantly the **`.ufw` file table** ([ch. 04](04-container-formats.md)),
the **LFSR "phases"** ([ch. 05](05-lfsr-cipher-and-key-recovery.md)), and the **stack-layer
multipoint capability** ([ch. 22](22-bluetooth-7-multipoint-architecture.md)). The official
toolchain also **independently validated our disassembler** (§24.5).

## 24.1 Chip/family map — we have the right SDK now

The `fw-AC63_BT_SDK` ("AC63N bt_data_transfer SDK") ships a `cpu/<x>` tree per core:

| SDK `cpu/` dir | Part(s) | Core | Evidence |
|---|---|---|---|
| `br23` | **AC635N** (AC695X family) | **pi32v2** | `doc/datasheet/AC635N/`, `CHIP_NAME=AC635N` in patch configs, `fw-Bootloader` README ("AC635N/AC695X/AC695N = br23"), our `.ufw` header chipname `AC695X` |
| `br25` | AC636N/AC638N | pi32v2 | `apps/hid/board/br25/AC636N_hid.cbp` |
| `br30` | AC637N | pi32v2 | `apps/hid/board/br30/AC637N_hid.cbp` |
| `bd19` | AC632N | q32s | `apps/hid/board/bd19/AC632N_hid.cbp` |
| `bd29` | AC631N | q32s | `apps/hid/board/bd29/AC631N_hid.cbp` |

**CONFIRMED: `cpu/br23` = AC635N = our SoC.** The older `fw-AC630N_BT_SDK` contains only
`cpu/bd29` — a BLE-only part on the cut-down **q32s** core (the jielie site: *"AC630N and
AC632N … q32s, a severely cut-down version of pi32v2"*), which is why it was dismissed as
"the wrong chip". **Open question #4 from the project notes (SDK acquisition) is resolved:
`fw-AC63_BT_SDK` is the correct public SDK for the H3 Plus**, including AC635N datasheets
(`doc/datasheet/AC635N/{AC6351B,AC6351D,AC6354B}`), board files, and prebuilt
`cpu/br23/liba/*.a` (btstack, btctrler, cpu, update, JL_Phone_Call, …).

The AC635N builds with `--plugin-opt=mcpu=r3` (from `apps/hid/board/br23/AC635N_hid.cbp`)
and `-DCONFIG_CPU_BR23`.

## 24.2 `isd_config.ini` — we can now read ours fully

`cpu/br23/tools/isd_config_rule.c` is the *generator* of the `isd_config.ini` that isd_download
embeds in every image (and that the community unpacker extracts from **our** firmware). The
TLV text section decoded from `BIN/TD-H3-PlusV1.0.50.bin`:

| Key | Value | Meaning (from `isd_config_rule.c` comments) |
|---|---|---|
| `SPI` | `2_3_0_0` | flash SPI data_width=2 (dual), clk_div=3, mode 0, **port A** (CS:PD3 CLK:PD0 D0:PD1 D1:PD2) |
| `RESET` | `PB01_00_0` | long-press reset pin **PB01**, time `00` = **disabled**, active level 0 |
| `UPDATE_JUMP` | `0` | no jump-to-mask after update |
| `PSRAM` | `0` | PSRAM not used |
| `VLVD` | `4` | VDDIO brown-out ≈ 2.2 V |
| `EOFFSET` | `0` | no 4K·n offset (only needed >256 KiB flash; see the `AC63N_OTA升级4K偏移补丁` in `patch_release/`) |

Region semantics from the same file: `VM` (volatile memory, `OPT 1` = preserved across
downloads), `BTIF` (BT info), `PRCT` with `OPT 2` = **download-time protected region**
(our `PRCT` @code-len), `EXIF`, `ANCIF`, plus `[BURNER_PASSTHROUGH_CFG] FLASH_WRITE_PROTECT = YES`.
`OPT`: 0 = erase, 1 = leave alone, 2 = protect. The chipkey travels as the 32-byte
`chipkey.bin` blob prepended to the `isd_config.ini` JLFS entry (§24.6).

## 24.3 SFC/ENC hardware block — register-level confirmation of ch. 07

`include_lib/driver/cpu/br23/asm/br23.h` defines the exact block we reverse-engineered:

```c
//............. 0x0300 - 0x3ff............ for sfc encrypt
typedef struct {
    __RW __u8  CON;
    __RW __u16 KEY;        // 16-bit key register — the chip key (0xF181)
    __WO __u32 UNENC_ADRH; // unencrypted window (high)
    __WO __u32 UNENC_ADRL; // unencrypted window (low)
    __WO __u32 LENC_ADRH;
    __WO __u32 LENC_ADRL;
} JL_SFCENC_TypeDef;
#define JL_SFCENC_BASE  (hs_base + map_adr(0x03, 0x00))   // 0x1f0000 + 0xC00 = 0x1F0C00
```

- The **16-bit `KEY` register** explains why chip keys are 16-bit and why
  `jl_sfcenc.py`'s `key ^ (addr >> 2)` per-32-byte-line model works: the SFC scrambles each
  32-byte cache line with an LFSR seeded from `KEY ^ (addr >> 2)` (the jielie
  `periph/enc.md` page we used is now corroborated by the vendor header).
- `init_enc_key(u8 cmd)` / `get_sfc_enc_key()` are declared in
  `include_lib/driver/cpu/br23/asm/crc16.h` (implemented in the closed `cpu.a`), next to
  `CrcDecode()` — the same name the community cipher uses.
- `UNENC_ADRH/L` confirms the hardware supports **unencrypted windows** — relevant to any
  future "run code from a second region" idea (§24.7).

## 24.4 BT stack — the multipoint answer (ch. 22 open question (b))

`cpu/br23/liba/btstack.a` (built from the `data_trans_sdk` tree, per embedded build paths)
contains a full BR/EDR profile set **including HFP AG**: `hfp_ag_profile.c`,
`sdp_hfp_ag_service_data`, `setup_hfp_ag_esco_link`, `hfp_ag_buf_init` — matching the H3
Plus's role (HFP AG on RFCOMM ch 6; our app carries the same SDP name strings
`JL_HFP_AG`, `JL_HFP`, `JL_A2DP`, `JL_A2DP_SRC`). Also present: SPP, HID, PBAP/MAP, IAP2,
AMA/GMA/Dueros SDP records, and remote-device-type detection (`REMOTE_DEV_ANDROID/IOS/XIAOMI`).

**The stack API is explicitly multi-device** (`include_lib/btstack/avctp_user.h`):

```c
extern void __set_user_ctrl_conn_num(u8 num);      // "设置蓝牙支持连接的个数"
extern void __set_auto_conn_device_num(u8 num);    // power-on reconnect: try N stored devices
extern bool is_1t2_connection(void);               // "1拖2" = 1-to-2 multipoint
extern u8   get_total_connect_dev(void);           // connected device count
extern u8   is_bt_conn_hfp_hangup(u8 *addr);       // per-address HFP state
extern void __set_hfp_switch(u8 en);               // 1拖2: call pre-empt ("抢断")
extern void __set_hfp_restore(u8 en);              // 1拖2: call restore after pre-empt
extern u8   check_esco_state_via_addr(u8 *addr);   // BD_ESCO_IDLE / BUSY_CURRENT / BUSY_OTHER
extern void __set_auto_pause_flag(u8 flag);        // auto-pause when interrupted
extern void __set_music_break_in_flag(u8 flag);    // later device may interrupt earlier
```

Profile channel bitmask (same header): `SPP_CH 0x01, HFP_CH 0x02, A2DP_CH 0x04, …,
HFP_AG_CH 0x80` (profile bits, not RFCOMM channel numbers). `btctrler.a` additionally carries
BLE multilink scheduling (`multilink_diff_us`, `ble_master_multilink_schedule`) and a BLE-5
baseband (`RF_ble5.c`).

**Conclusion (CONFIRMED at API level, INFERRED for the H3 build):** two concurrent BR/EDR
ACL links with call pre-empt/restore semantics are a *supported, first-class* feature of this
stack family. The single-device constraint we mapped in [ch. 22](22-bluetooth-7-multipoint-architecture.md)
(global struct @`0x102F0`) is therefore an **app-layer** limitation, not a stack limitation.
Whether TIDRADIO's build enables it is still settled empirically by
`tools/bt_multipoint_probe.py` (open question #2 stands), but the prior probability moved
sharply toward "stack can do it".

## 24.5 Official toolchain — our disassembler validated byte-exactly

`jieli-linux-toolchains-20250324.1` (LLVM/clang **4.0.1**, targets `pi32`, `pi32v2`, `q32s`;
README notes `ulimit -n 8192` before linking). `pi32v2/bin/objdump` registers the pi32v2
backend, and the **AC635N CPU is `r3`**. LLVM objdump 4.0 cannot disassemble raw binaries,
but `ld` accepts `-b binary` input — the working recipe (platform-independent, no flashing):

```bash
# wrap raw decrypted app bytes in an ELF .text at the true VA, then disassemble
printf '.section .text,"ax"\n.global x\nx:\n.incbin "work/app_dec.bin"\n' > /tmp/full.S
TC=../jieli-linux-toolchains-20250324.1/pi32v2/bin
$TC/clang --target=pi32v2-unknown-unknown -mcpu=r3 -c /tmp/full.S -o /tmp/full.o
$TC/ld -o /tmp/full.elf -e x --section-start=.text=0x01E00000 /tmp/full.o
$TC/objdump -d /tmp/full.elf > /tmp/official_full.lst
```

**Cross-validation result (CONFIRMED):** comparing `work/full.lst` (our `tools/pi32dis.py`)
against the official disassembly of the same `work/app_dec.bin`:

- **12,786 branch/call targets in common — 0 mismatches.** Every `call`/`goto`/`if(r0==N) goto`
  target we decode matches the official backend, including the BT-PTT release window
  @`0x01E75E78` (`if (r0 == 8) goto` / `if (r0 == 7) goto` / `pc = [sp++]`) and the
  `word1 = (N<<9)|disp9` (2-byte units) encoding in `tools/isa/pi32v2.md`.
- Instruction *boundaries* differ only where LLVM is **table-aware**: after `tbb [r0]` it skips
  the jump-table payload (282,330 instructions) while our linear sweep decodes it
  (333,270). Not an error in either — a feature to consider adding to `pi32dis.py`.
- ELF machine for pi32v2 is **0xF1 (241)** (jielie site) — useful for Ghidra
  (quarkslab/ghidra-jieli) and for tooling that keys off `e_machine`.

The official syntax (`sp =`, `{rets, r5, r4} = [sp++]`, `rep N r2 { … }`, `if (r2 > 0) goto`)
matches `tools/isa/pi32v2.md` conventions exactly.

## 24.6 Containers, keys, flash map — what the packagers and community tools proved

Full details in the session report `postbuild-misctools-report.md`; headline results, all
verified against **our own** v50 firmware:

- **`.ufw` file table located — ch. 04 open question CLOSED.** `ufw_maker 1.1.14` output:
  0x40 header + N×0x50 entries, each LFSR-descrambled (key 0xFFFF), all CRC16-CCITT verified:
  `[etype, index, datacrc, off, size, size2, blob44, name16]`; etypes `flash.bin 0x00`,
  `info.log 0x02`, `isd_config.ini 0x34`, `uboot.version 0x37`, `blimit.bin 0xA1`,
  `farg.cfg 0xFB`, `tail.bin 0xFF`. The 64-byte "JL_FW trailer" **is** the `tail.bin` entry
  (chipkey.bin blob + stamp + magic `JL_FW`/`JLUFW` @ +0x30). The `.fw` wrapper carries the
  same table, per-32-byte-line descrambled with a chipkey-seeded LFSR seed cycle
  `[F181, E593, 19C6, A159, 5C9D]` (states at steps {0,32,64,16,48} of key 0xF181).
- **LFSR phases explained — ch. 05 reinterpretation.** The 0xFFFF-seeded keystream orbit has
  period **32767**; our `.bin` phase 32591 = 32767−0xB0 and `.fw` phase 31567 = 32767−0x4B0
  are pure *alignment artifacts* of the continuous stream that restarts at key 0xFFFF at
  payload_base+0xB0. No tool mentions 32591/31567 — they are emergent, not constants.
- **Community `fwunpack_newfw.py` parses our firmware end-to-end** and its extracted
  `app.bin` is **byte-identical to `work/app_dec.bin[0x100:]`** — an independent confirmation
  of our SFC decryption (ch. 07) and of the layout: `app_dir_head` @0x5000 (VA `0x1E00000`,
  entry point `0x1E00100` in the head's offset field; SDK default is `0x1E00120`),
  `app.bin` @0x5100 (797,536 B), resources (`cfg_tool.bin`, `eq_cfg_hw.bin`, `config.dat`,
  `md5.bin`) @~0xC7C60, then **`VM` @0xC9000 size 0x34000**, `BTIF` @0xFD000,
  `EXIF` @0xFE000, `key_mac` @0xFF000 (4 KiB, reserved). Flash header: size field `0xFF000`,
  VID `0.01`, PID `X12345678` (plaintext inside the scrambled header).
- **Chipkey blob + `.key` files.** The 32-byte `chipkey.bin` blob is steganographic
  (`key bit i = (data[16+i] ^ data[15-i]) < sum(data[:16])&0xFF`); community decode of our
  blob yields **0xF181** (CONFIRMED again). `.key` files (consumed by `isd_download`/
  `fat_comm -key`, and presented on-wire by upgrade cmd `0xC5 EX_KEY`) are AES-128-ECB +
  CRC32(init 0x26536734); `keyfgen.py 0xF181` generates one for official tools.
- **`fw-Bootloader`** documents the AA55 uboot upgrade protocol (cmds `0xC0`–`0xCA` incl.
  `EX_KEY`) — the official spec for the "upgrade strings" region of [ch. 06](06-decrypted-bootloader.md) —
  and confirms `uboot.boot` = BankCB, bank0 load `0x4000` (matches our decode).
- **`jl-misctools` ciphers are byte-for-byte our ciphers**: `jl_enc_cipher` ≡ ch. 05 LFSR,
  `jl_sfc_cipher` ≡ ch. 07 SFC/ENC. Extra tools: `recrypt.py` (re-key an SFC region),
  `bruteforce.py` (known-plaintext chipkey search — the scheme is weak by design),
  `mkjlfs.py`/`mkbankcb.py`/`debank.py` (repack), `mkbfu.py` (BFU loader container).

### ⚠️ Flash-map caution for ch. 23 / Route B

The "erased flash `0xCA000–0xFC000`" we earmarked as **Route B** trampoline space lies
**inside the JLFS `VM` entry (0xC9000–0xFD000)** — reserved for the append-only VM
wear-leveling area. Writing code there risks VM collisions and download-tool erasure
(`VM_OPT 1` only protects it from *download* ops). The **in-app cave** used by BT-PTT2
(flash `0xAC6DE`, inside `app.bin`) is unaffected. Route B should be reconsidered or the VM
size shrunk via `VM_LEN` semantics before use.

## 24.7 Updated open questions

- ~~Locate the `ufw` file table~~ ✅ CLOSED (§24.6).
- ~~JieLi SDK acquisition~~ ✅ CLOSED — `fw-AC63_BT_SDK` covers br23/AC635N (§24.1).
- ~~Stack-layer max-link policy~~ ✅ largely answered — stack API supports 1-to-2 with
  pre-empt/restore (§24.4); empirical probe still decides for the H3's specific build.
- **New:** does the H3's `btstack.a` build include the 1拖2 code paths? Compare
  `btstack.a` (SDK) vs the H3 app's stack region by function-pattern diff, or just run
  `tools/bt_multipoint_probe.py`.
- **New:** H3 entry point is `0x1E00100` but the SDK default `CONFIG_ENTRY_ADDRESS` is
  `0x1E00120` — TIDRADIO overrode it (or an older SDK default). Cosmetic, but worth a
  version fingerprint across v44/v45/v50.
- **New:** feasibility build test — compile `apps/spp_and_le` (or `hid`) for br23 with the
  Linux toolchain to prove we can *build* for the chip (a prerequisite for any eventual
  SDK-rebuild route for true multipoint).
- **New:** `UNENC_ADRH/L` (SFCENC) + `LENC_ADRH/L` windows: worth a hardware experiment —
  an unencrypted window would let a patched region run with ENC off for that range.
- Route B (erased flash beyond app end) is now **deprioritized**: it is VM-reserved (§24.6).

---

*[<< Index](Findings.md)*
