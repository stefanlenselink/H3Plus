# Ch. 32 — SDK Rebuild Route: working plan + live tracker (goal: two-device via source)

> **Status: ACTIVE — started 2026-11-07.** Resumes the crashed session
> `ses_e7662ceaaffefQpA7dZ513aaWO` (died 2026-11-06 22:59 ECONNRESET mid-build).
> This chapter is the **live working document** for the SDK-rebuild route chosen in
> [§30.14.40](30-two-device-plan.md): updates are written here **immediately after
> every step** so a crash never loses state. Companion chapters:
> [ch. 24](24-jieli-ecosystem-sdk-toolchain.md) (ecosystem/toolchain),
> [ch. 25](25-ghidra-decompile-compile-route.md) (decompile⇒compile proof),
> [ch. 28](28-sdk-forks-survey.md) (fork survey + Linux-build gotchas),
> [ch. 29](29-static-analysis-reference-map.md) (VA/RAM reference map).

---

## §32.0 — Why this route

Byte-level patching is exhausted: R1–R7 (ch. 30 §30.14) all field-FAILED — the wall is
the app's single current-device struct (RAM `0x102F0`): the audio bind only happens on
the **app-originated connect flow**, and six in-image levers (force routing byte /
replay cmd 1 / re-dial mailbox / stamp-at-redial / current-device write / direct
bind-block goto) all produced the same goal-miss (TX = first device's mic, RX silent).
NOP-era (ch. 27) proved the same from the other side. A source-level rebuild lets us
write the two-device logic the app never had.

Goal unchanged: **TID-PTT (SPP command button) + Jabra (HFP audio) connected
simultaneously, either order** ([ch. 30 §30.1](30-two-device-plan.md)).

## §32.1 — Phased plan

| Phase | Deliverable | Gate | Status |
|---|---|---|---|
| **P0** | SDK feasibility build: `apps/spp_and_le` for br23 compiles + links + packages on Linux | `app.bin` produced | ✅ **DONE 2026-11-07** (§32.3) |
| **P1** | Flash-gate: SDK-built app packaged as an H3+ image, flashed by user | Radio boots with SDK app (BT discoverable) | ✅ **FIELD-PASSED 2026-11-07** — boots, `JL_SPP` visible, pairs. PTT+3 combo dead on SDK app, but **HID re-flash path PROVEN** (§32.10.2: `work/ch32_hidclient.py` verified end-to-end on hardware) |
| **P2** | Full-image rebuild from `disassembled/` Ghidra C tree (user's original idea) | image functionally matches stock | ⬜ exploratory (§32.6) |
| **P3** | Clean source tree: rename/polish (known names from ch. 29 map), re-glue SDK, single Makefile → H3+ image | reproducible image build from our tree | ⬜ (§32.7) |
| **P4** | Two-device work: SPP + HFP concurrent, inspired by `apps/spp_and_le` + `examples/multi_conn` (BLE-only — inspiration, not template); multipoint APIs `__set_user_ctrl_conn_num` / `__set_hfp_switch` / `__set_hfp_restore` | goal behaviour, hardware-confirmed | ⬜ (§32.8) |

Ordering note: P1 before P2 deliberately — the SDK pipeline (P0/P1) proves
toolchain→image→flash end-to-end with *known-good vendor sources*, which de-risks the
much harder P2 (rebuilding the OEM app from Ghidra output). If P1 passes, P2 becomes
optional: porting H3+ features onto the SDK app may beat rebuilding the OEM app.

## §32.2 — Build environment (reproduce exactly)

```bash
cd work/sdk-forks/Acy19888_fw-AC63_BT_SDK/apps/spp_and_le/board/br23
ulimit -n 8192
PATH=/home/stefan/h3plus/h3plus/work/sdk-shim/bin:$PATH \
  CPU=br23 APP_CASE=spp_and_le \
  make TOOL_DIR=/home/stefan/h3plus/jieli-linux-toolchains-20250324.1/pi32v2/bin -j8
```

- Fork: `Acy19888_fw-AC63_BT_SDK` @ HEAD `8f72ada` (the fork with green Linux CI for
  its own product — ch. 28 §28.4). Toolchain: JieLi Linux `pi32v2` (clang, `-mcpu=r3`).
- Output: `cpu/br23/tools/{sdk.elf, app.bin, sdk.map, symbol_tbl.txt, *.lst}`.
- Logs: `work/logs/sdk_feasibility_{1,2,3}.log` (round 1 = link fail, 2 = link OK +
  post-build cwd fail, 3 = **full pass**).

## §32.3 — P0 result: FEASIBILITY BUILD PASSED (2026-11-07)

~200 sources compile, link OK, post-build produced `app.bin`:

| Artifact | Size |
|---|---|
| `cpu/br23/tools/sdk.elf` | 2,755,092 B |
| `cpu/br23/tools/app.bin` | **218,812 B** (= `text.bin` 199,656 + `data.bin` 19,132 + empty overlays) |
| `cpu/br23/tools/sdk.map` | 213,429 B |

Fixes applied (all in the fork working tree, uncommitted — see §32.4 diff list):

1. **Link fix (the round-1 blocker):** `--allow-multiple-definition` added to LFLAGS in
   `apps/spp_and_le/board/br23/Makefile` (after `--dont-complain-call-overflow`, ~L490).
   Round-1 errors were `multiple definition of lmp_ch_update_resume_hdl /
   update_result_get / exception_analyze` (app `apps/spp_and_le/modules/misc.c` vs
   `cpu/br23/liba/update.a` + `debug.c.o` bitcode). Proven pattern from the zuupah_pen
   fork CI; linker keeps the app's `misc.c` definitions.
2. **Post-build cwd fix:** Linux branch of the Makefile:
   `RUN_POST_SCRIPT := bash $(POST_SCRIPT)` → `cd $(TOOLS_DIR_ABS) && bash download.sh`
   with `TOOLS_DIR_ABS := $(abspath ../../../../cpu/br23/tools)` — ported verbatim from
   the fork's proven `apps/zuupah_pen/board/br23/Makefile` L60–61. (Upstream spp_and_le
   Linux branch ran `download.sh` from the app dir, so `sdk.elf`/sections were not
   found; `link` itself had already succeeded by then.)
3. **`/opt/utils` coupling removed:** `cpu/br23/tools/download.c` — dropped the
   `/opt/utils/` prefix from `remove_tailing_zeros` + `strip-ini` so they resolve via
   PATH (shim). `download.sh` is generated from `download.c` every build — always edit
   the `.c`.
4. **Build-host shim** `work/sdk-shim/bin/` (platform-independent Python, MIT):
   `host-client` (no-op stub — real packaging is ours, §32.5), `remove_tailing_zeros`
   (working: strips trailing mark byte), `strip-ini` (passthrough), `lz4_packet` (emits
   empty `-o`; spp_and_le has no audio overlay banks).

## §32.4 — Fork working-tree state (uncommitted deltas vs HEAD 8f72ada)

- `apps/spp_and_le/board/br23/Makefile` — L1 fix + post-build cwd fix (this session).
- `cpu/br23/tools/download.c` — `/opt/utils/` prefix removal (this session).
- `cpu/br23/sdk_used_list.used`, `cpu/br23/tools/isd_config.ini`,
  `cpu/br23/tools/download.sh`, `*.objs.txt`, `*.resolution.txt` — **generated** by
  pre_build/post-build, not authored.

## §32.5 — P1: flash-gate design (IN PROGRESS — entry fixed 2026-11-07)

The fork was tuned for the author's **AC695N** (board cfg
`apps/spp_and_le/board/br23/board_ac635n_demo_global_build_cfg.h` had
`CONFIG_ENTRY_ADDRESS = 0x1D000C0`, `CONFIG_CHIP_NAME AC693X`, PID `Zuupah_Pen`).
**Entry RESOLVED 2026-11-07 = `0x1E00100`** with hard evidence from the stock image:
`work/app_dec.bin` header offset `0x04` = `00 01 E0 01` (LE `0x01E00100`) and stock code
starts exactly there — `work/full.lst`: `01E00100 call 0x01E2D930` (header occupies
app+0x00–0xFF; app code @flash `0x5100`, matching the ch. 24 map). Ch. 28 §28.7's
TID-OEM override `0x1E00100` confirmed; the SDK default `0x1E00120` is NOT what this
radio uses. Board cfg now reads `CONFIG_ENTRY_ADDRESS 0x1E00100`, `CONFIG_CHIP_NAME
AC635N`, `CONFIG_PID H3Plus` (chip name/PID affect only the SDK's own packaging ini —
ours is manual anyway). Rebuilt round 4 (`work/logs/sdk_feasibility_4.log`, EXIT=0):
`sdk.elf` entry = **`0x1e00100`** (readelf, Machine `0xf1`), `app.bin` 218,812 B; its
first instructions mirror the stock prologue shape (`call …; sr14=…; sr14=…`).

Steps:

1. ~~Set `CONFIG_ENTRY_ADDRESS`~~ ✅ **DONE — `0x1E00100`** (evidence above); rebuild +
   `readelf` entry verified. Cross-check `isd_config.ini` flash base/size for 1 MiB
   when packaging (SDK ini is reference only).
2. ~~Rebuild → `app.bin`~~ ✅ **DONE** — plaintext, VA-based at `0x01E00100`.
3. Package the H3+ image ourselves (the `host-client` stub intentionally does nothing):
   ✅ **DONE 2026-11-07 — `work/ch32_p1_pack.py`** (stdlib Python, MIT). Semantics found:
   `jl_sfcenc.py` processes and writes ONLY its input segment (`--start=0` on a standalone
   segment file), so the packager encrypts the 0xC3FE0-byte app segment separately and
   splices it. Image `work/ch32_p1.bin` (1 MiB) sha256 `c1e090e3da61648d…` =
   stock uboot + stock 0x100-byte app header (entry field `0x01E00100` kept — header
   size/CRC fields are NOT checked at boot: every byte-patched image ever flashed boots
   with them stale) + SDK `app.bin` 218,812 B @flash `0x5100` + 0xFF pad; base =
   `Dumps/dump_pre_ch30.bin` so the 32 device bytes @`0x0C8FE0` + VM ride along
   untouched. Verified: SFCENC round-trip byte-exact; uboot region + `0x0C8FE0+`
   identical to dump; `code0` ORIGIN `0x01E00100` in `sdk.map`, data LMA immediately
   after text (flat `app.bin` placement consistent). 196 sectors differ vs R7
   (`0x05000..0xC8000`) → `work/ch32_p1_sectors/%05X.bin`.
   Sub-bullets (original design, all satisfied):
   - bootloader/uboot region: keep the **stock OEM bytes** from the user's dump (do NOT
     try the fork's SDK uboot first — the fork hybrid v2
     (`cpu/br23/tools/create_hybrid_v2.ps1`, AC695N-specific) is concept-reference only),
   - app region: our SDK `app.bin` at app offset 0 → flash `0x5000`, re-encrypted with
     `tools/jl_sfcenc.py` (symmetric — ch. 24),
   - **splice the 32 device-specific bytes @`0x0C8FE0`** from the user's dump,
   - VM region: leave the radio's existing VM intact (use `--sectors`, NOT erasechip).
4. ✅ **DONE — `work/ch32_p1.sh`** (user-run, ch. 30 pattern): preflight sha
   `c1e090e3da61648d`, 196×erase+write+readback (2 attempts), full 1 MiB read +
   strict-region `0x0000–0x0C8FDF` byte-compare (§30.3), boot Q&A. Rollback **recipe**
   (no script, directive 2026-11-03): re-write the same 196 sectors from
   `work/ch30_e7ref.bin` (`90bec320…`).
5. Gate S1 (field): radio boots, BT advertises the SDK app's name — expect
   **`JL_SPP`** (string in `app.bin`) — and pairs. Audio/PTT NOT expected
   (SDK app ≠ H3+ app) — boot + BT is the proof the pipeline is real.

Rollback safety: radio currently on R7 `575e593d`; daily-use rollback = 2 sectors
`0x066000`+`0x0AC000` from `work/ch30_e7ref.bin` (`90bec320…`). A P1 experiment writes
only the app region sectors — full recovery from the user's stock dump remains possible
(never erasechip).

## §32.6 — P2: full-image rebuild from `disassembled/` (exploratory)

`disassembled/` (Ghidra 12 + ghidra-jieli, 6558 functions decompiled; ch. 25) is the
OEM app's C source. Round-trip per-function recompile is hardware-proven (ch. 25
`rt_test.bin`); whole-image link is the untested leap: needs a linker script pinning
every function to its original VA (Ghidra addresses are known-good), data/bss at the
RAM VAs, and fixing Ghidra's decompiler artifacts (pointer arithmetic, aliasing) until
it compiles at `-Oz` with JieLi clang. Fallback strategy if P1 passes: skip wholesale
rebuild; instead port OEM features (menu, SPP protocol `+SPP=P/R`, display) onto the
SDK app incrementally, function-by-function, using the decompiled C as reference.

## §32.7 — P3: clean tree + re-glue

New folder (under `work/`, gitignored — JieLi SDK is vendor code; repo publishes no
firmware): `work/h3plus-sdk/` = fork tree + our renames (ch. 29 reference-map names:
classifier `0x01E7EC28`, kick `0x01E5B22A`, conn slots `0x1A5B8` stride `0x1C`, routing
byte `0xB464`, …), H3+ board cfg (BR23/AC635N, 1 MiB, entry `0x1E00120`), one top-level
Makefile: `make image` → flashable encrypted image with device-bytes splice.

## §32.8 — P4: two-device work

`apps/spp_and_le/examples/multi_conn` is **BLE-only** — architecture inspiration only.
Real levers: btstack API decls in `include_lib/btstack/avctp_user.h` —
`__set_user_ctrl_conn_num` (L479), `__set_hfp_switch` (L600), `__set_hfp_restore`
(L605); pools are already 2-slot in the vendor libs (ch. 27 §27.1); the eviction/
single-device policy we are replacing lives in OUR app layer, so writing a two-device
app around the prebuilt stack libs is exactly the unblocked path. Design from
§30.14.17–19 findings: accept incoming ACL + SPP session per-device (no
single-session `0x1A740` chokepoint), bind HFP/SCO to the audio device explicitly.

## §32.9 — Session log (append-only; newest last)

*(See also §32.10 — bootloader-entry incident after the P1 flash.)*

- **2026-11-07** — Session resumed from crash. Round-1 state recovered: fork built to
  LINK, failed on multiple definitions. Applied fixes 1–4 (§32.3). Round 2: link OK,
  post-build cwd fail → fix 2. Round 3: **full pass, `app.bin` 218,812 B.** Found AC695N
  entry-address landmine (§32.5 step 1) — must fix before any flash. This document created.
- **2026-11-07** — Entry landmine RESOLVED: stock `work/app_dec.bin` header @0x04 =
  `0x01E00100` and `work/full.lst` shows code starting exactly at `01E00100`
  (`call 0x01E2D930`) ⇒ TID entry = **`0x1E00100`** (not the SDK default `0x1E00120`).
  Board cfg edited: `CONFIG_ENTRY_ADDRESS 0x1E00100`, `CONFIG_CHIP_NAME AC635N`
  (fork had AC693X/`0x1D000C0`/Zuupah_Pen for the author's AC695N), `CONFIG_PID H3Plus`.
  Round-4 rebuild EXIT=0 (`work/logs/sdk_feasibility_4.log`): `readelf` entry =
  `0x1e00100` ✅, `app.bin` 218,812 B, prologue shape matches stock. NEXT: §32.5 step 3
  — P1 packaging script (`work/` Python: stock uboot + header + SDK app at app+0x100,
  SFCENC re-encrypt, splice 32 device bytes @`0x0C8FE0`) + printed flash commands.
- **2026-11-07** — **P1 IMAGE BUILT + VERIFIED (static) — awaiting user flash.**
  `work/ch32_p1_pack.py`: discovered `jl_sfcenc.py` processes/writes only its input
  segment → encrypt the 0xC3FE0 app segment standalone, splice into
  `Dumps/dump_pre_ch30.bin` base. `work/ch32_p1.bin` (1 MiB) sha256 `c1e090e3da61648d…`:
  stock uboot + stock header (entry `0x01E00100`; size/CRC fields proven inert at boot by
  the whole patched-image history; std CRC32 of stock app ≠ field, irrelevant anyway) +
  SDK app 218,812 B @`0x5100` + 0xFF pad; device bytes + VM byte-identical to dump;
  SFCENC round-trip exact; `sdk.map` `code0` ORIGIN `0x1e00100` + data LMA contiguous.
  196 differing sectors vs R7 exported → `work/ch32_p1_sectors/`. Staging script
  `work/ch32_p1.sh` (ch. 30 pattern; bash 5.3 gotcha: nested `$(( ))` in `$( )` is a
  parse error — use `for (( ))`). NEXT: user runs `sudo bash work/ch32_p1.sh`; gate =
  boots + `JL_SPP` discoverable (§32.5 step 5).
- **2026-11-07** — **P1 FIELD RUN = GATE PASSED + BOOTLOADER-ENTRY INCIDENT.** User
  ran `sudo bash work/ch32_p1.sh`: flash clean, **Q1 boots YES, Q2 `JL_SPP` visible
  YES, Q3 pairs YES** ⇒ the SDK-compiled image runs on H3+ hardware — **P1 PASSED**,
  the SDK pipeline is real. BUT afterward the PTT+3 (+`8`) uboot-entry combo no longer
  works — radio cannot be put into download mode from the SDK app. Analysis §32.10.

- **2026-11-07 (later)** — Bootloader-entry incident progressed: HID face identified as the
  JieLi official **fw-Bootloader** upgrade protocol, fully cracked incl. keys; client
  `work/ch32_hidclient.py` built (self-tests green). Details + recovery plan: §32.10.2.

- **2026-11-07 (final)** — HID protocol field-verified end-to-end: `info` handshake OK,
  chip CRCs == crc16-XModem of `work/ch32_p1.bin` @`0x5000` (4/4), then
  **`restore work/ch30_e7ref.bin` PASSED — 196/196 sector CRCs, radio rebooted to E7
  daily driver**. Tool promoted to **`tools/jl_hidboot.py`** (Tools.md §10, ch. 17
  index row). Radio state: **E7-ref `90bec320`**. Next phase per §32.1: P2/P3 decision.

## §32.10 — Bootloader-entry incident (2026-11-07, radio on P1 SDK image)

**Symptom.** With the P1 SDK demo app running, "hold PTT + `3`, power on" (and the
alt `8` from standby, README §1) no longer enters the JieLi USB bootloader. Flash
regions: uboot `0x0000–0x4FFF` **byte-identical to stock** (kept from the dump),
VM untouched, 32 device bytes intact.

**Mechanism (established from `jl-uboot-tool/docs/how-to-enter-uboot.md` + SDK
`apps/common/update/`):** on BR23 the download-mode entry points are
1. **MaskROM USB_KEY** — a 16-bit key `0x16EF` bit-banged on the USB lines
   (D- clock, D+ data) at every power-on; what the vendor updater *dongle* does.
   Independent of flash content. `jl-uboot-tool` does **not** implement sending it.
2. **NVRAM/VM boot-mode tag** — the *running firmware* sets an update flag
   (SDK: `update_mode_api_v2(USB_UPDATA, …)` / `VM_UPDATE_FLAG` via `syscfg_write`)
   then `cpu_reset()`; ROM/uboot then stays in download mode.
3. **Boot-failure fallback** — ROM enters download mode automatically if the flash
   has no valid firmware (blank chips boot straight into it).

The README note "*on later firmware versions, holding `8` from regular standby may
also trigger USB upgrade mode*" proves the H3+ combo is handled by the **OEM app**
(path 2): the OEM app checks the keys at boot/standby and calls the SDK update
entry. The SDK `spp_and_le` demo app contains no such handler (no `update_mode_api`
call; `USER_UART_UPDATE_ENABLE=0`), so with the P1 image the combo is dead. The
uboot itself does not scan the keypad (`CONFIG_UART_UPDATE_PIN PB05` is an
app-level UART-init define, not a uboot key check). **UNTESTED caveat:** user may
also simply have never achieved a true power-on-reset — if the SDK demo app does not
drive the H3+ power latch, knob-"off" may not power down the chip, so knob-"on" is
not a POR and path 3 never triggers.

**Recovery ladder (cheap → hardware):**
1. True POR: radio off, **pull the battery** ≥30 s, reinsert/power on while holding
   PTT+3 (also try `8` alone, PTT alone, `3` alone), side USB-C plugged, watch
   `dmesg -w` / `python3 jldevfind.py` for a `BR23 UBOOT`-type device.
2. If still unreachable: **SPI programmer restore** — CH341A-class programmer +
   SOP8 clip on the 1 MiB NOR inside the radio; write back `work/ch30_e7ref.bin`
   (`90bec320…`, daily-driver) or `Dumps/dump_pre_ch30.bin`. 100% recoverable — the
   flash content is fully known and the chip cannot be bricked (ROM path 3 only
   needs *invalid* firmware, and the clip can always rewrite everything).
3. USB_KEY dongle build (bit-bang `0x16EF` per the doc waveform at POR) — restores
   in-place flashing without opening the case, for future experiments.

**Lessons (binding for P2+):**
- Any custom app we ship **must implement the uboot-entry combo** (SDK
  `update_mode_api_v2(USB_UPDATA, …)` + `cpu_reset()`, keys checked early at boot) —
  non-negotiable, else every experiment risks a case-opening.
- Before any future full-image flash, secure a recovery path first (clip programmer
  or verified combo works on the image being replaced).
- P1 staging script's note "bootloader still reachable (sector 0 untouched)" was
  **wrong** — sector-0 integrity does not imply entry is reachable when the
  *app-layer* trigger is gone. Corrected here.

**Recovery attempts log (2026-11-07):** user first tried a CH340-based "Kenwood"
serial cable on the port — dmesg enumeration loop (`device descriptor read/64,
error -71`). Expected and a dead end: uboot download mode is **native USB HID on
the side USB-C port** (the plain data cable that flashed P1 works), and the
uboot's UART listener is only active *after* download mode is entered. Instructed:
battery-pull POR + PTT/3/8 key variants with the good cable while running
`jldevfind.py`; if unreachable, route A = CH341A SPI clip restore
(`work/ch30_e7ref.bin`) or route B = USB_KEY (`0x16EF`) bit-bang dongle at POR
(MaskROM-level, firmware-independent). Awaiting user result.

### §32.10.1 Recovery investigation 2026-11-07 (same day, later) — the HID face

User found **PTT + 1 + power-on** enumerates USB `4c4a:4155` "Jieli Technology USB
Composite Device" — one interface, class 3 (HID), EPs 0x82 IN / 0x02 OUT, bound to
`/dev/hidraw4`. Live report descriptor (sysfs, world-readable):
`06 00FF 09 01 A1 01 09 02 16 0000 26FF00 75 08 95 40 81 02 09 03 16 0000 26FF00
75 08 95 40 91 02 C0` = vendor usage page 0xFF00, **64-byte INPUT + 64-byte OUTPUT
reports, no report IDs** — structurally the SDK `custom_hid.c` face (`sHIDReportDesc`,
64 B max packets).

**Identity: almost certainly the OEM uboot, not the SDK app.** Proof chain: the built
SDK app has NO USB device code — board cfg `TCFG_PC_ENABLE = DISABLE_THIS_MOUDLE` ⇒
`TCFG_USB_SLAVE_ENABLE 0` (`usb_common_def.h:106/132`) ⇒ `task_pc.c`/`custom_hid.c`
compile to **zero-length .text** (confirmed in `sdk.map`). And the decrypted OEM uboot
(`Dumps/dump_pre_ch30.bin` `0x0000–0x4FFF`, LFSR phase 32591 → `/tmp/opencode/uboot_dec.bin`)
contains HID strings: `**BootLoader**`, `[hid]ASSERT ... hid set interface_hander fail`,
`hid_reset`, `setup_interface`, `<Error> [hid]%s`, `jump to %x`, `wait uart cmd`,
`isd_config.ini`, `UARTUPDATE`, `jlfs_check_all_head`, flash-pgm wait — a full USB-HID
download face alongside the MSC face.

Why PTT+3 worked before P1 but not after: PTT+3 is handled by the **OEM app** (sets the
update flag → reset → uboot MSC `UBOOT1.00` at `/dev/sg2`, per `work/logs/ch32_P1_*.log`).
The SDK app has no such handler. PTT+1 + POR instead trips a **uboot/boot-ROM-level**
entry straight to the HID face (exact mechanism UNCONFIRMED — boot ROM key-sample vs
uboot sub-mode; the OEM app was not involved since the flash already holds the SDK app).

Tooling status for the HID face:
- `jl-uboot-tool` = SCSI-only (`scsiio/linuxport.py` SG_IO ioctl; no hidraw anywhere) —
  cannot speak to it yet.
- Official **Linux `isd_download`** (`cpu/br23/tools/isd_download`, static x86-64) now
  **RUNS** on Ubuntu 26.04 after extracting `libicu55_55.1-4ubuntu1_amd64.deb`
  (old-releases.ubuntu.com) to `/tmp/opencode/icu55/x` +
  `LD_LIBRARY_PATH=/tmp/opencode/icu55/x/usr/lib/x86-64-linux-gnu`. Interactive usage:
  `open <disk volume>` / `ds` / `st` / `wr <type> <sdram file> [addr]` / `wd <fw> [addr]` /
  `ed <addr> <len>` — but `open` expects a **mass-storage volume**, i.e. the MSC face
  again. Its ini flow (`DOWNLOAD_MODEL = USB`) is also MSC-based.
- ⇒ Gap = **HID transport shim**: same loader-protocol CBs (jltech/uboot.py: 16-byte CB,
  opcode/sub-opcode BE, pad 0xFF, 16-byte response packet) very likely framed into the
  64-byte HID reports. NEXT: probe `/dev/hidraw4` (needs root; user-run) with candidate
  framings — raw CB in 64-byte OUTPUT report, then read IN reports; uboot disasm
  (`/tmp/opencode/uboot_dis.txt`, VA-base guess wrong, mostly data — RE pending) can
  confirm framing if probing is silent.

Radio state after all this: normal power-on boots the P1 SDK app (user-confirmed);
nothing was written at this point. RESOLVED same day — see §32.10.2: the HID face was
cracked and `restore work/ch30_e7ref.bin` ran clean (196/196 sector CRCs verified,
radio rebooted to the E7 daily driver).

### §32.10.2 HID upgrade protocol CRACKED 2026-11-07 — it is the JieLi official fw-Bootloader

The report-descriptor bytes from the live device (`06 00 FF 09 01 A1 01 ...`) were
found at offset `0x42D8` in the decrypted OEM uboot, next to source paths
`E:\work\fw-Bootloader-main\user_boot\app\src\hid.c`. The OEM uboot IS the official
**JieLi-Tech/fw-Bootloader** (GitHub, cloned to `/tmp/opencode/fw-Bootloader`) — which
ships the PC-side reference client `update_tools/win-usb_hid/main.cpp` (Qt/hidapi).
Protocol ("JL SU"), 64-byte HID reports, all LE:

- Frame: `AA 55 | cmd_len u16 | body | crc16 u16`. Body = `cmd u8 | status u8 | params`
  **XOR-encrypted** with the 4-byte key = u32 `communication_key = 12345678`
  (`4E 61 BC 00`, cycling from body byte 0). CRC-CCITT **XModem** (poly 0x1021, init 0,
  verified vs official table fn + `0x31C3` test vector) over sync+len+**encrypted** body.
  Confirmed both sides: `user.c:enc_cmd_data()` / `set_remain_and_upgrade_rsp()`.
- Commands: `0xC0 DEVICE_INIT` (file_name[16]+mode; opens JLFS file — uboot's own
  default is `app_dir_head`; rsp: upgrade_addr/len/eoffset/alignsize), `0xC1
  DEVICE_CHECK` (sdk_id u32 == `0x12345678`; rsp vid[4]+pid[16]+sdk_id), `0xC2 ERASE`
  (addr+type 1/2/3 = 256/4096/65536), `0xC3 WRITE` (addr+len+data, ≤40 B/packet),
  `0xC4 FLASH_CRC` (addr+len+block_size → u16 crcs per block, max 16/packet),
  `0xCA REBOOT`. **No READ command** — verification is by CRC only. Addresses are
  relative to the INIT-opened file (`jlfs_fseek`); `app_dir_head` addr 0 == flash
  `0x5000` (assumed — `crcfile` subcommand settles it empirically).
- **Keys NOT customized by TID**: comm_key `4E 61 BC 00` @uboot_dec `0x3F20`,
  sdk_id `78 56 34 12` @`0x194E`. First raw-CB probe (no AA55/XOR/CRC) correctly got
  silence — the framing above is the missing piece.
- Official write sequence quirk (`main.cpp`): per 4K unit — erase, write bytes
  `32..4096` first, then `0..32` **last** (header-with-CRC written last). Replicated.
- **App-side uboot entry magic** (for our future SDK apps): write
  `{'u','b','o','o','t',0x5A,'s','t'}` to `NV_RAM_LIST_ADDR` then reset → uboot runs
  `uboot_check_upgrade_magic()` and stays in upgrade mode. This is how P2+ builds make
  themselves flashable without PTT combos.
- Client: **`tools/jl_hidboot.py`** (stdlib MIT, root/hidraw; promoted from
  `work/ch32_hidclient.py` 2026-11-07 at user request — documented in `tools/Tools.md`
  §10 + `findings/17`): `info` / `crcfile <img> [addr0] [nblk]` (read-only) /
  `restore <1MiB img> --yes` / `reboot`.
- **RESTORE FIELD-PASSED 2026-11-07**: `sudo python3 tools/jl_hidboot.py restore
  work/ch30_e7ref.bin --yes` → 196/196 sectors written, **all 196 block CRCs
  verified**, auto-reboot. Radio back on the E7-ref daily driver (`90bec320…`);
  P1 SDK image retired to disk (`work/ch32_p1.bin`). The HID channel is now the
  project's universal re-flash path for combo-less custom images.
  Status: **FIELD-VERIFIED 2026-11-07** — `info` run on the radio: CHECK status=0
  (sdk_id echoed; response layout slightly shifted vs guess — `vid` bytes read
  `30 2E 30 31` = version string "0.01"), INIT(`app_dir_head`) →
  upgrade_addr=**`0x5000`**, len=0xFFFFFFFF (unbounded), alignsize=4096, and
  FLASH_CRC 0..3x4K = `5AE8 890D F65D C719` = **byte-exact crc16-XModem of
  `work/ch32_p1.bin` flash `0x5000+` (encrypted bytes)** — transport, framing, CRC
  variant and address mapping ALL CONFIRMED (e7ref/dump CRCs differ as expected).
  `restore` hardened: INIT len is unbounded → span capped to flash
  `0x5000..0xC9000` (196 sectors, VM untouched, device bytes inside last sector).

Recovery ladder (updated): (1) `ch32_hidclient.py restore work/ch30_e7ref.bin --yes`
via HID — restores daily driver AND proves the re-flash path for all future images;
(2) SPI clip; (3) official `UbootHid.exe` (in `update_tools/win-usb_hid/build-out-bin/`)
under Wine if the Python client hits a snags.
