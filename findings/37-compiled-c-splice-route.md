# 37 — The Compiled-C Splice Route: toolchain live, pipeline proven (2026-11-13)

Chapter §37: opening of the **compiled-C splice route** (chosen at §30.14.40, strategy
set by [ch. 35 §35.9](35-pre-flash-simulation-and-pinned-oracle.md)): hand-authored C,
compiled with the open `pi32v2-llvm` clang, linked at a fixed cave VA with ld.lld,
spliced into the app image. Goal: the task-level bind routine for the two-device plan
([ch. 30](30-two-device-plan.md)) — the multi-step, state-waiting sequence that the
seven one-shot byte/command levers (R3–R8, §30.14.21–49) could not express.

## 37.1 Toolchain

- **`jvitkauskas/pi32v2-llvm` release `pi32v2-23.1.5-5`** (linux-x64, 62 MB),
  sha256 `a20e257b840eb6b212761bfa93a7f3804502940d0035d62790da3d42fefa31e3` —
  **verified against the release `SHA256SUMS`** (manifest saved alongside).
  Installed OUTSIDE the repo (no binaries published): `/home/stefan/h3plus/pi32v2-llvm-23.1.5-5-linux-x64/`.
  `bin/clang --version` → `clang version 23.1.5 (…/pi32v2-llvm 60b0340f) Target: pi32v2` ✓.
  Full suite present: `ld.lld`, `llvm-objdump`, `llvm-objcopy`, `llvm-readelf`.
- Flags that work (smoke-tested): `-target pi32v2 -mcpu=r3 -Oz
  -mllvm -pi32v2-large-program` (the large-program option is a **-mllvm** flag, not a
  plain clang option — `unknown argument` otherwise), `-nostdlib` for cave blobs.

## 37.2 Pipeline proof (compile → link → splice → sim → oracle) — PASS

Test source (`helper` + caller of absolute app VA `0x01E1792E` via function-pointer cast)
compiled and linked at **cave VA `0x01EA7702`** (the free gap right after the BT-PTT2
handler, which ends exactly there; run end `0x01EA7849`):

- Linker script: `ENTRY(<fn>) SECTIONS { . = 0x01EA7702; .text : { *(.text .text.*) } }`.
- **Codegen observations** (all vendor-form, byte-verified):
  - imm32 absolute load = `c1 ff 2e 79 e1 01` — identical to the known `li.u32`
    `cD ff <4B LE>` form (hand-encodings match the compiler).
  - Prologues/epilogues match vendor: `[--sp]={rets,r4}` = `74 04`, `[--sp]=rets` =
    `10 04`, `pc=[sp++]` = `00 04`, `{pc,r4}=[sp++]` = `54 04`, `rts` = `80 00`.
  - **Intra-blob direct calls RELAX to 2-byte short calls** (`71 9a` = `call -12`) —
    position-independent once linked, no relocation left (`llvm-readelf -r`: none).
  - **Absolute-address app calls stay `li.u32 + call r1`** (`c1 00`) — the compiler does
    not constant-fold a cast integer into a direct branch. Exactly the mechanism the
    bind routine needs to call app functions (`user_send_cmd_prepare`-style posts,
    `FUN_01e5af40`, etc.) from cave code, with the full JieLi C ABI handled correctly
    (args r0–r3 + stack words, r4–r15 callee-saved).
- **jl_sim execution**: `--start 0x01EA770A --patch 0x01EA7702:50e15a00800010040881719a0004
  --regs r0=5 --rets 0x01EA7712 --expect r0=92` → **PASS** — `r0 = (5+1)^0x5A = 0x5C`:
  the compiled push/call/xor/return chain executed correctly on the AC791N
  hardware-fitted CPU model. (Sim note: `--rets` lands as return-link-4; the run
  re-entered the tail and hit the step limit AFTER the assertion value was final —
  for future sim gates stop on a sentinel or use `--call`.)
- **Upstream oracle** (`pi32v2-isa disasm`): all 14 blob bytes decode exactly, correct
  lengths, re-entry aligned. (MANDATORY second opinion satisfied for compiler output too.)
- **Image round-trip**: E7-ref `work/ch30_e7ref.bin` (`90bec320…`) → `sfc_enc_decrypt`
  (library call, `base=0`, `chipkey=0xF181` — round-trip identity `True`) → splice 14 B
  @file `0xA7702` → re-encrypt → `work/ch37_pipeproof.bin` sha256
  `b2c28b8adf5d3b19c16ad52b5dfdfaa9dbaf1db9b7dd6e52e0793b8bfc411120`:
  **14 bytes changed, sector `0xAC000` ONLY, uboot `0x0000–0x4FFF` byte-equal** ✓,
  decrypt-back shows the blob ✓. NOT staged for flash — pipeline artifact only.
- Gotcha recorded: the `jl_sfcenc.py` **CLI** defaults to the stock app span
  (`0x5000`–`0xC8FE0`, `--start`) and silently truncates differently-sized slices;
  use the **library** `sfc_enc_decrypt(data, base=0, chipkey=0xF181)` for arbitrary
  windows (it is symmetric — re-encrypts).

## 37.3 Cave budget (current lineage)

Run @`0x01EA76DE` (364 B ALLZERO, ends `0x01EA7849`), users in the E7/S1 lineage:
BT-PTT2 handler `0x01EA76DE..0x01EA7702` (36 B incl. tail redirect) → **free
`0x01EA7702..0x01EA7849` = 327 B** (led-probe's 44 B only exists on ch36 images).
The R-series INCHRDL cave (`0x01EA7722..0x01EA77D0`) is NOT in E7-ref/S1.
327 B is the first budget for the C routine; if it needs more, ch. 23-style ALLZERO +
pointer-scan hunts (freespace.py) find further runs.

## 37.4 Design target — the task-level bind routine

Spec = §30.14.41 Phase-A bind decode + §30.14.47–49 R8 findings. What died and why:
incoming joins never run the app-originated dial flow ⇒ struct `0x102F0`/app handle
`_DAT_00010372` never written ⇒ no HFP/SCO (R8 moved the mic routing by swapping the
slot — first audio-state movement — but SCO was never live). One-shot cave hooks
cannot express the app's multi-step connect sequence with inter-step state waits.

The C routine's job (task context = bt task main loop `FUN_01e60e44`, where the tbh
hook `0x01E61270` lives): a small **state machine across hook invocations** that (a)
detects the incoming HFP-class join, (b) drives the app's own profile-establishment
path for the joiner — including the **profile-start command family 12/14/18/74
(never tried: §30.14.28 NEXT was cut short by the R5 pivot)**, (c) delivers the app
handle/slot like R8 did (proven mechanism), (d) opens SCO via the app's own path.
Static homework next: map the stock Connect-press HFP/SCO establishment sequence
(settings handler `FUN_01e6ec9e` → dial → connect-complete sink `FUN_01e5af40` →
who posts cmd `0x1E`/`0x3e` and the 12/14/18/74 family).

Status: **pipeline proven, routine NOT yet authored, nothing UNTESTED on hardware in
this chapter** (`ch37_pipeproof.bin` is a bench artifact, not staged).
