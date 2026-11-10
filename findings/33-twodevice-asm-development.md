# 33 — Two-Device Development on the Byte-Exact ASM Route

**Status: ACTIVE (started 2026-11-09).** Goal per user directive (verbatim):

> B: build an image with two bluetooth device support, having the TID-PPT on the SPP
> channel, so handling the PTT over bluetooth and the other device (Jabra) on the HFP
> simultaneously. If required hardcoded Device Name == TID-PPT than SPP else HFP is
> allowed. also incoperate following settings from patch_h3plus_firmware_bluetooth.py
> `--bt 4 --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT`

Carried goal context: [Ch. 30](30-two-device-plan.md) plan of record (one SPP command
device + one HFP audio device, both connected, either order). The R-series
(§30.14.21–43) proved byte/command-level tbh patches CANNOT make the app bind audio to
the second device — the wall is the app current-device struct `0x102F0`, which is only
written correctly by the FULL app-originated connect flow. The byte-patch era ended;
[Ch. 32 §32.11](32-sdk-rebuild.md) delivered the replacement capability: a
**byte-exact editable asm source of the whole app** (`tools/jl_rt_asm.py`, hardware-
proven twice — marker `0748f2d1` + `-BT` `200a7e11` both field PASS). This chapter runs
the two-device attack on that route.

## §33.0 — Why the asm route changes the game

| Era | Capability | Outcome |
|---|---|---|
| Byte patches (ch. 26–30) | ≤ ~240 B cave, fixed hook points, no refactor | 6 levers exhausted, wall = struct `0x102F0` |
| Ghidra-C splice (ch. 32 §32.6) | whole-image C | DEAD — 4 field-dead images, decomp loses HW bits |
| **ASM source (ch. 32 §32.11)** | edit ANY instruction/string/table in the app, provable byte blast radius, offline lossless verification | **ACTIVE** |

User-allowed simplification: **hardcoded name-based routing** — device name `TID-PTT`
→ SPP (PTT), any other device → HFP (audio). The classifier `0x01E7EC28` is already
name-only (§30.14.18), so this is a natural fit.

## §33.1 — Stage ladder

| Stage | Deliverable | Gate | Status |
|---|---|---|---|
| **S1** | `-BT` base + full E7 feature set (BT-PTT2 + `--bt 4` + kick-NOPs = the §30.14.17 stable press-free two-device CONNECT state) folded into `di.s` as asm edits | boots; BT pairs; BT-PTT2 works; two devices stay connected; Firmware Ver `V1.0.50-BT` | 🟡 building 2026-11-09 |
| **S2a** | static: decode the app-originated connect state machine — exactly what writes struct `0x102F0` fields BEFORE/AT connect-complete (UI "connect selected device" `0x01E61E22` → dial → tbh → bind block `0x01E61292`) | written record here | ⬜ |
| **S2b** | asm implementation: route the incoming second device (Jabra) THROUGH the app-originated flow (name-based: non-`TID-PTT` → HFP bind), real code in cave `0x01EA76DE`+ (364 B free, ch. 23) or new cave space | Jabra audio bound while TID-PTT holds SPP: TX = Jabra mic via BT-PTT, RX = Jabra speaker, PTT keys from TID-PTT | ⬜ |
| **S3** | polish: either-order connect, teardown hygiene (R5 echo-latch lesson §30.14.22) | daily-driver quality | ⬜ |

Key assets for S2 (all from ch. 29/30 reference map): bt-task main loop `FUN_01e60e44`
(event case `0xB` = bind block `0x01E61292`), connect-complete mode tbh `0x01E61270`,
outgoing dial `user_send_cmd_prepare(1,6,addr)` @`0x01E60114`, re-dial mailbox
`0x1A5F1` (odd), stack current-device record `0xBF41..46` + `b[0xBF3A]|=0x40`,
`is_current_device` `0x01E184D6`, classifier `0x01E7EC28` via ops-table `[0xBF48+4]`,
conn records `0x1A5B8`/`0x1A5D4` (stride `0x1C`, inused bit29 of `+0xE`).
R-series negative results MUST be respected: forcing the routing byte, replaying cmd 1,
mailbox redial, stamp-at-redial-complete, current-device write, direct bind-block goto
— all six field-FAILED because the app task state machine never ran.

## §33.2 — Build pipeline (per ch. 32 §32.11, standing)

1. Edit `/tmp/opencode/rtasm/di.s` (add pins to `di.pinned` + re-round when target
   bytes are text lines; `round` must always run from `/tmp/opencode/rtasm`).
2. Assemble: `$TC/clang -target pi32v2 -mcpu=r3 -c di_X.s -o di_X.o && $TC/ld -Ttext
   0x1e00100 di_X.o -o di_X.elf && $TC/objcopy -O binary -j .text di_X.elf di_X.bin`
   (`TC=/home/stefan/h3plus/jieli-linux-toolchains-20250324.1/pi32v2/bin`).
3. Blast radius vs `work/app_dec.bin[0x100:]` = intended bytes ONLY.
4. `python3 work/ch32_p2_pack.py <plain> work/ch32_<name>.bin work/ch32_<name>_sectors <lbl>`
   (`CUR_RADIO=<image on radio>` env overrides the sector-diff baseline).
5. Stage script from `work/ch32_bt.sh` pattern; **ABSOLUTE RULE**: stock uboot
   `0x0000–0x4FFF` byte-identical (asserted); flashing = user action; HID fallback
   PTT+1+power-on → `sudo python3 tools/jl_hidboot.py restore <img> --yes`.
6. Version convention: every build carries the `-BT` postfix (§32.11.8).

## §33.3 — Ledger (append-only)

- 2026-11-09: chapter opened per user directive (Option B). Radio on
  `work/ch32_bt.bin` `200a7e11` (stock v1.0.50 + `-BT`, field PASS). S1 started:
  36 E7 diff runs (159 B, `e7_runs.json`) → 92 new pins in `di.pinned` (15,889 total),
  re-round launched. E7 runs = kick NOPs (`0x178CE`, `0x18B0E`, `0x1A03A`+`0x1A042`,
  `0x21DE4`, `0x21EC4`, `0x5B22A`), conn-num byte `0x182DD` `24→25`, BT-PTT2 bodies
  (`0x75E38`, `0x75E7A-0x75E86`, `0x794DA`, `0x7EC87`), mode strings `0x52401`/`0x524BF`
  (`(→*`), `0x8E30E` BT-PTT2 label, cave `0xA76DE..0xA7722` (72 B), blob defaults
  `0xBD744`/`0xBD764`/`0xBF0A8..0xBF403` (`T→W` + `13e3e8→1020e9`). No overlap with the
  `-BT` sites (`0x9B817`/`0x9CBF0`/`0xBDDBC`) → intended total 172 B.
- 2026-11-09: **S1 IMAGE BUILT + VERIFIED (awaiting user flash).** `di.pinned` 15,891
  pins (+92 E7 words, +2 item bases `0x1e75e78`/`0x1e75e7c`, +12 BT pins) → re-round
  BYTE-EXACT OK round 1 (text 263,618 / short 48,248). Fresh `di_e7.s` emitted via
  `jl_rt_asm` module API (`parse_all`→`plan`→`emit_s`; `emit_s` takes a PATH, line map =
  `addr_of_line[ln-1]` item BASE, interior words at `base_line+(va-base)/2`); 100 word
  edits applied (92 E7 + 8 BT), every target line asserted `.short`. Assembled
  `di_e7.bin` = **0 diffs vs computed target** (stock ∪ E7 ∪ BT), **exactly 172 B** vs
  stock. Packaged with `CUR_RADIO=work/ch32_bt.bin` baseline →
  **`work/ch32_bt_e7.bin` sha256 `d7a29a3eaeffbe67…`, 13 sectors**
  (`0x1C000/1D000/1F000/26000/57000/60000/7A000/7E000/83000/93000/AC000/C2000/C4000`).
  Stage script `work/ch32_bt_e7.sh` (PTT+3 SCSI from ch32_bt app; HID fallback;
  uboot-sacredness assert; Q1-Q8 gate incl. two-device-both-stay-connected + BT-PTT2).
  Flash: `sudo bash work/ch32_bt_e7.sh`.
- 2026-11-10: **S1 FIELD-PASSED.** Log `work/logs/ch32_BTE7_20261110_002343.log`:
  13/13 sectors + FULL-FLASH VERIFY PASS. Q1 boots yes / Q2 menu ok / Q3 BT-PTT keys
  TX with TID-PTT mic yes / Q4 **both connected** (TID-PTT incumbent + Jabra join —
  E7 two-device stability reproduced via the asm-route source) / Q5 BT-PTT2 yes
  (TID-PTT mic — expected: audio bound to first device) / Q6 Firmware Ver
  V1.0.50-BT yes / Q7 TX TID-PTT mic + **RX silence** = the §30.14.17 first-device
  binding crippling, EXPECTED on this base, = the S2 target / Q8 nothing unusual.
  ⇒ multi-site CODE patching (172 B, 13 sectors) hardware-proven on the asm route.
  Radio now on `work/ch32_bt_e7.bin` `d7a29a3eaeffbe67`. S2a started.
- 2026-11-10: **Card S1.5 — zero-patch ORDER test** on `ch32_bt_e7.bin` (no reflash):
  Jabra OFF-order reversed vs §30.14.17 — radio DIALS Jabra first via
  Paired→Connect (stock flow binds audio = S5b), THEN TID-PTT pages in as second
  (E7 accepts incoming joins; SPP session slot `0x1A740` free since Jabra is HFP-only).
  Steps: 1 radio ON TID-PTT OFF; 2 dial Jabra; 3 baseline Jabra audio; 4 power
  TID-PTT -> joins; 5 both stay 30 s?; 6 button keys TX? which mic?; 7 RX still Jabra?
  GOAL-pass => order is the policy, add name-guard asm only as safety. Fail => pins S2b.
- 2026-11-10: **Card S1.5 = FAIL (step 4).** Jabra dialed first binds PERFECTLY (S1-S3:
  TX mic Jabra, RX earphones) — but after first TX an **echo loop** starts (radio audio
  into earphones; same as all E7-era experiments). TID-PTT powered on -> did NOT page in
  (incoming join blocked when Jabra is incumbent — asymmetry vs §30.14.17). User directive:
  **the final solution MUST be echo/sideloop-free** (may remain during experiments);
  **continue with S2b**. Echo root-cause added to S2 scope (likely SCO downlink left open /
  sidetone path under the kick-NOP regime — to be located statically).

- 2026-11-10: **P9 FIELD-FAILED (card poisoned by boot order + freeze regression).**
  Flash clean (3 sectors + FULL-FLASH VERIFY PASS, boots, Firmware Ver V1.0.50-BT).
  Card: TID-PTT did NOT auto-join (Jabra had auto-joined first = radio reconnected the
  S1 session last-device), manual connect froze the radio, pairing mode showed no
  devices, radio froze + rebooted; Jabra alone works fine. Log
  `work/logs/ch33_P9_20261110_085644.log`. ANALYSIS: with Jabra holding the HFP link the
  state IS the P8 wall (incoming pages die at LL; the settings-dial of TID-PTT = outgoing
  page while HFP up — froze, NEW regression vs S1 which never froze). The intended P9
  sequence (button incumbent FIRST, then dial Jabra) was never executed. Retry card
  §33.8 on the same image.

- 2026-11-10: **P9 RETRY = FAIL (confirmed regression).** Idle-ish radio, menu
  Paired->TID-PTT->Connect LOCKS the radio on the press. USER CORRECTION: the TID-PTT
  NEVER auto-joins in any recent build (S1 included) — only the Jabra auto-joins, every
  boot. Static trace of all 4 NOP sites shows them behaviorally == stock when no link is
  up => the lock happens on the dial-WITH-LINK-up path (Jabra auto-joined before the
  press): the NOPped 0x4A/cmd-5 posts are LOAD-BEARING state cleanup (close current
  channels + free the record so the stack can accept the new dial); without them the
  cmd-1 dial hits a dirty state machine, never completes, UI waits forever = lock.
  ⇒ P9 route (NOP the eviction posts) DEAD. Next: §33.9 Card P10 (zero-patch dial
  sequence on S1 base).

- 2026-11-10: **Stage-script baseline GOTCHA (caught by full-verify).** Re-running
  `work/ch32_bt_e7.sh` to undo P9 wrote only its 13 exported sectors (baseline
  `ch32_bt.bin`) — P9's 3 sectors (`0x65000/0x66000/0x73000`) were not among them, so the
  16 NOP bytes stayed and the strict-region verify STOPPED with exactly 16 mismatches
  (log `work/logs/ch32_BTE7_20261110_093737.log`). RULE: sector exports are
  BASELINE-DEPENDENT — before any restore/re-flash, re-export vs the CURRENT radio image.
  Fix staged: `CUR_RADIO=work/ch33_p9.bin` repack of the same S1 plain (image sha
  identical `d7a29a3e…` — packager deterministic) -> `work/ch32_bt_e7fix_sectors/` (3
  sectors) + `work/ch32_bt_e7fix.sh`.

## §33.4 — S2 design (2026-11-10, post S1.5)

Facts: stock settings-Connect dial of the Jabra binds audio PERFECTLY (S5b/S1.5 S1-S3);
incoming joins stable when incumbent = SPP device (§30.14.17); incoming join FAILED when
incumbent = HFP device with open SCO/echo active (S1.5 S4). Teardown gap known (§30.14.25):
RX-source/BT-SCO routing latches, teardown restores only mic/speaker enables + routing byte.

**Probe P8 (field, no reflash)**: dial Jabra first, power TID-PTT BEFORE any TX (SCO not yet
opened, no echo) -> does it page in? Hypothesis: open SCO starves page-scan scheduling
(controller-level, cf. E4 incoming-page wall). PASS => goal = order-of-connection; asm scope
shrinks to echo-fix + name-guard. FAIL => incoming join while ANY link is up is controller-
blocked when the incumbent holds HFP; S2b = kick joiner + run FULL app dial flow
(FUN_01e60120(1) + posts 0x11/0x12 + FUN_01e600b4) from a NON-bt task context (UI-task event
injection — bt-task call deadlocks on LOOP B waits) — design pass then asm.

**S2b-echo (required either way)**: locate TX-release SCO-stop path; in 2-link state SCO
stays open (ch. 27 §27.13) => sidetone loop. Static: bind block posts SCO-start; SCO-stop
dispatcher cases NOT in 0x01E21AF8/0x01E1792E (checked, no 0x1e/0x1f) => poster lives in
precompiled relay; approach = find TX-release handler via PTT-release call chain instead.

- 2026-11-10: **P8 = FAIL.** Jabra dialed first (no TX, no SCO, no echo) -> TID-PTT
  power-on does NOT page in. Incoming join is blocked whenever the incumbent holds an
  HFP link (vs §30.14.17 where Jabra paged in while incumbent was SPP-only; E4/E6:
  incoming pages die at LL ~700 ms 0x13 = controller wall) => join-order trick is dead;
  S2b must make BOTH links radio-originated or keep TID-PTT incumbent.

## §33.5 — S2b architecture decision: "dial the button" (2026-11-10)

Rationale from field facts: (1) radio-ORIGINATED second link works in 2-link state
(E6 PROVEN: outgoing join while incumbent held SPP); (2) incoming join while HFP
incumbent = controller-dead (P8); (3) app dial flow binds audio when it dials (S5b);
(4) settings-press posts cmd 5 KILL (kills incumbent) but the dialer FUN_01e600b4
itself posts ONLY cmd 1 (ch. 31 Q1) — no kill.

DESIGN: Jabra dialed first via stock Connect (audio binds). Cave hook armed at the
bind completion (bt loop case 0xB tail) triggers a ONE-SHOT dial of the TID-PTT
address: stack pages the button = radio-originated second ACL (E6-path). Button's
SPP client then rides the up ACL (or its own page succeeds once radio LL allows —
field-test). No cmd 5, no incumbent kill, audio stays bound to Jabra. Name policy
lives in the arming step: dial ONLY the paired entry whose name == "TID-PTT".

NEXT STATIC (S2b-a, before any asm): (a) FUN_01e600b4 LOOP-B "state==0" variable:
which RAM cell, who writes it, is calling from bt-task deadlock-safe (settings press
runs in UI task); if unsafe, find the UI-task event that reaches FUN_01e6ec9e minus
its cmd-5 post, or replicate the minimal prologue; (b) paired-list [0xB468] entry
layout (stride 0xC, +8 = BD_ADDR ptr; name field?) to locate the TID-PTT entry;
(c) trigger point: post-bind arming at 0x01E612CC tail (cave 0x01EA76DE has room —
currently 72 B of 364 B used by BT-PTT2 code).

## §33.6 — S2a static PASS: classifier patterns + "dial-without-eviction" design P9 (2026-11-10)

CLASSIFIER DECODED (FUN_01e7ec28, disasm): remote name (r9) tested via ROM strstr
(0x021127C4) against main-pool patterns: "TID-MIC-EAR" (11 ch, pool+0x1B4C @file
0x9BF5C), "TID-MIC" (7 ch @file 0x9B970), base pool+0x558 "TID-PTT" @file 0x9B968.
Result byte written to b[0xB390+0xD4] (= routing byte 0xB464) only when
b[gp+0xB10]&~0x3F == 0x80 (mode 2): name contains TID-MIC-EAR -> 3; TID-MIC w/o
EAR -> 4; neither -> 1. ROOT-CAUSE INSIGHT: the OEM app only ever routes audio to
TID-branded combo headsets; a Jabra classifies to mode 1 = no-op. This is the
designed behavior, not a bug — ch. 30 crippling fully explained.

DIALER FUN_01e600b4 FULL DISASM (work/full.lst 0650B4): gate mode==1;
0x01E16E0E (link mask via 0x01E16878(1)) != 0 -> posts cmd 0x4A (l2cap teardown
ALL channels = the button-killer); ==0 but transitional r5!=0 -> posts 0x12 then 5;
converge @0x01E600FE `call 0x01E1792E` @0x01E60102; LOOP-B waits 0x01E17F26
(=goto 0x01E07BD4, reads 0 on stable link — ch. 31) then posts cmd 1 (1,6,addr).
Settings press FUN_01e6ec9e posts 0x11, 0x12, 5 (calls 0x01E1792E @0x01E6ECC6/
0x01E6ECD0/0x01E6ECD8) then dialer. E9 0x4A posters: 0x01E61E22 (`bdea84ad`) +
0x01E60188 (`bdead1bb`) — patcher constants L2CAPTEARDOWN_*.

P9 DESIGN "DIAL WITHOUT EVICTION" (asm, 16 B, 4 sites on top of ch32_bt_e7):
NOP the call 0x01E1792E at: (1) 0x01E60102 dialer 0x4A/5 converge [NEW site —
E9/E10/E11 never NOPped the dialer's own post; §27.16 root-caused the surviving
close to the chokepoint for SPP targets, but the dialer post is the HFP-target
close path = the button-kicker of §27.13]; (2) 0x01E6ECD8 settings-press cmd 5;
(3) 0x01E61E22 + (4) 0x01E60188 E9 sites. Fire-and-forget posts (no wait for
completion => no E11 deadlock). Workflow tested: TID-PTT connects (incumbent,
mode 1) -> settings Paired->Jabra->Connect -> dialer gate passes, 0x4A/5 suppressed,
button SPP untouched -> cmd 1 dials Jabra (E6-proven 2-link shape) -> connect-
complete -> case-0xB bind block re-points app current device + SCO to JABRA
(E6-proven: dialed device binds) -> audio on Jabra, button keeps SPP keys.
Single SPP session 0x1A740 stays with button (Jabra = HFP, never touches it).
Echo (SCO-stays-open) = S2b-1, deferred per user.

## §33.7 — P9 BUILT (2026-11-10)

Image `work/ch33_p9.bin` sha256 `6c9c94218e4b3385976e9c03a09fa9b82096f66590b3d064aa19d7cf614c0fe4`
= p9_plain.bin (bte7_plain.bin + 16 NOP bytes at 0x60102/0x60188/0x61E22/0x6ECDA —
site 4 corrected to file 0x6ECDA = VA 0x01E6ECD6; first attempt asserted at 0x6ECD8
'4220bdea' and was caught by the byte pre-assert) . Packaged vs CUR_RADIO=ch32_bt_e7:
**3 sectors 0x65000, 0x66000, 0x73000** -> work/ch33_p9_sectors/. Stage script
`work/ch33_p9.sh` (jluboottool PTT+3 path from ch32_bt_e7 OEM app; uboot-sacredness
assert; Q&A = P9 workflow Q1 boot / Q2 button connects / Q3 settings-Connect Jabra /
Q4 BUTTON STAYS CONNECTED = the test / Q5 Jabra audio / Q6 button keys / Q7 V1.0.50-BT
/ Q8 anomalies). Method note: plaintext surgery on the verified S1 plain (NOPs need
no asm-source semantics; blast radius asserted byte-exact). UNTESTED — flash = user.

## §33.8 — P9 retry card (same image, strict order) (2026-11-10)

No reflash. The P9 card failed because at first boot the radio re-dialed the Jabra
(last-device reconnect) and the run started in the P8 wall state. Disciplined retry on
`work/ch33_p9.bin` `6c9c94218e4b3385`:

1. Power OFF both Jabra and TID-PTT. Power-cycle the radio.
2. Power TID-PTT -> it should connect (idle radio accepts incoming pages = S1 behavior).
   If it does NOT connect with nothing else up => P9 image regression, STOP + report.
3. With the button connected, power ON the Jabra (do NOT touch the radio menu). Wait 30 s.
   Expected on this image: Jabra does NOT page in (P8 wall) — that is fine, next step dials it.
4. Radio menu: Paired -> Jabra -> Connect. OBSERVE: (a) does the radio freeze (as in the
   P9 card)? (b) does Jabra connect? (c) does the BUTTON STAY CONNECTED?  <- the P9 test
5. If both up: TX -> which mic? RX -> earphones or speaker? Button press keys TX?
6. Only after 4-5 pass: power-cycle test (reconnect order on boot) + echo check.

PASS = 4c yes + 5 Jabra audio + button keys. A freeze at step 4 with the button (SPP-only)
incumbent would indict the cmd-5 NOP at `0x01E6ECD6` (press-flow wait); a freeze only with
the Jabra (HFP) incumbent points at the dialer LOOP-B/transitional-wait under HFP.

## §33.9 — P9 post-mortem + Card P10: the dial seesaw (zero patch, S1 base) (2026-11-10)

P9 dead-end lesson: the app's dial path (dialer `FUN_01e600b4` + settings press
`FUN_01e6ec9e` + mode setter `FUN_01e60120`) posts `0x4A`(L2CAP close-all)/cmd 5(kill)
BEFORE every dial; these posts are required by the stack/UI state machine — removing
them deadlocks the connect flow (P9 field: menu Connect press locks radio).

Convergence theory (why the seesaw may settle on the Jabra): the button is FRAGILE
(own firmware drops the ACL when its SPP channel closes — §27.13) but the Jabra is
ROBUST (like the PC in E6, survives channel-close with ACL up). So: dial Jabra (button
drops, audio binds Jabra = S5b/S1.5-proven), THEN dial the button back (its dial closes
the *current* = Jabra channels — Jabra keeps ACL + SCO/audio per E6; button re-attaches
SPP). Unknown risk: the button connect-complete may run the bind block (case 0xB) and
steal audio back — SCO to the button fails (no HFP), so audio *may* stay on the Jabra.

Card P10 (no new image — first restore S1):
```bash
sudo bash work/ch32_bt_e7.sh   # re-flash S1 (d7a29a3e), its 13 sectors cover the 3 P9 sectors
```
Then: 1 fresh boot, both accessories OFF. 2 Connect TID-PTT (pairing/manual — works on S1).
3 Menu dial Jabra (expect button dropped, Jabra audio bound). 4 Verify TX/RX on Jabra.
5 Menu dial TID-PTT (Paired->TID-PTT->Connect). 6 OBSERVE: button back? Jabra still
connected? TX mic? RX location? button keys PTT? 7 30 s stability + power-cycle behavior.
PASS = both up + Jabra audio + button keys => goal state via PROCEDURE on the stock-feel
S1 image; automation (auto re-dial at bind-complete via cave) becomes S2c polish.
FAIL modes are diagnostic: 5 kills Jabra => 0x4A hits HFP harder than E6 suggested;
audio moves to button after 5 => bind-block re-runs per dial, need name-guarded bind skip.

## §33.10 — Radio reverted to PURE STOCK; S1-vs-stock flash staged (2026-11-10)

Operator safety-reset the radio by writing the FULL stock image himself
(`JL: write 0x00000000 Dumps/dump_internal.bin`, 1 MiB incl. VM): radio now runs
**pure stock v1.0.50** with the old pairing data from that dump — all devices must be
re-paired. The stock OEM app restores the PTT+3 SCSI download-mode combo.

`work/ch32_bt_e7fix.sh` (3 sectors, exported vs the P9 baseline) is NOT usable from
stock — sector exports are baseline-dependent (§33.9 gotcha). Re-exported the SAME
deterministic S1 image (`work/ch32_bt_e7.bin` sha256 `d7a29a3eaeffbe67…`) against the
stock baseline:

```bash
CUR_RADIO=$PWD/Dumps/dump_internal.bin python3 work/ch32_p2_pack.py \
  /tmp/opencode/rtasm/bte7_plain.bin work/ch32_bt_e7.bin work/ch32_bt_e7_stock_sectors bte7stock
```

→ **15 differing sectors** `0x1C000,0x1D000,0x1F000,0x26000,0x57000,0x60000,0x7A000,
0x7E000,0x83000,0x93000,0xA0000,0xA1000,0xAC000,0xC2000,0xC4000` exported to
`work/ch32_bt_e7_stock_sectors/`; packager asserts (uboot region, device bytes) pass
(dump_internal's `0xC8FE0` bytes identical to dump_pre_ch30, §32.11 inventory).
Stage script **`work/ch32_bt_e7stock.sh`** (from the e7fix template; `bash -n` OK)
flashes S1 onto stock; afterwards run **Card P10** (§33.9) on the restored S1 base.
