# 40. The radio's JLFS resource filesystem — config.dat parsed, paging-policy verdict (2026-11-21)

← [Index](Findings.md) · prompted by §38.26-7 (tmon.ch field report: `config.dat` =
patch-without-code door on his BR28 soundbox) · tool: `tools/jl_jlfs.py`

## §40.1 Question

User: the tmon.ch headphones dump unpacked to a real filesystem
(`uboot.boot`, `app.bin`, `config.dat`, `tone/*.mp3` …). Is our radio dump the same,
what is the listing, does it have a `config.dat`, and is the **paging policy** in it?

## §40.2 YES — a real JLFS resource chain, exactly as §24.6 predicted

Walking `work/app_dec.bin` (plaintext app region; flash = offset + `0x5000`) from the
resource tail gives a contiguous JLFS entry chain at **`0xC2C60..0xC3696`**
(flash `0xC7C60`), 16-byte-header variant:

```
[u32 datacrc][u32 data_off][u32 block_size_incl_hdr][u8 flags][u8 resvd][u16 index] + name[16]
```

| Entry | hdr | data | size | flags | crc32 |
|---|---|---|---|---|---|
| `cfg_tool.bin` | `0xC2C60` | `0xC2C80` | 969 B | `0x82` | `0x67ed45d6` |
| `eq_cfg_hw.bin` | `0xC3049` | `0xC3069` | 1149 B | `0x82` | `0xb5ea4c44` |
| `config.dat` | `0xC34E6` | `0xC3506` | 336 B | `0x82` | `0xa34ab13f` |
| `md5.bin` | `0xC3656` | `0xC3676` | 32 B | `0x82` | `0x1e9df4ba` |

That is the WHOLE filesystem: 4 files. **No `tone/` dir, no `.mp3`, no
`uboot.boot`, no `p11_code.bin`** in this region — the radio is not a soundbox
distribution. `app.bin` itself is the JLFS container head (§24.6: `app_dir_head`
@`0x5000`, `app.bin` @`0x5100` 797,536 B); the chain above is its resource tail.

## §40.3 config.dat — COMPLETE parse (JCRT TLV container)

Header (32 B): magic `JCRT`, u32 hash `0xdbabb697`, u32 total-size 336, **u16 count 6**
@+0x0C. Then 6 × 32 B records
`[u16 idx][u16 type][u32 val_off][u32 val_len][u16 crc16][u16 ffff] + name[16]`
(names **0xFF-padded**, not NUL). Values at `base + val_off`:

| # | key | type | len | value |
|---|---|---|---|---|
| 0 | `ver_info` | bytes | 6 | `00 02 00 5f 00 00` |
| 1 | `ver_info_ext` | str | 22 | `hE9yfseX6UdK7rFh,jl_v8` |
| 2 | `reset_io` | str | 1 | `1` |
| 3 | `pilot_lamp_io` | str | 4 | `PB03` |
| 4 | `link_key` | bytes | 16 | `06 77 5f 87 91 8d d4 23 00 5d f1 d8 cf 0c 14 2b` |
| 5 | `power_io` | str | 6 | `PC03_1` |

Findings:

1. **PAGING POLICY: NOT PRESENT.** Grep for
   `page[_ ]?scan|1t2|conn[_ ]?num|multi[_-]?bd|auto[_-]?conn|reconnect|pairing`
   across ALL four extracted files: **zero hits**. The paging/eviction policy is
   compiled code only (known sites: page-scan disable branch `0x01E18B0E`,
   `is_1t2_connection` reader `0x01E1787C`, scan mgmt — ch. 22/26/27). The tmon.ch
   `config.dat` patch-without-code door (§38.26-7) is **CLOSED for the two-device
   goal**: this config store carries no behavior keys. (The TID-PTT's own `config.dat`
   is a different device's file — still worth checking when the Route A dump lands.)
2. `pilot_lamp_io = PB03` — **the exact key/value pair from the tmon.ch article**:
   same cfg_tool schema across JieLi families.
3. **`link_key` surprise**: a fixed 16-byte BR/EDR link key burned into the factory
   image — a factory/default pairing key baked at build time (all units of this image
   share it). Security-relevant; UNVERIFIED whether the stack actually consults it at
   runtime (static follow-up if ever needed).
4. `ver_info_ext` embeds `jl_v8` (SDK soundbox version tag) + a build hash string.

## §40.4 cfg_tool.bin (969 B) — the vendor cfg_tool project file

Magic `be@)`; records: BT name + PIN **`TD-H3 Plus1234`** (= `TD-H3 Plus` / PIN
`1234` — the pairing PIN is IN the image); SDK soundbox bank template names
`jl_soundbox_2`..`jl_soundbox_20`; BLE name **`H3_Plus_BLE`**; then audio/EQ float
parameter blocks (5.0/6.0/3.0/−50.0 …), a u16 level/volume-curve pair table, and the
project tag `soundbox-1.0.0`. Confirms the radio is built from the JieLi **soundbox
SDK** lineage with BT name/PIN/EQ as project data.

## §40.5 eq_cfg_hw.bin (1149 B) — hardware EQ

Header `02 01 00 00 00 fd ff 36`; biquad coefficient structures, per-band gain tables
(repeated float 0.7 `33 33 33 3f`), six channel blocks (@`0x144/0x190/0x1e4/0x244/
0x2a6/0x306`). Tail from `0x370` is high-entropy (compressed/encrypted sub-blob —
unresolved, low value).

## §40.6 md5.bin (32 B) — scope PROVEN

Content = ASCII `60890ad74db1f29b6753a2312959b4f0`. Span test: it is the
**MD5 of `app_dec.bin[0x100:0xC2C60]`** — i.e. `app.bin` (the 797,536 B code image)
plus everything up to the resource chain. Convention: the tail checksum covers the
entire payload BEFORE the resources, not the resource data (MD5 of entry data =
`452621d9…` ≠ stored value — ruled out by test).

## §40.7 Tone table — 393 prompt names, audio ABSENT from the dump

The app carries a resource-name table @`0x86A30..0x87400`: mount strings
(`storage/res_nor`, `storage/fat_nor`, `storage/nor_ui`, `mnt/sdfile/res/`,
`fm_inside`, `nor_fs`, `rec_fs`), decoder args `-tMP1MP2MP3WAVDTS -sn -r`, and
**393 `storage/res_nor/C/tone/<name>.*` wildcard entries** — base set (numbers,
`bt_conn/bt_dconn/bt_mode/fm_mode/call_rem/rx_sound/lock/unlock/welcome/confirm/
cancel/on/off/menu/low_voltage/tx_timeout/channel_m/frequency_m/save_mode/d_sound…`)
plus per-language sets prefixed `cn_ de_ es_ fr_ it_ ru_ th_ tr_` (matches the nine
menu languages of §9C.9).

**But the tone AUDIO is not in the 1 MiB dump**: the VM region `0xC9000+` is
effectively empty (`0xC9000`: 783 non-FF bytes = VM headers; `0xCA000–0xFCFF` all-FF;
`0xFD000`: 9 B BTIF), no RIFF/WAVE (3 incidental hits), no FAT boot signature
anywhere, entropy scan of the whole tail (per-8 KiB) maxes at 7.003 — no audio blob.
OPEN QUESTION (→ ch. 18): where do the voice prompts live? Candidates: the
`res_nor` FAT volume is created empty on first boot and tones fall back silently;
audio shipped in a separate region the dump does not cover; or prompts only play on
variants with the volume written. Not blocking any current route.

## §40.8 Tool

`tools/jl_jlfs.py` (stdlib-only, MIT): walks the chain, extracts to an outdir, parses
the JCRT TLV, `--tones` lists the tone table. Verified 2026-11-21 reproducing this
chapter's tables from `work/app_dec.bin`.

## §40.9 Where the code touches this filesystem (static, 2026-11-22)

**One path primitive for everything:** `FUN_01e24d26(path)` @`0x01E24D26` — the SDK
`fopen`-equivalent on the mounted resource volume (FS context getter `FUN_01e24c82`,
name lookup `FUN_01e24cc6`, read via device ops-table `[ctx+8]+0x18` callback, lock
primitives `func_0x02002bc4/0x02002c3c` on RAM `0x101AC`). **Exactly 12 call sites**:

| Opener | Path | Role |
|---|---|---|
| `FUN_01e2c64e` | `mnt/sdfile/res/cfg_tool.bin` | cfg_tool loader (below) |
| `FUN_01e4fae6` | `mnt/sdfile/res/config.dat` | JCRT key lookup (below) |
| `FUN_01e4fc8a` | `mnt/sdfile/res/md5.bin` | resource-integrity check |
| `FUN_01e4faa8` | `mnt/sdfile/app/exif` | EXIF region read |
| `FUN_01e487d2` / `FUN_01e48812` / `FUN_01e48948` | `mnt/sdfile/res/eq_cfg_hw.bin` ×3 | EQ loaders, registered in the **boot initcall table @`0x01E00B60`** (fn+level pairs: `0x1015`/`0x0B`/`0x100E`…; `FUN_01e48948` via `FUN_01e48b4e`) |
| `FUN_01e3fe50` / `FUN_01e3fed2` / `FUN_01e521de` / `FUN_01e5e4e2` | dynamic `param_1` | tone/prompt openers — build the path from the 393-entry table @`0x01E86A30` (Ghidra misparses that string blob as code `FUN_01e86a30…`) |

**config.dat runtime path:** `FUN_01e4fae6` reads the 32 B JCRT header (record count
u16 @+0xC — matches §40.3), walks the 32 B records, `strcmp` (`func_0x021127b0`) the
key, reads the value into the caller's buffer. Code-side key strings live at
`0x01E9B9E0` (`ver_info`/`reset_io`/`link_key`/`power_io` contiguous block) and
`0x01E9C11A` (`pilot_lamp_io`). Wrapper `FUN_01e4fc42`; consumer `FUN_01e4fe42`
(table ref `0x01E4F824`).

**cfg_tool.bin runtime path — read once at boot, RAM-resident, ID-dispatched:**
- Loader `FUN_01e2c64e`: opens the file, sets RAM cursor `DAT_00010190`=loaded,
  `_DAT_00010194`=data+4, `_DAT_00010198`=size−4 (skips the u32 length prefix); a
  secondary resource via `FUN_01e9c770` (bank check at `+0x200`, cursor `_DAT_000101a0`).
- Source table @`0x01E2DC60..0x01E2DCB4`, stride `0x1C` = `[init, match_id, get, get_ptr]`:
  entry @`+0x00` = secondary record source (`FUN_01e2c964/c9f6/ca0e/ca5e`), entry
  @`0x01E2DC7C` = built-in defaults (`0x01E81806/0x01E81AD8/0x01E5F930/0x01E5FC2A/0x01E81AE6`),
  entry @`0x01E2DC98` = the cfg_tool.bin file source (`FUN_01e2c64e/c71a/c84a`).
- Dispatcher `FUN_01e2c49e(id, buf, len)`: config-ID space partitioned —
  `0x001–0x030`/`0x032–0x063` → defaults; **`0x200–0x2BC` → cfg_tool.bin records**;
  else scan registered sources. Size query `FUN_01e2c52c`. Boot init `FUN_01e2c616`
  (registered @`0x01E2DC44`) calls every entry's init ⇒ loads the file.
- Consumers (app config reads): `FUN_01e01318`, `FUN_01e44e8e`, `FUN_01e5e144`,
  `FUN_01e6058e` (BT init — reads **id `0x56` into RAM `0x11390`** = device-name
  setup), `FUN_01e630c8`, `FUN_01e637ee`, `FUN_01e6b654`, `FUN_01e81b7e`.

**Write verdict: READ-ONLY at runtime.** No `fwrite`/`f_write`/write-mode open exists
anywhere in the decompiled app; the record API only memcpys OUT of the RAM copy
(`FUN_01e2ca0e/ca5e`). `cfg_tool.bin` and `config.dat` are modified only externally —
by the vendor cfg_tool USB workflow (the `be@)` project format) reflashing the
resource chain — never by the running firmware. Practical consequence: patching the
JLFS files (e.g. BT name, PIN, `link_key`) is a **repack-and-reflash** operation
(sector `0xC7000` region), not something the app can be talked into doing.

## 40.10 Sibling filesystems — the mount table (2026-11-22)

The JLFS chain is only ONE of **four registered filesystem instances**. The firmware has a
central mount table @`0x01E93420` (file offset; VA `0x01E93420`), 4 × 20-byte entries
`[fs_name_ptr, dev_ptr, mount_point_ptr, mount_point2_ptr, driver_class_ptr]` (terminator
zeros @`0x93470`), iterated by the mount executor **`FUN_01e4a8ba`** (name `strcmp`
`func_0x021127b8`, mounted-list head RAM `0x1173C` guarded by lock `0x11744`, actual mount
`FUN_01e24e48(dev, path, 3)`, mount record `FUN_01e3106c(0x18)`):

| # | FS name | Mount point(s) | Driver class | Meaning |
|---|---|---|---|---|
| 0 | `sdfile` | `mnt/sdfile` (+ alias `mnt/sdfile/res/`) | `sdfile` | **the JLFS resource chain** — §40.2/40.9 (`cfg_tool.bin`, `config.dat`, `md5.bin`, `eq_cfg_hw.bin` all open via `mnt/sdfile/res/`) |
| 1 | `fat_nor` | `storage/fat_nor` + `storage/fat_nor/C/` | `fat` | NOR **FAT** volume (user/record area) |
| 2 | `res_nor` | `storage/res_nor` + `storage/res_nor/C/` | `nor_sdfile` | NOR resource volume — **the tone files live here by path** (`storage/res_nor/C/tone/…`, §40.7): refines the open question — the tone table resolves to `res_nor`, which is ERASED in the dump (VM span `0xC9000–0xFD000`), i.e. formatted blank at first boot |
| 3 | `nor_ui` | `storage/nor_ui` + `storage/nor_ui/C/` | `nor_sdfile` | NOR UI-asset volume (also erased in the dump) |

Supporting evidence:

- **FAT driver present in app**: inline `FAT` OEM-name compares @`0x26628`/`0x2663C`, and a
  complete **MS FAT32 boot-sector (BPB) template** embedded @`~0x9AD40` (x86 bootstrap stub,
  `LNO NAME    `, `FAT32   ` sig) — the firmware can **format** a FAT32 volume at runtime
  (fresh-boot init of `fat_nor`/`res_nor`/`nor_ui` when erased).
- **Device-name strings** for the block layer @`0x9B4BF–0x9BDB5`: `nor_fs` (NOR block device,
  ops table ref @file `0x2D95C`), `rec_fs` (recording FS device, ops table @`0x2D9D0`),
  `udisk0` + `udisk0_rec` (USB-MSC **client** — radio mounts a USB stick; refs
  `FUN_01e626a2`/`FUN_01e7f40a`), `sd0`/`sd1` (SDK SD-card names — dormant, no HW),
  `fm_inside` (FM resource, ref @`0x63338`), `res.bin`, `/sin.wav`, JLFS dir set
  `res`/`app`/`sys`/`sbc` @`0x9B4D4`.
- **The `app/` directory of the JLFS** maps the tail flash regions into the same tree:
  `mnt/sdfile/app/exif` (@`0x9C66A`, EXIF @flash `0xFE000`, reader `FUN_01e4faa8` §40.9) and
  `mnt/sdfile/app/btif` (@`0x9C770`, BTIF @flash `0xFD000`, refs @`0x2C65E`/`0x2CA9E`) — the
  "secondary source" of the cfg_tool loader (§40.9) is this **`app/btif`** file: the BTIF
  region re-presented as a file inside the JLFS mount, record base `+0x200`.
- Boot mount sequence: initcall table @`0x01E00B60` (§40.9) registers the `eq_cfg_hw.bin`
  readers; `FUN_01e63310` (the BT/audio init task) walks a device list comparing names incl.
  `fm_inside` (`func_0x021127b0(...,0x1e86aa7)`).

**Verdict for the two-device hunt:** all filesystems are resource/user-data stores; none
carries BT policy. The interesting new lead is **BTIF-as-file (`mnt/sdfile/app/btif`, flash
`0xFD000`)** and **EXIF-as-file** being read through the same cfg_tool record dispatcher —
consistent with §40.3's finding that behavior config is minimal; the paging policy remains
compiled code only.

## §40.11 Full file map of the RUNNING-radio dump (2026-11-22)

Source: `Dumps/dump_internal.bin` (1 MiB, md5 `8080a152df6221a538bf3970453953cb`) — taken
from a running, loaded radio, so it contains live runtime state. Every FS from the §40.10
mount table is enumerated below, recursively, with per-file contents + read/write sites.
**Headline: the tail holds exactly ONE live runtime store — the VM record bank at
`0xC9000` — and we cracked its record format (§40.11.3), including the radio's stored
pairing records (BD_ADDR + link keys).**

Non-FF content map of `0xC9000–0x100000` (64 B granularity): VM bank A `0xC9000–0xC948F`
only, plus 9 bytes @`0xFD000` (BTIF header). Everything else — `0xC9500–0xFCFF`,
`0xFE000–0xFFFF` (EXIF, key_mac) — is all-`FF` (erased).

### §40.11.1 `sdfile` — the JLFS tree (flash `0x5000` + tail) — READ-ONLY

```
mnt/sdfile/                       ← sdfile driver, JLFS container (app_dir_head @0x5000)
├── app/
│   ├── exif                      ← flash 0xFE000 — ERASED in dump (all FF)
│   │                                read: FUN_01e4faa8 (§40.9); write: none (reflash-only)
│   └── btif                      ← flash 0xFD000 — 9 live bytes: 81 66 60 00 92 85 e8 59 ff
│                                    (header/seq only; record area @+0x200 all-FF ⇒ ZERO
│                                    BTIF records on this unit)
│                                    read: cfg_tool loader 2nd open (§40.9 refinement —
│                                    the "secondary source" IS this file, base +0x200);
│                                    write: none at runtime
└── res/
    ├── cfg_tool.bin   969 B      ← §40.4: BT name 'TD-H3 Plus' + PIN '1234', BLE name
    │                                  'H3_Plus_BLE', jl_soundbox banks, EQ floats
    │                                read: FUN_01e2c64e once at boot → RAM cursors
    │                                  0x10190/0x10194/0x10198; ID-dispatched 0x200–0x2BC
    │                                write: NONE (verified §40.9)
    ├── eq_cfg_hw.bin  1149 B     ← §40.5: EQ biquads + high-entropy tail @+0x370
    │                                read: FUN_01e487d2/0x01E48812/0x01E48948 (boot
    │                                  initcall table @0x01E00B60)
    │                                write: NONE
    ├── config.dat     336 B      ← §40.3: JCRT TLV, 6 keys (ver_info…power_io, fixed
    │                                  factory link_key); NO paging policy
    │                                read: FUN_01e4fae6 key lookup; write: NONE
    └── md5.bin         32 B      ← §40.6: MD5 of app_dec[0x100:0xC2C60]
                                     read: FUN_01e4fc8a integrity; write: NONE
```

### §40.11.2 NOR volumes `fat_nor` / `res_nor` / `nor_ui` — EMPTY (unformatted)

All three mount via NOR block devices (`nor_fs` ops tables §40.10) into
`storage/<name>/C/`. In this dump **no FAT BPB, no `nor_sdfile` header, no file entries
exist anywhere in `0xC9500–0xFCFF`** — the span is all-`FF`. They are format-on-first-use
volumes (embedded FAT32 BPB template @`~0x9AD40` §40.10) and this unit never used them.
Expected-but-absent content: the 393 tone files (`storage/res_nor/C/tone/…` §40.7 — openers
`FUN_01e3fe50`/`FUN_01e3fed2`/`FUN_01e521de`/`FUN_01e5e4e2` get open-fail → prompts silent,
**closing the §40.7 open question: the tone audio is genuinely not on this radio**); UI
assets on `nor_ui`. Reads: the tone openers + `nor_ui` consumers; writes: format path +
vendor tooling only.

### §40.11.3 The VM record bank @`0xC9000` — the ONLY live runtime FS — format CRACKED

Record framing (brute-forced to a **perfect 54-record tiling** of bank A, validated
against the §9A.8/§12A.7 anchors):

```
bank header (14 B): 55 AA AA 55 | seq u32 (here 0x006068FB) | aa 7c bb 55 | 1f ef
record:  [u8 crcLo][u8 idx][u16 (len<<4)][data × len]     (len = code>>4, ≤ 0x3F? — max seen 35)
crcLo  = LOW BYTE of CRC-16-CCITT (poly 0x1021, init 0x0000, non-reflected) over DATA ONLY
delete = append same idx with all-FF payload (crc of 32×FF = 0xB4 — the old "tombstone")
lookup = append-only log, LAST live record per idx wins; two banks @0xC9000/@0xC9490
```

(The SDK's `vm.h` `struct vm_table {u16 index; u16 value_byte; …}` is the RAM-side API
shape; the on-flash framing above is what the precompiled `cpu.a` VM lib actually writes.
Bank B @`0xC9490` is all-`FF` in this dump — the old §12A.7 'TD-H3-Plus-9320' bank was a
different unit/era read.)

Full bank A listing (idx names from `fw-AC630N_BT_SDK/include_lib/system/syscfg_id.h`;
H3+ deviations marked):

| off | idx | name | len | content |
|---|---|---|---|---|
| `0xC900E` | 101 | `CFG_BT_NAME` | 32 | `TD-H3-Plus-3511` |
| `0xC9032` | 103 | (H3+: **BLE name**) | 32 | `TD-H3-Plus-3511-ble` |
| `0xC9056` | 104 | `CFG_SYS_VOL`? | 6 | `c9 e8 0f 7a 92 d1` |
| `0xC9060` | 92 | `CFG_AAP_MODE_INFO` | 8 | `7c fc 00 f8 7b fc 00 00` |
| `0xC906C` | 90 | `CFG_POR_FLAG` | 1 | `a5` |
| `0xC9071` | 86 | `CFG_USER_RESET_SOURCE` | 1 | `1e` |
| `0xC9076` | 93 | `CFG_DAC_TRIM_INFO` | 29 | `00 00 fb ff fb ff 78 00 78 00 fc ff 0d 00 18 00 7b 00 fb ff 03 02 02 02 02 00 01 04 df` |
| `0xC9097` | **71** | **PAIRING** (AC630N: TWS_INFO) | 32 | ctr `8235 0100` mask `ffff` sub `0003` **addr `bc:54:4a:c8:17:90`** key `07c3b3b0e8cab913c52e06e54cef5e41` |
| `0xC90BB` | **71** | PAIRING rewrite | 32 | ctr `370a 0200`1… same addr+key |
| `0xC90DF` | **71** | PAIRING rewrite | 32 | ctr `549e 0300`… same addr+key |
| `0xC9103`…`0xC922D` | 17 | user-range | 35 | `07 13 <id>` + 32×00, ids `01,23,24,25,26,25,24,d3` (append log) |
| ×13 | 86 | RESET_SOURCE log | 1 | `07 0a 1e 0c 12 1e … 0b 04 01 0c 19 09 00 05 02 1e 07 18 12 1e 02 1e 14` = **one byte per reboot** |
| `0xC927C` | **81** | **PAIRING** (AC630N: DAC_TEST_VOLT — H3+ reuse) | 32 | ctr `9538 0100` mask `ffff` sub `0030` **addr `34:73:e2:4b:5c:74`** key `6c5f6a536df2557ebcfc6f1055202a8e` |
| `0xC92AA` | 81 | deleted (32×FF) | 32 | — |
| `0xC92D3` | **81** | PAIRING rewrite | 32 | ctr `c280 0100` addr `34:73:e2:4b:5c:74` key `5c62b5cfef4cd1ebc8b2e349a2808709` |
| `0xC92FC`–`0xC9440` | 72–81 | deleted slots | 32 | 32×FF each (idx 72,73,74,75,76,77,78,79,80,81) |

Reading of the table:

- **Two paired devices live in the VM**: `bc:54:4a:c8:17:90` (idx 71, one key, rewritten
  3× — append-only counters) and `34:73:e2:4b:5c:74` (idx 81, key rewritten once after a
  delete). §9A.8's "mystery constant" `34:73:e2:4b:5c:74` appears as the idx-81 record's
  ADDR field — consistent with it being **this radio's own BD_ADDR** stamped into its
  pairing records (identity binding), not a remote. OUI of `bc:54:4a` = the remote device.
  The TID-PTT (`6F:E5:E7:FB:12:4F`) is NOT in this dump (predates the PTT pairing era of
  the project).
- idx 86 = per-reboot reset-source log (~20 reboots recorded); idx 17 = app user-range
  event log (`07 13 <id>` events).
- **VM write sites**: precompiled `cpu.a` VM lib (`vm_write`/`vm_delete` per SDK
  `vm.h`); callers = btstack pairing storage (link keys), syscfg config writes, reboot
  logging. **Read sites**: `vm_read` via the same lib at boot (names, trims) and on
  pairing lookups. No app code reads the bank directly — §40.9's file readers are
  separate.
- **Two-device relevance**: the VM holds ONLY keys/ids — no device-type or policy field
  (confirms §9A.8 on a fresh decode). The eviction/bind wall is NOT data here either.

### §40.11.4 Loose tail structures (not filesystems)

| Region | Bytes | What | Read/Write |
|---|---|---|---|
| `0xC8FE0` | 32 | device-specific block (§12A.6): `04 00 … 03 01 1e ff 0d 21 1c 00 67 de 8f 43 4a be 78 00` — survives sector reflashes; candidates MAC/serial/cal | read at boot (bootloader/app); written by factory flow |
| `0xFD000` | 9 | BTIF header `81 66 60 00 92 85 e8 59 ff` (§40.11.1) | via `mnt/sdfile/app/btif` |
| `0xFE000` | — | EXIF — erased | via `mnt/sdfile/app/exif` |
| `0xFF000` | — | key_mac — erased | loader-side |

### §40.11.5 Devices with no content in the dump

`rec_fs` (recordings), `udisk0`/`udisk0_rec` (USB-MSC client), `sd0`/`sd1` (no HW),
`fm_inside` (FM res), `res.bin`, `/sin.wav` — driver strings + ops tables exist (§40.10),
no mounted content: these need external media and are empty/absent by definition.

## §40.12 THE VOICE PROMPTS — where "Bluetooth connected" actually comes from (2026-11-24)

**Question (user, verbatim):** *"when I connect a bluetooth device I hear the words
"Bluetooth connected" and when I disconnect … "Bluetooth disconnected" … where are those
samples coming from? Are they in memory? Compiled inline? … changing the langue in the menu
did not change the words / samples. Also … "Menu" and "Confirmed" and … "Channel mode" and
"Frequency Mode""*

**VERDICT: they are audio FILES, not inline data.** Each prompt is a file opened by path
`storage/res_nor/C/tone/<name>.*` from a per-event pointer table in the app, and the
`res_nor` volume is backed by a **second (external) SPI NOR flash mapped at flash
`0x100000`…`0x300000`** — a region the 1 MiB chip dump and the bootloader's FLASH_CRC
(both masked to the internal chip) have NEVER covered. That is why every earlier scan of
`work/app_dec.bin` and of both full-chip dumps found no audio.

### §40.12.1 The per-event voice pointer table @`0x01E9F1C4`..`0x01E9F294`

Contiguous u32 LE array in `work/app_dec.bin` (file `0x9F1C4`..`0x9F294`); every entry is a
pointer to a path string `storage/res_nor/C/tone/<name>.*` in the pool at file
`0x86B44`..`0x87BA0` (133 strings). Index is relative to `0x01E9F244` (= index 0):

| idx | prompt | idx | prompt | idx | prompt |
|---|---|---|---|---|---|
| −33..−14 | `zero` `one` … `nine` | 6 | `low_voltage` | 14 | `bt_mode` |
| −12..−5 | `twenty` `thirty` … `ninety` | **7** | **`channel_m`** | **15** | **`bt_conn`** |
| −4 | `hundred` | **8** | **`frequency_m`** | **16** | **`bt_dconn`** |
| −2 | `en_and` | **9** | **`confirm`** | 17 | `fm_mode` |
| 0 | `d_sound` | 10 | `cancel` | 18 | `call_rem` |
| 1 | `tx_timeout` | 11 | `on` | 19 | `d_sound2` |
| 2 | `welcome` | 12 | `off` | 20 | `rx_sound` |
| 3 | `lock` | **13** | **`menu`** | | |
| 4 | `unlock` | | | | |
| 5 | `save_mode` | | | | |

All six prompts the user asked about are in this table (7, 8, 9, 13, 15, 16). The table base
has **zero absolute references** in the image — it is reached by computed addressing.

### §40.12.2 How a prompt is played (`FUN_01e5e4e2`, the tone runner)

Sequence object: `obj+0x10` → list, `list+0x14` → u32 array, `obj+9` index, `obj+0xb` enable,
`obj+0xc` repeat. Entry class = top 2 bits: `0x80000000` loop/segment marker, `0x40000000`
repeat-count (low 16 bits), **`&0xc0000000 == 0` → FILE PATH POINTER**, `≥0xc0000000` →
built-in beep via callback `FUN_01e807b4` (id → descriptor tables `0x01E9C424`/`0x01E9C434`/
`0x01E9C9FC`/`0x01E9CA1C`/`0x01E9CA3C`/`0x01E9CD8C` — sine/beep only, no speech).
File branch: `FUN_01e24d26(path, "r")` = fopen (mode string `"r"` @`0x01E9B437`), reads the
first 16 bytes, `strncmp(name,"sin",3)` sniff (`"sin"` @`0x01E9B4C7`) → `FUN_01e3fed2`
(header + extension table `PTR_FUN_01e9ce34`) else `FUN_01e3fe50` (plain decoder, 16 kHz);
built-ins use `FUN_01e3fdb8`. **All three return 0 (silence) if fopen fails** — so audible
voice proves the volume and files exist at runtime. Supported extensions list
`wtg`/`mty`/`aac`/`mp3`/`wma` @file `0x86A1C`. Sequence builder example: `FUN_01e7ed80`
(assembles from table @`0x01E9F104` + appends `0x4000ffff`,`0xc0000005`,`0x80000000`,0).

### §40.12.3 Mount table @`0x01E93418` (stride 0x14: name, name, mountpoint, prefix, fs-type)

| volume | mount point | prefix | fs type |
|---|---|---|---|
| `sdfile` | `mnt/sdfile` | `mnt/sdfile/res/` | (sdfile/JLFS — §40.2, flash `0xC2C60`) |
| `fat_nor` | `storage/fat_nor` | `storage/fat_nor/C/` | `fat` |
| **`res_nor`** | **`storage/res_nor`** | **`storage/res_nor/C/`** | **`nor_sdfile`** |
| `nor_ui` | `storage/nor_ui` | `storage/nor_ui/C/` | `nor_sdfile` |

Mounted by `FUN_01e4a978` → `FUN_01e4a8ba(name)` → `FUN_01e24e48(mountpoint, type, 3)` →
`FUN_01e2c3ea(type)` device lookup. `nor_sdfile` driver: init `FUN_01e260f2`, read primitive
`FUN_01e26116` → `FUN_01e2c472(handle,buf,addr,len)`, dir walk `FUN_01e26146` (0x20-byte
entries, head crc16 `FUN_01e4cbea(entry|2,0x1e)`, dir base RAM `_DAT_000412c0`), open
`FUN_01e261ac` (root name check vs `"C"` @`0x01E932EE`), file read `FUN_01e262c0`.

### §40.12.4 ★ The physical base — device table @`0x01E24734` (stride 0xc) ★

| entry | name | device struct | region descriptor | region | ioctl class |
|---|---|---|---|---|---|
| `0x24734` | `"fat_nor"` | `0x01E93484` | `0x01E935EC` | **+0x10 `0x00000000` / +0x14 `0x00100000`** = internal 1 MiB | `0x200` |
| `0x24740` | `"res_nor"` | `0x01E934A4` | `0x01E93604` | **+0x10 `0x00100000` / +0x14 `0x00300000`** = 2 MiB ABOVE 1 MiB | `1` |

Both descriptors carry `{2, 0x17, 0, ptr→"A"}` (port/CS group letter `"A"` @`0x01E9361C`).
res_nor read `FUN_01e4caf0` = `FUN_01e4c386(*(int*)(*(int*)(ctl+4) + 4) + off, 0)` →
**physical = instance base (`0x100000`, loaded from the descriptor) + file offset**; write
`FUN_01e4cb0a` = `FUN_01e4c696(base+off, 0)`; ioctl passes class `1` where the internal chip
passes `0x200` — i.e. a DIFFERENT flash device, not a partition of the internal one.
**Status: statically derived; hardware-confirmed only indirectly** (voice is audible while the
entire internal 1 MiB is CRC-proven free of any tone data).

### §40.12.5 Corroboration from the live radio and the SDK

* Live FLASH_CRC oracle (HID mode, read-only): internal chip holds ONLY VM bank A
  (`0xC9000`, live churn) + 4 KiB content at `0xCA000` (chip `C179` vs dump `E03E`=all-FF) +
  erased `0xCB000`–`0xFDFFF`. Reads at `0x100000`+ **wrap mod 1 MiB** — the bootloader is
  masked to the internal chip, so the wrap does NOT disprove the external flash; it only
  proves the bootloader cannot see it. `crc16(4 KiB FF) = E03E`.
* Uppercase `nor_sdfile` dir-name scan (`BT_CONN`, `BT_DCONN`, `INDEX.IDX`, `CHANNEL_M`,
  `CONFIRM`, `FREQ`) over `Dumps/dump_internal.bin`, `Dumps/dump_pre_ch30.bin`,
  `work/app_dec.bin`: **zero hits** (dir entries store names UPPERCASE —
  `sdfile_str_to_upper`). Consistent: the res dir is not in the internal chip.
* SDK (`fw-AC630N_BT_SDK`) packing: `cpu/bd29/tools/download.bat` →
  `isd_download.exe … -app app.bin cfg_tool.bin **-res tone.cfg**`; `tone.cfg` = packed tone
  container (`index.idx`, `bt_conn.wtg`, `bt_dconn.wtg`, `power_on/off.wtg` + zh labels);
  `conf/source/tone/tone.lua` maps zh/en names → fixed base filenames (`connected`→`bt_conn`)
  and offers formats `wtg`/`msbc`/`sbc`/`sin`/`mty`; sample `extra_tones/bt_conn.wtg` = 960 B
  with a repeating 10-byte record framing (not MP3/WAV/zlib) — explains why audio-magic scans
  could not have found these even if present.
* SDK DWARF (`include_lib/liba/bd29/system.a`, `sdfile_new.c`) gives the exact driver
  structs: `sdfile_file_head {u16 head_crc; u16 data_crc; u32 addr; u32 len; u8 attr,res;
  u16 index; char name[16]}`, `nor_sdfile_hdl {addr_offset; read; write;}`,
  `_sdfile_handle {sfc_base_addr; app_addr; app_part_addr; res_part_addr; dir_addr;
  vm_end_addr}`, symbols `__initcall_sdfile_init`, `tone_saddr`,
  `sdfile_flash_addr2cpu_addr`/`sdfile_cpu_addr2flash_addr`.

### §40.12.6 Answers to the sub-questions

* **"Are they in memory / compiled inline?"** No. Not in the app plaintext, not in the VM,
  not in either full-chip dump. They are files in a filesystem (`nor_sdfile`) on the external
  NOR at `0x100000`+; the app only carries the *paths* (§40.12.1) and the decoder code.
* **"Why doesn't the language menu change them?"** The menu localises UI text only. The tone
  filenames are FIXED English base names baked into the pointer table (`bt_conn`, `menu`,
  `confirm`, `channel_m`, `frequency_m`), and the res bank holds a single set — the SDK's
  `addToneNameMapLang("en", …)` mechanism renames labels, not files, and TIDRADIO shipped one
  bank. (Static inference from the table + SDK; the bank contents themselves unread.)
* **Per-event mapping** is exactly the table in §40.12.1: connect→idx 15 `bt_conn`,
  disconnect→idx 16 `bt_dconn`, menu open→idx 13 `menu`, confirm→idx 9 `confirm`,
  channel-mode→idx 7 `channel_m`, frequency-mode→idx 8 `frequency_m`.
* **Corollary for §40.11.2/§40.11.5:** those sections' "NOR volumes empty / `res.bin` no
  content" statements remain true **for the internal 1 MiB chip**; `res_nor` is NOT empty —
  its content was simply never addressable from the bootloader. The "128 Mb external
  storage" vendor claim (findings/18) is now explained: the app addresses `[0x100000,
  0x300000)` through the class-1 flash device.
* **To get the bytes** (future work, UNTESTED): the class-1 device is reachable only from the
  app. Candidates: an MSC/`udisk` or AT/RCSP-side file dump of `storage/res_nor/C/tone/*`, or
  a code-cave that calls `FUN_01e26116`/`FUN_01e4c386` and ships bytes out over SPP. The
  uboot HID/MSC path cannot read it (masked to 1 MiB).
