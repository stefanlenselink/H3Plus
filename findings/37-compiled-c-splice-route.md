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
BT-PTT2 handler `0x01EA76DE..0x01EA7722` (**FULL 68 B** incl. tail redirect — corrected
in §37.6: the earlier "36 B / free from `0x01EA7702`" was wrong, bytes `0x702..0x722`
are live press/release helper code) → **free `0x01EA7722..0x01EA7849` = 295 B**
(led-probe's 44 B only exists on ch36 images).
The R-series INCHRDL cave (`0x01EA7722..0x01EA77D0`) is NOT in E7-ref/S1.
295 B is the first budget for the C routine (`--bind-c` v1 fits: 200 B, §37.6); if it
needs more, ch. 23-style ALLZERO + pointer-scan hunts (freespace.py) find further runs.

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

## 37.5 Static homework — the stock Connect-press flow FULLY DECODED (2026-11-13)

Evidence: `work/notes/ch37_disasm_evidence.txt` (384 lines: `app_dispatcher_0x01E1792E`,
`dial_0x01E600B4_and_setter_0x01E60120`, `press_tail_0x01E6EC9E`), all regions decoded
with the upstream oracle (ch. 34) — the 6-byte `FF00–FFEF` compare forms that desynced
`work/full.lst` are resolved there.

**Press = `FUN_01e6ec9e` (settings Connect), ends `0x01E6EDDC`:**
1. `r9=0xB390`; record table ptr `[0xB4A8]`, record stride `0xC`, `idx*0xC`; class byte `[rec+4]`.
2. `call 0x01E60120(r0=1)` = **mode setter(1)** @`0x01E6ECBA` — waits `b[0x10E00]>>6 == 1`
   (10 ms × ≤100), on timeout posts `0x4A`/`0x12`/`0x5` cleanup.
3. Posts via USP wrapper `0x01E1792E`: **cmd 17 PAGE_CANCEL, cmd 18, cmd 5** (each `(cmd,0,0)`)
   @`0x01E6ECC6/D0/DA` (ch. 31's "cmd-5 kick post" = this one ✓).
4. `call 0x02001F82(5)` delay.
5. **DIAL @`0x01E6ECEA`: `r0 = [[0xB4A8]+idx*0xC+8]` (record's BD_ADDR ptr) → `call 0x01E600B4(r0)`.**
6. Post bookkeeping (paired-table slot copy via `0x01E52B9C`/`0x01E52BC6` walks) — **NOT the
   `0x102F0` current-device record.**

**Dial wrapper `0x01E600B4(6-byte BD_ADDR ptr)`:** gate `b[0x10E00]&~0x3F == 0x40` else
return 0; loop wait handle-valid (`0x01E16E0E` ≠ 0, delay 10); `r5=0x01E17F26()` (idle check,
`0x80`=busy); `handle==0` → post `0x4A`; `r5==0` → post `0x12`; post `0x5`; wait
`0x01E17F26()==0`; **post cmd 1 `(1, 6, addr)`** → dispatcher marshals addr → `0x1A65D` →
relay case 1 → dial executor `0x01E07386`. So stock Connect = teardown + wait-idle +
app-originated DIAL; the `0x3e` connect-complete sink `FUN_01e5af40` then writes
`_DAT_00010372` + `0x102F0` and the classifier/bind proceed — exactly the state R3–R8
never created (§30.14.49). **Why R4 died:** raw cmd-1 replay skipped setter(1)/17/18/5/
delays AND hit the live-ACL no-op; **why R5 died:** mailbox redial dials at STACK level,
bypassing this app wrapper entirely.

App dispatcher `0x01E1792E` full map + relay `0x01E22890` case table (cmd 1 dial executor
`0x01E07386`, cmd 3 `0x01E073F4`, cmd 5 executor `0x01E074DE`, cmd 11 conn-record create,
cmd 21 scan/conn enable family) + SDK enum (`fw-AC630N_BT_SDK/include_lib/btstack/
avctp_user.h`: 1=START_CONNEC_VIA_ADDR, 5=READ_REMOTE_NAME, 17=PAGE_CANCEL, 18=SNIFF_IN …)
are in the evidence file. ⚠ Enum/field drift noted: enum cmd 5 = READ_REMOTE_NAME but the
kick's cmd-5 post empirically executes HCI-Disconnect (`0x01E074DE`) — vendor enum ≠ our
build's relay table; trust the decode.

## 37.6 The `--bind-c` compiled-C routine — BUILT 2026-11-13, UNTESTED on hardware

**Design (v1):** at the proven tbh hook `0x01E61270` (connect-complete, ran in-field on
R3/R4/R5 without freeze), when routing byte `b[0xB464]==1` AND both conn slots inuse
(`b[0x1A5CA]&0x20 && b[0x1A5E6]&0x20`) AND not yet fired → arm **sticky** sentinel
(`0xB17DF17D` @`0x1C008`, one attempt per boot, matches P7 one-join-per-boot), save the
joiner BD_ADDR (`[sp+20]`, R4-proven contract) → `0x1C000`, HCI-kick the joiner
(`0x01E17420(0,addr)` → `0x01E07B08(h,0x13)`, R5-proven calls), wait-gone ≤400×10 ms, then
**replay the press flow for the joiner**: `0x01E60120(1)`; USP `17/18/5`; delay 5;
`0x01E600B4(&store)` = app-originated DIAL. Returns the routing byte in r0 (hook replaced
stock load `50ee640d`; `r6=0xB390` preserved by the C ABI). Worst-case block ≈ 6 s in the
bt task (setter/dial have their own bounded waits) — accepted risk, stock setters block
similarly; queue check DROPPED (v1 bug: `[0x1A688]` is a queue head ptr, always non-zero ⇒
would have hung).

**Build:** `work/ch37/bind_c.c` →
`/home/stefan/h3plus/pi32v2-llvm-23.1.5-5-linux-x64/bin/clang -target pi32v2 -mcpu=r3 -Oz
-mllvm -pi32v2-large-program -nostdlib` + `ld.lld -T blob.ld` (`. = 0x01EA772A`) →
**zero relocations**, 192 B body + 8 B hand thunk = **200 B @`0x01EA7722..0x01EA77EA`**
(≤ cave end `0x01EA7849` ✓). Thunk `00 25 80 ea 01 00 80 00` = `r0=[sp+20]; call body; rts`.
Gotchas found: (1) `d8 e9 14 00` is a **halfword** load — the word-load form is `00 25`;
(2) the BT-PTT2 handler fills the FULL 68 B `0x01EA76DE..0x01EA7722` — free cave starts at
`0x01EA7722` (first blob base `0x01EA7702` was a placement bug, re-based; body is
PC-relative/slide-safe); (3) statics RAM `0x1C000..0x1C00F` chosen by full-app scan: zero
absolute refs (`0x1B6B8`+ = PM sleep save span → live RAM, writes survive; `0x1BFF8`/
`0x1D400` hits were bogus/relative).

**Verification:** upstream oracle decoded all 200 B at final base (thunk/guard/sentinel/
copy-loop/FIND/KDISC/DELAY/SETTER/USP×3/DIAL/tail-return all correct); **jl_sim T1/T2/T3
PASS** (`--start 0x01EA7722 --sp 0x1C100 --rets 0x01E61274 --regs r6=0xB390`: T1 full chain
→ dial reached, `0x1C000=aabbccddeeff` + `0x1C008=7df17db1` mem-asserts OK; T2 byte=3 →
r0=3; T3 armed → r0=1).

**Patch tool:** option `--bind-c` (dest `bind_c`): `bindchook` (`50ee640d`→`82ea5732` —
byte-identical to the R5 hook, cave window disambiguates) + `bindccave` (200 B);
mutually exclusive with `incoming_*`/`redial_*`/`cmd5_target`/`gate_close`/`r1_*`/
`d1_target_wait`/`led_probe` (shared hook and/or cave run); reciprocal recognition states
taught into ledprobefire/gatecave/r1cave/r1bcave/cmd5tcave/presstcave/inchrdlcave/
inchrdlcurcave + the three tbh-hook sites; bindccave legacy states include the R1-e combo
payloads (`legacy_cmd5t_presst`, `legacy_gate_cmd5t_presst`) — three recognition-state
fixes were needed (2 combos + presstcave 6 B window pad; lesson: every window must be
taught at FULL state length). **Both suites 0 failures** (verify_cli +7 bindc cases;
verify_actions + bindc build/show/idempotent block).

**Image:** `work/ch37_bindc.bin` sha256 `3753c7966a573eb6ab79f25fee5756a60ff84d562a3da3a3706ade3751be30f9`
= E7-ref `90bec320…` + full S1 recipe (`--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT
--conn-num=2 --no-kick --force-page-scan --force-role-keep --no-disconnect-13
--no-pairing-kick`) + `--bind-c`. Diff **183 bytes, sectors `0x066000`+`0xAC000` ONLY,
uboot byte-equal** (17 of the 200 cave bytes are literal `00` = unchanged keystream).
Stage `work/ch37_bindc.sh` (EXPECT_SHA + 183 B/2-sector assert + radio-state precheck +
uboot assert + readback + full strict verify) + card `work/ch37_bindcc.sh` (S1 GOAL =
audio bound to Jabra both directions after incoming join; S2 echo/teardown; S3 menu-Connect
press; S4 repair press; S5 S1 features; S6 P7 power-cycle) — `bash -n` OK.
**UNTESTED on hardware — verdict §37.7.** If the goal-miss signature repeats (TX radio mic
+ RX silence), the remaining lever inside the press-replay is the never-tried profile-start
family 12/14/18/74 posted between setter and dial (§30.14.28 NEXT).

## §37.7 FIELD VERDICT — `--bind-c` v1 GOAL-FAIL + TID-PTT crippling regression (2026-11-14)

**Run:** flashed clean via stage (after two stage-script assert-format bugs — image innocent
both times: `%05X` vs 6-digit expected list, mirrors the R7 stale-assert class; fixed in
`work/ch37_bindc.sh`). Card log `work/logs/ch37_bindccard_20261114_183920.log`.

**User report (verbatim):** "I noticed that the TID-PTT never worked. Not when only 1 device
connected, not via aut-join not via menu connect or via pairing. It seems to be connected,
according to the leds but not working when pressing the button."

**Card summary:** T0b Jabra connected. S1.0 TID-PTT first = y. S1a "Mobile connected audio
from the Jabra" (the Jabra went to the phone, not the radio — no drop+reconnect to the radio
observed). S1b TID-PTT ACL alive (LED; radio PTT lights the TID-PTT) but its button events
never reach the app. S1c TX = silence (second radio sees carrier, no audio). S2a no echo;
S2c TID-PTT still dead. S3a menu Connect press: no freeze, **directly disconnected the
TID-PTT**; S3b responsive. S4a both-up press on Jabra: "only jabra kicked". S5a BT-PTT via
TID-PTT = n. S5b PTT/PTT2 normal = y. S6a power-cycle: TID-PTT auto-reconnects only.
O1 no freeze/crash. **V1 = GOAL FAIL (8th identical-class miss) + NEW REGRESSION: the SPP
command path is crippled whenever the bind sequence engages.**

**Analysis (two converging hypotheses, both rooted in the v1 guard being too naive):**
1. **Self-kick at boot:** the guard (byte==1 && both conn slots inuse) cannot tell WHICH
   connect-complete it is looking at. With both TID-PTT and Jabra remembered and powered,
   the boot auto-reconnect can present BOTH slots inuse at TID-PTT's own connect-complete ⇒
   the cave kicks the joiner address `[sp+20]` = **the TID-PTT itself**, then re-dials it.
   ACL re-establishes (LED "connected") but the single-SPP-session chokepoint `0x1A740`
   (E10/E11 wall) never re-binds the session ⇒ button events dead for the rest of the boot.
2. **Teardown collateral + wedge:** the press-replay posts cmd `0x4A` =
   `l2cap_disconnect_all_channel()` (dial-wrapper handle==0 path / setter timeout) which
   closes the **TID-PTT's SPP channel** while its ACL lives (the E9/E10/E11 half-dead-link
   signature), and/or the stock dial wrapper's **unbounded** handle-wait loop
   (`if(handle==0){delay10;repeat}`) wedges the bt task when the kick sends the Jabra to the
   phone instead of back to us ⇒ app BT processing dead (menu still responsive — UI task
   separate; matches S3b=y + S1b ACL-LED-alive + dead buttons).

**Lesson:** blocking stock wrappers have no place in the bt task; teardown posts (`0x4A`)
are poison to the incumbent SPP session; the guard must key on the JOINER identity vs the
current-device record, not on a global slot count; every wait must be bounded and resumable
⇒ a **tick-driven state machine** (the §37.4 design intent), not a one-shot blocking cave.

**Decision point (user's call), routes:**
- **v2 hardened bind (recommended):** no kick at all — on incoming join, drive the never-tried
  profile-start family (12/14/18/74 posts, §30.14.28 NEXT) + R8-style handle delivery
  (`_DAT_00010372`) + name replay, as a non-blocking state machine with per-step timeouts;
  zero `0x4A`/`0x12` posts, never blocks > a few ms.
- **ESP32 combo device:** single ACL presenting SPP+HFP = the stock happy path (§9B.6.1
  hardware-proven); sidesteps the entire bind problem.
- **SDK rebuild (ch. 28):** full control, highest cost.

**Radio state:** on `work/ch37_bindc.bin` `3753c796…`. **Must NOT be treated as daily
driver while the bind engages** (cripples the command device); a boot with the Jabra
powered-off should leave the guard unfired and TID-PTT functional — pending confirmation
(discriminating test: fresh boot, Jabra OFF/out of range, TID-PTT only — do buttons key?).

## §37.8 Route (a) chosen — v2 design requirements + refined v1 mechanism (2026-11-14)

**User decision (verbatim):** "no, the TID-PTT never auto-joins must me menu => BT -> Connect
than the PTT button on the TID-PTT does not work". So: the TID-PTT **never** pages in on its own —
it joins only via the radio's menu BT→Connect (radio-originated dial). Yet after that manual
Connect its buttons were dead ⇒ **v1 crippled the TID-PTT itself**, and the cripple trigger is
the TID-PTT's *own connect-complete* hitting our hook.

**Refined v1 mechanism (statically consistent):** boot with Jabra on → our hook fires at the first
tbh (byte==1 + both slots inuse — the second slot fills when the user menu-Connects the TID-PTT),
saves the TID-PTT addr as "joiner", HCI-kicks it (H1), dial-redirect (H2) then re-dials it; the ACL
re-establishes but the **single-SPP chokepoint `0x1A740`** (ch. 27 §27.18: last-connection-wins,
the TID-PTT app never re-opens SPP after a forced kick) never re-binds → key-presses go nowhere.
Secondary suspects: the self-kick itself, or the `0x4A` close collateral.

**v2 requirements (hardened design):**
1. **Identity guard:** never act on a device that is the app's current-dial target / already the
   bound device (the bind must only ever *adopt* a device the app did NOT dial).
2. **NO kick, NO `0x4A`, NO cmd 0x12/0x5** — the joiner's ACL stays untouched (E9 lesson: closing
   channels wedges the app; the kick is what killed the TID-PTT).
3. **Non-blocking tick state machine** (the tbh hook re-executes ~every 5 ms while connected —
   proven: R5/R6a/R8 stamped markers were field-observed) with per-step timeouts; never block the
   bt task (R6b freeze lesson).
4. **Bind = drive HFP profile-start + SCO for the joiner + deliver the handle on the 0x3e sink
   path** (R8 §30.14.49 proved handle delivery re-points the app's TX-mic routing — the mic
   *followed* the swap; it was silent only because no live SCO existed).
5. Statics to pin first: `0x01E07386` executor internals (what no-op'd R4's cmd-1 replay on an
   existing ACL — the decisive question), writers of current-device record `0xBF41..46`, and the
   profile-start command family (far-path 12/14/18/74, NEVER 5) per §30.14.28 NEXT.

**Status:** v2 static phase STARTED 2026-11-14 (autonomous per user directive "start and only stop
if hardware testing is needed or a decision is required").

## §37.9 v2 architecture — restore-after-rebind bind (statics round 2, 2026-11-14)

**New static findings (this round):**
1. **SPP RX command handler = `FUN_01e5b2f4`** (app module next to the kick): memcmp chain
   (`func_0x021127c4` = memcmp) — `+SPP=P`→`FUN_01e52362(0x2A)` virtual PTT-press key,
   `+SPP=R`→key `0x2B`, `AT+MPTT=1`→`0x01E5993E`, `AT+MPTT=0`→`0x01E5A20A`,
   `CH_KEY=+`→key 3, `CH_KEY=-`→key 4, `+POWER=0`→shutdown if `b[0xC094]==1`.
   Tail `0x01E5B388`: echo-back `FUN_01e5b28e` unless `_DAT_00010450` set + `FUN_01e5b2e8()`.
   **NO current-device/handle gate anywhere** ⇒ commands key the radio through the SPP
   session (`0x1A740`) even when the app's current device is another (the Jabra). E11's
   "echo without keying" was therefore NOT this gate (open: second-session routing — moot for v2).
2. **Relay `0x01E22890` case 5 = `if (param != 0) FUN_01e074de(handle)`** — the press-flow
   cmd-5 post is `(5,0,0)` ⇒ param 0 ⇒ **no-op**. The dial itself (relay case 1
   `FUN_01e07386` = `FUN_01e029de(0x400006,2,0x200a,addr)` = controller create-connection
   write) is confirmed the dial executor.
3. **`0x3e` sink `FUN_01e5af40`** (app HCI-event sink, param_1==4): event `0x3e`+status 1 ⇒
   `_DAT_00010372 = read16(payload+4)` (handle) + `FUN_01e5af18/FUN_01e240a0(handle)` + state
   clears; `DAT_0000b463` and `DAT_00010d80` gate the re-init branch. Event 5 = full teardown
   (`_DAT_00010372 := 0`). **Every** connect-complete rewrites the app handle — last dial wins.

**v1 field re-read (⇒ v2 order is ALREADY the right one):** Jabra connected first (app-dialed,
HFP live, P6-proven audio) → user menu-Connects TID-PTT → stock dial rebinds current-device to
TID-PTT ⇒ audio dies (8th signature) — and v1's hook then kicked/redialed the TID-PTT itself
(identity bug) killing its SPP session (dead buttons). The Jabra ACL SURVIVED the second dial.

**v2 = "restore-after-rebind", non-blocking, kick-free:**
- **Snapshot phase:** at first bind (tbh hook, exactly one slot inuse) save primary
  BD_ADDR+handle to statics `0x1C000..`.
- **Trigger:** second connect-complete (both slots, joiner `[sp+20]` ≠ snapshot, one-shot per
  join — re-arm on primary teardown). Do NOTHING at that instant.
- **Settle:** tick state machine (~5 ms hook cadence) waits ~1–2 s for the app's rebind +
  classifier to finish, then **restores**: stack current-device record := snapshot
  (`0xBF41..46` + `b[0xBF3A]|=0x40`, R6b-proven safe write), `_DAT_00010372` := primary handle
  (`0x01E16E0E(addr)` live-handle query, R8-proven moves the mic path), routing byte
  `b[0xB464] := 3` + mode-3 enabler. NO kick, NO dial, NO 0x4A/0x12/0x5 posts.
- **Result state:** current-device Jabra (audio: TX SCO uplink on its handle, RX downlink) +
  TID-PTT ACL + SPP session intact ⇒ `+SPP=P/R` keys via the ungated handler.

**Open statics before build (in order):**
(a) does the TID-PTT dial's teardown close the Jabra's HFP RFCOMM? — decode the `0x4A`
    `l2cap_disconnect_all_channel` walk scope (UI poster `0x01E61E22` posts it unconditionally,
    E9; walk targeted the CURRENT device in E10 — at press time current = Jabra ⇒ likely YES)
    → if yes: v2 adds a targeted conditional skip of the 0x4A post (branch when a live HFP
    primary exists) or a profile-reopen primitive;
(b) exact audio-state field list: who reads `_DAT_00010372`/`0x102F0`/`0xB464`/mic-speaker
    enablers (`0x50398`/`0x503CA`, flags `0xB476/77`) at TX-start/RX-route;
(c) writers of `0xBF41..46` + `is_current_device` `0x01E184D6` contract.

## 37.10 v3 — DIAL-stamp discriminator (the built design; supersedes §37.9 v2)

The §37.9 v2 "restore-after-rebind" plan was superseded before implementation by a
cleaner discriminator that removes the kick-target ambiguity entirely. Decisive
statics this round:

1. **The dial wrapper `0x01E600B4` has exactly 3 callers** (`findva` pointer scan: no
   table refs): inside setter `FUN_01e60120` @`0x01E6022C`, the auto-reconnect task
   `FUN_01e66ef8` @`0x01E670C6` (BARE — no USP posts), and the settings press
   `FUN_01e6ec9e` @`0x01E6ECEA`. Every radio-originated dial passes the wrapper ENTRY
   with `r0 = BD_ADDR ptr` ⇒ a 4 B entry hook stamps the dialed address with zero
   guesswork. Entry bytes `75 04 41 e0` = `push {rets,r5,r4}` + `r1 = 0xB10`
   (exactly 4 B, resume at `0x01E600B8`).
2. **Queue dial addr is inline** — relay `FUN_01e22890` case 1 dials
   `puVar18[3]` from the queue payload (`0x1A694`), no persistent dial cell exists;
   the stamp is the only way to observe "who did we last dial".
3. **tbh hook cadence correction:** the hook at `0x01E61270` lives in the bt-task
   event-dispatch path (reached via `0x01E61C12/C16` gotos), NOT per loop iteration —
   the §37.8 "5 ms natural cadence" assumption was WRONG. All waiting/multi-step work
   therefore runs on a real timer: `TMRADD 0x01E249CE(0, cb, ms)` (cb executes in the
   creating task = bt task).
4. **`FUN_01e60120` setter(1) full path posts `0x4A`** (the v1 SPP-poison suspect) and
   its only effect needed by the dial is the gate byte: dial wrapper `0x01E600CA`
   bails unless `b[0x10E00] & ~0x3F == 0x40` ⇒ v3 writes `b[0x10E00] := (b & 0x3F) | 0x40`
   DIRECTLY and never calls the setter. USP 0x11/0x12 press-hygiene posts omitted
   (bare dial proven: auto-reconnect caller is bare, R5 mailbox redial worked).
5. **Conn record live test:** rec0 `0x1A5B8` / rec1 `0x1A5D4` (stride `0x1C`): live =
   `b[+0x12] & 0x20` && `u16[+6] != 0`; addr = `u32[+0]` + `u16[+4]`.

**v3 design (built):**
- **DIAL stamp** (26 B tramp @`0x01EA7828`, reached by goto32 from the patched
  wrapper entry): `push {rets,r5,r4}`; `r3 = 0x1C000`; three halfword copies
  `[r0+i] -> [r3+i]`; `r1 = 0xB10`; `goto 0x01E600B8`. Runs in the dialing task,
  ~15 instructions, no state touched beyond `0x1C000..05`.
- **Body** (252 B compiled C @`0x01EA772A` behind the 8 B thunk, hook
  `0x01E61270: 50ee640d -> 82ea5732`): engage iff `b[0xB464]==1` && `CTRL==0` &&
  both records live && `DIAL` matches EXACTLY one record ⇒ target = the OTHER
  record. By construction the target ≠ the app's last-dialed device ⇒ **TID-PTT can
  never be the kick target** (fixes the v1 self-kick structurally). Save target to
  `PRIM 0x1C008`, `CTRL(0x1C010).STATE := 1`, `arm()` (TMRADD 500 ms) and RETURN —
  nothing blocking in connect-complete context (fixes v1's blocking waits).
- **tick** (TMRADD cb, bt task): STATE!=1 → return. `h = FIND(0x01E17420)(0, PRIM)`;
  `h != 0` → `KDISC(0x01E07B08)(h, 0x13)`, `TICKS++`, ≥10 → STATE=3 give-up, else
  re-arm. `h == 0` (ACL gone) → `b[0x10E00] := (b & 0x3F) | 0x40` + `DIAL(PRIM)` via
  the (stamped) wrapper = app-originated dial: `0x3e` sink rewrites `_DAT_00010372`,
  classifier stamps routing byte 3, HFP+SCO ride the dial. STATE := 3 (sticky).
- **Re-arm:** `b == 0xF0` (teardown sentinel) → `CTRL := 0` — every later join gets
  the fix again (self-heal; v1's one-shot-per-boot P7 limitation gone).
- Statics: `DIAL 0x1C000..05`, `PRIM 0x1C008..0D`, `CTRL 0x1C010` (STATE byte0,
  TICKS byte1). Source `work/ch37/bind3_c.c`.

## 37.11 v3 build + verification record (2026-11-14)

- **Compile:** `clang -target pi32v2 -mcpu=r3 -Oz -mllvm -pi32v2-large-program` +
  `ld.lld -T blob.ld` at `0x01EA772A` → **252 B body, zero relocations** (size history
  v2 330 ✗ → v3-292 ✗ → drop USP posts + shared `arm()` helper → 252 ✓; budget 288 =
  296 cave − 8 thunk). nm: `bind_main 0x01EA772C`, `arm 0x01EA77B2`, `tick 0x01EA77CA`.
- **Cave blob** 288 B = thunk(8) + body(252) + pad(2) + stamp(26), ends `0x01EA7842`
  ≤ `0x01EA7849` ✓.
- **Upstream oracle (ch. 34):** stamp assembled WITH the real `pi32v2isa` assembler
  (`python3 -m pi32v2isa stamp9.o`) and every blob byte re-disassembled — all decode
  exactly, lengths + re-entry aligned. `75 04` push {rets,r5,r4} ↔ epilogue `55 04`
  confirmed (`65 04` = push WITHOUT rets — would corrupt the return link).
- **jl_sim gate — 11 scenarios ALL PASS** (`--image work/app_dec.bin --patch
  0x01EA7722:<288 B>`): T1 byte=3 dormant r0=3; T2 engage → `PRIM=rec1` + `CTRL=1` +
  `TMRADD(0, tick 0x01EA77CA, 500)`; T3 DIAL matches neither → dormant; T3b rec1
  handle 0 → dormant; T4 CTRL=3 sticky → no re-engage; T5 tick h=5 → `KDISC(5, 0x13)`;
  T5b → `TICKS=1` + re-arm; T5c TICKS 9→10 → STATE=3 give-up; T6 gone →
  `b[0x10E00] |= 0x40` + `DIAL(0x1C008)` + STATE=3; T7 0xF0 → CTRL cleared;
  T8 stamp window-exec `r0=0x1C020` → `0x1C000 = deadbeefcafe` + resume `0x01E600B8`.
- **Patch tool:** `--bind-c` v3 constants + `bindcdial` site (stock `750441e0` ↔
  stamp goto `c2eab83b`); `--sectors` wanted-list now includes `bindcdial` (bug fix —
  v3-era builds would have shipped without the dial hook); CLI help/validation updated
  to v3. **Recognition-state fixes this round** (15 verify_actions failures → 0): the
  288 B window now swallows the legacy d1thunk/incmode3/inchfp windows ⇒ bindccave
  learned states `d1thunk`, `incmode3`, `inchfp`, `legacy_cmd5t_presst_d1`,
  `legacy_gate_cmd5t_presst_d1`; reciprocal `bindc` states added to incmode3cave,
  inchfpcave, d1thunk; presstcave bindc slice corrected to
  `BINDC_CAVE_BYTES[174:174+32]` (window length = `len(PRESST_CAVE_BYTES)` = 32, NOT
  50 — lesson re-learned: **every window must be taught at FULL state length**).
- **Both suites: 0 failures** (verify_actions bindc block rewritten for v3: 288 B,
  stamp bytes, `decode_goto32` resume check, `--only bindcdial` in build/idempotent).
- **Image:** `work/ch37c_bindc.bin` sha256
  `2b488a239909dfdf6acd65f8b4e934f039525549b47c71dc14f70a8b1034ebb6` = E7-ref
  `90bec320…` + full S1 recipe + `--bind-c`: **266 bytes changed, sectors `0x065000`
  (dial hook) + `0x066000` (tbh hook) + `0x0AC000` (cave) ONLY, uboot `0x0000–0x4FFF`
  byte-equal to `Dumps/dump_pre_ch30.bin`** ✓.
- **Stage:** `work/ch37c_bindc.sh` (EXPECT_SHA + 3-sector assert + radio-state
  precheck + readbacks + full strict-region verify) + field card
  `work/ch37c_bindcc.sh` (S1 goal, S2 teardown/echo, S3 SELF-HEAL repeat, S4 menu
  Connect, S5 repair press, S6 feature checks). **UNTESTED on hardware — verdict
  §37.12 (user flashes).**

## 37.12 FIELD VERDICT — v3 BROKEN: no Bluetooth connection at all (2026-11-15)

User report (radio on `work/ch37c_bindc.bin` `2b488a23…`): **fully unusable —
no connection path works**: no auto-join, no menu Connect, no pairing Connect
(devices ARE discovered in pairing, pressing Connect never establishes). Radio
never froze; multiple radio/Jabra/TID-PTT reboot combinations no help.

**ROOT CAUSE (static, same day) — the DIAL hook resumes mid-instruction.**
Upstream-oracle decode of the pristine dial wrapper entry:

```
0x01E600B4  75 04              [--sp] = {rets, r5, r4}    ; 2 B
0x01E600B6  41 e0 10 0b        r1 = 2832                  ; 4 B (spans B6..B9)
0x01E600BA  c2 ff f0 02 01 00  r2 = 66288 (=0x0102F0)     ; 6 B
```

The v3 hook replaced **4 bytes** (`B4..B7`) with the `goto32` to the stamp and
resumed at `0x01E600B8` — the **second halfword of the 4-byte `r1 = 2832`
instruction**. Every call into the dial wrapper (auto-reconnect `0x01E670C6`,
setter `0x01E6022C`, settings press `0x01E6ECEA` — xref: the ONLY three callers;
zero branch targets into `B6/B8/BA`) executed garbage from `10 0b` onward ⇒ no
connection could ever be dialed. The tbh hook (R-series-proven pattern) was
never reached because nothing connected. The stamp itself was CORRECT — it
already replays both stolen instructions (`75 04` at stamp+0, `41 e0 10 0b` at
stamp+18); only the resume target was wrong (hook+4 instead of first intact
boundary `0x01E600BA`).

**Why the gates missed it:** the oracle + jl_sim verified the CAVE bytes and the
stamp window in isolation (T8 checked "resume reached 0x01E600B8" — the value,
not its validity as an instruction boundary). **LESSON (now enforced): every
hook site must assert that the replaced window ends on an instruction boundary
in the pristine decode, and at least one sim run must start AT the hook entry VA
and stop at the resume VA on the BUILT image.**

## 37.13 v3b — one-byte fix: stamp resume `0x01E600B8` → `0x01E600BA` (2026-11-15)

- Patch tool: `BINDC_DIAL_RESUME_VA = 0x01E600BA` + boundary comment; cave stamp
  tail `fd ea 3b c4` → `fd ea 3c c4` (goto −292744 = exactly `0x01E600BA`);
  stamp 22 B replay assert already pins both stolen instructions; hook bytes
  `c2 ea b8 3b` UNCHANGED (site stock/recognition untouched).
- `verify_actions.py`: stamp-tail check now pins the literal `0x01E600BA`
  boundary. **Both suites: 0 failures.**
- **Image `work/ch37d_bindc.bin` sha256 `73b6747bf2a49477723327bdc081594f7566fbeca5419d503dfd9ae80756f2b9`**
  = same recipe as §37.11 → **266 B changed, sectors `0x065000`+`0x066000`+`0x0AC000`
  only, uboot byte-equal** ✓; vs v3 = exactly **1 ciphertext byte** (`0xAC840`).
- **Upstream oracle on the BUILT image:** stamp tail `goto -292744` → `0x01E600BA` ✓;
  hook region decodes `goto 292720` (→ stamp `0x01EA7828`) + dead `10 0b`
  (2 B, never executed, linear sweep re-syncs at BA) + `r2 = 66288` intact ✓.
- **jl_sim END-TO-END PASS (new gate):** `--start 0x01E600B4` on the built-image
  plaintext, `r0=0x1C020` seed `deadbeefcafe` → 11 steps, stops at `0x01E600BA`
  with `r0` preserved, `r1=0xB10` (replayed), `0x1C000 = deadbeefcafe` (DIAL
  written), `sp 0x20000→0x1FFF4` (push contract), rets stored ✓.
- Stage `work/ch37d_bindc.sh` + card `work/ch37d_bindcc.sh` (same tests as the v3
  card: S1 goal via boot-dial arming + Jabra power-on, S2 teardown, S3 self-heal
  repeat, S4 menu Connect, S5 repair press, S6 features). **UNTESTED — verdict
  §37.14 (user flashes).**

## 37.14 FIELD VERDICT — v3b (2026-11-15): connectivity FIXED, 9th goal-miss

Log `work/logs/ch37d_bindccard_20261115_113042.log` (radio on `work/ch37d_bindc.bin` `73b6747b…`).

**The v3 dial-break is FIXED — every connection path works again:** boot OK
(T0a), pairing works (TID-PTT had to be re-paired via the radio menu — pairing
data lost during the v3 experiments — that manual Connect press dialed it =
armed the DIAL stamp), menu Connect dials with **no freeze** (S4a "no freeze
kick TID-PTT" = stock kick semantics), radio responsive through the whole card
(O1=n). The 1-byte resume fix (§37.13) did exactly what it claimed.

**New behaviours, unseen in the R-series / ch. 37 before:**
- S1: TID-PTT first, Jabra powered on → "I heared mobile connected"; **both
  devices ended up connected** and **TID-PTT still keyed the radio** (S1b=y) —
  the first bind-series image where the incumbent SPP device survived the join
  moment with keying intact.
- S2a: clean teardown, no echo / side loops (R3/R4 echo class gone).
- Zero freezes anywhere (R6b class gone).

**GOAL: FAIL (9th identical signature).** S1c TX with both up = "TX happened, no
audio" — the classic bind-to-BT-mic-path with **no live SCO** (TID-PTT has no
microphone ⇒ a BT-path bind is silence). S1d/S3c RX untestable (no second
transmitting radio at hand). S6b: PTT/PTT2 key normally but silent — routing
bound to the dead BT mic path.

**Regressions:** after the cycle the TID-PTT SPP never keyed again (S2c "No
never did not even on pairing alone / single device"; S6a=n) — the engage/
teardown cycle destroys the app single-SPP session (`0x1A740` never re-binds,
v1 class). S3a: Jabra re-join refused after power-cycle — consistent with stock
P7 (one incoming join accepted per boot; S1 consumed it). Note S1b=y vs S2c=n:
SPP died between them, i.e. during the Jabra-off teardown our cycle produced.

**Fire confirmation: UNCONFIRMED.** "Mobile connected" is the Jabra's own prompt
and cannot distinguish our radio-dial from phone-roam (v1 S1a failure mode); no
ACL drop was observed. With the LED probe dead (§36.10) and no UART there is no
on-hardware execution oracle.

**Assessment.** The compiled-C splice machinery is now PROVEN SAFE — first image
of the bind series with all connect paths working and zero freezes. The wall is
unchanged from R7/R8: no live HFP/SCO on the re-dialed device, and the kick/
teardown cycle costs the incumbent SPP session.

## 37.15 DECISION POINT (2026-11-15, user's call)

1. **v4 — profile-start replay** (cheap: one static round + one flash). The
   stock press posts `setter(1)` + USP `17/18/5` BEFORE the dial (§37.5); v3b
   deliberately omitted all of them (§37.10: hygiene omitted; setter avoided
   for its `0x4A` SPP-poison). Static round: decode USP 17/18/5 + which
   app/stack state the setter writes that feeds the dial's profile bring-up,
   then replay the missing profile-start posts after our redial's
   connect-complete, and protect the SPP session. Honest odds: moderate — R7
   posted cmd `0x1E` (SCO start) directly and still missed, BUT that was for a
   stack-owned (incoming) link; v3b's device is app-DIALED — materially better
   position.
2. **SDK rebuild (ch. 28).** P0 + P1 field-PASSED (SDK image boots and pairs on
   this radio). Full source control = the only route with a guaranteed path to
   real two-device audio; heavy lift (feature parity: BT-PTT/BT-PTT2, key remap,
   SPP protocol, `-BT` name).
3. **ESP32 combo device (§9B.6.1).** Single ACL presenting SPP+HFP — the
   stock-proven happy path, zero further firmware risk; needs small hardware +
   pairing-flow change (the combo relays button + audio).

Radio currently on v3b `work/ch37d_bindc.bin` `73b6747b…` — connects fine; not
a daily driver while the bind engages (engage costs the SPP session).

## 37.16 v4 — DIRECT DIAL POST + is_1t2-BAIL NOP (BUILT 2026-11-15)

User chose route 1 (§37.15). The static round re-decoded the dial wrapper
`0x01E600B4` end-to-end (upstream oracle + `work/full.lst`) and found BOTH v3b
defects plus the SPP killer:

```
B4  push {rets,r5,r4}; r1 = b[0x10E00] & ~0x3F; r4 = addr
CA  if (r1 == 0x40) goto DC else return            ; mode gate
DC  r5 = call 0x01E17F26                           ; stack state get
    if (r5 == 0x80) goto D0                        ; busy -> wait loop
D0  call 0x01E16E0E; if (r0) goto E6; delay(10); fall DC
E6  r0 = call 0x01E16E0E (live handle); if (!r0) goto F0
EC  r0 = 0x4A -> FE: USP(0x4A,0,0)                 ; l2cap_disconnect_all_channel
                                                    ; = TID-PTT SPP KILLER (§37.14
                                                    ; S2c) — taken whenever ANY
                                                    ; handle is live (always, TID-PTT up)
F0  if (r5 == 0) goto 10E else USP(0x12)+USP(0x5)  ; teardown posts
10E wait until 0x01E17F26() == 0 (delay-10 loop)
114 r0=1; r1=6; r2=r4; call USP 0x01E1792E         ; THE dial post (START_CONNEC_VIA_ADDR)
11E return
```

And the dispatcher bail that dropped v3b's dial: `0x01E17A26 call is_1t2_connection
(0x01E1787C)` → `0x01E17A2A if (r0 != 0) goto 0x01E17BC4` (4 B `80 f8 cb 00`).
`is_1t2_connection()` decoded (oracle; `full.lst` gap): `r0 = (h[0x1A682] & 7) ==
((b[0xBF39] >> 4) & 3)` — TRUE in our conn-num=2 build with a link up ⇒ every
cmd-1 post bailed silently. (This is the same bail R4 NOP'd — `inchfpbail` site,
constants already in the tool.)

**v4 = two surgical changes, machinery otherwise identical to v3 (§37.10):**
1. tick gone-branch no longer calls the wrapper: writes mode byte
   `b[0x10E00] := (b & 0x3F) | 0x40` directly (gate value, no `0x4A`/`0x12`/`0x5`
   posts, no busy-wait) then posts `USP(1, 6, PRIM)` at `0x01E1792E` — the
   wrapper's own inner dial post. No L2CAP teardown ⇒ TID-PTT SPP should survive.
2. `inchfpbail` NOP @`0x01E17A2A` (`80 f8 cb 00` → `00 00 00 00`) so the cmd-1
   post is processed (falls into the case-1 handler @`0x01E17A2E` intact — our
   post has r6=6 ✓).

**Build.** Source `work/ch37/bind4_c.c` (bind3_c.c + tick rewrite). Body 256 B
(+4), cave **290 B** = thunk 8 @`0x01EA7722` + body @`0x01EA772A` + stamp tramp
26 @`0x01EA782A`, ends `0x01EA7844` ≤ `0x01EA7849` ✓. Compile recipe unchanged
(§37.6). Patch tool: `BINDC_STAMP_OFF=264`, cave bytes/asserts, embedded-target
tuple `0x01E600B4`→`0x01E1792E`, `inchfpbail` gated `incoming_hfp or bind_c`,
wanted-list adds `inchfpbail`, CLI help v4. **Suites: BOTH 0 FAILURES.**

**Verification.** Upstream oracle: 290 B cave 0 unknowns; on the BUILT image —
bail region `call is_1t2; nop; nop` + case-1 handler intact; dial hook
`c2 ea b9 3b` → stamp `0x01EA782A`, dead `10 0b`, resume `0x01E600BA r2=66288` ✓;
tbh hook `82 ea 57 32` ✓; stamp goto → exactly `0x01E600BA` ✓.
**jl_sim 12/12 PASS** on the decrypted built image (T1 dormant r0=3; T2/T2b
engage both mirrorings → PRIM=other record + CTRL=1 + TMRADD(0,tick,500);
T3 DIAL-mismatch dormant; T4 CTRL=3 sticky; T5a tick→KDISC(5,0x13); T5b
TICKS=1+re-arm; T5c give-up STATE=3; **T6 gone→USP post r0=1,r1=6,r2=0x1C008 +
mode byte 0x80→0x40**; T6b STATE=3 after post; T7 0xF0 re-arm; T8 stamp
end-to-end from real dial entry `0x01E600B4`).

**Image `work/ch37e_bindc.bin` sha256 `b91b35351108e6723c4dbc1690215a61e47469a87f56f1196ae3d29aa51af6ea`**
= E7-ref + full S1 recipe + `--bind-c`: 274 B changed, sectors
`0x01C000`+`0x065000`+`0x066000`+`0x0AC000` only, uboot byte-equal ✓.
Stage `work/ch37e_bindc.sh` + card `work/ch37e_bindcc.sh` ready.

## 37.17 v4 FIELD VERDICT — FIELD-FAILED 2026-11-15 (log `work/logs/ch37e_bindccard_20261115_140120.log`)

**Connectivity:** boot normal (T0a y); TID-PTT connected first (S1.0 y); Jabra then
connected ("yes mobile connected", S1a). Menu Connect press = "its trying to connect",
no freeze, radio responsive (S4a/S4b y). Normal PTT/PTT2 unaffected (S6b y). No echo
on Jabra-off (S2a n).

**GOAL FAIL — 10th identical audio signature.** S1c "Tx only happens on radio ptt and
with silence"; S3b after a repeat join "still silence"; S1e/S3c/V1 = fail. RX
untestable (no second radio).

**NEW REGRESSIONS — v4 must NOT ship:**
1. **First crash of the whole series:** O1 "radio rebooted once on a auto join of the
   jabra" — a watchdog reboot inside our engage path. The direct `USP(1,6,addr)` post
   with the `inchfpbail` NOP runs the cmd-1 case-1 handler in stack states it was
   designed to bail out of — including for STOCK dials (the NOP is global, not
   bind-scoped). Unsafe.
2. **TID-PTT SPP keying dead for the ENTIRE card:** S1b "as from the initial start the
   TID-PTT ptt button does not trigger the TX"; S2c "no never did"; S6a BT-PTT = n.
   Worse than v3b (which keyed at join). The engage cycle (kick + direct post) leaves
   the SPP command path permanently broken even across the Jabra power-off (S2) and a
   repeat join (S3).

**Interpretation.** Even a correctly-formed radio-originated cmd-1 dial (the exact post
the stock wrapper makes) never binds audio when the app's pre-dial state
(setter(1) + USP 17/18/5, single-device incumbent context) was not created by the app
itself — the R7/R8 wall, reconfirmed through the compiled-C route. The NOP'd bail also
removes a stock safety check globally, which plausibly explains both the reboot and the
permanent SPP damage. **The in-image bind route — byte-level (R3–R8) AND compiled-C
(ch. 37 v1–v4) — is CLOSED. Twelve levers exhausted.**

## 37.18 DECISION POINT + the free reverse-order test (2026-11-15)

Every bind attempt assumed the natural order **TID-PTT first** (radio remembers ONE last
device and dials it) with the Jabra joining second, then tried to move audio onto the
joiner. But §30.14.17's crippling is "audio routing bound to the FIRST device" — so if
the FIRST device is the **JABRA**, stock S1 should already put audio on the headset
(P6: Jabra-alone audio = PASS), and the TID-PTT joining second should still get the
ONLY SPP session (the `0x1A740` single-session wall only bit with TWO SPP devices, E11)
and key. **This reverse order was never tested.** Zero build required.

**Order-test card (on S1 `work/ch32_bt_e7.bin` — flash `sudo bash work/ch32_bt_e7.sh`);
scripted: `bash work/ch37_ordertest.sh` (logs to `work/logs/ch37_ordertest_*.log`):**
- O1 Make the Jabra the radio's remembered device: menu-Connect the Jabra once, power-cycle,
  confirm the radio dials the Jabra on boot (TID-PTT switched OFF during this).
- O2 Jabra alone: confirm HFP audio healthy (baseline = P6).
- O3 Power on the TID-PTT: does it page in and stay connected (both up)?
- O4 Does the TID-PTT button key the radio (BT-PTT over SPP)?
- O5 While keyed: TX mic source = JABRA (observer/second-radio needed)?
- O6 Power-cycle the radio: does the full daily sequence repeat (Jabra dialed, TID-PTT joins,
  keys + Jabra audio)? (P7 caveat: incoming join accepted ONCE per boot — fine if TID-PTT
  is always the joiner.)
- Verdict → §37.19. GOAL PASS here = ship S1 as-is with an operational order-of-connect recipe.

If O4/O5 fail (second-joiner SPP or first-device audio broken): remaining routes are the
**ESP32 combo device** (§9B.6.1 — single ACL presenting SPP+HFP = stock happy path,
hardware-proven at profile level) or **stop at S1** (two-device stable, audio on first
device). SDK rebuild (ch. 28) is NOT a bind route: the H3+ app itself is closed-source —
rebuilding replaces the whole radio app.

## 37.19 Join-strategy field intel (user, 2026-11-15) — §37.18 order test WITHDRAWN

User observation (careful, multi-reboot): the two accessories run **different join
strategies**:
- **Jabra = active pager**: if it was connected when it powered off, on power-on it
  pages the radio itself and the radio **always accepts** (matches §30.14.17's
  incoming-join state + P7 once-per-boot).
- **TID-PTT = pure peripheral: it NEVER pages.** It joins ONLY when the radio dials it
  (radio's remembered last-device = TID-PTT). If the radio is connected to / remembers
  the Jabra, the TID-PTT never connects. Behavior: 1 s hold = power-on + discoverable
  (red/green blink); button = TX when connected; 3 s hold = power-off. Single button.
- User's model: the radio holds ONE "last connected device X" register and dials it;
  other devices coming online are ignored; the Jabra's OWN last-device register drives
  its active paging.

**Consequence: the §37.18 reverse-order test is invalid** — it required the TID-PTT to
page in second; it never does. Withdrawn, not run.

**MIRROR INSIGHT (untested, the one firmware-only door this intel opens):** the goal's
missing half is not the radio-side audio bind — it is the **join direction of the
TID-PTT**. If the radio remembers the JABRA: dial Jabra = app-originated connect =
audio binds natively (P6-proven alone). The TID-PTT then only needs to arrive as an
INCOMING joiner — and incoming connects demonstrably do NOT retarget the app's
current-device struct (state (a) keeps the TID-PTT current even while the Jabra joins),
and it would get the FREE single-SPP session (`0x1A740` — the Jabra uses no SPP) →
BT-PTT keys (the app's SPP command path is device-agnostic, ch. 22 §9B). Every piece of
that chain is individually proven EXCEPT the one thing the TID-PTT cannot do: page.
⇒ Remaining doors: **(1) TID-PTT-side patch** — make it page the radio when the link to
its remembered host drops (if its firmware is flashable — make/chipset unknown, ask
user); **(2) ESP32 combo device (§9B.6.1)** — one ACL presenting SPP+HFP = stock happy
path; (3) stop at S1 (audio bound to first device).
