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

### §32.6.1 P2 kickoff 2026-11-08 — compile-feasibility harness (`work/ch32_p2_survey.py`)

Inventory: `disassembled/decompiled/` = **6,492 per-function .c files**
(`<addr>_FUN_<addr>.c`, self-contained Ghidra output, no headers);
`symbols.txt` 27,833 entries (incl. RAM `DAT_` labels); `full.lst` + `functions.txt`
(addr/size/name). Toolchain for the survey: JieLi clang 4.0.1
`-target pi32v2 -mcpu=r3 -Oz -std=gnu89 -w -include prelude.h`.

Harness design (what the eventual P2/P3 build needs anyway):

- **Generated prelude** (`work/ch32_p2/prelude.h`, ~16.7k lines): Ghidra typedefs
  (`undefined1..8`, `code`, `byte/word/dword`, `CONCAT`-free), `BADSPACEBASE`,
  `bool/true/false`, `extern` fallback decls for `in_sp`-style register pseudos, and
  `extern unsigned int DAT_x;` for every data symbol (widths approximate — link-time
  addresses are what matter; narrow accesses keep working via `(byte *)&DAT_x` casts
  the decompiler emits).
- **FUN_ symbols are NOT prototyped** (would conflict with the real definitions in the
  same TU): calls rely on gnu89 implicit-int declarations (warnings suppressed).
  Functions used as **values** (`pcVar1 = FUN_01ec2c38;`) get per-invocation
  `-DFUN_x=((int(*)())0xADDR)` macros (address parsed from the symbol name; own-symbol
  excluded).
- `symbols.txt` sanitizing: skip non-C identifiers (`FUN_01e077cc+1` offset symbols)
  and keywords (`default` label).

Survey iterations (5 rounds, all fixes in the harness): 91.2% → 94.8% (`code` as K&R
function TYPE `typedef int code();` — not a macro, not a fn-ptr typedef) → 95.8%
(pseudo-var rewrites `uRamNNNN`/`iRamNNNN`/`pcRam`/`&stack(0xN)`/`switchD_x::caseD_y`
→ `uintptr_t` casts; `BYTE_/WORD_/UNK_/PTR_/PTR_FUN_` address macros from a body scan;
`&LAB_x` → `((unsigned int *)(uintptr_t)0x..)` only when the label is NOT defined
in-file) → 98.3% (BADSPACEBASE→`void`, `uint3` struct, DAT-as-callee `(*DAT_x)(...)`
→ call through value, DAT subscript) → **6388/6491 = 98.4%** final (per-file retry
with `-DJL_CODE_STRUCT` rescues `code`-as-data files). One nasty bug caught and fixed
on the way: a loose `* _DAT_x` deref rewrite was silently matching **multiplication**
(`b * _DAT_x`) and corrupting expressions — the rewrite is now context-aware
(preceding-char check), confirmed by the fail-class census (22→2 'subscript int()',
6→2 'called object uint').

**P2 FEASIBILITY VERDICT (compile): FEASIBLE.** 103 residual failures, all in small
hand-fixable classes: 17 bare `* _DAT_x` deref forms, ~23 mixed `code`-type use files
(call AND data in one TU — need per-file manual `typedef` choice), ~15 Ghidra parse
artifacts (`expected )`/statement), 5 `undefined4`-field/`uint3`, 2 cross-file `LAB_`
refs, 2 misc. None indicate a structural problem; each gets a targeted sanitize rule
or a small override list. Results: `work/ch32_p2/survey.json` (fails{name→class}),
per-file stderr `work/ch32_p2/fails/`, log `work/logs/ch32_p2_survey.log`.

**Next milestone = P2b LINK harness** (design pending): per-function sections +
generated linker script pinning all 6,492 VAs (from `functions.txt`), stock data blobs
kept verbatim, then boot test. Caveats to settle there (not compile blockers): (1) implicit-int
return-type mismatch on ~all cross-function calls — semantics preserved on pi32v2
(32-bit reg returns) EXCEPT pointer-returning funcs called into 64-bit contexts —
audit later; (2) `DAT_` declared uint where original was byte/short — alignment +
read-width risk on RAM aliases; (3) `_DAT_`/`&DAT_` forms; (4) switch jump tables
(`switchD_` labels are file-local — fine); (5) the LINK step (per-function sections +
linker script pinning 6,492 VAs + stock data blobs) — next milestone, not in survey
scope.

### §32.6.2 P2b LINK harness design 2026-11-08 (micro-test passed, full run pending)

Concept (proved end-to-end on a 2-function micro-test in `/tmp/opencode/p2b`):
**pin every recompiled function onto its exact stock VA; everything not recompiled
stays stock bytes.**

- Toolchain facts: JieLi clang accepts `-ffunction-sections` (sections
  `.text.<fn>`; verified ELF32-pi32v2); `ld` is lld-in-GNU-script-mode — note
  **`. = ADDR` INSIDE an output section is section-RELATIVE** (first attempt
  silently misplaced code at 0x03c00200); the working form is **one output section
  per function with an explicit VMA**: `.f<name> 0x01E00100 : { KEEP(obj(.text*)) }`.
  Cross-function `call` sites relink correctly (verified in disasm).
- Data symbols: every `symbols.txt` name that is a valid C identifier gets
  `PROVIDE(name = 0xADDR);` (absolute) — code reading `DAT_x` becomes an
  absolute-address access; no RAM blob needed to LINK. Pseudo-registers
  (`in_sp`/`in_lr`/...) `PROVIDE`=0 (functions legitimately using them should be
  excluded from recompile — audit `fit.json`).
- **Fit rule**: compiled size ≤ stock size (from `functions.txt`) → include;
  overflow → EXCLUDE (stock bytes keep that function). Shrunk functions leave gaps
  filled from stock (harmless). `--no-check-sections` guards nothing semantic —
  the fit pass is the real overlap prevention.
- Extract: `objcopy -O binary -j .f<name>` per function → splice into a copy of
  `work/app_dec.bin` → `work/ch32_p2/p2_spliced.bin` → package exactly like
  §32.5 (`ch32_p1_pack.py` pattern: stock header + SFCENC + device bytes).
- Harness: **`work/ch32_p2_link.py`** (stdlib MIT; reuses survey's prelude +
  sanitize + value_uses; `--compile-only`/`--link-only`/`--jobs N`; outputs
  `work/ch32_p2/{objs/,fit.json,p2.ld,p2.elf,p2_spliced.bin}`).
- Known residual risks (to be read off `fit.json`): % overflow under `-Oz`
  (ch. 25 round-trip said sizes come out close, not identical); jump tables
  emitted per-function may push size; `in_sp`-using functions are semantic no-gos;
  103 survey-fail functions stay stock (fine — subset gate, §32.6 fallback).

Verdict criteria for P2 gate (downgraded per §32.6 fallback): image BUILDS, links
clean, splices ≥90% of function bytes, boots on radio with BT working = PASS
(functionally-matches-stock remains the stretch goal).

### §32.6.3 P2b LINK + SPLICE + PACKAGE PASSED 2026-11-08 (image ready for flash gate)

Debug rounds (each a link run, logs `work/logs/ch32_p2_link{2..14}.log`): PROVIDE
hex prefix (octal-parse), EXT_FUN_ name-embedded addrs, `_DAT_x` aliases,
`func_0x<hex>` ROM externals, thunk-file exclusion, `halt_baddata` → stock
self-jump `0x01E24750`, CONCAT11..44 + ZEXT48 macros, `switchD_*_caseD_*` →
PROVIDE-at-own-VA (14), `-ffreestanding -fno-builtin` (memset libcalls), inline-asm
statement-expr macros for the pspec intrinsics (`nop/sti/cli/csync/hbkpt/idle/
syscall/lockset/lockclr`, `LZCOUNT`→`__builtin_clz`), `TODO(x)`→`((void)(x))`,
files using unmodelable intrinsic forms (SoftwareInterrupt etc.) excluded.

**Final (link14): `ld` rc=0. FIT: 2172 fit, 809 OVERFLOW, 605 in_sp-excluded,
14 caseD-provided, 2766 unknown(fake/thunk/nosize). Spliced 2166 functions** (6
skipped: linker appends branch **veneer thunks** to section ends → blob > stock
size → clamp `len(blob) > ssz → keep stock`; root cause of 7 out-of-range diff
runs found in the first splice verification).

Verification of `work/ch32_p2/p2_spliced.bin` (802,784 B):
- diff vs `work/app_dec.bin` = 4,980 runs / 58,219 B, **all strictly inside the
  fitted stock slots** (boundary "crossers" = adjacent fitted fns, false positives);
- entry bytes @0x100 identical;
- disasm spot-check (`tools/pi32dis.py` @0x01E05BC0): rebuilt function is
  semantically IDENTICAL to stock — same control flow, only register-allocation
  diffs; ROM `call 0x02001634` byte-identical encoding.

Packaged: **`work/ch32_p2_pack.py`** (clone of `ch32_p1_pack.py`; asserts header
untouched + entry `0x01E00100`) → **`work/ch32_p2.bin` (1 MiB) sha256
`74ab0b03…d2af`**; 152 differing sectors vs E7-ref → `work/ch32_p2_sectors/`.

**FLASH GATE (user): radio boots E7-ref now — enter HID mode (PTT + 1 + power-on),
then `sudo python3 tools/jl_hidboot.py restore work/ch32_p2.bin --yes`.** Gate =
boots + BT + PTT work (P1 proved the HID restore path; recovery = same command with
`work/ch30_e7ref.bin` — SAFE ladder).

### §32.6.4 P2 FIELD-FAIL triage + P2b poison-reverted variant 2026-11-08

P2 (`work/ch32_p2.bin` `74ab0b03`) did not boot; radio restored to E7-ref via the HID
path (first live use of the ultimate fallback — the ABSOLUTE RULE earned its keep).

Static triage (`work/ch32_p2_triage.py`, screens S1 unknown-decode-delta / S2 bad call
targets / S3 stock-slot-data-likeness / S4 size-collapse / S6 slot-overrun; boot BFS from
the crt0 stub seeds `0x01E2D930`, `0x01E80EEE`, `0x01E5B67A`, `0x01E5CC42` — direct-call
BFS reaches only 25 fns, boot is table-driven): 834/2172 fitted flagged. `.rodata`
hypothesis DEAD (p2.elf has zero rodata bytes — `-Oz` inlines all constants).

**POISON HYPOTHESIS (prime suspect):** 235 spliced functions contain
`call 0x01E24750` (`halt_baddata` PROVIDE = stock self-jump = INFINITE HANG);
**193 of them at VA ≥ 0x01E80000** — the high region holding crt0's `.data`-init /
table images (copy srcs `0x01EC2C38` + `0x01EB6140` per the entry stub) that Ghidra
disassembled as "functions". Splicing replaced boot-critical tables with hang-calling
code. Full list: `work/ch32_p2/halters.json` (42 code-region + 193 high-region).

**P2b variant** (`work/ch32_p2b_variant.py`): from `p2_spliced.bin`, restore STOCK over
(a) all 890 fitted slots at VA ≥ 0x01E80000 and (b) all 42 code-region halters →
**1240 rebuilt functions kept**, 43,154 B differ from stock (was 58,219). Packaged via
parameterized `work/ch32_p2_pack.py <plain> <out> <secdir> p2b` →
**`work/ch32_p2b.bin` sha256 `e6dd4208…`**, **120 sectors** vs E7-ref →
`work/ch32_p2b_sectors/`. Stage script **`work/ch32_p2b.sh`** (jluboottool PTT+3 path +
uboot-sacredness preflight + readback ×2 + full 1 MiB strict verify; HID fallback
documented inside).

FLASH GATE (user): `sudo bash work/ch32_p2b.sh`.
- **boots** ⇒ hypothesis confirmed — bisect by re-enabling reverted sets (halvers'
  loop), converging on the true poison list while keeping max rebuild coverage;
- **still dead** ⇒ halve the remaining 1240 (P2c/P2d), each round repack + flash.
Rollback recipe (any state): same 120-sector pattern from `work/ch30_e7ref.bin`
(`90bec320`) or HID `tools/jl_hidboot.py restore work/ch30_e7ref.bin --yes`.

### §32.6.5 — P2c: full poison-class revert (2026-11-08)

P2b still did not boot (§32.9), so three MORE static poison classes were added on top
of P2b's (halters, high-region):

- **(d) triage-flagged** code-region slots — all 834 classes from `triage_flags.json`
  (S1 rebuilt decodes worse than stock, S2 invalid call targets, S3 stock slot is
  data-like, S4 size-collapse <40% = Ghidra dropped code, S6 slot overrun).
- **(e) pointer-dense** slots — stock bytes with ≥4 LE u32 pointers into code/ROM/RAM at
  ≥30% word density (tables Ghidra function-ified that S3 missed): exactly 2 hits,
  `0x01E3A000`, `0x01E5033A`.
- **(f) overlap participants** — 30 pairs of fitted slots that OVERLAP each other
  (Ghidra shared-tail/misparse artifacts; splices clobber each other → chimera code);
  57 slots reverted.

Boot-path check: crt0 seeds `0x01E2D930`/`0x01E80EEE`/`0x01E5B67A`/`0x01E5CC42` are NOT
fitted — entry chain is stock in every variant (and P2b's death is therefore NOT from
the first instructions).

Variant: `work/ch32_p2c_variant.py` → 1255 slots reverted (890 high + 42 code halters +
834 flags + 2 pdense + 57 overlap, with set overlaps) → **917 clean rebuilds kept,
29,325 B differ vs stock** (P2: 58,219; P2b: 43,154).
Packaged: **`work/ch32_p2c.bin` sha256 `147b478c1bdf6260…`, 114 sectors
`0x05000..0xC4000`** → `work/ch32_p2c_sectors/`; stage `work/ch32_p2c.sh`
(same discipline: sha + sector preflight, uboot-sacredness assert, 2-attempt
erase/write/readback, full 1MiB strict compare, boot Q&A).

Decision tree: boots ⇒ poison was inside the reverted classes (later: bisect
re-enable to maximize coverage); dead ⇒ halve the 917 kept slots by address (P2d,
log2(917) ≈ 10 rounds worst case, each round = 1 user flash + HID restore).

### §32.6.6 — P2c dead ⇒ ADDRESS BISECT begins (P2d) (2026-11-08)

P2c FIELD-FAILED (log ch32_P2c_20261108_141758.log: 114 sectors + full-flash verify
PASS; Q1-Q5 dead; PTT+1 HID mode still works). Three consecutive deaths spanning
29 KB of "clean" rebuilds ⇒ the poison is a semantically-broken function invisible to
every static screen used so far. Two more static checks run first:

- **Interior-pointer scan** (stock u32 LE words pointing strictly inside kept slots from
  outside): only ONE hit — `0x01E7E97A` (holders @file 0x848e/0x8492). Reverted
  unconditionally from now on (`FORCED` set in the bisect script). Class NOT the
  systematic killer.
- crt0 boot seeds confirmed unfitted (stock) in all variants (§32.6.5).

**Bisect design** (`work/ch32_p2d_variant.py`, generic; arg = keep-fraction):
P2c-kept list recomputed (916 after FORCED), sorted by VA, keep LOWER HALF, revert
upper to stock. DEAD ⇒ poison in kept half (recurse on it); BOOTS ⇒ poison in reverted
half (next round: keep this half + lower suspect half). log2(916) ≈ 10 rounds worst
case; each round = variant + packager + stage script + user flash + HID restore.

**P2d**: keeps 458 fns VA `0x01E004AC..0x01E3532E`, 13,407 B diff vs stock.
Image `work/ch32_p2d.bin` sha256 `017ffb4a33721f06…`, 64 sectors → `work/ch32_p2d_sectors/`,
stage `work/ch32_p2d.sh` (same discipline + uboot-sacredness assert).

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

- **2026-11-08 (P2)** — Compile-feasibility survey converged: **6388/6491 = 98.4%** clean with the JieLi clang after 5 harness iterations (§32.6.1). Verdict: compile route FEASIBLE; 103 residuals are hand-fixable. Next: P2b link harness design.

- **2026-11-08 (P2b)** — link harness converged: `ld` rc=0 after intrinsic/macros rounds; **2166 functions spliced** into stock, diff-vs-stock fully inside fitted slots, spot-check semantically identical; packaged `work/ch32_p2.bin` sha `74ab0b03…` (152 sectors). Awaiting user flash gate. Details §32.6.3.

- **2026-11-08 (later)** — P2 flash staged: `work/ch32_p2.sh` (jluboottool/PTT+3 SCSI route, 152 sectors, per-sector readback + full 1 MiB strict-region verify + stock-v50 boot Q&A; adds a preflight ASSERT that image uboot 0x0000-0x4FFF == stock dump). Absolute rule added to .github/copilot-instructions.md: every image must keep the stock uboot so PTT+1+power-on + tools/jl_hidboot.py remains the ultimate fallback (device cannot be opened/JTAGged).

- **2026-11-08 — P2 FIELD-FAILED (first gate: boots).** Flashed `work/ch32_p2.bin` (`74ab0b03…`, 152 sectors, `work/ch32_p2.sh`): radio does NOT boot. Restored via `tools/jl_hidboot.py`/`work/ch32_hidclient.py restore work/ch30_e7ref.bin --yes` (HID path, PTT+1+power-on — the ABSOLUTE RULE fallback, first live use). Verdict: the 2166-function splice (58 KB/802 KB; static verification all green) still breaks boot — at least one rebuilt function is semantically wrong in the init path. Next: bisect the fitted set (halving) to find the poison function(s), or downgrade to the §32.6 subset fallback. §32.6.3 gate = FAIL.

- **2026-11-08 (P2b)** — FIELD-FAIL triage: rodata hypothesis dead; PRIME SUSPECT = 235 `halt_baddata`-calling splices (193 in the ≥0x01E80000 crt0 data/table region — Ghidra-assembled tables as functions). Built poison-reverted variant: 1240 rebuilds kept (890 high + 42 halters reverted); `work/ch32_p2b.bin` sha `e6dd4208…`, 120 sectors, stage `work/ch32_p2b.sh`. Awaiting user flash gate. §32.6.4.

- **2026-11-08 P2b FIELD VERDICT = DEAD (2nd failure)** — flash itself clean: 120/120 sectors erase+write+readback PASS + full 1MiB strict-region VERIFY PASS (log work/logs/ch32_P2b_20261108_135335.log, image e6dd4208). Boot gate Q1-Q6: dead, no display. PTT+3 download combo dead (app-level, app dead) but **PTT+1+power-on HID works** → jl_hidboot restore path confirmed again. ⇒ poison hypothesis INCOMPLETE: reverting 890 high-region (≥0x1E80000) + 42 code halters still leaves a boot-breaking splice among the remaining 1240. NEW PRIME SUSPECTS: the 95 S3-flagged code-region slots (stock slot decodes ≥25% unknown = DATA tables mislabeled as functions — we compiled code over live tables; triage_flags.json) + S2/S6 (invalid-call/overrun). P2c plan: revert ALL 834 triage-flagged + halters + high region → ~1150 clean rebuilds; boots ⇒ poison in reverted set (bisect), dead ⇒ halve remaining. Restore e7ref first.

- **2026-11-08 (P2c)** — P2b FIELD-DEAD (2nd failure; flash+readback were clean). Added poison classes: 834 triage-flagged, 2 pointer-dense tables, 57 overlapping-slot participants; confirmed crt0 boot seeds unfitted (stock). P2c = 917 clean rebuilds, 29,325 B diff, image `work/ch32_p2c.bin` `147b478c…`, 114 sectors, stage `work/ch32_p2c.sh`. Radio restored to E7-ref via HID. §32.6.5.

- **2026-11-08 (P2d)** — P2c FIELD-DEAD (3rd failure; flash clean again). Interior-pointer scan: 1 hit (0x01E7E97A, force-reverted). Static screens exhausted ⇒ ADDRESS BISECT: P2d keeps lower 458 clean rebuilds (VA 0x1e004ac..0x1e3532e, 13,407 B diff), image `017ffb4a…`, 64 sectors, stage `work/ch32_p2d.sh`. Radio restored to E7-ref via HID between rounds. §32.6.6.

- **2026-11-08 (P2d)** — P2d FIELD-DEAD (4th failure; log ch32_P2d_20261108_150255.log, flash+verify clean). ⇒ poison ∈ lower-458 kept set (VA 0x01E004AC..0x01E3532E, only 13,407 B diff). User directive: prioritize ESTABLISHING a provable modify route (image→split→disasm→editable→assemble→recombine→flash) over bisecting; C-recompile route only returns after identity is proven. New plan §32.6.7: official-objdump asm round-trip.

- 2026-11-08 (P2d field-DEAD, 4th fail): flash-bisect paused per user directive; PIVOT to provable asm round-trip route — §32.11 opened. Window fixed-point PASSED (0x1e00100..0x1e01000, 2 rounds, 5 size-pins, 0 text mismatches); full-image round running.- **2026-11-08 (eve): ASM ROUND-TRIP FIXED-POINT PASS on full app — provable
  route established offline (§32.11.3). Tool = `/tmp/opencode/rtasm/rt_round.py`
  (promotion to `tools/jl_rt_asm.py` in progress). Key HW fact: it-blocks
  predicate ≤4 instrs. Next: E7-ref round-trip image + user flash gate.**

- **2026-11-08 (eve-2): `tools/jl_rt_asm.py` promoted (wrap/dis/round/bin).
  E7-ref app round-trip FIXED-POINT OK (2 rounds seeded by full.pinned); 8/8 E7
  kick sites byte-exact; gate image `work/ch32_rt.bin` 97320845… packaged
  (191 sectors). Awaiting user HID flash + daily-driver-identity verdict
  (§32.11.4).**

- **2026-11-08 (night): radio RESTORED to E7-ref by user; stage script
  `work/ch32_rt.sh` created for the RT gate (jluboottool PTT+3 path, 191 sectors
  0x05000..0xC8000, uboot-sacredness + device-bytes preflight asserts, 2-attempt
  per-sector readback, full-1MiB strict verify, boot Q&A incl. BT-PTT2 expected
  YES). Awaiting user flash verdict.**

- **2026-11-08 (late) RT GATE FIELD-FAILED: `work/ch32_rt.bin` (9732084590ca1abd)
  flashed clean (191/191 sectors readback PASS, FULL-FLASH VERIFY PASS) — app
  DEAD (Q1-Q5 dead; only PTT+1 HID works). 5th consecutive failure, but this is
  the KEY negative result: image = pure asm round-trip of the booting E7-ref,
  disassembly fixed-point OK offline, yet no boot => the fixed-point checker has
  a BLIND SPOT: objdump text does not capture every semantic bit
  (prime suspect: it-block PREDICATION bits living in body words — pinned
  headers + reassembled text bodies lose them; `19 80` vs `19 00` evidence from
  the b1.s micro-test proves body words carry predicate state). User restoring
  e7ref via HID. NEXT: prove predation hypothesis statically (stock vs rt bytes
  around real it-blocks), fix policy = pin whole block (header+body) raw,
  re-round, re-gate.**
| RT | 2026-11-08 20:03 | 9732084590ca1abd… | asm round-trip of E7-ref, 191 sectors | Q1=dead Q2=dead Q3=dead Q4=dead Q5=dead Q6=PTT+3 dead, PTT+1 works, restoring | work/logs/ch32_RT_20261108_200058.log | |
### §32.11.5 — BYTE-EXACT ROUND-TRIP PASS (2026-11-08) — the RT death explained

The RT gate (§32.11.4) flashed DEAD although the objdump-text fixed point held.
Root cause: **text fixed-point is not semantic fixed-point** — 14,430 items
reassembled to different BYTES while decoding to identical text (the assembler
makes legal-but-different encoding choices; at least one class — e.g. `swi`
operand/encoding family, it-block header fields — carries hardware-visible bits
the disassembly text does not show).

FIX: `tools/jl_rt_asm.py round` now continues past text fixed-point into a
**byte-strict pass**: every item whose reassembled bytes differ from stock is
pinned raw (`.short` stock words) and the loop re-runs until zero. On E7-ref:
**BYTE-EXACT OK in 2 rounds** (14,430 new pins; final emit 263,694 text instrs +
48,170 raw shorts + 1,025 closers; 15,783 pinned total).

PROOF (zero flash cycles):
- `e7rt2_text.bin` (802,528 B) vs E7 app body = **0 byte diffs**.
- Packaged `work/ch32_rt2.bin` vs daily driver `work/ch30_e7ref.bin` = **0 diffs
  in the entire strict region** (uboot + app + 32 device bytes); the only 1,679
  differing bytes lie at ≥`0xC9482` = VM pairing region (packager base was
  `Dumps/dump_pre_ch30.bin`) — legitimately device-state, not firmware.

**THE ROUTE IS ESTABLISHED AND PROVABLY LOSSLESS**: radio dump → decrypt
(`jl_sfcenc`) → ELF wrap → objdump → editable `.s` (263k real instrs; everything
else raw stock) → clang assemble → ld → objcopy → byte-identical image →
package → flash. Edits are now local text changes in `work/rt/e7rt2.s` with the
guarantee that every unedited byte of the output equals the stock byte.
Artifacts promoted to `work/rt/`: e7_app.bin (app plaintext), e7_dis.txt,
e7rt2.s (EDITABLE SOURCE), e7rt2.{pinned,dropc}, e7rt2_text.bin, e7_rt2_plain.bin.

Workflow for an edit (validated offline, then one flash):
1. edit text lines in `work/rt/e7rt2.s` (or add `.short` sequences for exact
   control of encodings);
2. re-run `round` with a fresh tag seeded from e7rt2 state — expect the ONLY
   byte diffs to be exactly the edited items (diff the emitted bin vs
   e7rt2_text.bin to confirm blast radius);
3. package + stage script + user flash.

- **2026-11-08 (night): BYTE-EXACT ROUND-TRIP PASS (§32.11.5) — RT death
  explained (14,430 same-text-different-encoding items); tool now byte-strict;
  E7-ref round-trip image == daily driver across whole strict flash region
  (0 diffs, VM aside). Route PROVEN lossless offline. Editable source =
  `work/rt/e7rt2.s`. NEXT: first edit (candidate: re-apply an R-series behavior
  at source level, or trivial marker edit) = true hardware gate.**

### §32.11.6 — First edit: the Roundtrip marker image (2026-11-08)

**Goal (user):** on clean stock v1.0.50 (`Dumps/dump_internal.bin`, app byte-identical to
`work/app_dec.bin`), change the Radio Info version display to V1.0.50 and add a row
'Modification: Roundtrip' below 'Work Mode: NORMAL MODE' — proof of chanability before
real development.

**Radio-Info menu row-add — NOT DELIVERED, consumer hunt closed (10 rounds, all negative):**
the menu label run ('Radio ID:' 0x8A935 … 'Work Mode:' 0x8A968) and its stride-4 pointer
table (file 0xBD8B0 → RAM 0x7770 via the crt0 blob copy) have ZERO references in
`work/full.lst` and the Ghidra tree — no absolute VAs, no RAM aliases, no displacement
forms, no u16-offset tables, no 6-byte immediates into the windows. `FUN_01e75dbc` is the
BT-menu cluster (Lock/Pairing/Reset/BT Mode), `FUN_01e6653e`+`FUN_01e65e58` the MAIN
standby screen. The blob tables are consumed via a runtime-computed base (UI framework)
never located statically. Live-strays left as leads: the stride-0x14 pool descriptor table
(`FUN_01e9b410 + param_1 * 0x14` in `FUN_01e6b5e6`) and flash-test iterations.

**Delivered marker (size-safe string-content edit on a CONFIRMED-visible slot):**
the main-standby model-name string `'TD-H3-Plus'` (pool 0x1E9B410+0x963 = file 0x9BD73,
12 B incl NUL, drawn by resolver `FUN_01e65e58` case 1) → `'Roundtrip\0\0\0'` (fits
exactly, neighbour 'Unlock SYS' intact). Version display requirement satisfied by
verification: this base already renders `'V1.0.50'` (file 0x9B810, resolver case 2).

**Method (the route working as designed):**
1. Added pins `1e9bd72/74/76/78/7a` to `di.pinned` (string bytes decode as *text*
   instructions in objdump; pinning forces raw `.short` emission) → `tools/jl_rt_asm.py
   round app_dis.txt 0x1e00100 0x1e0C4000 di` → **BYTE-EXACT OK** round 1 (263,690 text /
   48,176 short items).
2. Unique-sequence edit in `di.s`: six consecutive `.short` words
   `0x5400 0x2d44 0x3348 0x502d 0x756c 0x0073` → `0x5200 0x756f 0x646e 0x7274 0x7069 0x0000`
   (line 243092; odd string start handled by the even word grid — low byte of the first
   word is the preceding NUL, preserved).
3. `$TC/clang -c di_edit.s && ld -Ttext 0x1e00100 && objcopy -O binary -j .text` →
   **blast radius = exactly 10 bytes** (0x9BD73..0x9BD7C, `TD-H3-Plus`→`Roundtrip\0`),
   nothing else in 802,528 B.
4. `work/ch32_p2_pack.py /tmp/opencode/rtasm/marker_plain.bin work/ch32_marker.bin
   work/ch32_marker_sectors marker` → **`work/ch32_marker.bin` sha256
   `0748f2d1a751bb4184af3d8648666ee96195cd0c38e4490aeb960f46bc2000e7`**, 14 differing
   sectors vs `work/ch30_e7ref.bin` (the marker sector 0xA0000 + the stock-vs-E7
   differences: reverting the 8 kick-NOP sites + BT-PTT2 bodies — expected, base is
   clean stock).
5. Stage script `work/ch32_marker.sh` (from the `work/ch32_rt.sh` pattern: sha preflight,
   uboot-sacredness assert vs `Dumps/dump_pre_ch30.bin`, device-bytes assert, per-sector
   erase+write+readback ×2, full-1 MiB strict-region verify, boot Q&A tuned for the
   marker, PTT+3 SCSI entry, HID fallback header).

**Field gate (user flash):** boots normally; standby model line reads **Roundtrip**;
Radio Info Firmware Ver **V1.0.50**; TX/RX normal; BT pairs. BT-PTT2 expected NOT
working (stock base). Any anomaly → `sudo python3 tools/jl_hidboot.py restore
work/ch30_e7ref.bin --yes` (PTT+1+power-on).

### §32.11.7 — MARKER FIELD VERDICT: **PASS** (2026-11-09) — route HARDWARE-PROVEN

User flashed `work/ch32_marker.bin` (`0748f2d1a751bb41…`) via `work/ch32_marker.sh`
(PTT+3 SCSI, BR23 UBOOT1.00 @`/dev/sg3`, chip key 0xF181, flash ID 0x856014): all 14
sectors erase+write+readback PASS, **FULL-FLASH VERIFY PASS** (strict region
0x0000–0x0C8FDF). Boot gate: Q1 boots **yes** · Q2 menus/display **all normal** ·
Q3 TX/RX **yes** · Q5 Firmware Ver **V1.0.50** · Q7 BT pairable **yes** ·
Q8 **nothing unusual**. Log: `work/logs/ch32_MARKER_20261109_081658.log`.

**Marker placement (field correction, pleasant):** Q4 answer —
`Menu -> Radio Info -> [1] Radio Info -> Radio Alias: Roundtrip`. The string @0x9BD73 is
the **Radio Alias default rendered IN the Radio Info menu** (not the main standby as the
`FUN_01e65e58` case-1 reading suggested — that cluster is the same screen family). The
user's requested marker therefore IS visible in the Radio Info menu, on the Radio Alias
row, right above Firmware/Hardware Ver — no row-insertion needed after all.

**Verdict: the image → disassemble → editable asm → assemble → repackage → flash route
is fully established and hardware-proven with a 10-byte source edit.** Ten consecutive
field failures of the Ghidra-C route (§32.6) vs one-pass success here. Development may
proceed on this route at the user's direction. Radio currently on
`work/ch32_marker.bin` (stock v1.0.50 + marker; BT-PTT2 absent — daily-driver rollback
recipe: sectors from `work/ch30_e7ref.bin` `90bec320`).


- 2026-11-08 (night): MARKER IMAGE BUILT (first source edit on the byte-exact asm route). Consumer hunt for the Radio-Info 5-row menu closed negative after 10 rounds (label table file 0xBD8B0 → RAM 0x7770 has zero visible refs; mechanism = runtime-computed base) → delivered size-safe visible marker instead: di.s pins 0x1e9bd72..7a added, round BYTE-EXACT OK, then 6 `.short` words edited 'TD-H3-Plus'→'Roundtrip' (10 bytes @file 0x9BD73, main-standby model slot FUN_01e65e58 case 1). Blast radius = exactly 10 bytes. Image work/ch32_marker.bin sha 0748f2d1a751bb41 (clean stock v1.0.50 base + marker; BT-PTT2/E7 kick-NOPs absent by design), 14 sectors vs e7ref → work/ch32_marker_sectors/, stage script work/ch32_marker.sh (PTT+3 SCSI + uboot-sacredness assert; HID fallback). Awaiting user flash verdict.

### §32.11.8 — Second edit: V1.0.50-BT version postfix, marker removed (2026-11-09)

**User directive:** from stock v1.0.50 (`Dumps/dump_internal.bin`) via the full chain:
Radio Alias back to stock (marker removed) and **Firmware Ver = `V1.0.50-BT`** —
convention going forward: every build carries the `-BT` postfix.

**Constraint:** `'V1.0.50\0'` (8 B @file 0x9B810) has no room — `'Waiting\0'` follows and
is live (status-message string table, single u32 pointer @file 0xBDDBC; `findva`
confirmed). Sole code reference to the version string = `r1 = r7 + 0x400` @0x01E65EEC
(4-byte insn, **12-bit immediate → max pool+0xFFF**; the 28-B gap @0x9CBF0 = pool+0x17E0
is out of reach). So no repoint-by-offset; instead **relocate the neighbor**:

1. `'V1.0.50-BT\0'` written over 0x9B810..0x9B81A (clobbers `'Wai'` of 'Waiting';
   residue `'ting\0'` unreachable behind the new NUL).
2. `'Waiting\0'` relocated into the 28-B zero gap @0x9CBF0.
3. Table entry @0xBDDBC repointed `0x01E9B818` → `0x01E9CBF0` (2-byte word edit
   `0xB818`→`0xCBF0`).

**Method:** 12 pins added (`1e9b810..1e9b81a`, `1e9cbf0..f6`, `1ebddbc/be`) →
`round` **BYTE-EXACT OK** round 1 (263,680 text / 48,186 short). di.s has no address
comments — edit sites located by re-running the tool's own `parse_all`/`plan`/`emit_s`
and mapping `addr_of_line` (robust vs value-sequence search; context words may be TEXT,
not `.short`). Eight `.short` value edits → `di_bt.s` →
`clang -c && ld -Ttext 0x1e00100 && objcopy -O binary -j .text` →
**blast radius = exactly 13 bytes** (0x9B817..0x9B81A, 0x9CBF0..0x9CBF6,
0xBDDBC..0xBDDBD), verified in the assembled body.
Gotcha hit: running `round` from the repo root re-created empty state files there
(pins are `<tag>.pinned` relative to CWD) → 60× "backend fatal" loop; state files live
in `/tmp/opencode/rtasm` — always `cd` there first.

**Image:** `work/ch32_bt.bin` sha256 `200a7e11f73a3ea2d7fcdafaf5eb9b2fa2dadba6edb541a536f0e86c1704c287`,
15 sectors vs `work/ch30_e7ref.bin` → `work/ch32_bt_sectors/` (14 of the marker image +
0xA1000 for the relocated 'Waiting'; marker revert implicit — built from stock di.s).
Stage script `work/ch32_bt.sh` (same discipline: sha/sector/uboot-sacredness/device-bytes
preflight, per-sector erase+write+readback ×2, full-1 MiB strict verify, Q&A incl.
Q4 Alias stock / Q5 Firmware Ver **V1.0.50-BT**). **Field verdict 2026-11-09: PASS.** Flashed via work/ch32_bt.sh (PTT+3 SCSI): 15/15 sectors + full-flash strict verify PASS; Q1 boots yes / Q2 all normal / Q3 TX-RX yes / Q4 Radio Alias stock (marker gone) / Q5 Firmware Ver shows **V1.0.50-BT** (user: "all ok"). Log work/logs/ch32_BT_20261109_190217.log. Radio now runs `work/ch32_bt.bin` `200a7e11f73a3ea2` (stock-v1.0.50 base; BT-PTT2/E7 kick-NOPs absent — daily-driver rollback recipe = sectors from work/ch30_e7ref.bin 90bec320).
- 2026-11-09: **MARKER FIELD-PASSED — ROUTE HARDWARE-PROVEN.** work/ch32_marker.bin 0748f2d1a751bb41 flashed via work/ch32_marker.sh (PTT+3 SCSI): 14/14 sectors + full-flash strict verify PASS; Q1 boots / Q2 normal / Q3 TX-RX / Q5 Firmware Ver V1.0.50 / Q7 BT pairs / Q8 nothing unusual. Q4 marker: shows at **Radio Info -> Radio Alias: Roundtrip** (string 0x9BD73 = Radio-Alias default — marker lands IN the Radio Info menu, correction to the standby-screen reading; §32.11.7). First successful source edit on the byte-exact asm route (10 bytes). Radio on marker image; daily-driver rollback = sectors from work/ch30_e7ref.bin 90bec320. NEXT: user directs development.
- 2026-11-09: **BT-VERSION IMAGE FIELD-PASSED.** work/ch32_bt.bin 200a7e11f73a3ea2 (stock v1.0.50, marker removed, Firmware Ver -> "V1.0.50-BT" via 13-byte asm-source edit: version string extended into clobbered "Wai" of "Waiting" + "Waiting" relocated to pool gap 0x9CBF0 + status-table ptr 0xBDDBC repointed; no code change). 15/15 sectors + full verify; all functions normal, alias stock, version shows V1.0.50-BT. -BT postfix = standing convention for all future builds. Radio on ch32_bt.bin; NEXT: user directs development on the asm route.

- 2026-11-09 — ch. 33 S1: E7 feature set + `-BT` folded into `di.s` via asm route; `work/ch32_bt_e7.bin` `d7a29a3eaeffbe67` (172 B vs stock, 13 sectors) staged `work/ch32_bt_e7.sh` — awaiting user flash.

- 2026-11-10 — ch. 33 S1 FIELD-PASSED: `work/ch32_bt_e7.bin` `d7a29a3eaeffbe67` (E7 feature set + `-BT`, 172 B via asm route) — boots, BT-PTT, two-device stable, BT-PTT2 works; RX silence = expected first-device-binding wall (S2 target). Radio on this image.

- 2026-11-10: ch. 33 S2a static PASS (classifier = TID-name-only: "TID-MIC-EAR"->3/"TID-MIC"->4/else 1 @pool 0x9BF5C/0x9B970/0x9B968 — OEM routes audio ONLY to TID combo headsets; Jabra=m1 no-op = the crippling root cause). Dialer FUN_01e600b4 fully decoded (0x4A/5 post @0x01E60102 = new eviction site). P9 image built: work/ch33_p9.bin 6c9c94218e4b3385 = ch32_bt_e7 + 16 B dial-eviction NOPs, 3 sectors, stage work/ch33_p9.sh. UNTESTED.

- 2026-11-10: ch. 33 P9 (dial-without-eviction NOPs, 16 B, image `work/ch33_p9.bin`
  `6c9c94218e4b3385`) FIELD-FAILED — card boot-order poisoned (Jabra reconnected first =
  P8 wall state), TID-PTT could not connect by any means, manual connect/pairing froze +
  rebooted the radio; Jabra alone fine. Retry card = findings/33 §33.8 (same image, strict
  order: button first, then dial Jabra). Route itself healthy (asm edits flash clean).
- 2026-11-10: ch. 33 P9 retry FIELD-FAILED (menu Connect locks radio with link up) —
  the dial-path eviction posts are load-bearing state cleanup ⇒ NOP-the-eviction route
  DEAD (findings/33 §33.9). Next: Card P10 zero-patch dial seesaw on S1 base.
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

## §32.11 — Asm round-trip route (2026-11-08, the post-P2-d field-fail pivot)

USER DIRECTIVE (verbatim gist): flash-bisecting the Ghidra-C splice is not the goal —
establish a PROVABLE route `image → split → disassemble → editable language → assemble
→ recombine → flash`, verified OFFLINE (fixed-point) before any flash, then and only
then make changes. Alternative to decompile⇒recompile explicitly welcomed.

ROUTE = objdump text round-trip (asm level, NOT Ghidra C):
`app_dec.bin → ELF wrapper → objdump -D → normalize → clang -c → ld → objdump →
compare texts` — acceptance = disassembly fixed-point (instruction TEXTS identical,
addresses 1:1), not byte identity (assembler legitimately picks different valid
encodings; sizes preserved by pinning).

### §32.11.1 Dialect + tooling facts (all micro-tested, /tmp/opencode/rtasm/)

1. Assembler = same JieLi clang (`-target pi32v2 -mcpu=r3`); its own `-S` output is
   the canonical dialect: bare immediates (`r0 += 3`), `r0 = r1`, reg-lists
   `[--sp] = {rets, r4}` / `{pc, r4} = [sp++]`, `ifs (r2 < r1) goto .L`, `call r1`,
   `rts`, `.globl/.type/.size/.p2align`.
2. objdump -D output is nearly assembler-ready VERBATIM; branch operands are signed
   decimal RELATIVE offsets (`call 186412`) — accepted by the assembler unchanged,
   so NO target rewriting is needed provided sizes are preserved.
3. ELF wrapper for the raw app (objdump refuses `-b binary`): hand-rolled minimal
   ELF32, machine **0xF1**, 1 PT_LOAD + `.text` PROGBITS AX @0x01E00000; Shdr =
   40 B (10 u32s — 32 B packs are rejected). `/tmp/opencode/rtasm/app_wrap.elf`.
4. `.word` is NOT a directive on pi32v2; **`.short`/`.2byte` = 16-bit** (verified
   bytes `34 12`). Data islands (`<unknown instruction>`, 9.5% of words) → `.short`
   raw words.
5. `rep N rX {` blocks: assembler cannot parse objdump rep text (`rep 4 {` assembles
   but wrong encoding family) → emit header as raw `.short`; body instrs normal;
   closers skipped via block-kind stack.
6. `if (C) {` / `ifs (C) {` = 4-byte predicated headers — assembler accepts the
   multi-line block form VERBATIM incl `} else {`; byte-less `}` display lines must
   be passed through for if-blocks and skipped for rep-blocks (kind stack; `} {`
   occurs only in rep chains).
7. `#` dual-issue markers: objdump prints paired instrs as two normal addressed
   lines; trailing `#` accepted as comment. Sizes preserved.
8. **Size pinning**: assembler sometimes picks a SHORTER valid encoding than the
   original compiler (`r1 = 8388608`: stock 6 B `c1ff00008000` → asm 4 B;
   `r2 = 0`: stock 6 B → 2 B `42 20`). Shrinkage breaks relative-branch absolute
   targets + code-pointer data islands ⇒ any instruction whose re-encoded size
   differs from stock is pinned as raw `.short` stock bytes; iterate until stable.
   Window 0x1e00100..0x1e01000: 5/1483 divergent → round 2 **FIXED-POINT OK**
   (1316 editable text instrs, 158 data shorts, 9 rep, 0 text mismatches).
9. Text-normalizer equivalence rules (display-only diffs): strip ` <_end+…>` symbol
   annotations; hex↔dec canonicalization; `rX = rX + Y` ≡ `rX += Y`; strip trailing
   ` #` dual-issue marker.
10. **Dual-issue `#` pairs** (8133 lines): objdump marks parallel-A instrs with a
    trailing `#`; the pair bit lives IN the word (2-byte: bit 0xC0 of hi byte —
    `01 d6` par vs `01 16` ser for `r1 = r0`; 4-byte: bit 0x10 of byte1 — `61 f1…`
    vs `61 e1…`). B-slot word = serial word verbatim (`1a 41`). Assembler accepts
    `X #` + B-subset only (rejects `.short`/most instrs as B). STRATEGY: strip all
    `#` → every pair becomes two serial instrs: same sizes, same semantics
    (performance-only), fixed-point judged equal.
11. **Hardware it-block range = 4 instructions**: `if (C) {` predicated blocks
    (objdump display) are real HW it-blocks; the assembler FATALS with
    `if-clause out of range` for bodies of ≥5 instructions (verified empirically:
    1-4 OK, 5+ fail). Real stock blocks are all ≤4 instrs; larger displayed blocks
    = data garbage or else-continuations. Policy: text-emit `if {` only when body
    ≤4 instrs; pin header raw + drop closer otherwise (body stays serial text —
    raw header word + serial body is byte-identical after re-decode, verified by
    the fixed-point loop). `} else {` always pin-header+drop (else = state path).
12. **Self-healing pin loop**: data regions misdecoded as blocks produce garbage
    that the assembler rejects (`??` conditions, `{}` empty reglists, orphan
    closers, `invalid location of it block` cascades). rt_round.py iterates:
    assemble-fail error lines → (a) closer-line errors drop THAT closer (stable
    file-order ordinal, `<tag>.dropc`) since it is a display artifact; (b) other
    errors pin ±15-line address window raw (`<tag>.pinned`). Plus structural
    hygiene: any `if {` left open at EOF (display artifact) auto-pinned raw.
    Sizes stay exact: dropped closers + pinned headers have no bytes of their own
    beyond the raw words emitted.

### §32.11.2 Tools

- `/tmp/opencode/rtasm/rt_round.py` (stdlib MIT) — the loop above: normalize →
  clang -c → ld -Ttext → objdump → index-aligned compare → pin → retry (≤12).
  Usage: `rt_round.py <dis.txt> <start> <end> <tag>`; state in `<tag>.pinned`.
- `rt_norm.py` — standalone normalizer (superseded by rt_round's gen_s).
- To promote into `tools/` once the full-image fixed-point lands.

### §32.11.3 Full-image status

Superseded — see the PASS record below (§32.11.3, 2026-11-08).

### §32.11.3 — FULL-IMAGE FIXED-POINT PASS (2026-11-08)

`rt_round.py` converged on the whole app (`0x1E00100..0x1EC3FE0`, 311,866 words):
**FIXED-POINT OK — text_mismatch=0, size_divergent=0**. Final emit stats:
278,124 text instrs + 33,742 raw `.short` words (data garbage + 1,351 pinned
addresses) + 2,032 block closers. Byte diff vs stock = 19,219/802,528 (2.39%)
in 14,221 runs — all valid alternative encodings decoding to identical
instruction text at identical addresses (the agreed correctness criterion;
byte identity is impossible because the assembler makes different legal
encoding choices than the vendor compiler).

Convergence path (60-round self-healing loop, all state persisted in
`<tag>.pinned` / `<tag>.dropc`):
- `if-clause out of range` backend fatal → **HW it-block = max 4 predicated
  instrs** (facts list #11); >4-instr displayed blocks and all `} else {` =
  pin header raw + drop closer, body serial text.
- `-1` vs `0xFFFFFFFF` display drift → norm() canonicalizes signed/unsigned
  immediates to u32 decimal (uppercase hex was the miss).
- odd image tail: two 1-byte `<unknown instruction>` items merge into one
  2-byte word at parse (else emit overshoots by 2 B).
- closer-line assemble errors → drop closer by stable file-order ordinal.

**The route is PROVEN offline**: image → ELF wrap (machine 0xF1) → objdump →
editable asm text (+`.short` data) → clang assemble → ld → re-decode == input.
Zero flash cycles were needed to establish this. NEXT: hardware gate = round-trip
the E7-REF plaintext (daily driver) and flash it: pass criterion = radio behaves
EXACTLY as before (BT-PTT2 + kick NOPs intact) — any behavior change = rt bug.
Then the edit workflow: modify text lines in the .s, reassemble, splice, package
(`work/ch32_p2_pack.py` args pattern), flash.

### §32.11.4 — Tool promoted + E7-ref round-trip gate image (2026-11-08)

`tools/jl_rt_asm.py` (stdlib MIT, env `JIELI_TC` override): subcommands
`wrap` (raw app plaintext -> ELF32 machine 0xF1; phdr byte-trick: LLVM 4.0.1's
objdump REJECTS a correct phdr, accepts the quirky field set copied from the
proven wrapper), `dis`, `round <dis> <start> <end> <tag>` (the self-healing
fixed-point loop; state `<tag>.pinned`/`<tag>.dropc` persist and seed across
images), `bin` (objcopy -j .text). Verified: wrap+dis of `work/app_dec.bin`
byte-identical to the proven baseline dis; window + full rounds reproduce
FIXED-POINT OK.

**E7-ref round-trip (the hardware gate)**: decrypted app segment of
`work/ch30_e7ref.bin` (159 B/36 runs vs clean stock = the 8 kick-NOP sites +
BT-PTT2 bodies) -> wrap -> dis -> round seeded with `full.pinned` ->
**FIXED-POINT OK in 2 rounds** (+2 pins only). Reassembled body = 19,220/802,528
bytes (2.39%) differ from stock — all valid alternative encodings; **all 8 E7
kick-NOP sites byte-EXACT** (verified individually). Assembled plaintext
`/tmp/opencode/rtasm/e7_rt_plain.bin` (stock 0x100 header + rt body) packaged:
**`work/ch32_rt.bin` sha256 97320845…**, 191 sectors differ vs e7ref, sector
export `work/ch32_rt_sectors/`. FIELD GATE (user flash, radio currently dead on
P2d so HID direct): `sudo python3 tools/jl_hidboot.py restore work/ch32_rt.bin
--yes` in PTT+1+power-on mode. PASS = radio behaves EXACTLY as the E7-ref daily
driver (boots, BT pairs, BT-PTT2 works, PTT+3 SCSI mode works from app).
Any behavior change = round-trip bug -> restore e7ref same way. This is the
hardware proof of the provable-edit route the user asked for.
