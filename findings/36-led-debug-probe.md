# 36 — LED debug probe (the two top LEDs)

§36: the two top LEDs of the H3 Plus decoded as a **serial 4-wire LED-driver IC**
bit-banged by a self-contained app library, and an `--led-probe` patch option that
fires a known LED frame at every TX start as an on-hardware execution marker for
statically-predicted code paths. Requested by the user 2026-11-11 (find a controllable
probe to verify assumptions on hardware; "if not possible or useful leave it").

## §36.1 Hardware model (static, 2026-11-11/12)

The top-left/top-right bi-color LEDs are **not** plain GPIO and **not** the JieLi
PWM/PLED peripherals. They hang off a serial LED-driver IC driven by a small
self-contained app library at `0x01EB6xxx` — **zero external call edges** into
`[0x01EB6000, 0x01EB7600)` (call/goto scan of `work/full_upstream.lst`); the library
is entered only via indirect `rN = <addr>; call rN` pairs (e.g. `r1 = 0x01EB6140`
@`0x01E00168`/`0x01E5D102` — that target decodes as zero padding in the app image;
unresolved, deprioritized).

Signals (all via the library primitives below):

| Line | Pin(s) | Primitive |
|---|---|---|
| CS / latch | PD3 (strap 0) / PA13 (strap 1) | `FUN_01eb62c0(r0=0/1)` — DIR-bit-clear output, OUT bit := r0!=0; returns 0xA |
| CLK | PD0 | inside `FUN_01eb6f0c` |
| DAT (out) | PD1 | inside `FUN_01eb6f0c(r0=byte)` — 8-bit shift-out |
| MISO (read-back) | PA14 / PD2 | variant `0x01EB7064` (3-wire with read) |

The CS pin choice is a **board strap**, sampled once at boot:
`DAT_00010d25 = (_DAT_001e511c & 0x20) >> 5` in `FUN_01e81f04` (only writer; the
single reader is `FUN_01eb62c0`). Not a VFO selector.

Bus helpers: `FUN_01eb6eea(r0=2)` = lock/delay around frames; `FUN_01eb6fac` =
bus init. A frame renderer at `0x01EB6FF0` reads a RAM state record
(`[r4+0x10], [r4+0x11], [r4+0x12], [r4+0x14], [r4+0x15]`) and shifts it out with
CS toggles — the library renders frames from RAM, several fixed sequences exist in
the cluster `0x01EB6FF0..0x01EB71xx` (internal gotos only).

**Frame protocol (working hypothesis, from the app's own sequences):**
`[0x0F, b1, b2, b3, b4]` — reg `0x0F` = LED control, byte3 = LED select
(bit0/bit1/3 = both), byte4 = brightness/mode (`0x40` = lit); `0x18` = commit.
Observed frames: `[0x0F,0,0,3,0x00]`, `[0x0F,0,0,1,0x00]`, `[0x18]`, and in the
animation runner `0x01EB70CE`: `[0x0F,0,0,3,0x40]` (= **both LEDs lit** hypothesis)
followed by an `r6=0x1FFFF` delay loop (that runner is NOT IRQ-safe; the frame
writer itself is short). Charge-status LED dispatcher `0x01EB6432` reads
`JL_CHG 0x1F0200` bits 8–11 + tbb switch.

Rejected paths (recorded so they are not re-chased): PLED engine `0x1E5200`
unused at runtime (zero `_DAT_001e520x` refs); `FUN_01e5ca36`/`FUN_01e5cc42` =
deep-sleep GPIO park; `FUN_01e136b4` + the `0x1E5160` refs = USB band;
`FUN_01e51740` = 5-byte table writer into `0x102F0+0xFA4/+0xF7C` (its PORTx
immediates are mis-bounded Ghidra artifacts); `FUN_01eb6f0c` itself is the
shift-out primitive, not a top-LED setter.

br23 GPIO facts confirmed en route: `ls_base=0x1E0000`,
`map_adr(grp,adr)=(64*grp+adr)*4`; PORTA=`0x1E5000`, PORTB=`0x1E5040`,
PORTC=`0x1E5080`, PORTD=`0x1E50C0` (stride 0x40); struct
`OUT=+0x00/IN=+0x04/DIR=+0x08/DIE=+0x0C/PU=+0x10/PD=+0x14`; **DIR-bit-CLEAR =
OUTPUT** (confirmed by `FUN_01eb62c0` + the SDK `IO_DEBUG_*` macros). The
menu label array for Radio Settings is `0x01EBD088` (41×4 B string ptrs,
"Breath LED" = idx 31 @`0x01EBD104`, string VA `0x01E8A013`); its menu indexer
was not needed and remains untraced.

## §36.2 The probe design

`--led-probe` (patch tool) = **62 B fire routine @`0x01EA7722`** (ends
`0x01EA7760`, inside the 364 B ALLZERO cave run `0x01EA76DE..0x01EA7849`) +
**4 B redirect** of the BT-PTT2 cave handler tail at `CAVE_VA+32`
(`0x01EA76FE`: `fe ea f3 8e` → `c0 ea 10 00`). Fire-routine bytes:

```
80ea437c 4022 80eadf7b 4020 80eac775 402f 80eaea7b 4020 80eae77b 4020
80eae47b 4023 80eae17b 5020 80eade7b 4021 80eab575 4022 80eac77b feeac48e
```

= `call 0x01EB6FAC` (init) / `r0=2; call 0x01EB6EEA` (lock) / `r0=0; call
0x01EB62C0` (CS low) / shift `0x0F,0,0,3,0x40` via `0x01EB6F0C` / `r0=1; call
0x01EB62C0` (CS high) / `r0=2; call 0x01EB6EEA` / `goto32 0x01E794E8`
(`H2A_RESUME_VA`) — stock TX start proceeds unchanged.

Because it rides the BT-PTT2 handler tail, it fires at **every key-0x2A TX
start** (main PTT, PTT2, BT-PTT) in the key-scan standby-handler **task
context** (HW-confirmed safe per ch. 23). Requires a BT-PTT2 action
(`--PTT2=BT-PTT2` or `--OD-PTT=BT-PTT2`); mutually exclusive with
`--incoming-redial/--incoming-mode3/--incoming-hfp/--cmd5-target/--gate-close/
--r1-kill/--r1-walker-kill/--d1-target-wait` (cave-window overlap at
`0x01EA7722`). Patch site `ledprobefire` carries recognition-only states for
the other window occupants (gated / inchrdl / inchrdlbind / inchrdlcur /
inchrdlappswap) so `--show` stays clean on every image family; the
gatecave/r1cave/r1bcave/inchrdlcave sites gained matching `ledprobe` states.

## §36.3 Verification evidence (pre-flash)

- **Upstream oracle** (ch. 34/35 MANDATORY SECOND OPINION): every byte of the
  fire routine decoded via `pi32v2isa` objdump — all call targets land exactly
  (`0x01EB6FAC/0x01EB6EEA/0x01EB62C0/0x01EB6F0C`), final `goto −189048` lands
  exactly on `0x01E794E8`; lengths + re-entry aligned.
- **Suites**: `tools/verify_actions.py` FAILURES: 0 and `tools/verify_cli.py`
  FAILURES: 0 — incl. 7 new CLI cases (`lp`, `lp_e7`, `lp_alias`, `lp_alone`
  rc1, `lp_conf_redial` rc1, `lp_conf_gate` rc1, `lp_conf_mode3` rc1) and a
  verify_actions block (fire bytes at `P.LEDPROBE_CAVE_VA`, redirect
  `c0ea1000` at `CAVE_VA+32`, ALLZERO fit, `--show` clean, idempotent).
  (One real bug found by the suites: `show()` KeyError — every `states` key
  needs a `labels` key; fixed.)
- **jl_sim** (ch. 35 gate): `jl_sim.py --start=0x01EA7722` on the decrypted
  `ch36_ledprobe.bin` ran 200 000 steps (bit-bang loop spins — expected), pc
  ended inside the shift-out helper `0x01EB6F00`, return chain `0x01EB6FB2`,
  SP return addr `0x01EA7726` (our routine's 2nd insn), GPIO-style writes
  observed (`0x1E0400←0x11`, `0x1E0408←0x28`). Window-execution evidence per
  the R8 precedent; flashing stays the final authority.
- **Image**: `work/ch36_ledprobe.bin` sha256
  `00a36286578a54ef32e7f9ebc59d3187e8b98356de442041d234344032faacd9` =
  E7-ref (`90bec320…`) + full E7 recipe + `--led-probe`; **65 bytes changed,
  sector `0x0AC000` ONLY**, uboot `0x0000–0x4FFF` byte-equal. Rebuild after
  the label fix reproduced the identical sha.

## §36.4 Field trial — UNTESTED

Stage: `sudo bash work/ch36_ledprobe.sh` (1-sector write + readback +
full-flash strict-region verify). Card: `bash work/ch36_ledprobec.sh` —
T1 breath control, T2 main PTT (both LEDs vs stock single red + keying
normal), T3 PTT2, T4 RX green control, T5 BT-PTT intact, T6 oddities, verdict
usable y/n + exact colors/positions (decodes byte3/byte4).

If T2 shows **no change**: alternates to try in a retry build — frames
`[0x0F,0,0,1,0x00]`, `[0x0F,0,0,3,0x00]`, `[0x18]` commit (one retry), then
per the user agreement the verdict is "impractical" and the probe is dropped.

## 36.5 Field run 2026-11-12: flash-verify STOP — orphan R8 hook (radio-state lesson)

The first flash of `work/ch36_ledprobe.bin` (stage `work/ch36_ledprobe.sh`, log
`work/logs/ch36_LEDPROBE_20261112_194429.log`) passed every preflight (image sha
`00a36286…`, uboot `cmp -n 0x5000` vs E7-ref, sector-diff = `0x0AC000` / 65 B) and
sector `0x0AC000` came back byte-identical — but the full-flash strict-region
verify (§30.3) flagged **4 mismatching bytes** and STOPped.

**Root cause (confirmed against the readback
`/tmp/opencode/ledprobe_full_rb_20261112_194429.bin`):** the radio was on **R8**
(`work/ch30_r8.bin` `4bb75a2c…`) before this flash. R8 had put its 4-byte tbh hook
at flash `0x66270` (VA `0x01E61270`, sector `0x066000`) redirecting
connect-complete into the R5/R8 cave at `0x01EA7722`. The ch36 stage writes only
sector `0x0AC000`, so the `0x066000` hook survived as an orphan — the readback
bytes `36 82 A6 F1` match R8 exactly where the expected image has E7-ref's
`E4 86 95 CE`. The STOP was correct: the orphan hook points into the new LED fire
routine (which resumes at `0x01E794E8`, wrong context for connect-complete) and
would have crashed on the first BT connect.

**Repair (image-consistency fix, not a rollback):** write sector `0x066000` from
`work/ch36_ledprobe.bin` (its content there is identical to E7-ref — clears the
orphan hook), then re-run the stage script (its `0x0AC000` write is idempotent and
the full verify then passes).

**Lesson (now enforced by the stage script):** single-sector images must only be
flashed onto a radio that is actually at the base image. `work/ch36_ledprobe.sh`
gained a **radio-state precheck**: full-flash read + strict-region compare against
the expected image (ignoring the sectors about to be written), STOP listing the
differing sectors when the radio is not at base.

Status: probe field verdict still **UNTESTED** (card `work/ch36_ledprobec.sh` to be
run after the repair).

## §36.6 v1 field card run 2026-11-12 — NO visible effect (stock behavior)

Log `work/logs/ch36_ledprobecard_20261112_202351.log` (after the §36.5 repair +
re-stage; sector `0xAC000` readback byte-identical, full strict-region verify green):

- T0 boot normal; T1 standby breath **unchanged** — both LEDs GREEN together
  ~0.5 s every 5 s (screen off).
- T2 MAIN PTT: left LED red while held — "same as stock"; T2c keying normal.
- T3 PTT2: right LED red — stock. T5 BT-PTT keys, left red; normal PTT after
  (no flag leak). T6: no freeze, no oddities.

**Verdict: the probe produced no visible marker.** No crash/reset across many TX
starts ⇒ the fire routine executed (all call targets are real live functions, the
redirect verified in the flashed sector); but frame `[0x0F,0,0,3,0x40]` + CS-high
changed nothing observable.

**Hypotheses:** (1) top — the driver IC needs the **[0x18] commit/latch frame** the
app's own cluster @`0x01EB6FF0` sends after its data frames (observed sequence:
`[0x0F,0,0,3,0x00]`, `[0x0F,0,0,1,0x00]`, `[0x18]`) — v1 omitted it; (2) the stock
LED state machine re-renders right after TX start and overwrites; (3) the
bit-bang library is vestigial on this board (breath = both-green-500 ms is not
explained by our model; the library's external entry points were never located).

## §36.7 v2 retry build (ch36b) — authorized one retry, 2026-11-12

Per the agreement (findings/36 §36.4 + user 2026-11-11): one retry, chosen fix =
hypothesis (1), then verdict "impractical" and the probe is dropped.

- **80 B fire routine** @`0x01EA7722` (ends `0x01EA7772`, cave run limit
  `0x01EA7849`): v1's 62 B sequence **plus** a commit frame — CS low (`call
  0x01EB62C0` r0=0), shift `0x18` (`call 0x01EB6F0C`), CS high — then
  `goto 0x01E794E8`. The v1 prefix (bytes 0..57) is byte-identical.
- **Encoding correction:** `r0 = 0x18` = `40 38` — my initial guess `50 28`
  assembles as `r0 = 0x48` (upstream disasm caught it). li.u8 rule:
  `byte0 = 0x40 | ((imm >> 2) & 0x30)`, `byte1 = 0x20 | (imm & 0x1F)`.
  All 26 instructions verified with the upstream oracle
  (`python3 -m pi32v2isa disasm --base 0x1ea7722`) — clean decode, correct
  lengths, new calls land on `0x01EB62C0`/`0x01EB6F0C`.
- Patch tool updated (fire bytes 62→80, asserts, R1/R1B/GATE/INCHRDL foreign-window
  slices 54:62→54:80, `_ird_w - 80`, help/error strings); **both suites 0
  failures**; import-time asserts green.
- **jl_sim** gate: same accepted signature as v1 (window executes into the LED
  library, GPIO-style writes `0x1E0400←0x11`/`0x1E0408←0x28`, bit-bang delay
  spins — R8-precedent window-exec evidence).
- **Image** `work/ch36b_ledprobe.bin` sha256
  `efa320904b6ab0cdeb4bd5bae84a0da31c3bbac92c1e71b481905c8f3ed9bcea` = E7-ref
  (`90bec320…`) + full E7 recipe + `--led-probe` v2; **83 bytes changed, sector
  `0x0AC000` ONLY**, uboot byte-equal. Stage `work/ch36_ledprobe.sh` (updated:
  EXPECT_SHA + 83 B assert + radio-state precheck) + card `work/ch36_ledprobec.sh`.
- **UNTESTED.** If T2 is still "same as stock" ⇒ verdict **impractical**: drop the
  probe, grind the compiled-C splice route (ch. 35 §35.9) instead.

**FIELD VERDICT 2026-11-12 (`work/logs/ch36_ledprobecard_20261112_222841.log`):
v2 ALSO shows NO visible change** — T2 main PTT = left red as stock ("different
from stock? no"), T3 PTT2 right red, T1 breath unchanged, T5 BT-PTT left red,
no crash, all features normal. Two raw-frame bit-bang attempts (v1 without, v2
with the `[0x18]` commit) both invisible ⇒ the frame theory was wrong; see
§36.8 for the root cause found by static analysis.


## §36.8 v2 field-fail root cause: the LED library is a RAM-RELOCATED BLOB (2026-11-12)

Static deep-dive (all decodings verified against the upstream oracle table,
ch. 34 MANDATORY SECOND OPINION):

- **App entry `0x01E00100`** (upstream decode of file `0x100`–`0x186`): after
  `call 0x01E2D930` + SSP setup + bss clear, a copy loop
  `r1=0x01EB6140; r2=0xCAF8; r2>>=2; loop {r3=[r1++=4]; [r4++=4]=r3}` with
  `r4=0` — **copies 0xCAF8 (51 960) bytes from flash `0x01EB6140` to RAM
  `0x00000000`**, then continues init (`call 0x01E80EEE`, `call 0x01E5B67A`,
  `goto 0x01E5CC42`). The blob IS the app's `.data` + RAM-code region
  (includes the `0xB390`/`0xBF4C` globals; stack at `0xD310` above it).
- **Consequence:** every LED primitive has a second, LIVE identity in RAM —
  CS `0x01EB62C0`→`0x180`, lock `0x01EB6EEA`→`0xDAA`, shift `0x01EB6F0C`→
  `0xDCC`, init `0x01EB6FAC`→`0xE6C`, runner `0x01EB70CE`→`0xF8E`. The
  bit-bang code itself is position-independent (absolute SFR writes), so the
  v1/v2 flash-copy calls DID toggle CLK/DAT — but see the render race below.
- **ZERO static references into `0x01EB6000`–`0x01EB7FFF`** anywhere in the
  app (call/goto scan, pointer-table scan, blob-internal low-RAM pointer scan
  for `0x180`/`0xDCC`/`0xDAA`/`0xE6C`/`0xF8E` — nothing). The library is
  entered only through runtime-patched RAM vectors (the blob starts at RAM 0 =
  the vector area). This is why the library looked "self-contained/orphan".
- **THE VENDOR RENDERER `0x01EB70CE` fully decoded** — this is the piece v1/v2
  missed. Prologue `77 04` = `[--sp]={rets,r7-r4}` (**preserves r4-r7 — safe
  to call from the BT-PTT2 handler context**); epilogue `37 04` pop + `goto
  0x01EB6FE8`. Body: `init(); lock(2); CS(0); shift[0x0F,0,0,3,0x40]; CS(1);
  lock(2)`; then `r6=0x1FFFF` (guard), `r5=0xB301`, `r7=0x1E0000`; outer loop
  `r4=0..6`: CS/shift transactions sending **`b[r4+r5]` = RAM STATE BYTES
  `0xB301..0xB307`**, inter-frame wait `if(--r6!=0)`, **SFR latch
  `[0x1E0000] |= 0x10`**, readback via the input fn `0x01EB7064` (bit-bang
  CLK pulse + sample PD1) with retry `if(r0!=0) goto -22`, `lock(5)`,
  `r4+=1`, `if(r4!=7) loop`.
- **The render race (root cause of v1/v2 invisibility):** the cave handler
  fires AFTER `call TXSTART2_VA 0x01E5993C` (stock TX start) and resumes at
  `0x01E794E8`; the app's own LED path then re-runs the vendor renderer,
  which RE-COMPOSES the whole panel from the state bytes `0xB301..0xB307` —
  instantly overwriting any raw frames we bit-banged. Raw frames without
  updating the state bytes can never win.
- **Off-cluster fn `0x01EB6FF0`** (RAM `0xEB0`) = fixed-frame blinder:
  `lock(2); CS(0); shift[0x0F,0,0,3,0x00]; CS(1); lock(2); CS(0);
  shift[0x0F,0,0,1,0x00]; …; shift[0x18]; CS(1); lock(2)` — confirms last
  frame byte = brightness (`0x40` on / `0x00` off) and `[0x18]` = commit.
  (Correction to §36.1–36.4: the earlier "renderer reads a RAM record at
  `0x01EB6FF0`" note was wrong — the RAM-payload sender is the runner loop.)
- **Bit-set API `0x01E51B1C`** (upstream decode): `r3=r0-0x18`; tbb 5 cases
  RMW bit `r1` (value `r2&1`) into `b[0x10355]` (no trigger) / **`b[0xB300]`**
  / `b[0x10353]` / `b[0x10354]` (these three `call 0x01FFFFD80` = trigger
  syscall into the second flash mapping `0x02000000`). Getter `0x01E821FC`
  returns `b[0xB300]`. No static callers/pointers found. Note `b[0xB300]` is
  NOT in the runner payload (payload = `0xB301..0xB307`). Blob init values at
  `0xB300` (file `0xC1440`): `03 10 F0 90 30 B0 80 00`.
- Re-confirmed dead ends: PLED SFR `0x1E5200` referenced once only
  (`0x01E821C6`, feature check); PORTE `0x1E5100` refs = keypad-scan/battery,
  not LEDs.


## §36.9 v3 build (ch36c): paint the state bytes + call the vendor renderer

Per the user's directive (2026-11-12): TX function expendable — make the
button drive a VISIBLE LED change by any means; observing what happens decodes
the interface.

- **44 B fire routine** @`0x01EA7722` (ends `0x01EA774E`, clear of the R1/R1-b
  cave at `0x01EA7758` — the old `FIRE[54:80]` overlap tail and the
  r1cave/r1bcave ledprobe recognition entries were REMOVED):
  `r0 = 0xB301` (`c0 ff 01 b3 00 00`, imm32 form); `r1 = 0xFF` (`79 3f`);
  7× `b[r0+n] = r1` (`52 ee 0n 10` — store-byte form, verified against the
  vendor `52 ee 77 1c` = `b[r7+0xC7]=r1`); `call 0x01EB70CE` (vendor runner);
  `goto32 0x01E794E8` (H2A_RESUME, stock TX start proceeds).
  HEX `c0ff01b30000793f52ee001052ee011052ee021052ee031052ee041052ee0510`
  `52ee061080eac27cfeeacd8e`.
  All 11 instructions verified via upstream `disasm` (call `63876` from +4 =
  `0x01EB70CE` ✓; goto `-189030` = `0x01E794E8` ✓).
- **Design:** paint the renderer's INPUT (state bytes all-ON = maximum
  distinctive signal) then run the VENDOR render sequence itself — it updates
  the state→panel mapping the same way stock does, including the SFR latch and
  the `[0x18]` commit, so the stock re-render afterwards recomposes the SAME
  all-ON panel (no race). Register safety: only r0/r1 touched before the
  runner; runner preserves r4-r7; resume overwrites r0 first instruction.
- Patch tool updated (fire 80→44 B, new asserts incl. literal imm/store
  forms, gatecave/inchrdlcave ledprobe states re-padded to `+44`,
  ledprobefire window/ctx_base 80→44, R1/R1B ledprobe entries removed,
  help/error strings); **both suites 0 failures**.
- **jl_sim** gate PASS: `--start=0x01EA7722` — memory trace shows
  `0xB301..0xB307: 00000000000000 → ffffffffffffff` (`--expect-mem` OK), the
  runner call lands (return link `0x01EA774A` pushed), bit-bang GPIO writes
  `0x1E0400←0x11` / `0x1E0408←0x28`, step-limit inside the delay loop
  (accepted window-exec evidence per v2 precedent — flashing is final
  authority).
- **Image** `work/ch36c_ledprobe.bin` sha256
  `387a4cf3865a139019bfed0737e91d374e972e93c21ef1112904e6fc7a3d16ee` = E7-ref
  (`90bec320…`) + full E7 recipe + `--led-probe` v3; **44 bytes changed,
  sector `0x0AC000` ONLY** (3 redirect + 41 fire — 3 fire bytes are literal
  `00`, identical to the zero-line keystream), uboot byte-equal. Stage
  `work/ch36_ledprobe.sh` + card `work/ch36_ledprobec.sh` updated.
- **UNTESTED.** Any visible change (which LEDs, colors, persistence) decodes
  the state-byte semantics for the real marker. If STILL invisible ⇒ verdict
  **impractical** per the agreement (user 2026-11-11): drop the probe, grind
  the compiled-C splice route (ch. 35 §35.9) for the two-device goal.

## §36.10 v3 FIELD VERDICT — STILL STOCK ⇒ probe IMPRACTICAL, DROPPED (2026-11-13)

Field card run on `work/ch36c_ledprobe.bin` (`387a4cf3…`); log
`work/logs/ch36_ledprobecard_20261113_074411.log`:

- T0a boot normal; T0b Jabra connected.
- T1 standby breath: "5 seconds both leds unchanged" (stock).
- T2 MAIN PTT: left red — T2b different from stock? **"stock"**; T2c keying normal.
- T3 PTT2: right red, "stock". T4 RX: green left/right stock.
- T5 BT-PTT: keys normally; LED as stock; T5b normal PTT afterwards (no flag leak).
- T6a: "all ok" — no freeze, no stuck LED, no oddity. V1 overall: **"stock"**.

⇒ **v3 produced ZERO visible effect — the third identical field result**
(v1 65 B raw frame, v2 83 B + `[0x18]` commit, v3 44 B state-byte paint +
vendor renderer call). No crash or reset in any round; every radio feature
normal; sector readback verified each flash.

**Interpretation.** The fire routine provably executes (the v3 sim trace shows
the stores landing and the runner call taken; the field shows no crash at the
same code). Two non-exclusive explanations remain, both fatal to the probe's
usefulness:

1. **Render race, final form**: the hook fires at TX START; the stock
   TX-start continuation (resume `0x01E794E8`+) recomputes the LED state from
   the app's own model and re-renders within milliseconds — whatever we paint
   is overwritten before the eye can see it.
2. **Vestigial library**: the serial LED-driver bit-bang lib (RAM blob
   §36.8) may not be the live panel engine on this board at all — the stock
   standby breath (both LEDs green ~0.5 s every 5 s) was never reproduced by
   anything we decoded, so the actual driver is elsewhere (unexplored
   candidates: PLED SFR `0x1E5200` hardware engine, charge-IC path).

**Verdict (per the binding agreement of 2026-11-11 and the card footer):
impractical — the LED probe is DROPPED.** No v4. The `--led-probe` option
stays in the patch tool (functional, oracle-verified, both suites green, and
its recognition states keep `--show` clean on the existing ch36 images) but is
marked **field verdict: impractical — DROPPED 2026-11-13**. The radio may stay
on `work/ch36c_ledprobe.bin` content — it is harmless (all features field-
normal); the user restores whichever image they want themselves.

Two-device work continues on the **compiled-C splice route** (ch. 35 §35.9).

