# 34. pi32v2-isa — the Open ISA Reference and Open Toolchain (jvitkauskas)

> Chapter 34 · added 2026-11-10 · upstream examined: `../pi32v2-isa` @ main (latest
> commit 2026-11-09) · <https://github.com/jvitkauskas/pi32v2-isa>

## 34.1 What it is, and why it matters to this project

`pi32v2-isa` (Julius Vitkauskas — same author as `m-bootloader`, already cited in
[ch. 24](24-jieli-ecosystem-sdk-toolchain.md) and [ch. 32](32-sdk-rebuild.md)) is a
complete **open reference for the pi32v2 instruction set**: a machine-readable
instruction table (`isa/pi32v2.toml`, **1,165 forms, every one `status = "confirmed"`
against the JieLi toolchain oracle, 1,079 of them additionally hardware-confirmed on a
real AC791N**), a pure-Python assembler / linker / objdump / ELF reader built from that
table (`python3 -m pi32v2isa check|disasm|as|ld|objdump|oracle …`, Python ≥ 3.11, zero
dependencies), generators + validation for a full **LLVM backend**
([`jvitkauskas/pi32v2-llvm`](https://github.com/jvitkauskas/pi32v2-llvm), branch
`pi32v2`, LLVM 23.1.5 — shipping binary toolchain releases `pi32v2-23.1.5-5` for Linux
x64/arm64 static, Windows x64, macOS), a hardware-semantics evidence base (two chips
run: M-VAVE FM-1 = AC791N, SMK-37 Pro), and detailed docs on JieLi's ABI, compiler
behavior, ELF format and linker.

Licensing is maximally friendly to us: **code MIT-0, docs and the instruction table
CC0-1.0** — the encodings themselves are public-domain facts we may use without any
attribution mechanics.

Why it matters: their whole oracle loop runs on the **same JieLi Linux toolchain
invocation we use** (`clang -target pi32v2 -mcpu=r3`; their chip AC791N is `-mcpu=r3` +
`fprev1`, our AC635N/BR23 app is built `-target pi32v2 -mcpu=r3` — [ch. 25](25-ghidra-decompile-compile-route.md)),
their table resolves the large majority of the `???` holes in our hand-built
[`tools/isa/pi32v2.md`](../tools/isa/pi32v2.md), and their open clang/ld.lld/llvm-mc is
a **drop-in replacement for the closed JieLi toolchain** on which ch. 25 (compile
route), ch. 28 (SDK rebuild) and ch. 32/33 (asm route, `tools/jl_rt_asm.py`) all depend.

## 34.2 Cross-verification of our hand encodings — ALL CONFIRMED (2026-11-10)

Every encoding this project ever reconstructed by RE was re-checked against the
upstream oracle-verified table (and against our own `tools/pi32dis.py`). All core
facts hold:

| Bytes | Our claim | Upstream decode | Verdict |
|---|---|---|---|
| `40 23 80 00` | `r0=3; rts` (app kick NOP, `--no-kick`) | `r0 = 3` ; `rts` | ✅ |
| `40 20 00 04` | `r0=0; pc=[sp++]` (`--no-spp-close`, after `push rets`) | `r0 = 0` ; `pc = [sp++]` | ✅ |
| `0b f8 d4 94` | `je r11,#0x4a` (`--no-l2cap-disconnect` branch) | `if (r11 == 74) goto 424` → `0x01E17B20` | ✅ |
| `00 f8` + `(N<<9)｜disp9` | `if (r0==N) goto` (§9A.26) | `if (r0 == 3) goto +0` etc. | ✅ |
| `71 8a` | 16-bit `call`, rel to insn end | `call -44` | ✅ |
| `c4 ea b5 81` | 32-bit `goto.l`, `target = addr+4+sign22(((w0&0x3F)<<16｜w1)*2)` | → `0x01EA773E` — formula identical | ✅ |
| `80 41` | page-scan branch (`--force-page-scan`) | `if (r0 != 0) goto 2` | ✅ |
| `00 00` | `nop` | `nop` | ✅ |
| `48 2a` / `48 2b` | `r0 = 0x2A/0x2B` | same | ✅ |
| `c0 ff 40 a7 01 00` | `r0 = 0x1A740` (li.u32) | `r0 = 0x1A740` | ✅ |
| `50 ed 52 08` | `r0 = h[r5+130]` | same | ✅ |
| `10 04` / `75 04` | `[--sp] = rets` / `{rets,r5,r4}` | same | ✅ |

Structural rule confirmed with **zero mismatches over 327,211 decoded words**
(§34.4): first word `< 0xE000` → 2 bytes; `0xFF00–0xFFEF` → **6 bytes**; otherwise →
4 bytes. Our WeirdIMM (`%`) table is upstream's `li.modimm` rotated-mask immediate
family; our tbb entry encoding (`(target − base)/2`) matches their
`target = addr-after + 2·byte`; the 32-bit call/goto formula is identical.

## 34.3 Correction: `--no-l2cap-disconnect` entry no-op is `r0 = [sp+12]; rts`, not `mov r0,#0; rts`

The entry no-op at `0x01E173D0` writes `00 23 80 00` (§27.17). Both our spec and the
upstream table decode `00 23` as **`r0 = [sp+0xC]`** — so the stub returns *caller-stack
garbage*, not 0, and the long-standing `mov r0,#0; rts` label was wrong. E11 is
unaffected in the field: the hardware test proved callers ignore the return value
(the evictor died exactly as designed), so **the bytes stay as flashed** — only the
labels/comments were wrong. Corrected 2026-11-10 in
`tools/patch_h3plus_firmware_bluetooth.py` (comment + `L2CAPDISC_ENTRY_STATES` /
`L2CAPDISC_LABELS` + CLI help), `tools/verify_actions.py` descriptions,
`tools/Tools.md`, [ch. 27 §27.17](27-firmware-2slot-stack-controller-wall.md#2717--e10-run-2026-10-20-failed--the-closer-is-the-all-channel-walk-kill-it-at-the-l2cap-door---no-l2cap-disconnect-e11),
[ch. 29](29-static-analysis-reference-map.md) patch-site table, `README`/`Findings`
index rows and `.github/copilot-instructions.md`. Both test suites re-run green
(`verify_actions.py` 0 failures, `verify_cli.py` 0 failures).

For the record: a true `mov r0,#0; rts` is `40 20 80 00`; the `--no-spp-close` stub
`40 20 00 04` sits **after** the entry `push rets`, so its `pc = [sp++]` pops the just
saved link — a clean `return 0`, as documented.

## 34.4 Full-image cross-check — `tools/isa_xcheck.py` (new tool)

`tools/isa_xcheck.py` disassembles `work/app_dec.bin` with **both** decoders
word-by-word (our `pi32dis.py` vs upstream `pi32v2isa`) and reports agreement,
length mismatches and the upstream `insn.id` histogram of everything our spec misses.
Full-density run (every 2-byte-aligned offset, 401,392 probes, ≈ 40 s):

| bucket | count | share |
|---|---|---|
| both decode | 327,211 | 81.52 % |
| **length mismatches (both decode)** | **0** | structure fully agrees |
| ours only | 30 | 0.0075 % |
| theirs only | 23,427 | 5.8 % |
| neither (data / undefined) | 50,724 | 12.6 % |

Sampled text pairs are semantically identical (spelling-only diffs: hex vs decimal
immediates, `<0==32>` vs `32`, absolute vs relative branch target printing).

- **The 30 ours-only** are all in the `0xE8xx–0xEExx` two-register-conditional-branch /
  register-indexed-load space: our §9A.31 `CONDBR` and `GROUP7_IDX` special cases match
  on the **first word only** (the community spec documents those forms with an
  all-zero operand word), so they over-match mid-instruction/data words that upstream
  (full 32-bit masks) correctly calls undefined — e.g. `09 ec c0 ff` @`0x01E03E20`
  (our bogus `if (r15 > r9) goto`, upstream: no instruction). §9A.31's reconstruction
  was directionally right but too loose; the `--upstream` mode of `pi32dis.py` (§34.5)
  now gates those special cases on upstream recognizing the word.
- **The 23,427 theirs-only** are exactly the `???` holes of our 32-bit table plus the
  whole 6-byte `FF00–0xFFEF` family. Top upstream forms our spec misses (occurrences
  in the image): `add.s14.rri.p` 1171, `insert.rrii` 1023, `uextra.rrii` 825,
  `st.b.sp.l` 821, `callns.r` 747, `rmw.and.nmodimm` 742, `rmw.or.modimm` 722,
  `ld.hu.sp.l` 652, `st.w.sp.l` 571, `beq.ri.l` 558, `mul.modimm.rri` 484,
  `ld.bu.sp.l` 460, `if.ne.ri.s12` 438, `bne.ri.l` 399, `beq.and.ri` 398,
  `bne.and.ri` 397, `st.w.modimm` 365, `if.eq.ri.s12` 319, `div.u.rrr` 318,
  `add.r_sp_i.l` 317 … (counts include data words that happen to decode). Categories:
  32-bit stack load/stores (`sp` + long immediate), 32-bit conditional branches
  (`beq/bne.ri.l`, `if.*.ri.s12`), **hardware divide** (`div.u/s.rrr` — our table has
  no divide entries at all), SFR read-modify-write bit ops (`rmw.*`), modimm
  mul/or/add, 3-register ALU forms, and DSP parallel-issue (`.p`) forms.

## 34.5 Tool update: `pi32dis.py --upstream` fallback (strictly additive)

`tools/pi32dis.py` now accepts `--upstream DIR [--mcpu r3]` (clone of
`pi32v2-isa`; default none → behavior byte-identical to before). With it:

- words our spec cannot decode are decoded by the upstream table and printed with a
  trailing `;upstream` marker, advancing by upstream's instruction length — this
  **resynchronises linear sweeps** across the 5.8 % gap and the 6-byte `FF00–0xFFEF`
  forms (previously a sweep desynced or stalled on `.word`);
- words upstream finds **undefined** no longer match the empirical §9A.31
  `GROUP7`/`GROUP7_IDX`/`CONDBR` special cases (kills the 30 over-matches).

```bash
python3 tools/pi32dis.py work/app_dec.bin --va 0x01E00040 --count 8 --upstream ../pi32v2-isa
# 01E00042  01 ff 00 90 0c 00   if (r9 != 0) goto 24  ;upstream   ← 6-byte form, sweep stays aligned
```

## 34.6 Our `???` unknowns resolved by the upstream table / docs

The following are now authoritatively settled (upstream `docs/ISA.md`,
`docs/COMPILER.md`, `docs/ELF.md`, hardware runs `hw/`) — each supersedes a `???` or
an empirical guess in `tools/isa/pi32v2.md`:

- **psr flags**: N = bit 3 (result bit 31), Z = bit 2, C = bit 1, V = bit 0; for
  subtracts **C = no-borrow**; add/sub write all four, logic/mul/bitfields write N+Z,
  32-bit shifts write N+Z+C, pair shifts write only C, `li`/`mov` write none.
- **`if (...) { } else { }` predication blocks** (our `???` "conditional blocks"):
  second word bits 15..14 = then-count−1 (1..4), 13..12 = else-count (0..3); a `call`
  must be the **last** instruction of a block (hardware bug otherwise); `goto` inside a
  block is always `goto.l`.
- **6-byte forms** (our whole 48-bit section was `??`): `FF00–0xFFEF` = long
  compare-and-branch family (`if (rX ==/!=/… imm) goto`); first-word **bit 5**
  distinguishes signed vs modified-immediate compares (`FF00–FF2F`).
- **Branch/call offsets** count from the **end** of the instruction and divide by 2;
  `call.s` −256..254 → `call.l` ±4 MiB; `goto.s` ±2048 → `goto.l`.
- **`rets` is 27 bits wide** (pops return `word & 0x07FFFFFE`); `npc` = instruction
  address + 4 rounded up to a word boundary; **misaligned word loads RESET the chip**
  (observed on AC791N — treat as a landmine on BR23 too, untested there).
- **Parallel issue** `A  #` packets: 16-bit load/store B issues with A and reads
  registers **as they were before A** (hardware-confirmed).
- **WeirdIMM** = `li.modimm` rotated-mask immediates; shift counts 1..32 (field 0
  means 32); `if` = unsigned / `ifs` = signed / `iff` = float compares.
- **DSP group** (our ~200 `???` entries) fully named in their table — with hardware
  caveats on AC791N: `popcnt` is a **NOP**, `popcnt.r_pair` runs as `mov.half`,
  `sum.*` forms are really `mul2`/`madd` variants (one ignored selector bit),
  `mem2.hh.rh` "two halfword loads" execute as **16×32**, the six `mem2.hh.i`
  multiplies **reset the chip**, `??`-condition vector compares **reset the chip**,
  `copex.ppi` is genuinely unpredictable. 42 table entries carry a
  `hw = { ac791n = "resets|nop|unpredictable|as:<id>" }` annotation.
- **ELF**: `e_machine` 0xF1 (matches ours), `e_flags` always 0, RELA-only, relocation
  types 0–16 fully specified (`LONG_JUMP_17M2`=1, `LONG_JUMP_23M2`=2,
  `EXTEND_JUMP_17M2`=3, `EXTEND_CALL_32M2`=4, `MOV_ABS32`=5, `ABS8/16/32`=6/7/8
  **add the in-place value**, `REL32`=13 not PC-relative in static links); branch
  relocs overwrite their fields, offsets `(S+A−(P+len))/2`. JieLi `ld` = GNU ld
  2.26.51 `elf32-pi32v2`, default text `0x50000`, phdr alignment 0x500 (GNU objcopy
  2.44 rejects it — upstream patches the field).
- **JieLi clang 4.0.1 ABI/codegen facts** (from `oracle cc`, i.e. compiler-as-evidence):
  args `r0..r3` then stack (5th word at `[sp]`), 64-bit low half in the **even**
  register with no pair alignment, `r4..r15` callee-saved, prologue
  `[--sp] = {rets, r5, r4}`, structs by reference (sret pointer in `r0`), dense
  switches via `tbb` (matches our §9A findings), `fabsf` = `and.invbit`, float negate
  = `xor.bit 31`, doubles soft-float, `__builtin_frame_address(0)` **crashes the
  compiler**, no `madd.f` ever emitted.

## 34.7 The open toolchain — impact on our routes

- **Open clang/ld.lld/llvm-mc/objdump for pi32v2** ([`pi32v2-llvm`](https://github.com/jvitkauskas/pi32v2-llvm),
  LLVM 23.1.5): `-mcpu generic|r3|ac791n`, static Linux x64/arm64 releases
  (`pi32v2-23.1.5-5`), GitHub Action `jvitkauskas/pi32v2-isa/.github/actions/setup-pi32v2`.
  Codegen follows JieLi's C ABI; `__attribute__((interrupt))` works; reads JieLi's
  **LLVM-4.0.1 bitcode** (4,898 of the AC79 SDK's 4,900 objects) through `llc`/LTO
  with compatibility shims; LLVM code sizes within ±0.6 % of JieLi, and the drop-in
  build is **4.64 % smaller** over 13 open firmwares. → For the [ch. 25](25-ghidra-decompile-compile-route.md)
  compile route and any cave C of [ch. 33](33-twodevice-asm-development.md), we can
  now compile with an **open, scriptable, CI-friendly toolchain** instead of the
  closed JieLi one (no libc — firmware supplies startup; `-nostartfiles -nolibc`).
- **Drop-in for JieLi's `/opt/jieli` layout** (`tools/dropin/make_dropin.sh`): the
  AC79 SDK's own Makefiles build unchanged (all 14 apps link). Direct precedent for
  the [ch. 28](28-sdk-forks-survey.md) SDK-rebuild route — though proven on
  `fw-AC79_AIoT_SDK`, **not** on `fw-AC63_BT_SDK` (different libs, linker scripts,
  packaging).
- **Byte-exact Python assembler/linker/objdump** (`pi32v2isa as|ld|objdump`, proven
  oracle-identical via `oracle asmcompare/objdumpcompare/ldcompare`; full firmware
  builds byte-identical with their `--open` overlay). → Candidate second opinion /
  assembler for the [ch. 32](32-sdk-rebuild.md) asm route (`tools/jl_rt_asm.py`):
  their `as` accepts JieLi objdump syntax and emits JieLi-identical objects.
  **Caveat they document**: JieLi `clang -c` output ≠ `clang -S` + assemble (e.g.
  `c0 21 80 00` vs `08 81 80 00` for `r0 += 1`) — byte-exactness expectations must
  respect which stage produced the bytes.

## 34.8 Methodology worth adopting (from `docs/ORACLE.md` + `AGENTS.md`)

- Pin the JieLi toolchain by **release name + SHA-256**, never commit it, use it as a
  **black box only** (`oracle fetch`; releases `20250324.1` `f686586b…`,
  `20260730.1` `a1545cdd…`, from
  `https://jl-update.oss-cn-shenzhen.aliyuncs.com/jieli-linux-toolchains-<rel>.tar.xz`
  / `pkgman.jieliapp.com/s/linux-toolchain`).
- **Two-direction confirmation** of every encoding: encode (assemble text → bytes) and
  decode (objdump bytes → text), each probe followed by two `nop`s so an over-long
  decode shows as a mismatch instead of desyncing. `oracle sweep` over all 65,536
  16-bit words is "the quickest way to see what a region of the encoding space holds".
- Status ladder `guessed → documented → confirmed`, where **confirmed covers encoding
  only** — behavior claims must cite `compiler` or `hardware` evidence (run-cited,
  e.g. `hw/fm1-2026-10-24`). Known-but-ununderstood goes in `GAPS.md`, never in the
  table as a guess. **No result is ever invented for a failed batch.**
- Pin **known tool bugs** as regressions (`asm_wrong` / `asm_rejects` /
  `asm_no_syntax`) "so a fixed toolchain shows up".
- Their hardware harness (mask-ROM USB download-mode RAM runner, FC60/FD61 private
  commands, alternating 32 KiB slots, nop-calibrated batches, full GPR+psr capture,
  `results.jsonl` + executable semantics models) is conceptually parallel to our
  `jl_hidboot.py` HID entry (PTT+1+power-on) — a possible future BR23 semantics rig.

## 34.9 JieLi toolchain bugs pinned by upstream (regression watch for us)

- `r = r | 0`, `r = r ^ 0`, `r = r & 0xFFFFFFFF` mis-assemble to set/toggle/clear of
  **bit 0**; zero-mask branch `if ((r & 0) == 0) goto` assembles as the single-bit form.
- objdump **hides feature-gated forms** unless told (`-mattr=+instrev3` for `sat8`/
  `vsat16`) — a sweep without the flag silently misses encodings.
- objdump prints empty register lists as `{}` which the assembler refuses;
  `d[r++=n]` accepts −512..508 but decodes −1024..1020.
- The LLVM assembler destroys `{`/`|`/`}` in inline asm strings (clang turns `{` into
  `$(`) — fixed upstream via `NoAsmVariants`.

## 34.10 What upstream does NOT give us (AC635N gaps)

- **Everything hardware-confirmed is AC791N.** Nothing in the repo touches
  AC63/BR23/AC635N: whether `popcnt` is a NOP on our die, whether the reset-on-forms
  reset ours, our FPU revision, and any form present/absent vs AC791N are **unmeasured
  on BR23**. (Our images run fine, so the forms the compiler actually emits are
  obviously present; the exotic DSP/reset families are irrelevant to our patches.)
- Only `-mcpu=r3` was swept; `r1/r2/r4/r5` differences unknown (irrelevant — BR23 is
  `r3`).
- AC63 SDK packaging (`isd_download`/`.ufw` for `fw-AC63_BT_SDK`) is out of their
  scope — we already have our own packager/flasher chain (ch. 24/ch. 32).
- No C library; `llvm-link`/`llvm-bcrename` not provided by the drop-in; 64-bit
  atomics missing from the LLVM target.

## 34.11 Artifacts produced by this chapter

- **New tool**: [`tools/isa_xcheck.py`](../tools/isa_xcheck.py) — both-decoder
  cross-check with gap histogram (documented in
  [`tools/Tools.md`](../tools/Tools.md) §4.7 and [ch. 17](17-tooling-index.md)).
- **Updated tool**: [`tools/pi32dis.py`](../tools/pi32dis.py) — opt-in
  `--upstream DIR [--mcpu r3]` fallback decode + special-case gating (§34.5).
- **Corrected labels**: `--no-l2cap-disconnect` entry no-op spelling (§34.3), across
  patch tool, verify suites, Tools.md, ch. 27/29, Findings index, copilot-instructions.
- `tools/isa/pi32v2.md` annotated with an upstream-reference section (table itself
  unchanged so the runtime parser is unaffected).
- **Corrected full listing**: `work/full_upstream.lst` — 311,921 lines regenerated with
  `pi32dis.py --upstream=../pi32v2-isa` (20,463 `;upstream` fallback decodes, 0 errors;
  the user's `work/full.lst` untouched) + census output `work/xcheck_census.txt` (§34.14).

## 34.12 Re-verification of the ch. 30/31 analysis sites (2026-11-10)

With the `--upstream` fallback in place, every function the ch. 30/31 R-series
analysis relied on was re-disassembled and diffed (default decode vs upstream):

- **Desync evidence**: across 13 critical windows, 283 text-diffs and **411
  boundary-diffs** — the old `pi32dis`/`work/full.lst` streams advanced 2 bytes
  at every word our spec missed (6-byte `FF00–FFEF` compare-branches, mask
  branches `if ((rN & m) op 0) goto`, `if (...) {` blocks, `insert`/`uextra`,
  `callns`, long stack ld/st), so everything after the first gap in each
  function was misaligned garbage in the old listings.
- **The Phase A bind-block decode SURVIVES**: the window `0x01E61292–0x01E612FC`
  (bind block: `b[0xB10+base]=120`, addr-copy `[sp+16]→[sp+12]`, free
  `[0x102F0+0x280]`, `is_current_device` call, state `|=5`) decodes **identically**
  in both modes. R7's field failure was a real architectural wall, not a decode
  artifact. The two abort branches after `is_current_device`
  (`if (r0 == 2) goto +2740` @`0x01E612C2`, `if ((r0 & 0x1) != 0) goto +2724`
  @`0x01E612D2`) were known from Ghidra but show as `.word`/`bkpt`/`idle`
  garbage in the old pi32dis stream — confirming Ghidra (not pi32dis) was the
  sound authority for that decode.
- **NEW control flow into the R-series redial heartland** (old xref saw ZERO
  incoming edges, upstream resolves them — all masked-branch forms our spec
  lacked):
  - `0x01E22348 if ((r0 & 0xFF) != 0) goto −1288` → **cmd-1 dial body
    `0x01E21E46`** — the dispatcher epilogue's 6-byte OR-fold of the re-dial
    mailbox (`r1 = b[++r0=209]` = `r14+0xD1`..`+0xD6`, parallel-`#` fold)
    branching to the dial. This is exactly the R5 mechanism — statically
    CONFIRMED by upstream (R6a's field-proven firing agrees).
  - `0x01E21D5C if ((r0 & 64) != 0) goto 230` → **cmd-1 dial body** — a SECOND,
    previously-unknown dial gate: bit 6 of `b[r12+0x15]` (event record byte)
    sends the dispatcher straight to the mailbox dial.
  - `0x01E21D6E if ((r0 & 0x20) == 0) { r2 = r14+0xD1; r2 = r14+0x13A; r0 = 1;
    r1 = 6; call 0x01E1792E }` — a DIRECT cmd-1 post selecting a **second
    mailbox at `r14+0x13A`** (dispatcher base `0x1A520` → `0x1A65A`); the
    `0xD1` write is dead code inside the block.
  - `0x01E21BE0 if ((r1 & 0x38) == 0) goto 1864` → epilogue `0x01E2232E`.
- **The reason-`0x16` pairing-kick loop is now FULLY visible** (`0x01E21DAE–
  0x01E21DF8`): `if (r6 != 74)` gate, walk conn records `r14+0x9E`→`r14+0xD0`
  stride `0x1C`, assemble BD_ADDR words via `insert` (the byte-assembly forms
  our spec lacked), test **bit 29** (`r8 & 0x20000000` = the §27 inused flag),
  `h[r6] != 0` → `r1 = 0x16; call 0x01E19492` (the `--no-pairing-kick` site
  `0x01E21DE4`). Also `r13 = 0x102F0` (app device struct) loaded inside the
  stack dispatcher @`0x01E21D84`.
- **Verdict**: the R-series conclusions stand (bind wall real, six levers
  exhausted for correct reasons), but every "sole caller/sole writer" claim in
  the dispatcher region was an UNDERCOUNT by the old xref tooling and must be
  re-derived on the corrected decode before further redial work. The newly
  visible bit-6 dial gate and the `r14+0x13A` second mailbox are fresh,
  grounded R8 candidates.

## 34.14 Corrected-decode xref census (2026-11-10)

With `work/full_upstream.lst` regenerated (§34.11), the ch. 30 xref questions were
re-run against the corrected decoder (script output: `work/xcheck_census.txt`,
old-vs-upstream counts):

- **Callers into every key site are UNCHANGED except two.** Disconnect wrapper
  `0x01E07B08` 4=4, page guard `0x01E16824` 12=12, find-conn `0x01E17420` 10=10,
  `spp_connect` `0x01E1750C` 2=2, conn dispatcher `0x01E1792E` 83=83, kick thunk
  `0x01E19492` 5=5, app kick `0x01E5B22A` 2=2, `is_current_device` `0x01E184D6` 1=1,
  tbh hook `0x01E61270` 2=2, bind block `0x01E61292` 1=1. The sites that showed
  old=0→up=0 (stack dispatcher `0x01E21AF8`, outgoing connect `0x01E60114`, mode
  setter `0x01E60188`, UI connect `0x01E61E22`, classifier `0x01E7EC28`) are
  pointer-table callbacks — unchanged, `tools/findva.py` remains the way in.
- **cmd-1 dial body `0x01E21E46`: old=0 → up=2.** Two hidden entries the old listing
  could not see: `0x01E21D5C if ((r0 & 64) != 0) goto 230` (gate = **bit 6 of
  `b[r12+0x15]`**) and `0x01E22348 if ((r0 & 0xFF) != 0) goto −1288` (the R5/R6a
  epilogue fold path — confirms the re-dial mechanism end to end).
- **Dispatcher epilogue `0x01E2232E`: old=0 → up=1** (`0x01E21BE0 if ((r1 & 0x38) == 0)
  goto 1864`).
- **Mailbox2 `0x1A65A` (= dispatcher base `0x1A520` + `0x13A`)** — a SECOND address
  mailbox, invisible in the old listings:
  - gated WRITER @`0x01E219A4–0x01E219B4`: `r6 = b[r2+0x4]; …; if (r6 == 0) { … r3 =
    r1 + 0x13A; b[r3++=r10] = r2; rep 0x2 0x5 { … } }` — gated on `b[r2+4] & 0x40`,
    copies the address bytes into `base+0x13A` with a `rep` loop.
  - direct cmd-1 POST @`0x01E21D66–0x01E21D7E`: `r0 = b[r12 + 0x10]; if ((r0 & 0x20)
    == 0) { … r2 = r14 + 0x13A; r10 = r2 + −0xEC0; r0 = 1; r1 = 6; call 0x01E1792E }`
    — gated on **bit 5 of `b[r12+0x10]`**, posts `user_send_cmd_prepare(1, 6,
    mailbox2)` — a radio-originated dial whose address operand is mailbox2, NOT the
    `0x1A5F1` mailbox the R5/R6b/R7 designs armed.
- **Mailbox `0x1A5F1` refs**: old=13 → up=17; the 4 new hits are the epilogue fold
  `0x01E22330 r1 = b[++r0=209] (u)` (known, now visible) + three weak DSP/data-region
  coincidences (`0x01E9987E`, `0x01EBF9DC/E`).
- **Struct `0x102F0`**: 810 refs old = 810 refs upstream — the app-side reference set
  was already complete; the decode gaps did NOT hide any current-device references.

**Verdict.** The R-series conclusions stand (bind decode §34.12, all edge counts,
`0x102F0` reference set). What the corrected decode adds is a fresh static lead for
R8: the stack keeps a second dial mailbox `0x1A65A` with its own gated fill
(`b[r2+4] & 0x40`) and its own gated cmd-1 post (`b[r12+0x10] & 0x20`), plus a
bit-6-of-`b[r12+0x15]` gate directly into the dial body — none of these were
addressable from the old listings, and the R5-lineage designs never armed mailbox2.
Any R8 design must consider BOTH mailboxes and the three gate bits
(`b[r2+4]&0x40`, `b[r12+0x10]&0x20`, `b[r12+0x15]&0x40`).

## 34.15 References

- <https://github.com/jvitkauskas/pi32v2-isa> — the open pi32v2 ISA reference
  (table CC0-1.0, code MIT-0); docs read: `ISA.md`, `ABI.md`, `COMPILER.md`,
  `ELF.md`, `ORACLE.md`, `GAPS.md`, `LLVM.md`, `DROPIN.md`, `BUILDING-OPEN.md`,
  `TOOLCHAIN.md`, `SOURCES.md`, `TABLE-FORMAT.md`, `CPU1.md`, `audits/`.
- <https://github.com/jvitkauskas/pi32v2-llvm> — open LLVM 23.1.5 target for pi32v2
  (releases `pi32v2-23.1.5-5`).
- <https://github.com/jvitkauskas/m-bootloader> — same author; already our FM-1/AC79
  boot-protocol reference (ch. 24).
