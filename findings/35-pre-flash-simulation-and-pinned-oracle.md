# 35. Pre-flash simulation and the SHA-pinned JieLi oracle (2026-11-10)

> Tools delivered this chapter: [`tools/jl_sim.py`](../tools/jl_sim.py) (§35.2–§35.4) and
> [`tools/jl_oracle.py`](../tools/jl_oracle.py) (§35.5). Both wrap the open
> [`jvitkauskas/pi32v2-isa`](https://github.com/jvitkauskas/pi32v2-isa) reference
> ([ch. 34](34-pi32v2-isa-open-reference.md)) — nothing of JieLi's and nothing of
> upstream's is vendored into this repo; the tools `sys.path`-import the upstream clone.

## 35.1 Task

User directive (verbatim, 2026-11-10):

> "can you make a tool like their sim.py (hardware-fitted models) to test cave logic
> pre-flash; SHA-pinned JieLi oracle per their ORACLE.md. for our simulation work? So we
> can simulate our code changes taking down the number of hardware validiation tests
> speeding up development. If that is possible build it and add it to the instructions"

Answer: **feasible, and both tools are built.** `jl_sim.py` executes our (patched) app
code on the upstream CPU model whose per-instruction semantics were fitted to a real
AC791N die; `jl_oracle.py` gives the vendor clang/objdump as a SHA-pinned black box for
the authoritative decode of any new encoding. Together they pre-check the two failure
classes that cost hardware round-trips: **wrong cave logic** (sim) and **wrong encoding
/ length / re-entry alignment** (oracle + the ch. 34 table check).

## 35.2 `jl_sim.py` — architecture

- Imports upstream `tools/llvm/sim.py` (`sim.CPU`) — its instruction models come from
  `tools/hwtest/semantics/*.py`, the executable models fitted against every hardware
  case in upstream `hw/` runs (FM-1/AC791N). `sim.py` is importable (its `main()` is
  `__name__`-guarded); we reuse it wholesale rather than reimplementing.
- Flat-loads the decrypted app (`work/app_dec.bin`, 802 784 B) at VA `0x01E00000` into
  the CPU's sparse 4 KiB-page memory; zero-init reads stand in for RAM.
- `--patch VA:HEX` splices patch/cave bytes into the image **before** the run — the core
  pre-flash feature: simulate exactly what the patched flash would execute. A whole
  patched image can also be passed via `--image` (e.g. `work/ch30_r7.bin`).
- `--seed VA:HEX` primes RAM after load (conn records `0x1A5B8` stride `0x1C`, routing
  byte `0xB464`, dispatcher base `0x1A520`, stack, …).
- Entry: `--start VA` (pc = VA, `rets` = stop sentinel `0x01C70000` unless `--rets`) or
  `--call VA --arg V…` (ABI: args in `r0..`, return caught at the sentinel).
- Loop stops on sentinel (`returned (rets sentinel)`), `--stop-va VA`, step limit
  (`--max-steps`, default 200 000) or a `RuntimeError` from the core
  (`unsupported form: <pc>: <insn.id>: …` = coverage report).
- `--trace` prints `ADDR  text` per executed instruction (upstream objdump text);
  `--expect rN=VAL` / `--expect-mem VA:HEX` assert at stop → **exit 0/1, CI-able**.
- Report: stop reason, pc, steps, all 16 registers, flags/sp/rets, and a byte-run diff
  of every memory write (`ADDR  oldhex -> newhex`).

**Upstream artifact worked around:** `tools/hwtest/semantics/m2.py` opens a dev-only
file `/root/.t3/projects/pi32v2-isa-wt/ids5-m.txt` at import (not committed upstream),
and `check.load_models()` aborts with `ld.w modelled twice (m2.py)` when m2's ids
collide with other modules'. `jl_sim.py` monkey-patches `load_models`: import every
semantics module except m2 first, reconstruct m2's intended id list from the table
(`startswith ld./st./rmw.`, minus `ld.w.npc*`/`st.w.modimm*`, minus already-modelled
ids), then import m2 with `builtins.open` redirected for that filename to an
`io.StringIO` of the reconstructed list.

## 35.3 Model coverage over our app

Census (upstream-decoded words of `work/app_dec.bin` vs `check.load_models()` keys):

| metric | value |
|---|---|
| both-decodable words | 327 211 |
| upstream forms with **no** model | 147 |
| image words using an unmodelled form | **1 001 = 0.31 %** |

The unmodelled set is entirely **DSP/multimedia + exception/debug** forms
(`sum.acc.*`, `mul4/mul2.*`, `mem2.hh.*`, `copex.ppi`, `syscall`, `hbkpt`, `btbclr`,
`idle`, `clip.*`, `vsat16`, `unpack4`, …). Every ALU / memory / branch / call / push /
pop form our caves and patch code uses **is modelled**. Hitting an unmodelled form stops
the run with a clear `unsupported form` message — that is the coverage report, not a
silent wrong answer.

## 35.4 Test evidence (2026-11-10)

1. **Kick NOP (`--no-kick`)** —
   `python3 tools/jl_sim.py --start=0x01E5B22A --patch=0x01E5B22A:40238000 --expect=r0=3 --trace`
   → trace `01E5B22A r0 = 3` / `01E5B22C rts`, stop `returned (rets sentinel)`, 2 steps,
   `r0 = 3`, **verdict PASS, exit 0**. Negative control `--expect=r0=4` → FAIL exit 1.
2. **Stock code, real semantics** — `--start=0x01E00000 --regs r3=0x10000` → 12 steps to
   `rts`; `b[r3++=4]` post-increment and `b[r3+-8] (u)` unsigned load execute with
   hardware-fitted semantics (`r6 = 4`, `r3 = 0x10004`); store run shows the memory diff
   `00020000 00 -> 04`.
3. **6-byte `FF00–0xFFEF` branch** — `--start=0x01E00042 --trace` →
   `if (r9 != 0) goto 24` executes with correct length and re-entry at `0x01E00048`
   (the form family that desynced our old listings, §34.12).
4. **R7-context tbh guard** — `--start=0x01E61270 --flags=2 --stop-va=0x01E612CA` →
   3 steps along the exact taken path R7's incoming-mode-3 hook relied on (mode byte 3 →
   table → `0x01E612CA`), verified on hardware-fitted models.
5. **Limitation observed** — app entry `--start=0x01E00000` from reset hits
   `icfg = r2` (`mov.sr_r`, an SFR write) → `unsupported form … needs the hardware
   run's context`. SFR access is outside the model; our cave code contains no SFR
   operations, so impact on the pre-flash workflow is minimal. `tbb` through `--call`
   hit a decode-offset quirk in the upstream core at `off=0` (known limitation).

## 35.5 `jl_oracle.py` — SHA-pinned vendor black box

Thin wrapper over upstream `pi32v2isa.oracle` (their ORACLE.md protocol, §34.8). Pinned
releases (SHA-256, from upstream `RELEASES`):

| release | SHA-256 |
|---|---|
| `20250324.1` | `f686586bcfb45e0f0bb27fd2b39c7a7f313cb4f0e88a66a14da621ffa8225958` |
| `20260730.1` (default) | `a1545cddbc451a06bac43eb5cd96d831470c42a97c5c0b1f98879a20fc7647bd` |

Source: `https://jl-update.oss-cn-shenzhen.aliyuncs.com/jieli-linux-toolchains-<release>.tar.xz`;
unpacks under the upstream clone's gitignored `oracle/` dir (or set
`PI32V2_TOOLCHAIN`). Vendor `clang` + `objdump` used strictly as a black box; nothing
committed here.

Sub-commands:

- `status` — pinned table + which toolchains are present (tested: clean `NONE` message +
  fetch hint, exit 0, no traceback).
- `fetch [--release]` — download, **verify SHA-256**, unpack. (User's call — a large
  vendor download; deliberately not run autonomously.)
- `decode HEXBYTES…` — JieLi objdump's reading of raw bytes; each probe padded with two
  `nop`s (upstream `PAD`) so an over-long decode cannot swallow the next probe.
- `encode "asm line"…` — JieLi assembler's bytes per line (exit 1 on any error).
- `site VA:HEX [--image]` — **the mandatory second opinion**: splices the patch into the
  image context (`VA−8 … VA+len+8`), prints JieLi objdump's reading of the neighbourhood
  with `(before)` / `<-- PATCH START` / `<-- re-entry aligned` marks, and FAILs unless
  the instruction at the site is exactly `len(HEX)` bytes **and** an instruction starts
  at `VA+len`. Prints a reminder that the decode **text** still needs a human for
  INTENT.

Without a fetched toolchain every sub-command except `status`/`fetch` degrades to a
clean one-line message + the fetch command, exit 1.

## 35.6 Caveats — what a sim PASS does and does not mean

- Models are fitted to the **AC791N** (upstream `hw/fm1-*` runs). **Nothing is
  hardware-confirmed on our BR23/AC635N die** (§34.10); chip-specific behaviours
  (FPU revision, `popcnt`, reset forms) are unmeasured here. Our caves use only plain
  ALU/memory/branch forms where the two revisions agree in the table.
- SFR reads return 0; SFR writes stop the run; interrupts never fire; timing is not
  modelled (no cycle accuracy).
- A sim PASS proves the **logic** of the patch executes as intended on hardware-fitted
  semantics. **Flashing the radio remains the final authority** — this tool's purpose is
  to remove the cheap-to-prevent failures (wrong branch, wrong register, wrong length)
  from the hardware queue, not to replace it.

## 35.7 Added to the instructions

`.github/copilot-instructions.md` MANDATORY SECOND OPINION bullet (static-analysis
workflow section) now reads — every new cave body / trampoline / patch encoding must be
checked **before flashing** by: (1) the upstream table decode (§34,
`python3 -m pi32v2isa disasm` / `pi32dis.py --upstream`), (2) `tools/jl_sim.py` — run
the patch overlay + `--expect` assertions pre-flash, (3) `tools/jl_oracle.py site` once
the pinned toolchain is fetched, for the JieLi-authority length/alignment/decode verdict.

## 35.9 Strategic: does the open toolchain re-open the C-source route? (2026-11-10)

- **Ghidra-C round-trip: NO.** ch. 32's 4 field-dead splices died at the *decompiler* (ghidra-jieli is 'very early stage' even in upstream's own SOURCES); the open LLVM fork replaces only the compile/link half, which ch. 25 already proved trustworthy (fixed-point). Whole-function decompile→recompile stays unsafe; `jl_rt_asm.py` remains the faithful-edit route.
- **Hand-authored C → cave splice: YES, newly strong (this is the R8 shape of §30.14.45).** We author the source, so nothing is lost at decompile time. Enablers: open `clang -target pi32v2 -mcpu=r3` + `ld.lld` releases `pi32v2-23.1.5-5` (`-Oz` code −4.64 % vs JieLi; `-pi32v2-large-program` 6-byte `call.xl` for far caves), fully documented ABI (upstream COMPILER.md + ch. 34), and the ch. 35 sim/oracle pre-flash gates. A C blob can call app functions by absolute address (function-pointer casts to `0x01E1792E` etc.). The Phase-A bind-flow decode (§30.14.41) becomes a re-implementable SPECIFICATION: a task-level routine walking the app's own state expectations — precisely where R3–R7's byte/command levers died (the bind needs app-originated flow state BEFORE connect-complete). The wall (bind logic in TID's closed app) is unchanged; the authoring weapon is upgraded from hand-asm caves to real C.
- **SDK rebuild as full-app replacement: still not the H3 app.** The `0x102F0` bind logic exists as C source only in the SDK's generic single-device analogue (`user_info_t`, ch. 22 §9B.11), never TID's app (no fork contains it, §28.7). An SDK build boots + pairs (ch. 32 P0/P1) but ships a reference app — all H3 radio UI/BK4819 work would need re-implementation; and the fork's JieLi-LLVM-4 bitcode reading (4898/4900) is proven on the AC79 SDK only, AC63/br23 unmeasured (upstream GAPS). For the two-device goal the ESP32 combo device remains the cheaper sidestep (§9B.6.1).

## 35.8 Artifacts

- `tools/jl_sim.py` — simulator wrapper (§35.2); tests §35.4 all as recorded.
- `tools/jl_oracle.py` — oracle wrapper (§35.5); `status` tested, graceful-degrade paths
  tested (`decode`/`encode`/`site` exit 1 with the fetch hint, no traceback).
- Docs: `tools/Tools.md` §4.8/§4.9 + TOC, `findings/17-tooling-index.md` rows.
- Reference: [ch. 34](34-pi32v2-isa-open-reference.md) (upstream repo study),
  upstream `docs/ORACLE.md`, `tools/llvm/sim.py`, `tools/hwtest/semantics/`.
