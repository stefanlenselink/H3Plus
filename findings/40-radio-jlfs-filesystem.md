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
