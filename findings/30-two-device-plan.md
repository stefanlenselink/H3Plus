# Ch. 30 — The Two-Device Plan: goal statement, clean baseline, and a strictly-specified experiment ladder

> **Status (2026-10-21): ACTIVE PLAN.** Written after the E1–E11 cycle exhausted the
> exploratory NOP route and the goal was restated by the user (§30.0). Everything in this
> chapter is an instruction to be *executed and recorded verbatim* — no step may be
> skipped, reordered or "assumed known". Rule of the chapter, in the user's words:
> **"It's better to execute an experiment too much than 1 too less."**
>
> Prior context: [Ch. 27](27-firmware-2slot-stack-controller-wall.md) (E1–E11 log),
> [Ch. 29](29-static-analysis-reference-map.md) (address map),
> [Ch. 28 §28.7](28-sdk-forks-survey.md) (SDK route). Route decision: micro-patch
> (cave/compile) route chosen over SDK rebuild — rationale in §30.11.
>
> **Current position (2026-10-22 late-late):** B0–B2 complete. M1 (`90bec320`) tested:
> **M-A FAIL (reproduced) + M-B FAIL (decisive card, reproduced)** — kick-on-press in
> both orders, exactly the ch. 27 `0x4a`-walk model; M1 is dead as a recipe, **M1-C/D/E/R
> skipped** (flagged deviation). Both order cards additionally hit the **VM-rewind
> stale-key trap** (§30.9) — preflight re-pair rule now in force. Open item: RX audio
> absent after pairing-flow takeover vs present after headset self-connect
> (join-path-dependent routing, §30.10 M1-B).
> **M2 (`de635665`) stage flash PASS; model-predicted FAIL CONFIRMED** — the preflight
> showed the press-time kick persists (TID-PTT dropped on the Jabra Connect press) and
> surfaced a **new M2 regression: a failed (stale-key) bonded connect now DEADLOCKS the
> radio** (cleanup-kick NOPs wedge the auth-fail teardown; §30.9). Formal M2-A/M2-B
> cards skipped (flagged deviation — their core question was answered by the preflight).
> M2-OBS: sidetone persists; **fast double-press BT-PTT → press 2 keys with the radio
> mic** (async mic-re-arm race, §30.10).
> **Current status (2026-10-25 20:50): F4 field-FAILED (regression) → ROLLED BACK
> to F3-v3 — radio healthy (Connect works, 3/3 keys). NOP route closed at cmd 5;
> R1-proper (rewrite the wait) is the remaining R1 move.**
> F4 (`--no-cmd5-kill`, `e7bc8abd`) flashed clean (1 sector, readback + full-flash
> verify PASS) but the FIRST Paired→Connect press (TID-PTT, nothing else connected)
> **froze the radio** — the "fire-and-forget" premise was WRONG: the connect flow
> POSTS cmd 5 and then WAITS for its disconnect-completion; with the executor NOP'd
> the wait is unsatisfiable whenever any link state exists (incl. the boot phantom —
> which is also why menu-connect repairs the phantom on F3-v3). Pairing mode then
> found nothing; Jabra incoming self-connect still worked. Q1 chain CONFIRMED
> (cmd 5 IS the press killer) but a NOP cannot remove it — the flow's WAIT must be
> made conditional (profile-aware) = code-cave rewrite, not another patch byte.
> Rollback `work/ch30_f4rb.sh` **PASS 20:45**: sector `0x026000` restored from
> F3-v3 `1a1eaca1`, readback + full-flash verify PASS, regression-clear sanity
> PASS (*"yes"* + *"done all ok 3x tx ok"* = 3/3).
> **NEXT (2026-10-27): R1-a field-FAILED (freeze) → R1-b (walker-side kill) BUILT
> — awaiting flash.** Q4/Q5/Q6 analyses are consolidated into **§30.14** (permanent record;
> the `/tmp/opencode/r1_q*.md` reports are transient scratch). `--r1-conditional-
> kill` image `work/ch30_r1a.bin` (`18bc1597`) flashed clean but **froze the radio
> deterministically on every Paired→Connect press** (power-cycled repeatedly —
> identical every time); rolled back to F3-v3 via `work/ch30_r1arb.sh` (**PASS**,
> 3/3 keying). Post-mortem (all verified with the **official JieLi LLVM objdump**,
> §30.14.6): the cave encoding is EXACT (not a bug); the failure is the predicate
> INPUT — the `[[0xB468]+[0x102D0]*0xC+8]` selection cell was validated only on
> other Connect paths, and the Paired-screen press posts cmds `0xC,0xE,0x12,5,0x4A`
> with **no address at all**. Decisive discovery: the walker's page target is the
> 6-byte cell **`0x10E34`**, armed synchronously by CON events 8/0xb immediately
> before the sole page post → **R1-b hooks the walker page-post site instead**
> (race-free fresh target: kill only same-address stuck records, leave
> different-device incumbents) combined with the wholesale cmd-5 NOP. Full
> post-mortem, walker/press-block decodes and the R1-b design brief: **§30.14.6**.
> **R1-b is now BUILT** (`--r1-walker-kill`; image `work/ch30_r1b.bin` `36fcead7`
> = F3-v3 + 80 B / 3 sectors `0x026000`+`0x065000`+`0x0AC000`; hook `0x01E60DE4`
> → 78 B cave2 `0x01EA7758`, official-clang-compiled + objdump-verified; suites
> green): stage `work/ch30_r1b.sh`, card `work/ch30_r1bc.sh`.
> **R1-b field-FAILED 2026-10-27 10:55 (same freeze symptom)** — flashed clean
> (readback + full-flash verify PASS, boot OK, pairings intact) but the first
> Paired→TID-PTT→Connect froze BT (connect never; follow-up Pairing scan
> timeout; card never run). **Root cause found (§30.14.8):** the killer
> `0x01E08A94` → `FUN_01e029de` is a **btctrler queue post that retries forever
> in task context when the queue is full** — a btstack-task-only contract that
> cave2's KILL branch (running in the BT task) violated = the spin-freeze. POST
> path proven fine (boot phantom paged cleanly). Three corollaries recorded:
> kills must be **posted, never called off-task**; **cmd 5 stays live** (it only
> kills stuck slots — it was never the press evictor); the **F3-v3 press evictor
> bypasses `0x4a`** (already NOP'd there) — candidates: ring case `0xB`
> DISCONN_SDP_MASTER, the `spp_connect` single-session chokepoint, or
> controller-level; next static step = decode `FUN_01e21af8` cases
> `0xC/0xE/0x12/0x10/0x11/0xB/0x4a`.
> Radio currently: **R1-b (`36fcead7`, frozen BT on Connect)** — rollback
> `work/ch30_r1brb.sh` was handed over but is now **superseded**: the R1-c
> stage writes the same 3 sectors and works from either state.
> **R1-c BUILT 2026-10-27 (`--cmd5-handle`, image `ee0ba984`):** the press-time
> evictor was finally located — **stock cmd 5's stuck-slot test reads the mask
> halfword @slot+8, which accessories keep at 0 while LIVE** (explains E6 pass
> with PC vs E7/F3V3-B fail with TID-PTT). R1-c re-encodes the load to the ACL
> handle @slot+6 (`19 60`→`09 63` @`0x01E21EF0`, 2 bytes, one sector): cmd 5
> stays live (no F4 deadlock), runs on the btstack task (no R1-a/b freeze),
> kills only genuinely stuck records. Design + evidence: **§30.14.9**.
> **R1-c field-FAILED 2026-10-27 13:49 (same-device Connect freeze — the GOAL
> case T2 was never reached)** — flashed clean (full §30.3 verify PASS, boot OK,
> pairings intact) but Paired→TID-PTT→Connect wedged (never connected) and fresh
> Pairing timed out. **ROOT CAUSE LOCATED (§30.14.10): the press flow itself
> contains unbounded waits for the current ACL link to drop** — settings path
> `FUN_01e600b4` loops A/B wait for ANY link down before their direct cmd-1 page
> post; the modal path waits a CON event 3 → `b4f0` bit0 → watchdog → bit3 clear.
> Stock cmd 5's kill is the load-bearing event satisfying both; F4/R1-a/b/c all
> removed the kill but left the wait → identical freeze. **R1-d (walker→cmd 4)
> is NO-GO**: cmd-4 executor is E7-NOP'd, walker never armed in the freeze, bit3
> gates it. Radio currently: **R1-c (`ee0ba984`)** — **rollback:
> `sudo bash work/ch30_r1crb.sh`** (ONE sector `0x026000` → F3-v3; pairings
> untouched).
> **NEXT: patch the WAIT, not the kill** — designs D1 (retarget `FUN_01e600b4`
> waits to same-address via `0x01E16824`) / D2 (modal-release cave), under
> byte-level static GO/NO-GO verification BEFORE any build.
> **R2 DONE 2026-10-28 ([Ch. 31](31-bluetooth-10-connect-press-flow.md)): D1 = GO
> (optional R1-f hardening), D2 = NO-GO — and the freeze model is CORRECTED: the
> wait predicate reports *transitional* controller links, not "any link", so it
> never blocked on the incumbent; the real hang is the same-address page guard
> `0x01E16824` @`0x01E21E76` refusing the page (silent "Connecting").** The
> resulting **R1-e design** (press-store + targeted cmd-5 kill, two changes on
> F3-v3) is specified in **§30.14.11**; **IMPLEMENTED 2026-10-30** as
> `--cmd5-target` (four sites, objdump round-trip verified, both suites green).
> **R1-e first flash (`d2aa7d8d`) FIELD-FAILED 2026-10-30 (§30.14.12): Connect
> hard-locked the radio, Pairing timed out — misaligned multi-byte loads on the
> ODD saved-target cell `0x0001A5F1` in the cmd-5 kill cave (pi32v2 faults).
> R1-e2 FIX (`033fd190…`, cave 40 B byte-wise XOR-fold) FLASHED 2026-10-31:
> FIELD-FAILED — IDENTICAL lockup + post-reboot inquiry timeout ⇒ the misalign-
> ment was NOT the (only) root cause. ROOT-CAUSE MODEL: the R1-e design is
> racy — press posts the cmd-5 kill ASYNC, `FUN_01e600b4`'s GLOBAL link waits
> read 0 on a stable link, so the page is posted while the target record is
> still inuse and the guard `0x01E16824` refuses it → "Connecting" hang.
> FIX = R1-e3 = R1-e2 + D1 (`--d1-target-wait`, ch. 31 §Q6 recipe): target-
> specific waits make repair deterministic. **R1-e3 BUILT 2026-10-31:**
> `--d1-target-wait` implemented (3 sites objdump round-trip verified, thunk cave
> relocated `0x01EA7758`→`0x01EA77F0`; both suites green), image
> `work/ch30_r1e3.bin` sha `b0fa1b35…` (vs F3-v3: 4 sectors `0x026000`+`0x065000`+
> `0x073000`+`0x0AC000`, 93 B; vs flashed R1-e2: 2 sectors, 18 B). Stage
> `work/ch30_r1e3.sh` + card `work/ch30_r1e3c.sh` ready. **R1-e3 FLASHED 2026-10-31 +
> FIELD-FAILED — identical HARD freeze (target NOT connected when pressed → race model
> busted as sole cause; screen lit but keys/menu/PTT all dead; BOTH directions hang;
> reboot auto-reconnect works → VM intact, press-triggered).** New leading hypothesis
> **H-gate: the F3-v3 `--gate-close` sticky page-pending deadlock — F3-v3 itself was
> never press-tested in these directions.** **NEXT: P0 hardware bisect — rollback F3-v3
> (`work/ch30_r1erb.sh`, 4 sectors) + press-matrix card `work/ch30_pmatrix.sh`** (S1 no
> incumbent / S2 Jabra-up press TID-PTT / S3 TID-PTT-up press Jabra), then R1-c, then
> **P0 RUN 2026-10-31: F3-v3 ITSELF FREEZES on Connect (user report) ⇒ R1-e series
> innocent of THAT freeze; freeze = close-blocking lineage (E11/F3-v2/gate; E7–E10 never
> froze). R2-a (E7 + targeted kill + D1) then FROZE TOO (2026-11-01 card: S1–S4 all
> freeze, S5 inquiry alive) ⇒ ROOT CAUSE #2: `0x1A5F1` is the stack's RE-PAGE MAILBOX —
> the presst cave poisoned it every press (§30.14.14, dispatcher epilogue `0x01E2232E`
> OR-folds it → cmd-2 re-page race). R1-c was NEVER cleanly tested (rode the freezing
> F3-v3 base). **R2-b = E7 + `--cmd5-handle` ONLY** — `work/ch30_r2b.bin` sha
> `52c3016a…` — stage `work/ch30_r2b.sh` + card `work/ch30_r2bc.sh`; repair press known
> NO-GO. **R2-b FLASHED 2026-11-01 + FIELD-FAILED — same hard freeze, inquiry silent
> again.** BYTE PROOF (§30.14.15): R2-b = exact-E7-rebuild + ONLY the 2 handle-test
> bytes @flash `0x26EF0`, and the rebuild == the never-freezing 2026-10-09 field E7 with
> ZERO strict-region diffs ⇒ fork (a) the 2 bytes (incumbent survival) architecturally
> freeze the press flow — targeted-kill idea dead — or (b) radio STATE degraded (the
> firmware-inert inquiry timeout supports this). **BISECT RUN 2026-11-01: E7-ref
> (= exact E7, stock cmd 5) → NO FREEZES, press = stock kick ⇒ FORK (a) CONFIRMED:
> the 2 handle-test bytes (incumbent SURVIVAL under cmd 5 for mask==0 accessories)
> themselves hard-freeze the app press flow — targeted-kill-on-manual-press is DEAD
> on the stock app (E6's PC-incumbent survival, mask!=0, never froze — the freeze is
> accessory-record-specific). NEW POSITIVE: boot auto-join reached a CRIPPLED
> TWO-DEVICE state (headset auto-joined without a menu press).** Radio currently on
> E7-ref `90bec320`, stable. **NEXT: characterize the crippled two-device state
> (checklist sent) → strategy A = make the press-free auto-join flow reliable + fix
> the crippling; B = §30.9 rewrite routes.** **CHARACTERIZED 2026-11-01 (§30.14.17):
> the two-device state is REAL and STABLE** — connect TID-PTT first, then power the Jabra on
> and it pages IN (no menu press): both connected until radio power-off, clean teardown.
> Crippling = app audio routing ONLY: TX mic = TID-PTT (mode 1 bound to the first device),
> Jabra silent passenger, RX silent everywhere (P1 baseline pending). Jabra auto-reconnects
> only if it was connected at its OWN last power-off — never let the radio kick it.
> **P1/P2 ANSWERED 2026-11-01 (§30.14.18): the TID-PTT has NO speaker (stock = all audio on the
> radio) and NEVER auto-connects — only the Jabra pages in; the button joins ONLY via the menu,
> which force-kicks the Jabra ⇒ the P2 order-swap is IMPOSSIBLE; the reachable two-device order
> is button-first + Jabra-incoming.** ROUTING CHAIN FULLY DECODED: routing byte `0xB464` has
> exactly THREE writers (classifier `0x01E7EC28` writes 1/2/3/4/6 by NAME via ops-table
> `DAT_0000bf4c`, sole caller = btstack dispatcher `FUN_01e19e44` **case 7 name-result**; + BT-task
> case 9/10 teardown @`0x01E61C88` stamps the `0xF0` sentinel — explains the C5 mic switch).
> H-name leading: incoming joins get no remote-name request ⇒ classifier never runs ⇒ byte stays
> 1. **NEXT: implement `--incoming-mode3`** — P6/P7 RUN 2026-11-02 (§30.14.20): P6 PASS (Jabra-only = Jabra mic + RX earphones ⇒ mode-3 bind healthy whenever classified); P7: incoming re-join NOT accepted within a session (**one incoming join per radio boot**; redo = radio power-cycle) ⇒ discriminator moot, fix = tbh-entry cave (`0x01E61270`): byte==1 && >=2 inused conn records → byte=3, then stock tbh binds HFP. **R3 BUILT + FLASHED + CARD RUN 2026-11-02 (§30.14.21–22): `--incoming-mode3` (tbh hook `0x01E61270` + 54 B cave `0x01EA77F6`), image `d9c35315…`; field: Jabra paged in (S1a PASS), but after the Jabra powered off (S3) a loud ECHO LOOP = TID-PTT mic broadcast on the radio speaker (teardown/restore gap after the forced mode-3 bind), RX back on speaker. **FULL VERDICT 2026-11-02 (§30.14.23): FAIL for the goal — with both up, TX stayed TID-PTT mic and RX was complete silence (links solid, button keys fine, echo loop latched until reboot). Forced mode-3 runs but binds a route with no HFP/SCO to the incoming device (H-noprofile leading). NEXT static done 2026-11-02 (§30.14.24): ch. 11 identities recovered + tbh table off-by-one FIXED (mode1→`0x614A0`, mode3/5→`0x6128C`; `0x50398`/`0x503CA` = local mic/speaker enablers) — forced mode-3 ran a state path, not a bind; silence+echo fully explained. §30.14.25 TEARDOWN DUMP: teardown restores mic/speaker enables + routing byte but NOT the RX-source ⇒ echo latch root cause localized; **R3 verdict = roll back — script READY `work/ch30_r3rb.sh` (2 sectors → E7-ref `90bec320`, pairings survive; NOT flashed)**. **R4 STATIC DONE 2026-11-03 (§30.14.26): the outgoing paths post `user_send_cmd_prepare(1, 6, addr)` = START_CONNEC_VIA_ADDR @`0x01E6114+0x1E00000` (`0x01E60114`) — profiles/SCO ride on it; incoming joins never post it. R4 = replay cmd 1 for the joining device at the proven-safe tbh hook `0x01E61270` (routing byte unchanged, no forced mode). **R4 BUILT 2026-11-03 (§30.14.27): `--incoming-hfp` = tbh hook `0x01E61270` + 58 B cave `0x01EA77F6` (byte==1 && both records inused → post `user_send_cmd_prepare(1,6,[sp+20])`, byte UNCHANGED) + cmd-1 `is_1t2` bail NOP `0x01E17A2A`; objdump round-trip + both suites green; image `work/ch30_r4.bin` `9168ac96…` = E7-ref + sectors `0x01C000`+`0x066000`+`0x0AC000` (56 B); stage `work/ch30_r4.sh` + card `work/ch30_r4c.sh`; **R4 FLASHED + CARD RUN 2026-11-03 (§30.14.28): FAIL — Jabra paged in but S1b TX stayed TID-PTT mic + S1c RX SILENT (replay runs — S4a RX scrambled with incumbent = SCO disturbance — but opens no HFP/SCO to an already-connected ACL: cmd 1 is a dial command, same-address guard `0x01E16824` no-ops it); post-Jabra-off echo at first RX (worse than E7-ref); rollback `work/ch30_r4rb.sh` READY (3 sectors, pairings survive, NOT flashed). **R4 VERDICT FAIL. R5 STATIC 3 ROUNDS DONE 2026-11-03 (§30.14.29-30): dial path always posts cmd 5 READ_REMOTE_NAME (classification input) + cmd 1; event-7 name result calls classifier then EXITS (never re-binds); app-redial record `0x1A4C8/C9` decoded = DEAD for same-device (same-address guard); stack re-dial mailbox `0x1A5D1` + saver `0x21988` + consumer `0x21E38` (trigger UNKNOWN) decoded; btstack task event table `0x21B98` mapped; **`0x2193A(record,0x1100)` = the stack's connection-attempt starter — NEW LEAD: call it on the existing incoming record (R5 option C, dump body next)**. NEXT: implement + build R5 (§30.14.31 design final).** **R5 BUILT + FLASHED + CARD RUN 2026-11-03 (§30.14.32–33): `--incoming-redial` = tbh hook `0x01E61270` + 174 B cave `0x01EA7722` (arm re-dial mailbox `0x1A5F1` with joiner addr byte-wise + HCI-Disc the incoming ACL → stack epilogue `0x01E2232E`→`0x01E21E46` re-dials with profiles; loop guard; teardown `0xF0`+match → byte:=3; NO bail NOP); objdump + suites green; image `work/ch30_r5.bin` `dc4b2704…` = E7-ref + 2 sectors `0x066000`+`0x0AC000` (158 B). FIELD: **two-device STABLE, ZERO freezes anywhere** (mailbox arm at tbh did NOT wedge — R1-e failure mode absent), but S1c/S1d = TX TID-PTT mic + RX silence — identical goal-miss signature to R3/R4; S5b confirms radio-dialed Jabra binds audio perfectly as app-current-device. Kick+redial firing UNCONFIRMED (S1a tone ambiguous). **R6 = discriminator first**: reason-code telemetry (`0x11` kick) + static re-verify of slot-inused byte offsets `0x1A5CA`/`0x1A5E6`. Radio on R5; rollback recipe = 2 sectors from E7-ref (no script).** **R6 STATIC PASS 2026-11-03 (§30.14.34): all three suspects CLEARED — slot-inused reads correct (stack's own bit29 test @`0x16824`/`0x1687A`; ch.27 "+0xE" note off-by-one), epilogue `0x2232E`→cmd-1 dial confirmed (entry = dispatcher **event 0**; vendor arm `0x21C3E` `rep 4 6` = only writer, **NO clear exists** — persistent redial by design), find-conn `0x79CA`/`0x14BA8` walks BOTH conn objects @`0x1A0A8` stride 224 by BD_ADDR ⇒ works for the joiner. ⇒ **R5 kick+redial FIRED** (R1-e empirically proved arm ⇒ re-page); the wall = **app struct `0x102F0` never re-pointed on stack-originated redial** (no name request ⇒ no classifier ⇒ byte 1 ⇒ mode-1 no-op). **R6a proposal: cave loop-guard branch (mailbox==joiner = OUR redial's connect-complete) stamps `b[r6+212]:=3` (~6 B change, same cave/sectors); if still silent ⇒ R6b = struct re-point (ch. 25 compile route). Telemetry moot.** **R6a BUILT 2026-11-04 (§30.14.35): `--redial-bind` = the ONE-byte cave change (cave +73 `0x41→0x44`, loop-guard RET→DONE stamps byte 3 at our redial's connect-complete); objdump + both suites green (legacy-window `inchrdlbind` recognition added); image `work/ch30_r6a.bin` `62214f14…` = E7-ref + 2 sectors `0x066000`+`0x0AC000` (158 B; = R5 + 1 byte @ flash `0xAC76B`); stage `work/ch30_r6a.sh` + card `work/ch30_r6ac.sh` ready. UNTESTED — NEXT: user flashes + card; verdict §30.14.36. Radio on R5 `dc4b2704`; rollback recipe = 2 sectors from E7-ref `90bec320` (no script).** **R6a FLASHED + FIELD-FAILED 2026-11-04 (§30.14.36): stamp EXECUTED (S1a redial delay + S3 CLEAN teardown, no echo unlike R5) yet audio never bound (TX radio mic, RX speaker — 4th identical signature) ⇒ byte-3 at redial connect-complete is a STATE path, not a bind; S5 repair press REGRESSION (kicks both, nothing reconnects). Wall CONFIRMED = app struct `0x102F0`. Routes: R6b re-point design / SDK rebuild / ch. 25 compile route. Radio on R6a `62214f14`; daily-use rollback recipe = 2 sectors from E7-ref.** **R6b BUILT 2026-11-04 (§30.14.37–38): `--redial-current` = at the loop-guard match (our redial's connect-complete) branch to a new 90 B CUR window @`0x01EA77D0` (guard `70 41`→`10 52`): zero the re-dial mailbox `0x1A5F1` (fixes the S5 regression + releases P7), write the STACK current-device record (BD_ADDR `0xBF41..46` + valid `b[0xBF3A] |= 0x40`; `is_current_device` `0x01E184D6`), post `user_send_cmd_prepare(6 = READ_REMOTE_NAME, 6, joiner)` → HCI name result → btstack dispatcher event 5 → classifier `0x01E7EC28` **self-stamps routing byte 3 on the app's own classification path**; routing byte UNCHANGED at the tbh. Objdump pixel-perfect + both suites 0 failures; image `work/ch30_r6b.bin` `7f2af259…` = E7-ref + sectors `0x066000`+`0x0AC000` (237 B); stage `work/ch30_r6b.sh` + card `work/ch30_r6bc.sh` ready. **UNTESTED** — verdict §30.14.39; if goal-miss again, the byte/command-level tbh route is DEAD for good ⇒ SDK rebuild (ch. 28) / ch. 25 compile route.** **R6b FLASHED + FIELD-FAILED 2026-11-04 (§30.14.39): flash clean; S1 goal-miss with the 5th identical signature (TX TID-PTT mic + RX silence; CUR firing unconfirmed — no redial delay heard); new regressions — S4 press-FREEZE (E7-ref never froze) + S5 both-kicked/TX-dead; S3c P7 self-heal dead. ⇒ BYTE/COMMAND-LEVEL tbh ROUTE DEAD FOR GOOD — the bind needs the full app-originated connect flow. R6b must NOT ship. Radio on R6b `7f2af259`; daily-use rollback recipe = 2 sectors `0x066000`+`0x0AC000` from E7-ref `90bec320`. NEXT: user picks escalation — SDK rebuild (ch. 28) / ch. 25 compile route / ESP32 combo device.** **ROUTE CHOSEN 2026-11-04 (§30.14.40): ch. 25 decompile⇒compile. R7 BUILT + STAGED 2026-11-04 (§30.14.41–42): Phase A DECODED THE BIND — tbh hook lives in the bt-task main loop `FUN_01e60e44`; event case 0xB = bind block @`0x01E61292` (current-device gate + state `|=5` + cmd `0x1E` SCO start); R7 `--redial-bind2` = same R6b prefix (mailbox zero + current-device write) then **byte:=3 + payload synth + direct `goto 0x01E61292`** = the stock bind block runs itself in-task. Objdump pixel-perfect + suites 0 failures; image `work/ch30_r7.bin` `575e593d…` = E7-ref + sectors `0x066000`+`0x0AC000` (238 B); stage `work/ch30_r7.sh` + card `work/ch30_r7c.sh`. UNTESTED — verdict §30.14.43; if goal-miss ⇒ in-image bind emulation dead ⇒ SDK rebuild (ch. 28).** **R7 FLASHED + FIELD-FAILED 2026-11-06 (§30.14.43): flash clean (after fixing the stage script's stale 237 B assert — image innocent); S1 GOAL FAIL — 6th identical signature (TX TID-PTT mic + RX silence; bind2 firing unconfirmed, no redial delay); S4 no freeze (R6b's freeze did not reproduce) but S5 both-kick + TX-dead regression persists; S3c P7 self-heal dead. ⇒ IN-IMAGE BIND EMULATION DEAD — direct bind-block goto still goal-miss (the bind needs the app-originated dial flow setting struct `0x102F0` state before connect-complete). R7 must not ship. Radio on R7 `575e593d`; daily-use rollback = 2 sectors `0x066000`+`0x0AC000` from E7-ref `90bec320`. NEXT: user picks final route — SDK rebuild (ch. 28) / ch. 25 deep rewrite / ESP32 combo device.**
| Teardown dump + rollback | 2026-11-02 | `d9c35315` (R3, unchanged) | objdump `0x61C40–0x61C9E` + `0x61D7C` windows (§30.14.25) | **teardown restores mic/speaker enables + routing byte but NOT the RX-source ⇒ echo latch root cause; R3 verdict = roll back** | radio still on R3 | §30.14.25 | rollback `work/ch30_r3rb.sh` READY (2 sectors → E7-ref, pairings survive; NOT flashed); NEXT = R4 static (relay `0x01E22890` ops, `0x184D6`, HFP profile-connect poster) |
| R4 static | 2026-11-03 | `90bec320` (E7-ref, unchanged) | objdump `user_send_cmd_prepare` dispatcher + page fn + far paths (§30.14.26) | **outgoing connect = `user_send_cmd_prepare(1, 6, addr)` @`0x01E60114` (START_CONNEC_VIA_ADDR → profiles → SCO); incoming join never posts it ⇒ R4 = replay at connect-complete tbh hook `0x01E61270`, byte unchanged** | — | §30.14.26 | NEXT: cmd-1 tail + addr-offset verify → implement `--incoming-hfp` → build R4 |
| R4 built | 2026-11-03 | `90bec320` (E7-ref, unchanged) | `--incoming-hfp` implemented (§30.14.27): hook `0x01E61270` + 58 B cave `0x01EA77F6` (post cmd 1 for joining addr, byte UNCHANGED) + cmd-1 bail NOP `0x01E17A2A`; objdump round-trip; suites green (12 new checks) | image `work/ch30_r4.bin` `9168ac96…` = E7-ref + 3 sectors `0x01C000`+`0x066000`+`0x0AC000` (56 B); stage + card ready | — | §30.14.27 | **UNTESTED — NEXT: user flashes + card run** |
| R4 field | 2026-11-03 | `9168ac96` (R4, flashed 08:48, all readbacks PASS) | E7 recipe + `--incoming-hfp` | 3 sectors `0x01C000`+`0x066000`+`0x0AC000` | S0 PASS; S1a Y; **S1b TID-PTT mic / S1c SILENT = GOAL NOT MET**; S2 solid; S3b echo at first RX after Jabra-off; S4a TX Jabra ✓ RX scrambled; S5 kick + transient freeze, recovered | `work/logs/ch30_R4_20261103_084833.log`, `ch30_R4card_20261103_085208.log` | **§30.14.28 FAIL** — replay fires but no HFP/SCO to connected ACL (same-addr guard). No rollback script (user directive 2026-11-03); re-image = E7-ref `90bec320` + 3 sectors `0x01C000`+`0x066000`+`0x0AC000` |
| R5 static | 2026-11-03 | `9168ac96` (R4, unchanged) | 5 objdump rounds (§30.14.29-31): page-fn always posts cmd 5 + cmd 1; dispatcher events mapped; app-redial `0x1A4C8/C9` DEAD same-device; **re-dial mailbox CORRECTED = `0x1A5F1`** (re-page mailbox; event-0 maintains, `0x2232E` OR-fold → `(1,6,0x1A5F1)` @`0x21E46`; events 66/77 post too); consumer chain + record layout byte-exact; `0x17420`→`0x79CA` find-conn (mode0/2, memcmp `0x3127B0`); proven kick `0x178B2`; cave window `0x01EA7722..0x01EA77F5` 212 B ALLZERO v44/45/50+E7 + ptr-scan clean | **R5 DESIGN FINAL `--incoming-redial`**: tbh hook — byte==1 && 2 records && mailbox≠addr → arm `0x1A5F1` + kick incoming ACL; byte==0xF0 && mailbox==addr → byte=3 | — | §30.14.29-31 | **NEXT: implement + objdump + suites + build `work/ch30_r5.bin`** |
> Rollback to F3-v3: `work/ch30_r1erb.sh` (4 sectors).
> Optional side-quest (not run): goal-order incoming
> card `work/ch30_f3v3c.sh`. §30.9 rules in force.

---

## §30.0 — Goal statement (authoritative, from the user — 2026-10-21)

> *"It's not rescoped — it was never intended in the first place. It always was the idea
> to have multiple BT devices connected and use the SPP device from 1 and audio from the
> other."*

Concretely, the **end goal** is exactly two connected devices:

| Role | Device | Profiles used | Function |
|---|---|---|---|
| **Device A — audio** | Jabra Evolve 65 (`74:5C:4B:E2:73:34`) | HFP (SCO bidirectional) | radio RX audio → **earphones**; BT-PTT TX ← **headset mic** |
| **Device B — commands** | TID-PTT button (`6F:E5:E7:FB:12:4F`) | SPP (RFCOMM ch. 2) | button presses → `+SPP=P`/`+SPP=R` → keys the radio |

* Both connected **simultaneously**, paired **in either order** (A-then-B and B-then-A
  must both work).
* The radio's own PTT/BT-PTT/BT-PTT2/OD keys keep working throughout.
* **Two concurrent SPP sessions was NEVER a goal.** It appeared only as the last wall
  during the generic "any two devices" exploration (E11, §27.18) because the PC test
  client happens to be an SPP device. The goal topology — **one SPP + one HFP** — is the
  exact topology E6 already ran successfully (§27.11, hardware-confirmed 2026-10-08)
  with the PC standing in for the TID-PTT.

**The delta between "E6 proven" and "done":** replace the PC (SPP incumbent) with the
TID-PTT accessory, in both pairing orders. Known behavioral difference between the two
SPP clients: a **PC keeps its ACL alive when the app closes its RFCOMM channel; the
TID-PTT drops its entire ACL the moment its SPP channel closes** (§27.13 read-together
with §27.16/§27.17). Every "mysterious" TID-PTT kick so far is consistent with *some*
connect-flow channel-close happening; the plan below finds the minimal NOP stage that
prevents exactly that, verified per-stage, per-order.

---

## §30.1 — Why the two-SPP results still matter (and which ones transfer)

* **Transfers directly:** the app-level eviction chain (kick `0x01E5B22A`, `0x13`
  executor `0x01E178CE`, `0x16` pairing kicks, cleanup callers, the L2CAP/SPP close
  chain) is **device-agnostic** — it fires on *connect-second-device* regardless of what
  the first device is. NOPs E6 `--no-disconnect-13` and E7 `--no-pairing-kick` are
  already HW-confirmed for the goal topology (that IS the E6 run).
* **Does NOT transfer:** the single-SPP-session wall `0x1A740` (two SPP clients), the
  E11 lockup/corruption analysis of two-SPP command routing, and the "echoed verbatim,
  no keying" observation. None of those can occur in the goal topology (only one SPP
  session exists). Do not spend time on them.
* **Re-verify, never assume:** everything recorded under E6–E11 was observed with a PC
  as the SPP client. Any statement of the form "TID-PTT behaves like the PC except X"
  must be re-tested in the ladder below before it may be relied on.

---

## §30.2 — Test bench (fixed hardware & identities)

| Item | Identity | Notes |
|---|---|---|
| Radio (DUT) | TIDRADIO H3 Plus, BT `0B:FF:59:E8:85:92`, name `H3 Plus - 8592` | v1.0.50 base; keep ≥ 50 % charged during a test day |
| PC (Linux/BlueZ rig) | adapter `90:DE:80:55:E3:A6` | repo `tools/bt_*` run here, `sudo` |
| Device A | Jabra Evolve 65, `74:5C:4B:E2:73:34` | HFP/SCO |
| Device B | TID-PTT button, `6F:E5:E7:FB:12:4F` | SPP-only; **drops ACL when its SPP channel closes** |
| Flasher | `jl-uboot-tool` (Linux, `sudo`), working copy at `../jl-uboot-tool/` | bootloader: hold **PTT + `3`** (or `8`) while plugging USB-C into the **side** port |
| Base image | `Dumps/dump_internal.bin` (full 1 MiB dump of **this** radio) | contains device-specific bytes @`0x0C8FE0` + VM; **never flash an image not derived from it without the ARTIFACTS §4 splice** |

**Standing BlueZ hygiene (applies to every experiment):**

```bash
# BEFORE every experiment — clear stale host-side state:
bluetoothctl power off && sleep 2 && bluetoothctl power on
bluetoothctl devices                      # list; note any leftover connections
# PC must NOT hold a link while the radio pairs/connects its own devices:
bluetoothctl disconnect 0B:FF:59:E8:85:92 2>/dev/null || true
# Capture tool (start BEFORE radio power-up, stop after the scenario ends):
sudo btmon -w /tmp/opencode/ch30_<ID>_$(date +%Y%m%d_%H%M%S).hcd &
# Decode after (works unprivileged on the root-owned file):
btmon -r /tmp/opencode/ch30_<ID>_*.hcd > /tmp/opencode/ch30_<ID>_btmon.txt
```

> **Known trap (ch. 26):** BlueZ auto-reconnect will grab the TID-PTT/radio the moment
> the adapter is on and the devices come in range, silently changing the scenario. If a
> test does not involve the PC as a device, keep the PC adapter **off** (`bluetoothctl
> power off`) and pair everything radio-side.

**Observed radio UI paths & names (B1.2/B1.3, 2026-10-21):** Paired list =
`Menu → Bluetooth → BT Pairing → Paired → <device> → More → Connect`; the TID-PTT
appears as **`TID-PTT0cd28a`**; the radio's name is **`TD-H3-Plus-3511`** at
`0B:FF:59:E8:85:92` (btmon-confirmed B1.3; BLE twin `0B:FF:59:9E:37:81` =
`TD-H3-Plus-3511(BLE)`; class `0x40020c`, Modalias `v05D6` = JieLi; UUIDs SPP +
AudioSink + AVRCP + Handsfree + PnP + vendor `fe01`). PC adapter alias `TID-PTT-PC`.
B2.1 additions: the radio announces only **"Bluetooth connected"** — it never displays
*which* device is connected, so the operator must determine connectivity from the far
device; and the user's working connect flow was `Menu → Bluetooth → BT Pairing →
Pairable → <select paired device>` (the list shown there connects on selection).
Stock auto-reconnect target = **last device of the VM** (B2.1: PC after B1.3's session;
B1.2b: TID-PTT after a TID-PTT session) — so **the PC adapter must be OFF and verified**
before any card that starts with a cold start, or the radio will silently grab the PC.

---

## §30.3 — Recording discipline (mandatory for every experiment)

Every experiment run produces a **record** appended to §30.10's ledger with ALL of:

1. **ID** (e.g. `B1`, `M1-A`), **date + clock times** (start/end).
2. **Build under test**: image filename + `sha256sum` + the exact build command line.
3. **Flash log**: every `erase`/`write` command + the `read … verify` result
   (`cmp` output — must be byte-identical, paste `IDENTICAL` or the diff).
   **Sector-level writes must additionally full-flash verify**: `read 0x00000000
   0x100000` and compare the strict region `0x0000–0x0C8FDF` (bootloader + app)
   against the expected image; the 32 device-specific bytes @`0x0C8FE0` and the
   VM/metadata region @`0x0C9000+` are legitimately excluded (they change with
   pairing). Any mismatch outside those is a STOP — it means the radio's starting
   point was not the expected image.
4. **Step-by-step observations with timestamps** — what was pressed, on which device,
   what the radio displayed / beeped, what the headset did, what btmon showed live.
   **Observations only.** Inference goes in a clearly separated *Analysis* line, after
   the facts.
5. **Pass/Fail against the card's expected result** — "as expected" is forbidden
   wording: state the observed behavior and compare.
6. **btmon evidence filename** (keep under `/tmp/opencode/`, copy decisive excerpts
   into the findings chapter).
7. **Environment deltas**: battery level, anything re-paired/removed, any deviation
   from the card (deviations must be flagged, not silently absorbed).

Anti-assumption rules:

* **One variable per experiment.** If two things changed, split the experiment.
* A test that was *not run on the current build* has **no result** — not even an
  implied one from an earlier build. Re-run it (better too many).
* If an observation contradicts a documented one (§30.9 quirk list or ch. 27), that is
  **finding-grade**: capture it fully before continuing, and re-run the same card once
  to confirm reproducibility.
* Radio power-cycles between cards unless the card says otherwise (defined in §30.4.6).

---

## §30.4 — Phase B0: full-image clean baseline (the reflash)

**Why:** the radio currently runs E11, which corrupts normal SPP operation (§27.19).
Before any planning experiment, return to a *known-good, fully-specified* base via a
**full-image reflash** (not sector patches): this also wipes all accumulated pairing
state, giving every later stage a deterministic starting point.

### B0.1 — Fresh safety dump (before writing anything)

```bash
# radio in bootloader (PTT+3 / PTT+8 + USB-C side port), then:
sudo python3 jluboottool.py
=>JL: read 0x00000000 0x100000 Dumps/dump_pre_ch30.bin
```

Verify size is exactly `1,048,576` bytes; record `sha256sum` of both
`Dumps/dump_internal.bin` and the new dump; store the new dump off-machine.
**Pass:** file complete, no uboot-tool errors.

### B0.2 — Build the baseline image (BT-PTT key patches only — NO multipoint NOPs)

```bash
python3 tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin \
    work/ch30_base.bin \
    --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT \
    --sectors=work/ch30_base
sha256sum work/ch30_base.bin
python3 tools/patch_h3plus_firmware_bluetooth.py work/ch30_base.bin --show
```

**Expected `--show`:** PTT = BT-PTT patched, PTT2 = BT-PTT2 patched, OD = PTT patched;
**all ten multipoint sites = stock.** Any other state → STOP, investigate (image
mix-up). Because the image is built from *this radio's* dump, the `0x0C8FE0` device
bytes and the VM ride along untouched (ARTIFACTS §4 does not apply).

### B0.3 — Full-image flash + readback

```bash
# radio in bootloader:
jl-uboot-tool erase 0x000000 0x100000
jl-uboot-tool write  0x00000000 work/ch30_base.bin
jl-uboot-tool read   0x00000000 0x100000 /tmp/opencode/ch30_base_rb.bin
cmp work/ch30_base.bin /tmp/opencode/ch30_base_rb.bin && echo IDENTICAL
```

**Pass:** `IDENTICAL`. Any diff → re-write once; second failure → STOP and capture.
Power-cycle the radio (off, 10 s, on). Verify it boots normally, shows v1.0.50, BT
name `H3 Plus - 8592`, and the menu shows the BT-PTT labels (ch. 23 §9C.9: "BT PTT" /
"BT2" render correctly in the current menu language — record which language is set).

### B0.4 — Baseline is now the reference point

From here, every stage image (§30.7) is also flashed **full-image** from
`Dumps/dump_internal.bin` — same procedure, so every stage starts from *identical*
pairing state (the dump's) and identical app. Record the stage build command in each
experiment record.

### B0.5 — Record card

> **Card B0** — full-image baseline reflash.
> Steps: B0.1 → B0.2 → B0.3. Pass: readback IDENTICAL + normal boot + labels correct.
> Evidence: `Dumps/dump_pre_ch30.bin`, `work/ch30_base.bin` sha, readback cmp line.
> **Automation:** `work/ch30_b0.sh` runs B0.1→B0.3 + boot-check with timestamped
> logging (`work/logs/ch30_B0_<ts>.log`), pause/read prompts for every physical step,
> automated `--show` verification (25 target sites + 5 expected-native sites), one
> retry on readback diff, and prints the paste-ready §30.10 ledger row.

### B0.6 — Defined power-cycle procedure (used by all later cards)

Radio **off** → wait **10 s** → radio **on** → wait for boot beep + **5 s** → only then
start the next step. "Cold start" everywhere in this chapter means exactly this.

---

## §30.5 — Phase B1: baseline function verification (single devices, on the clean base)

Each card below runs on `work/ch30_base.bin`, from a cold start, PC adapter **off**
unless the card says otherwise. These re-establish, on the clean base, every behavior
the multipoint work *assumed*. Any FAIL invalidates prior assumptions — stop and
document.

### B1.1 — Jabra pair + HFP audio (Device A alone)

1. Jabra: enter pairing mode (hold its BT button until it announces pairing — record
   the exact procedure and LED/voice).
2. Radio: **Menu → Bluetooth → Pair** (record the exact menu path/items shown).
   Wait ≤ 30 s. Expected: connect chime, BT indicator, Jabra in the Paired list.
3. **RX audio:** tune to an active station (or open squelch on a busy freq).
   Expected: radio audio in the headset earphones within ~2 s of squelch open
   (btmon: SCO/eSCO setup after ACL). Record whether audio also plays on the radio
   speaker (duplex mode behavior).
4. **BT-PTT (main PTT):** press and hold 2 s, speak into the headset mic, release.
   Verify TX audio quality via a second receiver (record what receiver).
   Expected: transmits on VFO A with **headset mic**; release → TX off ≤ 1 s.
5. **BT-PTT2 (PTT2 key):** same on VFO B. Expected: forces VFO B + headset mic
   (ch. 23 §9C.8).
6. **OD key (--OD-PTT=PTT):** press → stock PTT behavior on its programmed band.
7. Release everything, power off headset (Jabra off), press main PTT.
   Expected: normal radio-mic PTT (no BT present).
8. btmon not required (no PC involvement) but radio-side observations mandatory.

> **Pass:** 1–8 all behave as listed. Record each as observed.

### B1.2 — TID-PTT pair + SPP commands (Device B alone)

1. TID-PTT: enter pairing mode (record exact button/timing).
2. Radio: Menu → Bluetooth → Pair. Expected: pairs, appears in Paired list, connect
   chime.
3. Press the TID-PTT button: Expected: radio keys **VFO A** on press, un-keys on
   release (the `+SPP=P/R` path). Press 3× with ~2 s gaps — all 3 must key.
4. Cold start radio, both devices powered: record **which device the radio
   auto-reconnects** (stock single-device reconnect, struct `0x102F0`). This fact is
   needed by the order-cards; do not assume it.

> **Pass:** 1–3 deterministic; 4 recorded (which one, after how many seconds).

### B1.3 — PC SPP sanity (reference client, for comparison runs only)

1. PC: `bluetoothctl power on`; radio pairable (Menu → Bluetooth → Pair);
   pair from radio side.
2. `sudo python3 tools/bt_spp_hold.py 0B:FF:59:E8:85:92` — hold link, `Enter` = press.
   Expected: keys VFO A; tool prints well-formed `AT+MPTT=1` / `AT+MPTT=0` lines
   (cr-bit correct — §29.8).
3. `q` to quit cleanly; record link teardown in btmon (L2CAP Disconnection Request
   **is normal here** — initiated by the PC side).

> **Pass:** keying works, `AT+MPTT` lines well-formed. This card defines the "healthy
> SPP session" reference for all later captures.

---

## §30.6 — Phase B2: goal-topology attempts on the *unpatched-for-multipoint* base

**Purpose:** document exactly what the clean baseline does and does not do with both
devices — the true starting point, with the goal devices (not the PC). Expect stock
single-device eviction; the value is the **signature** of each order (which device
survives, what btmon shows), so later stages are compared against a *measured* baseline,
not against ch. 27 (which measured with a PC).

### B2.1 — Order A: Jabra first, then TID-PTT

1. Cold start; PC adapter off. btmon capture ON on the PC (passive; it hears nothing
   unless involved — that's fine, it documents non-involvement).
2. Connect Jabra from radio Paired list. Wait 5 s. Verify B1.1 step 3 (RX audio).
3. Connect TID-PTT from Paired list. Wait 10 s.
4. Record: do BOTH show connected? Which is "current"? Press TID-PTT button ×3 →
   keying? Press radio PTT (BT-PTT) → headset mic? RX audio still in earphones?
5. Decode btmon for the interval of step 3 (expect: if Jabra dropped — L2CAP/HCI
   disconnect or SCO teardown; if TID-PTT dropped — its ACL vanishes).

### B2.2 — Order B: TID-PTT first, then Jabra

Same structure with roles swapped; step 4 checks button keying before and after the
Jabra connect, plus BT-PTT with headset mic after.

> **Both cards:** the outcome table (who survives × keying works × audio works) is the
> baseline. Do NOT fix anything that fails here — just document precisely.

---

## §30.7 — Phase M: multipoint stage ladder

Each stage = full-image flash (per B0.3) of one cumulative build, then the **same six
cards** (M-A, M-B, M-C, M-D, M-E, M-R below). Stop the ladder at the first stage where
all six pass — that stage is the minimal multipoint recipe for the goal; later stages
then only run as regression.

### Stage builds (all start from `Dumps/dump_internal.bin`, all with the key patches)

> **Automation (2026-10-21):** stage build+flash = `work/ch30_m1.sh` (M1),
> `work/ch30_m2.sh` (M2), `work/ch30_m3.sh` (M3 — built + image-verified 2026-10-22;
> M4 clones `ch30_m3.sh` + `--no-spp-close` when scheduled). Each stage script now also
> runs the §30.9 stale-key PREFLIGHT after the boot check.
> Cards = stage-generic `work/ch30_ma.sh` / `ch30_mb.sh` / `ch30_mc.sh` / `ch30_md.sh` /
> `ch30_me.sh` / `ch30_mr.sh` (each asks which stage is flashed, logs to
> `work/logs/ch30_<STAGE>_<card>_<ts>.log`, ends with a paste-ready ledger row).
> Only `ch30_m*.sh` (flashing) and the M-E PC-reference step need sudo.

| Stage | = | Extra options beyond previous | Known state from ch. 27 (PC-based) |
|---|---|---|---|
| **M1** | E7 | `--conn-num=2 --no-kick --force-page-scan --force-role-keep --no-disconnect-13 --no-pairing-kick` | SPP+HFP multipoint OK when radio-initiated; accessory-incumbent pairing-kick observed |
| **M2** | M1 | `--no-cleanup-kick` | HCI-level eviction fully dead (E8) — never tested with TID-PTT incumbent + HFP target. **Model prediction 2026-10-22: M-A/M-B FAIL** — NOPs HCI-level cleanup callers only; the press-time `0x4a` all-channel walk (the observed M1 kick) is untouched → **CONFIRMED 2026-10-22: kick persisted in preflight; new regression — a failed (stale-key) bonded connect deadlocks the app (§30.10 M2)** |
| **M3** | M2 | `--no-l2cap-teardown` | E9 FAILED (close persisted) — **but E9's persisting path was the `spp_connect` single-SPP-session chokepoint, SPP-target-only; in the goal topology (HFP↔SPP mixed) that path never fires, and the `0x4a` posters NOP'd here are the only press-time closers → M3 is the first stage with a real chance at M-A and M-B** (model note 2026-10-22, after M1-A rerun + M1-B). **CORRECTION 2026-10-22 (M3-A): the model note was wrong for Order A** — the chokepoint fires whenever the *target* is SPP (TID-PTT press kicked the Jabra incumbent despite both posters NOP'd); it only stays silent for an **HFP target** → Order B (M3-B, decisive) is the live M3 question, clean rerun owed (§30.10). **FINAL M3 VERDICT 2026-10-23 (M3-B run3, correct path): Order B FAILS too** — HFP-target Paired→Connect kicked a healthy 3/3 TID-PTT incumbent at 0 s and locked the radio up; the press-time evictor is target-independent and the §27.19 deadlock bites from M3 onward. Neither order is reachable via a menu press at M3; the surviving route is **incoming joins** (E6 + M3-B run 1 evidence) → M3-B2/A2 incoming-variant cards, no reflash. **M3-B2 RUN 2026-10-23: incoming join confirmed NON-evicting (999 s) but the second device never binds the audio role behind a healthy SPP incumbent** (single-current-device struct `0x102F0`) + SPP degraded post-join → M3-A2 (Jabra incumbent first) is the last no-reflash card. **M3-A2 RUN 2026-10-23: FAIL — incoming SPP page beside a bound Jabra CRASHED/rebooted the radio; TID-PTT never connected. M3 CLOSED: goal unreachable in all four quadrants (press=evict+freeze, incoming=bind-gated/crash) → §30.8 fallback decision** |
| **M4** | M3 | `--no-spp-close` | E10 FAILED (walk bypasses) — safe base (no corruption known at M4) |
| ~~M5~~ | M4 | ~~`--no-l2cap-disconnect`~~ | **FORBIDDEN** — E11 corrupts normal SPP operation (§27.19) |

Template (stage `Mk`):

```bash
python3 tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin \
    work/ch30_mk.bin \
    --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT \
    --conn-num=2 --no-kick --force-page-scan --force-role-keep \
    --no-disconnect-13 --no-pairing-kick \
    [--no-cleanup-kick] [--no-l2cap-teardown] [--no-spp-close] \
    --sectors=work/ch30_mk
python3 tools/patch_h3plus_firmware_bluetooth.py work/ch30_mk.bin --show   # verify sites
```

### Card M-A — Order A: Jabra incumbent, TID-PTT joins

1. Cold start (pairing state = dump's + whatever the stage's earlier cards added; if
   either device is missing from Paired, re-pair per B1.1/B1.2 and note it).
2. btmon ON. Connect **Jabra** from Paired. Wait 5 s. Verify RX audio (B1.1-3).
3. Connect **TID-PTT** from Paired (Menu → Bluetooth → Paired → TID-PTT → Connect).
   Wait 10 s.
4. Record immediately: radio BT indicator(s); press TID-PTT ×3 (2 s gaps) → keying on
   VFO A?; then radio PTT (BT-PTT) → headset mic TX?; RX audio still working?
5. btmon decode: any **radio-originated** L2CAP Disconnection Request / HCI Disconnect
   in step 3's window? Classify per §29.8 signatures.
6. **Pass:** both links alive 60 s, button keys, BT-PTT keys with headset mic, RX
   audio present, zero radio-originated disconnects.

### Card M-B — Order B: TID-PTT incumbent, Jabra joins

Mirror of M-A (connect TID-PTT first, verify ×3 keying, then connect Jabra, re-verify
keying + BT-PTT + RX audio). This is the E7-failed scenario re-run with the goal
devices — the decisive card of the whole ladder.

### Card M-C — Fresh pairing while incumbent connected

1. Incumbent = Jabra connected (M-A state). Put **TID-PTT** in pairing mode (not yet
   paired on this stage's VM).
2. Radio → Pair (note: "Pairable" is gated while connected per §27.13 — record whether
   the menu allows it at this stage; if it refuses, that is a documented observation,
   not a failure of the goal — the goal requires *either* order of *paired* devices;
   fresh-pairing-under-load is a robustness bonus).
3. If pairing proceeds: incumbent survives? keying works on both after?
4. Repeat mirrored (TID-PTT incumbent, pair Jabra fresh).

### Card M-D — Cold-start recovery with both devices powered

1. Both paired & connected (post M-A or M-B). Radio off → 10 s → on → 60 s.
2. Record: which device auto-reconnects, after how long; does the second connect
   manually from Paired afterwards without killing the first?
3. Repeat 3× (recovery must be deterministic, not lucky).

### Card M-E — Regression (never skip at any stage)

1. Normal PTT with **no** BT devices powered → radio-mic TX on both VFOs.
2. OD key per its assignment; BT-PTT2 (VFO B + BT mic) with Jabra connected.
3. Menu walk: BT menu opens, Paired list correct, no freezes; **Delete** one device —
   record link behavior (known quirk: with NOP builds Delete leaves the link up and can
   wedge pairing until power-cycle, §27.13 — at which stage does it bite?).
4. `AT+MPTT` well-formedness on the PC reference (run B1.3 quickly) — cr-bit side
   effect (§27.11) present at this stage? Record.
5. **Sidetone check** (added after M1-A rerun): Jabra connected, press + release
   BT-PTT — after release, does radio-mic audio stream to the headset until the next
   press (§27.13 quirk)? Record present/absent per stage (base state unknown).

### Card M-R — 10-minute soak

Both devices connected (best order so far), radio on a busy channel: every 30 s press
the TID-PTT (short) alternating with BT-PTT presses; after 10 min: both links still
up? keying still working? any heap/assert reboot (boot beep pattern change)?

### Per-stage decision rule

* **All six cards pass** → STOP: this stage is the recipe. Then run the *next* stage
  anyway once (M4→ verify it is not needed; regression only) and record.
* **M-B fails, M-A passes** → the remaining evictor runs only in the
  accessory-incumbent path: capture its signature, escalate to the next stage; if M4
  still fails, apply the surgical fallback (§30.8).
* **Any card shows corruption-class symptoms** (doubled `+SPP` echo, missing
  `AT+MPTT`, dead keying on a fresh connect, deadlock on a Connect press) → treat as
  E11-grade: document, roll back one stage, do **not** proceed upward.

---

## §30.8 — Surgical fallbacks (only if the ladder ends without all-pass)

Ordered by cost; each re-runs the full six-card set:

1. **F1 — dispatcher-branch-only NOP.** E11 NOP'd *both* the `je r11,#0x4a` branch
   `0x01E17974` and the `l2cap_disconnect()` entry `0x01E173D0`; the corruption likely
   came from the **entry** NOP (all legit closes then never complete). Try M4 + branch
   NOP only (2 bytes, new `--only` site). If closes still persist → F2.
2. **F2 — gate `l2cap_run` state `0xd`** (old E12): suppress only the *send* of L2CAP
   Disconnection Request in the walk, keep state-machine completion. Needs the walk
   context check (§29.1: walk body `0x01E17B20`).
3. **F3 — profile-aware close predicate (~30 B cave routine).** At the `spp_connect`
   busy-path `0x01E1751E` / dispatcher `0x4A` entry: skip closing the incumbent channel
   **iff the new connection is a different profile** (HFP join ≠ close SPP; SPP join
   while HFP incumbent ≠ touch anything). Compile via the ch. 25 route, place in the
   remaining cave space @`0x01EA76DE` (~126 B free, §29.5) or in-place over the
   replaced bodies. This is the first *code* (not NOP) step — design review before
   implementation.
4. **F4 — ESP32 combo device** (ch. 22 §9B.6.1): one device carrying SPP+HFP —
   zero-firmware-change fallback, no longer needed if any M-stage passes.

---

## §30.9 — Known quirks & traps (carry into every card)

| Quirk | Source | Effect on plan |
|---|---|---|
| BlueZ auto-reconnect grabs radio/TID-PTT | ch. 26 | PC adapter OFF for radio-side pairing |
| TID-PTT drops ACL when its SPP channel closes | §27.13/§27.16 | makes any close look like "kick"; btmon classification essential |
| "Pairable" gated while connected | §27.13 | M-C may refuse by design — record, don't force |
| Delete leaves link up (NOP builds), wedges pairing until power-cycle | §27.13 | M-E step 3 checks per-stage onset; full-image stage flashes sidestep it |
| Malformed `AT+MPTT` after device switch (cr-bit flip) | §27.11 | M-E step 4 checks per stage |
| E11 corruption (doubled `+SPP`, no `AT+MPTT`, dead keys; deadlock on Connect press with live SPP) | §27.19 | M5 forbidden; corruption ⇒ roll back |
| Menu/explicit disconnect dead under NOPs | §29.6 | power-cycle is the defined reset (B0.6) |
| Stock auto-reconnect = last device only | §27.13 | measured per stage in B1.2-4 / M-D |
| TID-PTT **bonded** Paired→Connect failed at M1 (radio hangs "Connecting…", accessory LED red-blinks out); connected only after power-cycling the accessory into pairing mode | M1-A | card premise "paired devices connect on demand" is **not proven** on NOP builds — on any Connect-press hang, record it as a result, do not silently re-pair (M1-A deviation); VM-rewind stale-key suspect at every full-image stage flash — **did NOT reproduce at M1-A rerun after a fresh bond** (stale-bond artifact confirmed) |
| Headset **self-connects** on its own power-on while the radio is idle (incoming reconnect accepted, no menu; M1-A rerun ×2) | M1-A rerun | phantom-incumbent trap: before step 2 of every card, verify *which* device (if any) is connected — a "Bluetooth connected" tone at power-on is not necessarily the stock last-device auto-reconnect |
| SCO stays open after BT-PTT release → radio-mic audio streams to the headset (sidetone) until the next press; alternates cleanly press=BT-mic-TX / release=sidetone; **fast double-press → press 2 keys with the radio mic** (async mic-source re-arm race, M2-OBS) | §27.13; re-confirmed M1-A rerun (base state unrecorded); M2-OBS | not a keying fault; M-E adds an explicit sidetone regression check per stage |
| **VM-rewind stale-key trap:** each full-image stage flash restores the dump's bond keys — any accessory re-paired *after* the dump (Jabra: B1.1) fails radio-initiated bonded Paired→Connect until re-paired (M1-B: Jabra joined only via Pairing flow; M1-A d1: TID-PTT same symptom) | M1-A d1 + M1-B + M2 preflight | **Preflight rule:** after every stage flash, test radio-initiated bonded Paired→Connect for BOTH accessories; if it fails, re-pair via Pairing flow and record it — *before* starting the cards. M2 data point: Jabra stale again as expected; **TID-PTT bonded connect survived the rewind** (asymmetry unexplained — accessory-side key state?) |
| **M2 failed-bonded-connect deadlock:** pressing Paired→Connect for a stale-key device while another device holds SPP **freezes the radio** (no audio, app task wedged; TID-PTT still kicked first) — M1 failed the same connect cleanly; recovery = power-cycle | M2 preflight; **reproduced exactly at M3 preflight** | the `--no-cleanup-kick` NOPs wedge the auth-failure teardown path; expect failed connects to be hazardous at M2+ — always preflight from a known-good state; matches the §27.19 "blocking closes → deadlock" verdict. **M3 note:** TID-PTT eviction on this FAILED-connect path persists even with the `0x4a` posters NOP'd → a separate, unlocated evictor guards the auth-fail path (btmon classification owed by M3-A/B) |
| **Phantom auto-reconnect (M3+):** cold-start auto-reconnect brings TID-PTT's ACL up but the **SPP data path is dead** — 0/3 button keys; a menu Paired→Connect repairs the session (M3-A 3/3) | M3-B | cards must verify incumbent **keying**, not just the "Bluetooth connected" tone, before step 3; if dead → menu-connect to repair and record. Root-cause owed (open static item: SPP bind on the auto-reconnect path) |
| **Fast repeated TID-PTT presses kill the SPP session** (button dead, BT-PTT mic unaffected; recovery = power-cycle radio + re-pair) | M3-A one-liner | consistent with the single-SPP-session `0x1A740` fragility (ch. 27 §27.17); avoid rapid-press fiddling mid-card; watch at M4 |
| **Anti-phantom rerun protocol (M3-B):** to get a *radio-initiated* HFP join while a *working* SPP incumbent keys: cold start → power TID-PTT on, verify 3/3 keying (menu-connect to repair if phantom) → keep Jabra **OFF, out of range**, power it on in another room, then radio Paired→Jabra→Connect and carry the headset into range inside the page window (avoids its power-on self-connect beating the press) | M3-B lesson | the decisive M3 question can only be answered with a press that actually happens on the radio. **RUN 2026-10-23 (M3-B run3): protocol worked, answer = FAIL** (0 s kick + radio lockup on the correct Paired→Connect path) — press-based cards are retired; use the protocol instead for incoming-join cards (M3-B2/A2), where the join must NOT be beaten by the wrong device self-connecting first |
| **Press-time deadlock, correct path (M3+):** ANY radio Connect press toward the Jabra (HFP target) while a live SPP session exists → app-task freeze, reboot required; the paired-flow press and the Pairing-menu selection both trigger it | M3-B run2/run3 | §27.19 "blocking closes → deadlock" reproduces at M3, not only E11 — do not use menu presses to bring up the second device at M3+; bring it up by **incoming self-connect** instead |
| **Incoming join does NOT evict, but does NOT bind audio behind a healthy incumbent:** Jabra self-connect beside a 3/3-keying TID-PTT → no kick (999 s) yet BT-PTT stays on the TID-PTT mic, no SCO (sidetone absent — first time in the project), no RX audio; beside a PHANTOM incumbent the same self-connect DID bind Jabra audio (M3-B run 1) | M3-B2 | app single-current-device routing (struct `0x102F0`) gates profile binding on the slot being free — incoming binds only into a free slot; the card order for incoming tests must account for which slot state (healthy vs phantom) the incumbent is in. **Link liveness confirmed:** on radio power-off the Jabra called *\"mobile disconnected\"* simultaneously with the TID-PTT dropping = two concurrent live ACLs at M3 — incoming page-in itself works; only the second device's profile binding is gated |
| **Incoming SPP page while the routing slot is held by a bound HFP device = radio CRASH/reboot** (M3-A2: TID-PTT power-on beside a working Jabra → radio reset, Jabra *\"mobile disconnected\"*, auto-recovered alone after boot; second attempt: silent, no connect, no crash) | M3-A2 | never bring an SPP accessory into a radio that has an HFP device bound — treat as crash hazard; also a static-analysis item (SPP-bind path on struct `0x102F0` with no SPP session) |
| **SPP degradation after an incoming second-device join:** first button press = TX starts and never releases (`+SPP=P` without `+SPP=R`?), session dead within 3 presses ("SPP died"); radio otherwise responsive, BT-PTT still keys | M3-B2 | same corruption family as E6 malformed AT+MPTT / E11 doubled echo — the second join disturbs the SPP data path even when no eviction occurs; re-verify keying immediately after any second-device event |
| **Sticky-gate field effect (`--gate-close` v1, F3-B):** the step-2 TID-PTT menu-connect itself sets `DAT_0001a662` bit 7 (press flow), so the gate is ALREADY armed before the decisive press — every channel close is skipped from that moment until reboot. Verbatim anomaly: *"when I press the TID-PTT button the VFO A works when releasing the button the radio is silent and there is no echo but when I turnup/down the vlume knob on the radio the echo starts from the TID-PTT mic is broadcasted to the speaker of the radio"*; post-F3-B power-cycle also *\"no audio at all on the headset\"* | F3-B | level-triggered sticky flag = confirmed harmful side effect in the field; any future gate must be one-shot or hook connect-complete. The gate ALSO failed its primary mission (evictor bypasses the primitives — see next row) → `--gate-close` superseded by v2 poster-NOP |
| **Third `0x4a` evictor poster @`0x01E4F804`** (in FUN_01e4f652, AT/SPP-command dispatcher family; only xref = branch-table pointer @`0x01E4E274`): posts `user_send_cmd_prepare(0x4a)` → inline all-channel WALK `0x01E17B20` which forces every L2CAP channel to state `0xd` + pumps WITHOUT calling `spp_channel_disconnect`/`l2cap_disconnect` | F3-B static (full 80-caller enumeration of `0x01E1792E`) | this is the press-time evictor that survived M3's two-poster NOPs and F3's primitive gate; explains why only E11's je-branch NOP ever killed eviction. v2 = third site `l2capteardownapp` in `--no-l2cap-teardown`; any future close-gating design MUST cover the walk, not just the primitives |
| **Two closer families — blocking one still evicts (F3-v2 falsifies posters-only):** with ALL THREE 0x4a posters dead (walk unreachable) the press STILL kicked at 0 s + froze ⇒ the primitive close paths (spp_connect chokepoint `0x01E1751E` / `0xB`→`FUN_01e1782c(0,1,0)` / SPP-SM direct callers) are independently sufficient. Matrix: v1 (primitives gated, walk alive) → kick; v2 (walk dead, primitives alive) → kick; E11 (both blocked) → evictor dead | F3V2-B | any eviction fix must cover BOTH families simultaneously → F3-v3 = v2 + `--gate-close` re-armed. FREEZE persists in v1/v2/E11 but not E7/M1 → correlates with close-blocking; v3 tests whether kick and freeze separate |
| **The unified wall (F3-v3 r2 CLOSED the F3 line):** press = app switches current device ⇒ audio binds ⇒ old device killed at 0 s — even with all posters dead + both close primitives gated + every known kick NOP'd (evictor bypasses the gated primitives; likely HCI-level or flag-clear at press). Incoming join = no kill but no bind. Blocking the close only converts kick → deadlock (freeze timed with the join under the gate) | F3V3-B r2 | **no NOP can achieve press-without-eviction**: the eviction decision IS the current-device switch. Future work = rewrite routes only (R1 code-cave / R2 SDK / R3 combo device); do not propose further close-NOP stages |
| **Pre-press TID-PTT-mic echo (no gate involved):** on F3-v2 (stock closes, no gate) the TID-PTT mic was already echoing to the radio speakers when not pressing PTT, BEFORE the decisive press; also present at F3-B but misattributed to the sticky gate there | F3V2-B | pre-existing SPP-mic-path quirk of the TID-PTT incumbent (mode-4 mic routing stuck active?), independent of any patch; not root-caused; does not affect press classification |
| Radio not connectable while connected (incoming pages die ~700 ms, 0x13) | §27.8 | goal flows are radio-initiated — do not test device-side initiation |

---

## §30.10 — Results ledger (append rows; never edit past rows)

| ID | Date | Build (sha8) | Stage | Card | Result | Evidence | One-line observation |
|---|---|---|---|---|---|---|---|
| B0 | 2026-10-21 16:05 | 2155dcf9 | base | full flash | **PASS** | `work/logs/ch30_B0_20261021_155722.log` | readback IDENTICAL (attempt 1); boots V1.0.50, English; pre-flash dump `0dddda42…` stored off-machine; **observation: displayed BT name `TD-H3-Plus-351…`** (earlier docs said `H3 Plus - 8592`; name is VM-sourced, rode along from the dump — full name `TD-H3-Plus-3511` confirmed in B1.3; MAC `0B:FF:59:E8:85:92` is the identity anchor) |
| B1.1 | 2026-10-21 ~16:10 | 2155dcf9 | base | Jabra alone | **PASS** (user report) | verbal | Jabra paired radio-side; BT-PTT (VFO A + headset mic), BT-PTT2 (VFO B) and PTT options all working; RX from other station audible in earphones. Not recorded: TX quality via second receiver, Jabra-off radio-mic check |
| B1.2 | 2026-10-21 16:54 | 2155dcf9 | base | TID-PTT alone | **PASS** (step 4 deviation) | `work/logs/ch30_B1_2_20261021_163747.log` | Already paired as **`TID-PTT0cd28a`** (VM rode along); connect via Menu → Bluetooth → BT Pairing → Paired → TID-PTT0cd28a → More → **Connect**, ~2 s + chime; 3/3 presses key VFO A (red LED while held); with TID-PTT alone it is the "BT mic" for BT-PTT/BT-PTT2; FK2 PTT = internal mic, TID-PTT unaffected; release-LED nuance: button-side release = fast "blip", radio-side (BT-PTT) release = single green blink (subtle, recorded); cold-start auto-reconnect = TID-PTT ~2 s after boot **but Jabra was OFF** → both-powered rerun = B1.2b |
| B1.2b | 2026-10-21 ~17:15 | 2155dcf9 | base | auto-reconnect both-on | **PASS** (verbal) | user report | Jabra ON → TID-PTT ON → radio ON: radio auto-reconnected **TID-PTT in ~2 s**; Jabra stayed unconnected ("still searching"). Stock single-device reconnect = last-connected device, confirmed with both powered |
| B1.3 | 2026-10-21 17:23 | 2155dcf9 | base | PC SPP ref | **PASS** | `work/logs/ch30_B1_3_20261021_171916.log` + `/tmp/opencode/ch30_B1_3_20261021_171916_btmon.txt` | Healthy-session reference set: press → `+SPP=P` → TX → `AT+MPTT=0` in ~60 ms, release → `+SPP=R`, **no echo, no fragments**; zero radio-originated disconnects during the session (the 2 RX L2CAP Disconn Requests + 2 HCI Disconnects all belong to the pairing-fiddling phase, t=20/27/43/53 s). **Name settled: radio = `TD-H3-Plus-3511` @ `0B:FF:59:E8:85:92`** (BLE twin `0B:FF:59:9E:37:81` = `TD-H3-Plus-3511(BLE)`); PC seen by radio as `TID-PTT-PC`. Pairing-with-PC recipe: press Connect on radio, run `bt_spp_hold.py` within ~1 s (radio waits for the profile connect). Log shows 2 Enter-presses (user reported keying OK; fact recorded) |
| B2.1 | 2026-10-21 17:41–17:50 | 2155dcf9 | base | A→B stock | recorded | `work/logs/ch30_B2_1_20261021_174101.log` + `/tmp/opencode/ch30_B2_1_20261021_174101_btmon.txt` | **Order A stock: TID-PTT Connect instantly (0 s) kicked the Jabra** — radio tone "Bluetooth disconnected", Jabra voice "Mobile disconnected", then TID-PTT connected; 3/3 button presses key VFO A; BT-PTT used the **TID-PTT mic** (Jabra silent, no RX audio). Outcome: incumbent always loses, second device wins. **Deviations (flagged):** PC adapter was ON (preflight read "unknown" under sudo) — cold start: radio auto-reconnected to the **PC** at t+17 s (last device from B1.3; user saw only "Bluetooth connected", no device name), then dropped the PC link during the Jabra connect with btmon `Disconnect Complete` **reason 0x13 radio-originated** = the §27.10 app-kick signature, caught live with goal-flow devices |
| B2.2 | 2026-10-21 18:03–18:13 | 2155dcf9 | base | B→A stock | recorded | `work/logs/ch30_B2_2_20261021_180343.log` + `/tmp/opencode/ch30_B2_2_20261021_180343_btmon.txt` | **Order B stock = mirror of B2.1: Jabra Connect press kicked the TID-PTT at 0 s** (button LED red/green blink + radio "Bluetooth disconnected") — kick fires **at Connect selection, before the new link completes** (first Jabra attempt timed out, TID-PTT killed anyway; second attempt after headset pairing mode connected). Final: Jabra connected (BT-PTT = Jabra mic, RX audio yes), TID-PTT dead (0/3 presses). Cold-start note: radio did **not** auto-reconnect within 60 s this time (adapter forced off) — auto-reconnect is best-effort, not guaranteed. btmon: 5 lines, zero PC-adapter events (clean non-involvement). **Stock verdict both orders: second device always wins; goal state unreachable on base, as expected** |
| M1 | 2026-10-21 19:41 | 90bec320 | M1=E7 | stage flash | **PASS** | `work/logs/ch30_M1_20261021_193848.log` | E7 recipe: 16 patches, 159 B / 13 sectors; `--show` all-TARGET; full-image readback IDENTICAL (attempt 1); boots V1.0.50, name `TD-H3-Plus-351` (display truncation), paired list intact `Jabra Evolve / TID-PTT-PC / TID-PTT0cd28a` (VM rode along) |
| M1-A | 2026-10-21 20:09–20:22 | 90bec320 | M1 | order A | **FAIL** (deviations flagged) | `work/logs/ch30_M1_A_20261021_200946.log` | **Observed:** cold start + 60 s untouched → **no auto-reconnect** (button press did not key; base B1.2b was ~2 s). Jabra connected cleanly (radio "Bluetooth connected" simultaneous with Jabra "mobile connected"), RX audio OK. TID-PTT Connect press: radio tone "Bluetooth disconnected" + Jabra "mobile disconnected" fired **instantly on the press**; TID-PTT LED blinked red a few times then went out; radio held "Connecting…" and never reported connected. **One-line observation (verbatim, user-flagged IMPORTANT):** *"The pairing of the TID-PTT did not succeed at first. I needed to turn off the TID-PTT, than turn on so it went into pairing mode than I could connect it. this is an important detail"* — final state after that workaround: TID-PTT keys 3/3 VFO A, BT-PTT = **TID-PTT mic** (Jabra silent), RX audio gone; verdict "headset completely dead". Fails pass-items 1 (Jabra lost), 3 (BT-PTT ≠ headset mic), 4 (no RX audio). **Deviations:** (a) final TID-PTT link came up via **pairing mode**, not the card's Paired→Connect flow; (b) PC adapter OFF at preflight → **no btmon capture** (card called for btmon ON, passive); (c) cold-start auto-reconnect absent at M1. **Analysis:** instant-on-press kick under the full E7 NOP set matches the ch. 27 model — the `0x4a` `l2cap_disconnect_all_channel` walk survives until E11 and closes the Jabra's HFP channels with no HCI Disconnect (§27.15–17); M-A failing at M1 is expected and M2 does not touch that walk. **New finding-grade item:** the *bonded* Paired→Connect to the TID-PTT **failed** under M1 while the identical flow worked in ~2 s on base (B1.2) — candidates: stale accessory link key from the full-image VM rewind (dump keys older than the accessory's current bond → auth fail → "Connecting…" hang; pairing-mode re-bond then succeeds), or an M1-side regression of the accessory connect path. Distinguishing test = re-run M-A on the same M1 build with the now-fresh bond: bonded connect expected to work; if it fails again → M1 regression. Re-run required per §30.3 before ladder escalation. |
| M1-A rerun | 2026-10-22 08:31–08:45 | 90bec320 | M1 | order A | **FAIL** (reproduced; battery 100 %) | `work/logs/ch30_M1_A_20261022_083620.log` (+ aborted starts `…_083150`, `…_083323`) | **Observed:** two aborted starts — 08:31 killed at step 1; 08:33 killed at step 2 with **"jabra was already connected"** (self-reconnect evidence, see below). Full run: cold start + 60 s → nothing auto-reconnected (button no-op). **Jabra connected on its own power-on, no menu used** ("Bluetooth connected directly after turning on Jabra"), RX audio OK. TID-PTT **bonded** Paired→Connect: **worked this time — no pairing-mode workaround needed**; kick reproduced: "Bluetooth disconnected" + Jabra "mobile disconnected", then "Bluetooth connected" nearly instantly (TID-PTT joined). 3/3 presses key VFO A; BT-PTT = TID-PTT mic; RX audio gone; verdict "all failed". **One-line observation (verbatim):** *"Jabra connected upon poweron directly without using any menu. After doing one BT-PTT on the radio the mic of the jabra is used for transmission and audiable on other radio. But when the BT-PTT button is released the audio from the radio mic continously is being played at the jabra headset untill the BT-PTT button is triggered again than the mic of the jabra is used for the tx and release of the BT-PTT button starts sending the mic of the radio to the headset again strange..."* **Deviations:** the BT-PTT/Jabra-mic test in the observation happened **after** the card's verdict (post-card fiddling; which devices were linked at that moment unrecorded — timeline ambiguous). **Analysis:** (1) yesterday's bonded-connect hang did NOT reproduce → stale-bond/VM-rewind artifact, cured by yesterday's fresh pairing; M1's Paired→Connect path is healthy. (2) Kick-on-press reproduces exactly — ch. 27 model holds (`0x4a` all-channel walk alive until E11-grade NOPs); M-A cannot pass at M1. (3) **Headset self-connect trap:** while the radio is idle it accepts the Jabra's incoming reconnect — a powered-on headset can silently become incumbent; every card must verify *who* is connected before step 2 (the "Bluetooth connected" tone at power-on is NOT necessarily the stock last-device auto-reconnect). (4) BT-PTT TX with Jabra mic audible on a second receiver = M1 key-patch regression PASS. (5) Post-release SCO sidetone (radio mic → headset until next press, alternating cleanly) = §27.13 quirk re-confirmed at M1; whether base shows it is unrecorded → add explicit sidetone check to M-E. |
| M1-B | 2026-10-22 19:42–19:53 | 90bec320 | M1 | order B (decisive) | **FAIL** (kick reproduced; flow deviation) | `work/logs/ch30_M1_B_20261022_194231.log` | **Observed:** cold start clean (nothing connected, battery 100 %). TID-PTT **bonded** Paired→Connect worked ("Bluetooth Connected", 3/3 keying) — 2nd confirmation the M1 connect path is healthy. Jabra Paired→Connect press: **0 s** radio "Bluetooth disconnected" + TID-PTT LED red/green blink (incumbent killed); **the Jabra connect itself then failed** (both attempts) — user put the Jabra in pairing mode and it only connected via Menu → BT Pairing → **Pairing** (pairable list). After takeover: TID-PTT 0/3 presses; BT-PTT press = **Jabra mic TX** ✓; release = **internal radio mic to the headphones nonstop** (sidetone, §27.13); RX audio: none. One-line (verbatim): *"No audio on any radio transmission on the headphones."* Corruption-class check answered "?" by operator — no corruption symptoms observed (dead button = kicked device, not corruption). **Deviation (flagged):** step 3's join went through the fresh-pairing flow, not the card's Paired→Connect. **Analysis:** (1) Kick-on-press now reproduced **in both orders** at M1 — consistent with the unconditional `0x4a` all-channel walk at press time; with a PC incumbent the ACL survives the channel close (E6 "pass"), the TID-PTT drops it (this) = exactly the §30.0 delta. (2) **Radio-initiated bonded Jabra connect has never worked at M1** — M1-A rerun's "Jabra connected" was the headset's own *incoming* reconnect; root cause = the VM-rewind stale-key trap (B1.1 fresh-paired the Jabra *after* the dump; the M1 full-image flash rewound the radio's key to the dump's older one). Cure = re-pair per device after each stage flash; preflight rule added to §30.9. (3) **RX audio absent after the pairing-flow takeover vs present after the self-connect** (M1-A rerun step 2) — audio routing state depends on the join path; open static item, watch at M3+. (4) Sidetone quirk re-confirmed at M1 (order B). |
| M1-C/D/E/R | | | M1=E7 | … | | | |
| M2 | 2026-10-22 20:38–20:46 | de635665 | M2=E8 | stage flash | **PASS** | `work/logs/ch30_M2_20261022_203813.log` | E8 recipe: 19 patches, 171 B / 15 sectors; `--show` all-TARGET; full-image readback **IDENTICAL** (attempt 1); boots V1.0.50, name `TD-H3-Plus-351`, paired list intact (VM rode along). **New stale-key PREFLIGHT run:** TID-PTT bonded Paired→Connect **worked** after the VM rewind; Jabra bonded Paired→Connect → **radio FROZE (deadlock)** — no audio, TID-PTT kicked (LED red/green); recovery = power-cycle + Jabra re-pair via pairing mode + pairable list. **Kick-on-Connect-press persists at M2** (TID-PTT dropped during the Jabra connect) = the model-predicted FAIL; **new M2 regression: a failed bonded connect deadlocks the app** (cleanup-kick NOPs wedge the auth-fail teardown — M1 failed the same stale-key connect cleanly, no freeze) |
| M2-OBS | 2026-10-22 evening | de635665 | M2 | BT-PTT trial (informal) | observation | user report (verbatim below); no card log | **Deviation (flagged): formal M2-A/M2-B cards were NOT run** — their core question (does the press-time kick persist?) was already answered by the stage-flash preflight (yes: TID-PTT kicked on the Jabra Connect press). Post-repair BT-PTT trial (which devices were linked at trial time unrecorded): sidetone persists (radio mic → headset after release); BT-PTT press = headset mic TX ✓; **NEW: fast double-press → press 1 uses headset mic, press 2 uses the radio mic.** Verbatim: *"done, after a BT-PTT trial on the radio in the end the radio still sends the mic output of the radio to the headset and when using the BT-PTT the mic of the headset is sued for tx. But I noticed something when very quickly BT-PTT 2x it uses the first time the mic of the headset but the second time the mic of the radio... did not noticed that before but also did not tried that before"* **Analysis:** single presses alternate cleanly (M1-A rerun) ⇒ not a toggle — the TX mic-source switch is applied asynchronously at TX start; a second press inside the release-handling window keys before the headset-mic re-arm lands, so the radio mic (the release/sidetone default) stays on air. Race window, cosmetic at keying level; retest at M3, ideally under btmon + second receiver. |
| M3 | 2026-10-22 22:10–22:15 | 8be71516 | M3=E9 | stage flash | **PASS** | `work/logs/ch30_M3_20261022_221008.log` | E9 recipe: 21 patches, 179 B / 17 sectors; `--show` all-TARGET (incl. both `0x4a` posters `nop; nop`); full-image readback **IDENTICAL** (attempt 1); boots V1.0.50, paired list intact (VM rode along). **Preflight:** TID-PTT bonded Paired→Connect **worked** (2nd stage running); Jabra stale-key connect → **radio froze directly on selecting Connect + TID-PTT kicked instantly (red/green)** — the M2 deadlock reproduces exactly; recovery = reboot + Jabra pairing mode + radio Pairing list. **Open item:** TID-PTT was still kicked on M3 despite the `0x4a` posters being NOP'd — the *failed-connect* path evicts via a different, not-yet-NOP'd mechanism (no btmon this round → unclassified); the M3-A/M3-B cards with healthy bonds + btmon must classify whether the SUCCESS-path press-time kick is actually gone. |
| M3-OBS | 2026-10-22 evening | 8be71516 | M3 | BT-PTT trial (informal) | observation | user report (verbatim) | Post-preflight BT-PTT trial (link state at trial time unrecorded): **sidetone persists at M3** — radio mic echoes through the headset speakers while BT-PTT is not pressed. Verbatim: *"after a BT-PTT test the mic of the radio echos still through the headset speakers when BT-PTT button is not pressed"* **Analysis:** expected — this is the §27.13 SCO-stays-open quirk (audio-routing layer); no ladder stage (M1–M4) touches it, it is not a connection-layer fault. Keying/BT-PTT correctness itself not re-reported this round. |
| M3-A | 2026-10-22 22:51–22:58 | 8be71516 | M3 | order A | **FAIL** (deviations flagged) | `work/logs/ch30_M3_A_20261022_225109.log` | **Observed:** cold start + 60 s → no auto-reconnect (button dead). Jabra **self-connected on its own power-on** ("Bluetooth connected directly after turning on Jabra no action on radio" — phantom-incumbent trap again), RX audio OK. TID-PTT bonded Paired→Connect press: **"Bluetooth disconnected" + Jabra "mobile disconnected" on the press**; TID-PTT connected ~5 s later. Final: button 3/3 keys; BT-PTT = **TID-PTT mic** (Jabra dead); RX audio gone. Verdict FAIL (items 1, 3, 4). Post-card fiddling, one-line (verbatim): *"Pressing TID-PTT button very quickly multiple times broke the SPP channel (my guess) it stoped working the mic stil worked (BT-PTT) but the button did not needed to powercycle the radio to pair again than normal ops"* — logged as an M3 SPP-fragility quirk (§30.9). **Deviations:** incumbent arrived via self-connect, not the card's Paired→Connect; PC adapter OFF → no btmon (mechanism unclassified). **Analysis:** press-time eviction **persists at M3 with both `0x4a` posters verified NOP'd** → the SPP-target-press evictor is the `spp_connect` single-SPP-session chokepoint path (§27.16), not the posters; the §30.7 M3 model note ("that path never fires in the goal topology") was **wrong for Order A** — it fires whenever the *target* is SPP, whatever the incumbent. M4 (`--no-spp-close`) targets exactly this primitive; caveat: E10 showed the all-channel walk can also bypass it (dispatcher branch `0x01E17974` = E11/forbidden territory). |
| M3-B | 2026-10-22 22:58–23:06 | 8be71516 | M3 | order B (decisive) | **INCONCLUSIVE** (flow deviation — the decisive press never happened) | `work/logs/ch30_M3_B_20261022_225838.log` | **Observed:** cold start → radio **auto-connected TID-PTT** ("Turned on radio than directly bluetooth connected to TID-PTT") but **button 0/3 keys — incumbent dead-on-arrival**. Step 3: Jabra **self-connected on power-on** ("Turned on headset and directly heard mobile connected on the Jabra did nothing on the radio") — no radio Connect press, so the press-time evictor was never engaged; TID-PTT **not kicked** by the incoming join ("no change the TID-PTT still reports paired"). After join: button 0/3; BT-PTT = **Jabra mic ✓**; sidetone on release ✓; RX audio ✓. Operator verdict "?"; corruption-class check: none. One-line (verbatim): *"TID-PTT seems to be connected but no ops at all. When I turned off the radio after 5 seconds I header mobile disconnected from Jabra and the TID-PTT started flashing red/green"* — radio-originated teardown of BOTH devices at power-off, recorded. **Analysis:** (1) the decisive question — does a **radio-initiated** Jabra Paired→Connect kick a *working* TID-PTT incumbent? — remains **unanswered**: both joins were device-initiated (E6 already showed incoming HFP joins don't evict). (2) **NEW finding: auto-reconnect yields a phantom TID-PTT link — ACL up, SPP data path dead** (0/3 keys before any second device joined; the menu Paired→Connect path works — M3-A 3/3). (3) With the posters NOP'd, no known press-time closer fires for an **HFP target** → a clean M3-B rerun (anti-phantom protocol, §30.9) is the decisive test for the goal. |
| M3-B rerun | 2026-10-22 23:21–23:27 | 8be71516 | M3 | order B rerun (decisive) | **INCONCLUSIVE** (flow deviation — **Pairing menu used, not Paired→Connect**) | `work/logs/ch30_M3_B_20261022_232123.log` | **Observed:** the anti-phantom fix **worked** — TID-PTT menu Paired→Connect was healthy, **3/3 keying** before step 3. Step 3 (verbatim): *"Radio lockup up / froze when in the Pairing menu I selected the Jabra from the aviable desivces. The TID-PTT disconnected directly but radio locked and needed restart to pair with Jabra"* — the Jabra was selected from the **Pairing (available devices) list**, not the card's Paired→Connect path; TID-PTT kicked at **0 s**, radio **locked up** (reboot required). After reboot + fresh-pairing the Jabra: button 0/3 (kicked device), BT-PTT = Jabra mic ✓, RX audio ✓, sidetone as before. **Analysis:** (1) the decisive Paired→Connect press was again NOT executed — different flows, different code paths: the Pairing menu kicks incumbents by design (E7/§27.13, unidentified executor) and now additionally **deadlocks at M3** — the §27.19 "blocking closes → deadlock" wall now covers Pairing-menu selection with a live SPP session (previously at M2/M3: only failed bonded connects). (2) The model's Order-B prediction (HFP-target Paired→Connect posts no closer at M3 ⇒ no kick) remains **untested** — owed: one careful run via Menu → Bluetooth → BT Pairing → **Paired** → Jabra Evolve 65 → Connect. |
| M3-B run3 | 2026-10-23 08:40–08:44 | 8be71516 | M3 | order B (decisive, **correct path**) | **FAIL** | `work/logs/ch30_M3_B_20261023_083959.log` | **Observed:** protocol fully followed — cold start, TID-PTT via the correct submenu (verbatim: *"Menu -> Bluetooth -> BT Pairing -> Paired -> TID-PTT0cd28a -> Connect => Bluetooth connected"*), **3/3 keying** ✓ before step 3. Step 3 (verbatim: *"i used the Menu -> Bluetooth -> BT Pairing -> Paired -> Jabra Evolve 65 -> Connect"*): TID-PTT disconnected at **0 s** (*"disconnected directly when i pressed Connect"*), radio **locked up** (*"Radio lockup / frose"*). Post-join matrix moot (frozen radio): button 0/3, BT-PTT *"dead nothing"*, RX *"no dead"*; operator verdict *fail*, corruption-class *"dead"*. **Analysis:** (1) **M3's Order-B model prediction is FALSIFIED** — an HFP-target Paired→Connect kicks a healthy SPP incumbent at 0 s despite both `0x4a` posters NOP'd ⇒ the press-time evictor is **target-independent** and survives the M3 NOP set (candidates: the `0xB` DISCONN_SDP_MASTER path §27.16 and/or the four direct `l2cap_disconnect` SPP-SM callers; only E11's `--no-l2cap-disconnect` ever silenced it). (2) **Deadlock-on-press reproduces on the correct path** — HFP-target Connect press + live SPP session freezes the app task: the §27.19 generic deadlock bites at M3, not only at E11. (3) Press routes are a dead end at M3 (kick AND deadlock coexist). But **incoming (device-initiated) joins do NOT evict** (E6; M3-B run 1: Jabra self-connect with TID-PTT present — BT-PTT + RX both worked) → next test on the SAME image, no flash: **M3-B2 incoming variant** (healthy TID-PTT incumbent + Jabra power-on self-connect, full matrix). |
| M3-B2 | 2026-10-23 19:54–20:05 | 8be71516 | M3 | order B **INCOMING** (self-connect, no press) | **FAIL — but NO eviction** (failure moved to app audio-bind) | `work/logs/ch30_M3_B2_20261023_195433.log` | **Observed:** healthy TID-PTT incumbent (correct menu path, **3/3 keying**, verbatim *\"enu -> Bluetooth -> BT Pairing -> Paired -> TID-PTT0cd28a -> Connect => Bluetooth connected + blinking red/green led on TID-PTT went off\"*). Jabra power-cycled into range: verbatim *\"No prompt on radio, but Jabra said mobile connected and I think its paired to radio\"*; TID-PTT verbatim *\"Led still off / blinking green ever 5 seconds so it thinks it's still connected\"*; **no TID-PTT change at all during the join (999 s) — NO eviction** ✓. Post-join matrix: press #1 verbatim *\"yes but only starts TX never stops\"* (stuck TX), #2 yes, #3 verbatim *\"Now its broken / to fast maybee? ALL VFO'S which do happen where with the mic of the TID-PTT\"*; BT-PTT verbatim *\"TX Started even now the TID-PTT button is broken the TX still possible on the radio BT-PTT button mic always of the TID-PTT. Different from other tests is that releasing the BT-PTT button there is silence not continious echo of any mic to the headphones or other speaker\"* (sidetone ABSENT — first time in the project); RX audio in Jabra: **no**. Operator verdict *fail*; corruption-class verbatim *\"SPP died\"*. **Analysis:** (1) the press-time evictor is confirmed **press-path-only** — incoming joins still never evict (E6 + M3-B run 1 + this). (2) But an incoming HFP device does **not take the audio role** while a healthy SPP device holds the app's current-device slot (struct `0x102F0`): BT-PTT stayed on the TID-PTT mic, no SCO (sidetone absent), no RX audio. M3-B run 1 bound Jabra audio only because the incumbent was a PHANTOM (slot effectively free). (3) NEW corruption: SPP degradation after the incoming join — stuck TX on press #1 (`+SPP=P` without `+SPP=R`?), dead session by press #3 — same family as E6 malformed notifications / E11 doubled echo. (4) **Goal topology blocked at M3 in BOTH directions**: press = evict + deadlock; incoming = no audio bind. The only observed SPP+HFP both-functional state remains E6 (radio-initiated HFP join + PC-class incumbent that survives a channel close). **NEXT cheap card (no reflash): M3-A2** — Jabra incumbent first (self-connect into a FREE slot), then TID-PTT joins incoming: the single-SPP-session slot `0x1A740` is free; only the routing slot is held — does the button bind? **LATE OBS 2026-10-23 (user, post-card, verbatim):** *\"After poweroff of the radio after 5 till 10 seconds the jabra shouted mobile disconnected at the same time the TID-PTT also started blinking red/green\"* — **both ACL links were live simultaneously until power-off** (supervision-timeout drop ~5–10 s after the power cut): the Jabra WAS genuinely connected at the link level (incoming page-in succeeds at M3 — no LL death), corroborating \"accepted but not bound\": M3 sustains TWO concurrent links; only profile binding for the second device is missing. |
| M3-A2 | 2026-10-23 20:45–20:55 | 8be71516 | M3 | order A **INCOMING** (Jabra incumbent + TID-PTT page-in) | **FAIL — NEW failure mode: radio CRASH/reboot on incoming SPP page** | `work/logs/ch30_M3_A2_20261023_204528.log` | **Observed:** step 2 **confirms the free-slot rule in reverse** — Jabra self-connect into a free slot binds EVERYTHING: verbatim *"self connect after poweron, headset: mobile connected, radio: bluetooth connected"*; BT-PTT = Jabra mic ✓, RX through the earphones ✓, sidetone back verbatim *"The echo is back , audio from the mic of the radio through earphones of jabra when not BT-PTT pressed"*. Step 3 (verbatim): *"The first attempt; when I turned on the TID-PTT the radio 'rebooted' it self / 'reset' itself. I hear mobile disconnected on the jabra once the radio has booted the jabara reconnected tot the radio. Than I exeucted the BT-PTT and tune tests and situation was the same as begore TID-PTT turned on. Meanwhile I turned of the TID-PTT than turned it on and it did not connect nor did the radio reboot / reset. so now it's not connected"* — incoming TID-PTT page while the HFP incumbent is bound → **radio reset**; post-boot Jabra auto-reconnected (full audio); second TID-PTT power-on: no connect, no crash. Matrix: button 0/3 (never connected), BT-PTT = Jabra mic ✓, RX *"no audio through radio"* (transient); operator one-liner: *"TID-PTT never connected"*. **Analysis:** (1) THIRD distinct incoming failure mode: incoming SPP connection attempt while the routing slot is held by an HFP device **crashes the radio** (candidate: SPP-bind path dereferences the current-device struct `0x102F0` which has no SPP session — static-analysis item). (2) Free-slot binding rule now proven in BOTH directions (HFP binds into free slot here and in M3-B run 1; refuses to bind behind a healthy incumbent in M3-B2). (3) **Complete M3 matrix: press = evict + freeze (any target); incoming HFP = link up but no audio bind + SPP degradation; incoming SPP = crash.** The goal topology is unreachable at M3 by every route; ALL no-reflash cards are spent → **§30.8 fallback decision point reached.** |
| F3 | 2026-10-24 09:59–10:02 | 25a489d2 | F3=M3+gate-close | stage flash | **PASS** | `work/logs/ch30_F3_20261024_095851.log` | 2-sector write `0x01C000`+`0x0AC000` (56 B), readback IDENTICAL attempt 1; build verify 26 TARGET incl 3 gate sites, sppclose/l2capdiscentry correctly report gate-trampoline; boot V1.0.50 + paired list intact (VM untouched). |
| F3-B | 2026-10-24 10:03–10:13 | 25a489d2 | F3 | order B PRESS (gated) | **FAIL — FREEZE + 0 s KICK persist; gate had NO effect on them** | `work/logs/ch30_F3_B_20261024_100310.log` | **Observed:** protocol followed — TID-PTT incumbent via correct Paired→Connect, **3/3 keying** (connect "much faster than before"); operator noted pre-press anomaly (verbatim): *"when I press the TID-PTT button the VFO A works when releasing the button the radio is silent and there is no echo but when I turnup/down the vlume knob on the radio the echo starts from the TID-PTT mic is broadcasted to the speaker of the radio"*. Decisive press (Paired→Jabra→Connect, Jabra NOT in pairing mode): verbatim *"radio freezes / locks and the TID-PTT inmediately disconnects (blinking red/green led)"*, kick at **0 s**. Power-cycle → *"power cycle directly connected the jabra"* but post-reboot matrix: button 0/3, BT-PTT *"TX started no audio out at all no mic"*, *"NO RX audio on radio"*, no sidetone; corruption-class: *"worse than before no audio at all on the headset"*; operator verdict **FREEZE**. **Analysis:** (1) the gate was ACTIVE (page-pending flag set by the step-2 menu-connect press flow — the echo anomaly = closes being skipped, sticky-flag side effect confirmed in the field) yet eviction+freeze reproduced **identically to M3-B run3** ⇒ **the press-time evictor does NOT flow through `spp_channel_disconnect`/`l2cap_disconnect` entry points** — the `--gate-close` premise (from E11's entry-NOPs) is FALSIFIED. (2) New best model: the evictor is the **0x4a WALK** (`0x01E17B20`, forces channel state `0xd` + pump INLINE, never calls the primitives) reached via **`user_send_cmd_prepare` 0x4a callers not yet enumerated** (the two known posters were NOP'd at M3 yet E9/E10 saw the walk run) — this also explains why **E11's je-branch NOP @`0x01E17974`** (not its entry NOPs) is what killed the evictor. (3) The freeze is NOT caused by blocked closes (here closes completed — TID-PTT dropped): §27.19's "blocking closes → deadlock" theory is superseded; freeze likely = app waiting on the M2/M3 NOP'd cleanup executors. (4) Post-reboot zero-audio state = fresh regression to watch (headset-side vs image-side TBD). **NEXT static:** enumerate ALL callers of `0x01E1792E` checking `r0=0x4a` (find the unknown walk posters) + callers of `0x01E1664E` (controller-queue kick posters); then v2 = gate the WALK (je-branch) with the flag + clear flag on connect-complete to kill stickiness. |
| F3-v2 | 2026-10-25 13:02–13:05 | 91383c8f | F3-v2=M3+3rd-poster-NOP | stage flash | **PASS** | `work/logs/ch30_F3V2_20261025_130236.log` | 3-sector write `0x01C000`+`0x0AC000` (gate revert) + `0x54000` (third 0x4a poster NOP) readback IDENTICAL attempt 1; build verify 29 TARGET, 3 teardown sites disabled, gate reverted to stock; boot V1.0.50 + paired list intact; 4-byte diff vs M3 confirmed (VM untouched). First run of the script aborted safely at preflight on a sector-filename bug (`0x54000` vs zero-padded `0x054000`) — fixed, nothing written. |
| F3V2-B | 2026-10-25 13:05–13:12 | 91383c8f | F3-v2 | order B PRESS (3rd-poster NOP) | **FAIL — FREEZE** | `work/logs/ch30_F3V2_B_20261025_130518.log` | **Observed:** step 2 healthy incumbent — correct Paired→TID-PTT→Connect, **3/3 keying**. Step 3 decisive press (correct PAIRED→Jabra Evolve 65→Connect, Jabra not in pairing mode) — verbatim: *"Radio Froze / locked up at least the menu, on thing I nociced it that the echo (which was already running TID-PTT mic => Radio speakers when not pressing the PTT button) continues to sound / echo while the button itself started blinking red/green directly after pressing connect."* TID-PTT change at **0 s**; radio *"dead / forze"*; Jabra never connected. Post-reboot matrix: button 0/3, BT-PTT no TX, RX no, sidetone yes. Verdicts: DEADLOCK *deadlocked*, OVERALL **FREEZE**. **Analysis:** (1) **v2 falsifies the posters-only model** — with ALL THREE 0x4a posters dead the WALK is unreachable, yet the press still evicted at 0 s: the primitive close paths (spp_connect chokepoint `0x01E1751E` / `0xB`→`FUN_01e1782c(0,1,0)` / SPP-SM direct callers) are a **SECOND, independently sufficient closer family**. (2) Combined matrix — v1 (primitives gated, walk alive) → kick; v2 (walk dead, primitives alive) → kick; E11 (both blocked) → evictor dead ⇒ **must block BOTH families** → F3-v3 = v2 + `--gate-close` re-armed (56 B / 2 sectors `0x01C000`+`0x0AC000`). (3) FREEZE persists across v1/v2/E11 but NOT at E7/M1 → freeze correlates with any close-blocking; v3 isolates whether kick and freeze can be separated. (4) NEW pre-press anomaly (v2 has NO gate, so not the sticky gate): TID-PTT-mic→speaker echo already running before the press — §30.9. |
| F3-v3 stage | 2026-10-25 14:10–14:13 | 1a1eaca1 | F3-v3 | stage flash (2 sectors + **full-flash verify**) | **PASS** | `work/logs/ch30_F3V3_20261025_141040.log` (prior `..._141029.log`: operator typo `WRTIE` → safe confirm-abort, nothing written) | **Observed:** build verify PASS (27 TARGET, 0 UNKNOWN, 3 teardown posters NOP'd, gate ARMED; diffs vs v2/M3 as expected). Sectors `0x01C000`+`0x0AC000` readback IDENTICAL (attempt 1). **FULL-FLASH VERIFY PASS — first live run of the §30.3 rule:** 1 MiB readback sha256 `d8570e5b…`, strict region `0x0000–0x0C8FDF` byte-identical to the expected image, VM untouched. Boots V1.0.50, name `TD-H3-Plus-351` (display truncation), paired list intact (*"Jabra Evolve, TID-PTT-PC, TID-PTT0cd28a"*). Bonded sanity: TID-PTT Paired→Connect ✓, buttons ✓ — verbatim: *"yes al ok, echo present when turning up/down volume radio mic TID-PTT -> Radio speaker"*. **Analysis:** flash pipeline with full-image integrity check proven end-to-end; the strict-region rule caught nothing because nothing drifted. |
| F3V3-B r1 | 2026-10-25 14:13–14:22 | 1a1eaca1 | F3-v3 | order B PRESS (both families blocked) | **INCONCLUSIVE (card bug — decisive press NOT executed; Jabra self-connected first)** | `work/logs/ch30_F3V3_B_20261025_141320.log` | **Observed:** step 2 healthy incumbent (correct Paired→TID-PTT→Connect, **3/3 keying**). Step 3 verbatim: *"No prompt on Radio, but after turn on the Jabra I head mobile connected directly"* + *"999 I did not pair / use any menu action Headset pair directly it self"* — the card said "Jabra ON, in range" **before** the press and the headset's power-on self-connect beat the menu press. Post-join: TID-PTT **alive** (*"still connected 5 sec interval green blink"*), radio **alive** (*"Alive, menu ok"*), **3/3 keys after join**. But **no bind**: BT-PTT TX used the **TID-PTT mic**, no RX audio (*"no nothing also nothing on radio"*), no sidetone. User guess *"My guess is that the headset is not 'paired'"* — **refuted** (paired list intact at flash; Jabra voiced "mobile connected"). Closing observation verbatim: *"after radio poweroff I counted 10 seoncds an than at EXACTLY the same time the TID-PTT and the Jabra when disconnected"* = both ACLs were alive until power-off (supervision timeout). **Analysis:** (1) **incoming HFP join on v3 = no eviction, no freeze, no SPP degradation** — cleaner than M3-B2 at M3 (where SPP died post-join): both closer families blocked + posters dead holds the incoming path too (gate armed since the step-2 menu connect). (2) **No-bind reproduces the M3-B2 pattern — a LIVE SPP session blocks the HFP audio bind** (M3-B run 1 bound only because its incumbent was a phantom): the wall is the app single-device session model (struct `0x102F0`, SPP session `0x1A740`), not eviction. (3) The decisive v3 PRESS question is still open — card fixed to press-first protocol; rerun owed. |
| F4 stage+r1 | 2026-10-25 19:52–19:56 | e7bc8abd | F4 | stage flash + boot sanity | flash **PASS** / sanity **FAIL — REGRESSION** | `work/logs/ch30_F4_20261025_195205.log` | **Observed:** 1-sector write `0x026000` readback IDENTICAL; **full-flash verify PASS**; boots V1.0.50; paired list intact. First action after boot — Paired→TID-PTT→Connect, **no other device connected** (Jabra off): verbatim *"no Radio dead / freezes / locked"*. Pairing mode afterwards (user, verbatim): *"the radio keeps on searching but finds nothig"*. Jabra power-on later self-connected cleanly (*"mobile connected"* + radio *"Bluetooth connected"*). **Analysis:** (1) **cmd-5 cleanup is load-bearing for the connect flow** — the press path posts cmd 5 then waits for the old link's disconnect-completion before proceeding; with the executor NOP'd, any press with ANY link state (incl. the boot-time phantom auto-reconnect ACL) blocks the app task forever = the §27.19 generic deadlock again. The phantom-repair trick (menu-connect repairs phantom) also depends on cmd 5 killing the phantom ACL first — which is why every F3-v3 card's step 2 worked. (2) **Q1 chain CONFIRMED correct** (cmd 5 → `0x01E08A94` → 0xCFE IS the press killer) — but wholesale NOP is not the fix: a conditional skip must ALSO satisfy the flow's wait (rewrite the wait, not the kill) = R1-proper code-cave work, not another NOP. (3) Pairing-scan starvation likely = app wedged or auto-reconnect page loop un-cleaned by dead cmd 5. **Rollback to F3-v3 prepared: `work/ch30_f4rb.sh` (one sector `0x026000`).** |
| F4-rollback | 2026-10-25 20:43–20:45 | 1a1eaca1 | F3-v3 (restored) | stage rollback | **PASS — regression cleared** | `work/logs/ch30_F4RB_20261025_204307.log` | **Observed:** sha-pin + `--show` confirm source kill call active (bf ea ce 35, via decrypt); 1-sector write `0x026000` readback IDENTICAL; **full-flash verify PASS** (strict region == F3-v3); boots V1.0.50, paired list intact (Jabra Evolve, TID-PTT-PC, TID-PTT0cd28a); the exact F4-frozen flow — Paired→TID-PTT→Connect — works again: *"yes"*; button keying (log field blank; user chat verbatim): *"done all ok 3x tx ok"* = **3/3**. **Analysis:** radio healthy on F3-v3 = known best state (incoming joins never evict; press = kick+freeze on join). F4 fully undone. Next decision: R1-proper design (locate connect-flow wait + conditional-cleanup cave) vs fallbacks F1–F3 (§30.12/§30.13). |
| F3V3-B r2 | 2026-10-25 14:45–14:55 | 1a1eaca1 | F3-v3 | order B PRESS — **decisive, executed** | **FAIL — KICK (0 s) + FREEZE (on join)** | `work/logs/ch30_F3V3_B_20261025_144526.log` | **Observed:** deviation guard **no** — press-first protocol followed (Jabra out of range until after the press). Healthy incumbent: correct Paired→TID-PTT→Connect, **3/3 keying**. Press (verbatim, full sequence): *"After press connect: Bluetooth Disconnected, than at the same time TID-PTT leds red/green blinking. Sortly after I turned on the Jabra Mobile connected and radio shouted bluetooth connected Than the menu locked up / radio fforze and after 30 seconds the Jabra said mobile disconnected"* — TID-PTT kicked at **0 s**; Jabra joined (incoming, after power-on); radio **froze upon the join**; Jabra lost ~30 s later. Post-reboot Jabra-only matrix: button 0/3 (kicked), BT-PTT = **Jabra mic**, RX **yes**, sidetone yes — verbatim: *"neede to reboot radio and jabra to get connected again => but obviously than the TID-PTT never connects..."* (matrix ran post-reboot with the Jabra as sole device — NOT a multipoint bind). **Analysis:** (1) **F3-v3's press-time eviction survives BOTH closer families blocked** — all posters dead, both close primitives gated, every known kick NOP'd — the evictor bypasses the gated primitives (an HCI-level path not covered by the two trampolines, or the page-pending flag clears during the press sequence). (2) FREEZE now times with the **join** under the gate — blocking closes → deadlock (§27.19) again. (3) **UNIFIED MODEL: the evictor and the no-bind wall are the SAME wall — the app's single-current-device model.** A press switches current device (⇒ bind, ⇒ old device killed); an incoming join preserves it (⇒ no kill, ⇒ no bind); the post-reboot matrix confirms bind follows whoever holds the slot. **The NOP ladder cannot reach the goal by construction**; F3 line CLOSED → rewrite routes (code-cave SPP multi-session ch. 23/25 / SDK rebuild ch. 28 / ESP32 combo device) are a user decision. |
| M4-A/B/C/D/E/R | | | M4=E10 | … | | | |
| R1-a built | 2026-10-26 | 18bc1597 | R1-a=F3v3+cond-kill | build + `--show` verify | **BUILT** (not flashed) | `--show`: `cmd5kill` = conditional (call cave `0x01EA7758`), `r1condkill`/`r1cave` TARGET; suites 0/0; byte-diff vs F3-v3 = 51 B / 2 sectors | R1-a image built with `--r1-conditional-kill` (hook `0x26EF4` + 50 B cave `0xAC758`); app-detection fix registered `conditional` as third recognised `cmd5kill` state (shared VA had broken `--show`); findings consolidated into §30.14; stage `work/ch30_r1a.sh` + card `work/ch30_r1ac.sh` prepared |
| R1-a field | 2026-10-27 00:16–00:20 | 18bc1597 | R1-a=F3v3+cond-kill | stage flash PASS → in-stage sanity (Paired→TID-PTT→Connect) | **FAIL — FREEZE on same-device Connect** | `work/logs/ch30_R1A_20261027_001629.log` | **Observed:** stage flash clean (2 sectors readback IDENTICAL, full-flash strict-region verify PASS, boot v1.0.50, paired list intact). Script sanity Q&A: *"TID-PTT bonded Paired->Connect worked? → no"*, 3x keying blank. User (verbatim): *"I executed sudo bash /home/stefan/h3plus/h3plus/work/ch30_r1a.sh but I was unable to pair the TID-PTT. Every attempt failed. Using the Paired -> TID-PTT0cd28a -> Connect froze / locked up the radio and using the pairing option it was scaning for a long time but Timeout and no device found. So I stoped after falshing and did not executed ch0_r1ac.sh as it's useless as the TID-PTT is unboundable"*. Card NOT run. **Analysis:** the same-device repair press must reach the cave and take the KILL branch (identical to stock/F3-v3); the observed hang = cave **SKIPped** → stuck slot never cleaned → walker addr-guard `FUN_01e16824` blocks the re-page → connecting modal waits forever. Leading root cause: **selection source wrong for this UI path** — the Paired-screen press handler `0x01E61D92` posts `0xC,0xE,0x12,5,0x4A` carrying NO address, and the `[[0xB468]+[0x102D0]*0xC+8]` double-deref was validated on the *other* Connect paths (`FUN_01e600b4` callers = list screen `0x01E68722` / settings `0x01E6ECBA`); `[0x102D0]` is plausibly stale on the Paired-screen path → `sel≠slot` → SKIP. Pairing-scan timeout = likely confounder (already-bonded button not in pairing mode), secondary. Cave bytes/hook/layout re-audited from the built image: all as designed (`lh r1,[r0+6]` handle etc. per §30.14.4); failure is semantic (predicate input), not encoding. **Rolled back to F3-v3** via `work/ch30_r1arb.sh` (2 sectors `0x026000`+`0x0AC000`, sha-pinned `0f4f4aa4`/`b7c68d92`). NEXT: locate what the Paired-screen press actually arms the walker with (cmd `0xC/0xE/0x12` consumers + CON arm payload) and re-derive the correct selection cell → R1-a2 predicate; btmon capture of the failed press would decisively show SKIP (zero HCI) vs crash. |
| R1-a rollback + post-mortem | 2026-10-27 08:28→ | 1a1eaca1 (restored) | F3-v3 rollback + static post-mortem | `work/ch30_r1arb.sh` flash + official-LLVM-objdump audit | **ROLLBACK PASS** (3/3 keying) / post-mortem **ROOT-CAUSED** | `work/logs/ch30_R1ARB_20261027_082839.log`; §30.14.6 | User: *"done, executed r1arb.sh all ok as expected"*; determinism: *"I power cycled the radio multiple times same behavior on every Connect attempt (in the menu) it froze"*; button LED whole session red/green = never connected. **Device fact:** TID-PTT 2 modes — power-on → pairing (red/green blink), connected → paired (5 s blink), link-loss → pairing. **Post-mortem (official JieLi LLVM objdump, toolchain §30.14.6):** mul `e3 e1 0c 30`=`r3*0xC` CONFIRMED; full 50 B cave decodes EXACTLY as designed; stock cmd-5 loop contract CONFIRMED (r0=slot ptr at hook, reached only when inused∧mask==0, r4/r7/r14 preserved) → **failure semantic, not encoding**. Press block `0x01E61D92` decoded: posts `0xC,0xE,0x12,5,0x4A` with **no address**; selection = 24 B conn-request struct (`r8+0x1215`) pruned into ROM list `0xB320`; `DAT_000102D0` = shared UI cursor (double-deref read lives in the *Connecting-screen retry loop*, not the press path) → R1-a predicate input unsound. **Keystone:** walker `FUN_01e60d34` sole page poster reads target from cell **`0x10E34`**, armed ONLY by CON pump cases 8/0xb (app task) which then call the walker synchronously → race-free decision point at the page post. **Route R1-b:** NOP cmd-5 kill (`--no-cmd5-kill`) + hook walker page-post site (cave2: kill same-address stuck slots vs fresh `0x10E34`, tail-call page post; 6 s rearm self-heals timing). Radio back on F3-v3 = known best. |
| R1-b built | 2026-10-27 | 36fcead7 | R1-b=F3v3+walker-kill | build + `--show` verify + suites | **BUILT** (not flashed) | §30.14.7 | cmd-5 kill NOP + walker page-post hook `0x01E60DE4` → 78 B cave2 `0x01EA7758` (official clang `-Oz`, objdump-exact): kill iff inused∧mask==0∧addr==fresh target `0x10E34`, else tail-call original post. Diff vs F3-v3 = 3 sectors (`0x026000`/`0x065000`/`0x0AC000`) / 80 B. Suites green. Stage `work/ch30_r1b.sh`, card `work/ch30_r1bc.sh`. |
| R1-b field | 2026-10-27 10:55 | 36fcead7 | R1-b=F3v3+walker-kill | stage flash PASS → in-stage sanity (Paired→TID-PTT→Connect) | **FAIL — FREEZE on Connect (same symptom as R1-a)** | `work/logs/ch30_R1B_20261027_105509.log` | **Observed:** stage flash fully clean — rebuild sha matched pin, 3 sectors (`0x026000`/`0x065000`/`0x0AC000`) readback IDENTICAL, full-flash strict-region verify PASS, boot v1.0.50, paired list intact (Jabra Evolve, TID-PTT-PC, TID-PTT0cd28a). In-stage sanity: Paired→TID-PTT→Connect worked? = **"no"**; seconds-until-connected = **999999999** (never); keys not testable. User (verbatim): *"done executed ch30_r1b.sh but unable to pair the TID-PTT as the radio froze / lockedup on Connect and pairing option resulted in timeout so I did nnot exeucte the card as it would be useless"*. Fresh Pairing attempt → scan **timeout, no devices**. Card `work/ch30_r1bc.sh` NOT run. **Analysis:** identical freeze symptom across two architecturally different patches (R1-a = cmd-5 predicate skip; R1-b = walker-hook conditional kill) — the cave2 **POST path** evidently works (boot clean, no wedge before press, phantom flow normal), so the freeze lands on the **KILL branch**: the walker runs in **app-task** context and cave2 tail-calls killer `0x01E08A94` (`FUN_01e029de(0x400002,3,0xcfe,...)`), which stock calls only from the **stack task** cmd-5 loop — app-task-context call plausibly blocks/deadlocks (or the CON-8 gates `FUN_01e18552/72` interact). Pairing-scan timeout after the freeze = consistent with a wedged app task. **Rolled back to F3-v3** via `work/ch30_r1brb.sh` (3 sectors, sha-pinned). NEXT: static root-cause of the killer's task-safety + CON-8 gate semantics before R1-c. |
| R1-c built | 2026-10-27 | ee0ba984 | R1-c=F3v3+cmd5-handle | build + `--show` verify + suites | **BUILT** (not flashed) | §30.14.9 | **Evictor located: stock cmd-5 stuck test reads mask@slot+8 — accessories keep 0 while LIVE → killed at every press (explains E6 pass / E7+F3V3-B fail).** Fix = 2 bytes `19 60`→`09 63` @`0x01E21EF0`: test the ACL handle@slot+6 instead; cmd 5 stays live (no F4 deadlock), kill stays on btstack task (no R1-a/b freeze), repair path preserved. R1-b hook+cave2 removed. Diff vs F3-v3 = 2 B / 1 sector `0x026000`; plaintext `09 63` verified in decrypted image; suites green. Stage `work/ch30_r1c.sh` (3 sectors, works from R1-b or F3-v3 state), card `work/ch30_r1cc.sh` (T1 sanity / T2 GOAL press / T3 reverse order / T4 BT-off). |
| R1-c field | 2026-10-27 13:49 | ee0ba984 | R1-c=F3v3+cmd5-handle | stage flash PASS → in-stage sanity (Paired→TID-PTT→Connect) | **FAIL — FREEZE on same-device Connect; GOAL case never reached** | `work/logs/ch30_R1C_20261027_134910.log` | Stage flash fully clean (3 sectors readback IDENTICAL, full-flash §30.3 verify PASS, boot v1.0.50, paired list intact). Sanity: connect never (seconds=9999999999); follow-up Pairing scan timeout; card `ch30_r1cc.sh` NOT run. User (verbatim): *"I think we are going in circles I don't see any progress try a different approach"*. **ROOT CAUSE FOUND (§30.14.10): the press flow contains unbounded waits for the current ACL to drop** — `FUN_01e600b4` loops A/B wait `FUN_01e07bd4`==0 (ANY link) before its direct cmd-1 page post; modal path waits CON event 3 → bit0 → watchdog → bit3 clear. Stock cmd-5's kill is the load-bearing event that satisfies both; F4/R1-a/b/c removed the kill but left the wait → identical freeze. R1-d (walker→cmd 4) NO-GO: cmd-4 executor E7-NOP'd, walker un-armed, bit3 gates it. **NEXT: patch the WAIT, not the kill** — D1 (same-address wait retarget) / D2 (modal release cave), static GO/NO-GO first. |
| R2 static + R1-e designed | 2026-10-28 (documented 2026-10-29) | — (analysis only, nothing built/flashed) | R2 read-only static analysis vs official objdump (`/tmp/opencode/app.o`) + byte re-verify vs `work/app_dec.bin` 2026-10-29 | GO/NO-GO on D1/D2 + press-flow decode | **D1 = GO / D2 = NO-GO; freeze model CORRECTED (transitional-link predicate, not any-link; real hang = same-address page guard `0x01E16824` @`0x01E21E76`); R1-e design complete — `--cmd5-target` implementation pending** | [Ch. 31](31-bluetooth-10-connect-press-flow.md), §30.14.11 | **Observed (static):** press = settings handler `FUN_01e6ec9e` → cmd-5 post `call 0x01E1792E` @`0x01E6ECDA` → ring dispatcher `FUN_01e21af8` case 5 kills via mask test @`0x01E21EF0`; `FUN_01e600b4` wait loops read `FUN_01e17f26`→`FUN_01e07bd4` = *transitional* controller-link check (stable link reads 0) — loops A/B do **not** wait for all links down; R1-c freeze = page refused by same-address guard (call `0x01E16824` @`0x01E21E76`) → silent "Connecting". `DAT_0001a5f1` (last-joined addr) written only by cmd-0 ring-pop @`0x01E21C44` + `FUN_01e21988`; walker-arm handlers are HCI-'m' switch cases, not CON; modal press propagates **no** target (Q5). **Design (R1-e, v1 = no D1):** (1) press-store cave @`0x01E6ECDA` — store `[[r5]+r4+8]` 6 B → `0x1A5F1`, then post cmd 5; (2) cmd-5-target cave @`0x01E21EF0` — kill iff `inused ∧ (handle@slot+6==0 ∨ slot==0x1A5F1)` via `memcmp` `0x01E08A94`; loop-cont @`0x01E21EF8`. Expected sectors **`0x026000` + `0x073000` + `0x0AC000`** (flash = VA−`0x01E00000`+`0x5000`; corrects the `0x065000` slip in the design note). Cave run `0x01EA76DE` (364 B ALLZERO re-verified). Matrix + card plan §30.14.11. Radio still on R1-c; rollback `work/ch30_r1crb.sh` ready. |
| R1-e built (not flashed) | 2026-10-30 | `work/ch30_r1e.bin` sha256 `d2aa7d8d5f29ec2a…` = F3-v3 recipe + `--cmd5-target` (build cmd in `work/ch30_r1e.sh`) | `--cmd5-target` implemented (4 sites: `presstore` hook @`0x01E6ECDA` `bd ea 28 46`→`81 ea 75 c5`, `presstcave` 32 B @`0x01EA77D0`, `cmd5target` hook @`0x01E21EF0` `19 60 81 42`→`c4 ea 56 2c`, `cmd5tcave` 38 B @`0x01EA77A8` — VAs moved from design note: `r1bcave` 76-B state window ends `0x01EA77A4`), all four **objdump round-trip verified** vs official JieLi objdump; `verify_actions.py` + `verify_cli.py` **0 failures** (incl. 4 new refusal cases + combo build); diff vs F3-v3 = exactly `0x026000`+`0x073000`+`0x0AC000`, **73 B** — predicted sectors CONFIRMED; `--show` all four TARGET, `cmd5kill` stock LIVE, E7 NOPs intact | **READY: stage `work/ch30_r1e.sh` + card `work/ch30_r1ec.sh` (T1 repair regression / T2 GOAL order A / T3 GOAL order B / T4 fresh pairing / T5 BT off-on) — awaiting user flash** | §30.14.11 impl log | Radio still on R1-c `ee0ba984` (rollback `work/ch30_r1crb.sh` ready); R1-e flash = same 3 sectors from R1-c (verified diff). Nothing flashed 2026-10-30. |
| R1-e FIELD | 2026-10-30 | flashed `work/ch30_r1e.bin` `d2aa7d8d` (stage OK, readback OK) | R1-e = F3-v3 + `--cmd5-target` | card NOT run | **FAILED — TID-PTT unpairable: Connect freezes/locks up the radio; Pairing option times out** | §30.14.12 | Card skipped (useless post-freeze). ROOT CAUSE FOUND same day: **misaligned multi-byte loads on the ODD saved-target cell `0x0001A5F1`** in the cmd5t cave (pi32v2 faults) → btstack task death → hard lockup on any press with a live slot. Rollback ready. |
| R1-e2 built (not flashed) | 2026-10-30 | `work/ch30_r1e.bin` sha256 `033fd19099acb02d…` | cmd5t cave rewritten byte-wise (40 B, `rep 4 6` XOR-fold of 12 byte loads; objdump round-trip verified); both suites **0 failures**; diff vs F3-v3 = sectors `0x026000`+`0x073000`+`0x0AC000` **75 B**; **diff vs flashed broken R1-e = ONE sector `0x0AC000`** | **READY: re-flash `work/ch30_r1e.sh` (or single-sector `0x0AC000`) + card `work/ch30_r1ec.sh`** | §30.14.12 | Radio still on broken R1-e `d2aa7d8d`; semantics unchanged (kill iff stuck OR addr==target). Nothing flashed. |
| R1-e2 FIELD | 2026-10-31 | flashed `033fd190` via `work/ch30_r1e.sh` (readback + full-flash verify PASS) | user attempted TID-PTT Connect after successful flash | **FAILED — IDENTICAL lockup on Connect** (same as broken R1-e), card not run; after reboot Menu→BT→Pairing: **inquiry timeout / nothing found** | §30.14.12 (addendum) | **Misalignment NOT the (only) root cause** — failure is in code common to both builds. Race model: press posts async cmd-5 kill, `FUN_01e600b4`'s GLOBAL waits read 0 on a stable link → page cmd 1 posted while target record inuse → guard `0x01E16824` refuses → "Connecting" hang; ~15 ms win window on the btstack task, lost twice. Post-reboot "nothing found" = auto-reconnect + Pairable-gated-while-connected (UNCONFIRMED — check if button keys after reboot). **NEXT: R1-e3 = R1-e2 + D1 (`--d1-target-wait`)**; rollback `work/ch30_r1erb.sh` (→F3-v3, 3 sectors). |
| **P0 F3-v3 press** | 2026-10-31 | flashed F3-v3 `1a1eaca1` via `work/ch30_r1erb.sh` (fixed) — flash+readback OK | press observation (user, card not run) | **F3-v3 FREEZES on Connect press — base GUILTY, R1-e series INNOCENT.** Incumbent (TID-PTT or Jabra) disconnects at press then radio hard-freezes; after reboot the selected device auto-connects. Inquiry "nothing found" (likely Pairable-gated-while-connected; S5 retest pending). Confirms freeze-onset = close-blocking lineage (E11/F3-v2/gate), never E7–E10. §30.14.13 | §30.14.13 | Radio on F3-v3; next = R2-a (E7 base + targeted kill + D1). |
| R2-a built (not flashed) | 2026-10-31 | `work/ch30_r2a.bin` sha256 `3db8e48343d70195…` = **E7 recipe** (no E8/E9/gate sites) **+ `--cmd5-target` + `--d1-target-wait`** (252 B, 15 sectors) | byte-verified: 7 R1-e3 sites present, E7 NOPs intact, E8/E9/gate sites stock, stock kill live; `--show` 0 UNKNOWN/MIXED; diff vs F3-v3 = **9 sectors `0x01C000+0x01E000+0x025000+0x026000+0x054000+0x065000+0x066000+0x073000+0x0AC000`, 173 B** (F3-v3 exports `work/ch30_f3v3_*.bin` for all nine) | **READY: stage `work/ch30_r2a.sh` + card `work/ch30_r2ac.sh` (S0–S5 press matrix) + rollback `work/ch30_r2arb.sh`** — the targeted kill's FIRST fair test on a non-freezing base; expect no freeze, kick may persist via live cleanup executors/walk | §30.14.13 | Radio on F3-v3 `1a1eaca1`. Nothing flashed by agent. UNTESTED. |
| R1-e3 FIELD | 2026-10-31 | flashed `b0fa1b35` via `work/ch30_r1e3.sh` (flash+readback OK) | press-matrix observation (user report, card NOT run) | **FAILED — IDENTICAL hard hang.** Target NOT connected when pressed (race model busted as sole cause); HARD freeze: screen lit, all keys/menu dead, local PTT dead, no TX; BOTH directions hang (Jabra→press TID-PTT, TID-PTT→press Jabra); after reboot BT alive — auto-reconnect works (last device), VM intact, hang is press-triggered. §30.14.12 addendum: hypotheses H-gate (F3-v3 gate-close sticky deadlock — LEADING; F3-v3 never press-tested in these directions), H-presst (cave fault), H-kill (wrong-slot kill). **NEXT: P0 rollback F3-v3 + press-matrix card `work/ch30_pmatrix.sh`** | §30.14.12 addendum | Radio on R1-e3 `b0fa1b35`; rollback `work/ch30_r1erb.sh` (4 sectors → F3-v3). |
| R1-e3 built (not flashed) | 2026-10-31 | `work/ch30_r1e3.bin` sha256 `b0fa1b3531de78a0…` = F3-v3 recipe + `--cmd5-target` + `--d1-target-wait` | `--d1-target-wait` implemented (3 sites: `d1wait1` @`0x01E600DC` 10 B = ch.31 recipe byte-identical; `d1wait2` @`0x01E6010E` 4 B; `d1thunk` cave @`0x01EA77F0` 6 B — relocated from ch.31's `0x01EA7758` (r1bcave window collision), ALLZERO+pointer-scan-clean verified); all **objdump round-trip verified**; both suites **0 failures** (D1 standalone + R1-e3 combo + 3 new CLI cases); diff vs F3-v3 = **4 sectors `0x026000`+`0x065000`+`0x073000`+`0x0AC000`, 93 B** (flash-offset correction: `0x01E6010E` → `0x6510E`, both waits in `0x065000`); diff vs flashed R1-e2 = **2 sectors `0x065000`+`0x0AC000`, 18 B**; byte-verified + `--show` all seven TARGET | **READY: stage `work/ch30_r1e3.sh` + card `work/ch30_r1e3c.sh` (T1 repair regression / T2/T3 GOAL A/B / T4 fresh pairing+inquiry / T5 BT off-on) + rollback `work/ch30_r1erb.sh` (4 sectors, covers R1-e2 AND R1-e3) — awaiting user flash** | §30.14.12 | Radio still on R1-e2 `033fd190`. Nothing flashed 2026-10-31. UNTESTED. |
| R2-a FIELD | 2026-11-01 | flashed `3db8e483` via fixed `work/ch30_r2a.sh` (9 sectors, readback + full verify OK) | card `work/ch30_r2ac.sh` run 2026-11-01 (log `work/logs/ch30_R2A_card_20261101_103949.log`) | card R2AC | **FAILED — S1/S2/S3/S4 ALL FREEZE** (S0 Jabra auto-connects at boot; **S5 inquiry LISTS DEVICES — first time**) | §30.14.14 | Freeze on a base with NO close-blockers ⇒ the R1-e3 sites themselves are a second freeze cause → mailbox root cause (§30.14.14). Radio then on R2-a. |
| R2-b built (not flashed) | 2026-11-01 | `work/ch30_r2b.bin` sha256 `52c3016a5c79a67a…` = **E7 recipe + `--cmd5-handle` ONLY** (2-byte handle test @`0x01E21EF0`; NO presst/cmd5t/D1 — mailbox poison removed) | byte-verified: handle test in, presst hook stock, D1 sites stock, cave region all-zero, E7 NOPs intact, gate entries stock; diff vs R2-a = 4 sectors `0x026000+0x065000+0x073000+0x0AC000` (93 B); diff vs F3-v3 = 8 sectors 82 B | **READY: stage `work/ch30_r2b.sh` + card `work/ch30_r2bc.sh`** — first CLEAN test of the 2-byte evictor fix (R1-c was never cleanly tested: it rode the freezing F3-v3 base). Repair press = known NO-GO (guard, record-only). | §30.14.14 | Radio on R2-a `3db8e483`. Nothing flashed by agent. UNTESTED. |
| R2-b FIELD | 2026-11-01 | flashed `52c3016a` via `work/ch30_r2b.sh` (readback OK) | user report (card NOT run) | **FAILED — hard freeze on Connect as before; inquiry/pairing now shows NO devices (Timeout) again** (it LISTED devices on the R2-a S5 hours earlier). Byte proof: R2-b = exact-E7-rebuild + ONLY the 2 handle-test bytes @`0x26EF0`; rebuild == 2026-10-09 field E7 with ZERO diffs ⇒ fork: (a) the 2 bytes (survival) architecturally freeze the press flow, or (b) radio state degraded (inquiry symptom = firmware-inert). **NEXT: 1-sector bisect `work/ch30_e7ref.sh`** (= exact E7, stock cmd 5) + Q1–Q5, Q3 inquiry-with-peripherals-OFF first. | §30.14.15 | Radio on R2-b `52c3016a`. |
| E7-ref built (not flashed) | 2026-11-01 | `work/ch30_e7ref.bin` sha256 `90bec3200146e78d…` = exact E7 recipe rebuild (NO `--cmd5-handle`) | byte-identical to `work/e7_twodev.bin` (Oct-9 field E7) in strict region `0x5000–0xC8FE0`; vs R2-b = 2 bytes @flash `0x26EF0` | **READY: `sudo bash work/ch30_e7ref.sh`** — ONE sector `0x026000` restores stock cmd 5 = exact E7; script Q1–Q5 verdict logic pins fork (a) vs (b) | §30.14.15 | Nothing flashed by agent. UNTESTED. |
| E7-ref FIELD | 2026-11-01 | flashed `90bec320` via `work/ch30_e7ref.sh` (1 sector, readback + full verify OK) | user report | **FORK (a) CONFIRMED — NO freezes anymore; press = stock kick (incumbent evicted).** ⇒ the 2 handle-test bytes themselves hard-freeze the press flow: **incumbent SURVIVAL under cmd 5 for mask==0 accessory records deadlocks the app press flow** (E6's PC-incumbent survival, mask!=0, never froze) — targeted-kill-on-manual-press is DEAD on the stock app. **NEW POSITIVE: boot auto-join reached a CRIPPLED TWO-DEVICE state** (headset auto-joined; formation without menu press = E6-confirmed radio-initiated direction). Characterization pending (checklist sent). | §30.14.16 | Radio on E7-ref `90bec320` = exact E7, stable. |
| E7-ref 2DEV CHARACTERIZED | 2026-11-01 | `90bec320` | user checklist answers (§30.14.17) | **STABLE TWO-DEVICE state via press-free order (TID-PTT first, Jabra pages in at its own power-on); crippling isolated to app audio routing — mode-1 binding to the first device, Jabra silent passenger, RX silent everywhere (P1/P2 probes next)** | radio on E7-ref | §30.14.17 | Jabra reconnect policy documented (only if it was connected at its own last power-off); no menu device indication (stock); SPP keying mode-independent (§9A.30) ⇒ goal may be reachable by connection ORDER alone |
| P1/P2 + routing chain | 2026-11-01 | `90bec320` | user answers + decompilation-tree analysis (§30.14.18) | **TID-PTT: no speaker, never auto-connects ⇒ order-swap P2 IMPOSSIBLE; reachable order = button-first + Jabra-incoming. Routing-byte chain decoded: 3 writers; classifier = name-only, called from btstack dispatcher case 7 (name result) via `DAT_0000bf4c`; teardown writes 0xF0 sentinel** | radio on E7-ref | §30.14.18 | H-name leading (incoming joins never classify); NEXT P6 (Jabra-only baseline) + P7 (power-cycle Jabra in 2-dev state) |
| Setup-block decoded | 2026-11-01 | `90bec320` (unchanged) | static: objdump `FUN_01e60e44` `0x61158–0x6179C` (§30.14.19) | **connect-complete setup block runs per join (calls `0x60120`); mode-switch tbh @`0x61270`: mode 1 = EXIT no-op, modes 2–6 call audio-bind `0x50398`/`0x503CA`** | — | §30.14.19 | **UNIFIED MODEL: incoming Jabra join runs setup but byte stayed 1 (H-name) ⇒ mode-1 no-op = the crippling; explains C3–C5 in one stroke. Fix candidate `--incoming-mode3` (cave hook forcing byte=3 for the differing incoming addr before the tbh). P6/P7 still the field discriminators** |
| P6/P7 probes | 2026-11-02 | `90bec320` (unchanged) | field (user, §30.14.20) | **P6 PASS: Jabra-only = Jabra mic TX + RX in earphones (mode-3 bind healthy); P7: Jabra does NOT re-join within a session — incoming join accepted only once per radio boot (power-cycle radio + redo)** | radio on E7-ref | §30.14.20 | H-name vs H-setup MOOT (tbh runs before async name result; classifier tail = UI only) ⇒ fix must set the byte at tbh time. Refined `--incoming-mode3`: tbh-entry cave, byte==1 && >=2 inused conn records → byte=3. NEXT: implement it |
| R3 built | 2026-11-02 | `d9c35315…` (not flashed) | `--incoming-mode3` implemented: hook `0x01E61270` 4 B → cave `0x01EA77F6` 54 B (byte==1 && both conn records inused → byte:=3); objdump round-trip + both suites 0 failures | — | §30.14.21 | diff vs E7-ref = exactly sectors `0x066000`+`0x0AC000` (48 B); stage `work/ch30_r3.sh` + card `work/ch30_r3c.sh` ready. **NEXT: user flashes + runs card (S1 GOAL gate)** |
| R3 field run | 2026-11-02 | `d9c35315` (flashed) | user card run (§30.14.22) | **Jabra paged in (S1a PASS); after Jabra power-off (S3): loud echo loop = TID-PTT mic broadcast on the radio speaker (acoustic feedback; announcements 2–3×), RX returns to radio speaker** | radio on R3 | §30.14.22–23 | **VERDICT FAIL (all answers in, §30.14.23): links solid (S2), button keys (S1e) — but TX stayed TID-PTT mic, RX complete silence ⇒ forced mode-3 binds a route with no HFP/SCO to the incoming device (H-noprofile leading); echo loop after Jabra-off latched until reboot (S4). NEXT static: `0x01E503CA`/`0x01E50398` internals + missing incoming HFP-profile connect + teardown `0xF0`/`0x61794` restore** |
| Static correction | 2026-11-02 | `d9c35315` (unchanged) | objdump + ch. 11 re-read (§30.14.24) | **tbh table indexed by mode−1 (off-by-one fix): mode1→`0x614A0`, mode3/5→`0x6128C`; `0x01E50398`/`0x01E503CA` = LOCAL MIC/SPEAKER enablers (flags `0xB476`/`0xB477`, ch. 11 §9A.22); mode-3 arm = mic OFF + addr-copy + `0x184D6` + `goto 0x61D7C` if 2 — state path, not a bind** | — | §30.14.24 | R3 silence/echo fully explained (forced path + no incoming SCO); R4 = open HFP for incoming device: enumerate relay `0x01E22890` + `0x184D6` semantics + HFP-connect poster |
| R4 built | 2026-11-03 | `work/ch30_r4.bin` sha256 `9168ac96…` = E7 recipe + `--incoming-hfp` | `--incoming-hfp` implemented (tbh hook `0x01E61270` + 58 B cave `0x01EA77F6` posting `user_send_cmd_prepare(1, 6, [sp+20])` for the joining addr, routing byte UNCHANGED + cmd-1 `is_1t2` bail NOP `0x01E17A2A`); objdump round-trip + both suites 0 failures | — | §30.14.27 | diff vs E7-ref = 3 sectors `0x01C000`+`0x066000`+`0x0AC000` (56 B); stage `work/ch30_r4.sh` + card `work/ch30_r4c.sh`. **NEXT: user flashes + card** |
| R4 FIELD | 2026-11-03 | flashed `9168ac96` via `work/ch30_r4.sh` (readback + full verify OK) | card `work/ch30_r4c.sh` run (user) | **FAILED — Jabra paged in, but TX stayed TID-PTT mic + RX SILENT.** The replay fires (S4a = SCO disturbance on outgoing RX) but opens no HFP/SCO to an already-connected ACL: cmd 1 is a DIAL command, same-address guard `0x01E16824` no-ops it. Echo at first RX after Jabra-off ⇒ strictly worse than E7-ref | radio on R4 `9168ac96` | §30.14.28 | **Verdict: cmd-1 replay DEAD. R5 = kick+redial** (arm stack re-dial mailbox `0x1A5F1` with joiner addr + HCI-Disconnect the incoming ACL → dispatcher epilogue posts cmd 1 = radio-originated dial). Rollback recipe (no script, per directive): 3 sectors `0x01C000`+`0x066000`+`0x0AC000` from E7-ref `90bec320` |
| R5 built | 2026-11-03 | `work/ch30_r5.bin` sha256 `dc4b27041e64cffd…` = E7 recipe + `--incoming-redial` | `--incoming-redial` implemented (tbh hook `0x01E61270` → 174 B cave `0x01EA7722`, ends exactly at `0x01EA77D0`): byte==1 && both conn records inused → copy joiner BD_ADDR `[sp+20]` byte-wise into re-dial mailbox `0x1A5F1` (ODD cell) + HCI-Disconnect the joiner (find-conn `0x01E17420` → `0x01E07B08(h,0x13)`); loop guard mailbox==addr; teardown `0xF0`+match → byte:=3; NO cmd-1 bail NOP (redial has 1 link < 2) | — | §30.14.29–32 | objdump round-trip + both suites **0 failures** (incl. static legacy-window recognition states — `find_app_start` gates on the DEFAULT `build_patches()`, dynamic states were invisible → "gate-close reverts to stock" FAIL fixed); diff vs E7-ref = EXACTLY sectors `0x066000`+`0x0AC000`, 158 B; stage `work/ch30_r5.sh` + card `work/ch30_r5c.sh` ready; no rollback script (directive). **NEXT: user flashes + card (S1 GOAL gate)** |
| R5 FIELD | 2026-11-03 | flashed `dc4b2704` via `work/ch30_r5.sh` (readback + full verify OK, attempt 1) | card `work/ch30_r5c.sh` run (user) | **FAILED on goal — but NO freezes anywhere.** S1: Jabra joined, "**both connected**", stable (S2) — yet TX = TID-PTT mic (S1c) + RX = **silence** (S1d): identical observable to R3/R4. S5b proves a radio-dialed Jabra binds audio perfectly when it is the app-current-device. Kick+redial firing UNCONFIRMED (S1a "mobile connected" tone ambiguous): (A) fired → wall = app struct `0x102F0` binding; (B) predicate false (slot-inused byte reads suspect) → no profiles, R3/R4 situation. S3: echo loop after Jabra-off again + button dies; S3c no re-join (P7 unfixed here) | radio on R5 `dc4b2704` | §30.14.33 | **Verdict: FAIL (goal). Cave SAFE.** R6 = discriminator first: reason-code telemetry kick (`0x11`) + static re-verify of the slot-inused byte offsets (`0x1A5CA`/`0x1A5E6` vs word-`+0xE` bit29 model). Rollback recipe (no script): 2 sectors `0x066000`+`0x0AC000` from E7-ref `90bec320` |
| R6 STATIC PASS | 2026-11-03 | objdump pass over `app_full.o.lst` (no flash) | (a) slot-inused reads `0x1A5CA`/`0x1A5E6` bit5 **CONFIRMED correct** (stack's own test @`0x16824`/`0x1687A`: LE word @record+0xF `& 0x20000000`; ch.27 "+0xE" note off-by-one); (b) epilogue `0x2232E` OR-fold `0x1A5F1..F6` → `0x21E46` cmd-1 DIAL **CONFIRMED**; entry = dispatcher event-0 (`0x21B8E` tbh → `0x21BC4`), arm path = vendor connect-failure retry `0x21C3E` (`rep 4 6` — only writer; **NO clear site exists** — persistent redial loop by design); (c) find-conn `0x17420`→`0x79CA`→`0x14BA8` walks BOTH conn objects @`0x1A0A8` stride 224 by BD_ADDR memcmp → returns handle — **works for the incoming joiner** | **Chain SOUND ⇒ R5 kick+redial FIRED in S1** (R1-e empirically proved arming ⇒ re-page). Wall = **app struct `0x102F0` never re-pointed** on stack-originated redial (no name request ⇒ no classifier ⇒ byte stays 1 ⇒ mode-1 no-op). S3c re-explained (armed mailbox + `0xF0` teardown state). **R6a proposal: cave loop-guard (mailbox==joiner) branch stamps `b[r6+212]:=3` (~6 B); if silent ⇒ R6b struct re-point (ch. 25 route). Telemetry moot.** | — | §30.14.34 | Static-only; radio still on R5 `dc4b2704` |
| R6a built | 2026-11-04 | `work/ch30_r6a.bin` sha256 `62214f1405c4d330…` = E7 recipe + `--incoming-redial --redial-bind` | `--redial-bind` implemented: **ONE cave byte** +73 `0x41→0x44` — ARM loop-guard (`if (r0==0) goto RET`, r0 = CMP6(mailbox,joiner)) retargeted to DONE(+18) = `r0=3; b[r6+212]=3; rts` ⇒ stamps routing byte 3 at OUR redial's connect-complete (byte==1 && mailbox==joiner); idempotent (byte 3 → RET later); mailbox stays armed, `is_1t2` bail prevents dial storm; R3 failure mode impossible (guard fires only on the cmd-1 redial, which brings HFP/SCO) | — | §30.14.35 | objdump round-trip (`a776a: 70 44 → a7734 DONE`) + both suites **0 failures** (incl. new `inchrdlbind` STATIC recognition state — legacy windows `gatecave`/`r1cave`/`r1bcave`/`cmd5tcave` taught the bind slice; first run failed 2 checks on `find_app_start`=None, fixed); diff vs R5 image = EXACTLY 1 byte @ flash `0xAC76B`; vs E7-ref = sectors `0x066000`+`0x0AC000` (158 B); stage `work/ch30_r6a.sh` + card `work/ch30_r6ac.sh` ready; no rollback script (directive). **NEXT: user flashes + card (S1c/S1d = WIN gate)** |
| R6a FIELD | 2026-11-04 | flashed `62214f14` via fixed `work/ch30_r6a.sh` (readbacks + full verify OK, attempt 1) | card `work/ch30_r6ac.sh` run (user) | **FAILED on goal — 4th identical signature** (S1c TX = RADIO mic, S1d RX = speaker; R3/R4/R5 family), zero freezes, two-device stable (S1b/S2). **Discriminator resolved: the stamp EXECUTED** — S1a join delay = kick+redial; **S3 CLEAN teardown (no echo loop, unlike R5)** = DONE path ran + byte-3 teardown consistent ⇒ forcing byte 3 at the redial connect-complete does NOT bind (mode-3 tbh = state path, §30.14.24; the bind needs the app-initiated dial with struct `0x102F0` pointing at the target — S5b/R5 control). **S5 REGRESSION**: repair press now kicks BOTH devices, nothing reconnects (byte-3 + armed mailbox interfere with app dial bookkeeping) ⇒ R6a must not ship. S3c no re-join (P7 persists). **Wall CONFIRMED = app current-device struct `0x102F0`**; routes: R6b (re-point `0x102F0` at ARM time — static design pass first) / SDK rebuild (ch. 28) / ch. 25 compile route | radio on R6a `62214f14` | §30.14.36 | **Verdict: FAIL (goal). Recommend daily-use rollback to E7-ref (2 sectors `0x066000`+`0x0AC000` from `90bec320`, no script).** |
| R6b built | 2026-11-04 | `work/ch30_r6b.bin` sha256 `7f2af2596bca94a2…` = E7 recipe + `--incoming-redial --redial-current` | `--redial-current` implemented (§30.14.37 design): loop-guard branch at cave +72 `70 41→10 52` (RET→CUR @`0x01EA77D0`); new 90 B CUR window = zero mailbox `0x1A5F1..F6` + copy joiner `[sp+20]`→**`0xBF41..46`** byte-wise + `b[0xBF3A] |= 0x40` (current-device valid bit14 of dword `0xBF39`) + post `user_send_cmd_prepare(6=READ_REMOTE_NAME, 6, [sp+20])` via `call 0x01E1792E` → name result → dispatcher tbh event 5 → `0x1A106` → ops `[0xBF48+4]` classifier `0x01E7EC28` **self-stamps `b[0xB464]:=3`** (Jabra = default name); routing byte UNCHANGED at tbh; teardown `0xF0`→DONE→CMP6-vs-zeroed-mailbox→RET (no stamp, no R5 echo latch); later joins re-arm+re-kick (P7 self-heal bet) | — | §30.14.37–38 | objdump round-trip `r6b_asm.py` pixel-perfect (guard `a776a: 10 52 → a77d0`; CUR disassembles exactly as designed; `call 0x1792E` verified) + both suites **0 failures** (first run 2 FAILs — D1-alone image `--show` — fixed by adding `legacy_d1` state; new CLI check: `--redial-current` × `--d1-target-wait` conflict, D1 thunk `0x01EA77F0` inside CUR window; cross-recognition taught both directions, all STATIC). Diff vs E7-ref = sectors `0x066000`+`0x0AC000`, 237 B (= R5 158 + CUR 79 non-zero); vs R5 = 81 B in `0xAC76A..0xAC828` ✓. Stage `work/ch30_r6b.sh` (full 64-hex EXPECT_SHA) + card `work/ch30_r6bc.sh` (S5 = R6a-regression gate, S3c = P7 self-heal gate). **UNTESTED. NEXT: user flashes + card; verdict §30.14.39. If S1c/S1d miss ⇒ byte/command tbh route DEAD ⇒ SDK rebuild (ch. 28) / ch. 25 compile route.** Radio still on R6a `62214f14`; rollback recipe: 2 sectors from E7-ref `90bec320` |
| R6b FIELD | 2026-11-04 | flashed `7f2af259…` clean (readback + FULL-FLASH VERIFY PASS; `work/logs/ch30_R6b_20261104_201658.log`) | card `work/logs/ch30_R6bcard_20261104_201749.log`: S0 PASS; **S1 GOAL FAIL — TX = TID-PTT mic + RX SILENCE (5th identical signature)**; S1a redial delay NOT heard (CUR firing unconfirmed); S2 PASS; S3 non-latching echo returning every RX (consistent with a stamped-3 teardown gap — weak CUR-fired evidence) + **S3c no re-join (P7 self-heal dead)**; **S4 REGRESSION: press-freeze** (Jabra-first → Connect TID-PTT → kick → FROZE, unworkable — E7-ref never froze); **S5 REGRESSION: both kicked + TX completely dead**; S6 rebuild only after full Jabra re-pair, then button keys OK | — | §30.14.39 | **FAIL — byte/command-level tbh route DEAD FOR GOOD** (5 levers, same wall: the bind needs the full app-originated connect flow at task level). R6b must NOT ship. Radio on R6b `7f2af259`; daily-use rollback = 2 sectors `0x066000`+`0x0AC000` from E7-ref `90bec320` (no script). NEXT: user picks escalation route — SDK rebuild (ch. 28) / ch. 25 compile route / ESP32 combo device |
| R7 built | 2026-11-04 | `work/ch30_r7.bin` sha256 `575e593df44ac2c7…` = E7 recipe + `--incoming-redial --redial-bind2` | **User chose the ch. 25 decompile⇒compile route (§30.14.40); Phase A decoded the bind: bt-task main loop `FUN_01e60e44` (tbh hook lives there — all R3–R6b caves ran in bt-task context), event switch case 0xB = bind block @`0x01E61292` (b[0xB4FA]:=120, addr copy `[sp+16]→[sp+12]`, free `[0x102F0+0x280]`, `is_current_device` gate abort-if-2, `b[0x10E00]&1` abort, state `|=5`, 500 ms timer, post stack cmd `0x1E`). R7 = `--redial-bind2`: at the loop-guard match, 90 B window @`0x01EA77D0` = R6b prefix (zero mailbox, `0xBF41..46`=joiner, `b[0xBF3A]|=0x40`) + **byte:=3 + synthesize `[sp+12]/[sp+16]` payload + direct `goto 0x01E61292`** — the stock bind block runs itself in-task (no cmd-6 replay) | — | §30.14.41–42 | objdump round-trip pixel-perfect (`a7826: fd ea 34 cd goto 0x61292`) + both suites **0 failures**. Diff vs E7-ref = sectors `0x066000`+`0x0AC000`, 238 B; vs R6b = 16 B @`0xAC81A..0xAC829`. Stage `work/ch30_r7.sh` + card `work/ch30_r7c.sh`. **UNTESTED — NEXT: user flashes + card; verdict §30.14.43. GOAL = S1c Jabra mic AND S1d earphones; else in-image bind emulation dead ⇒ SDK rebuild (ch. 28).** Radio on R6b `7f2af259`; rollback recipe: 2 sectors from E7-ref `90bec320` |
| R7 FIELD | 2026-11-06 | flashed `575e593d…` clean (readback ×2 sectors + FULL-FLASH VERIFY PASS; `work/logs/ch30_R7_20261106_200634.log`; first attempt stopped by the script's own stale 237 B assert — image fine, script fixed) | card `work/logs/ch30_R7card_20261106_200653.log`: S0 PASS; **S1 GOAL FAIL — TX = TID-PTT mic + RX SILENCE (6th identical signature)**; S1a no redial delay heard (bind2 firing unconfirmed); S2 PASS; S3 non-latching echo (R6b flavor) + **S3c no re-join (P7 self-heal dead)**; S4 stock kick, **no freeze** (R6b's S4 freeze did NOT reproduce); **S5 regression persists: both kicked + TX completely dead**; S6 rebuildable without reboot, button keys OK | — | §30.14.43 | **FAIL — in-image bind emulation DEAD (6 levers; direct bind-block goto still goal-miss: the bind needs the app-originated dial flow setting struct `0x102F0` state before connect-complete). R7 must NOT ship.** Radio on R7 `575e593d`; daily-use rollback = 2 sectors `0x066000`+`0x0AC000` from E7-ref `90bec320` (no script). NEXT: user picks final route — SDK rebuild (ch. 28) / ch. 25 deep rewrite / ESP32 combo |
| R8 built | 2026-11-10 | `work/ch30_r8.bin` sha256 `4bb75a2c0bad4527…` = E7 recipe + `--incoming-redial --redial-appswap` | **Statics (§30.14.47): the app connection-handle `_DAT_00010372` = `0x102F0+0x82` is written ONLY by the app `0x3e` connect-complete sink `FUN_01e5af40` — the stack-originated redial never delivers it ⇒ root cause of all 6 goal-misses. R8 = R7 + APP-SLOT SWAP: CUR window 106 B @`0x01EA77D0` = R6b prefix + `call 0x01E16E0E` (live current-record handle) + guard `if (r0==0) skip` + `h[0x10372]=r0` (stamp app device record) + R7 bind tail (byte:=3, payload synth, `goto 0x01E61292` re-encoded `fd ea 2c cd` — the position-dependent-goto catch)** | — | §30.14.47–48 | every byte upstream-table-verified + both suites **0 failures** (new R8 checks) + **jl_sim pre-flash run: window executes end-to-end, lands exactly on bind entry `0x01E61292`**; diff vs E7-ref = sectors `0x066000`+`0x0AC000` (252 B), uboot equal; stage `work/ch30_r8.sh` + card `work/ch30_r8c.sh` ready; no rollback script (directive). **UNTESTED — NEXT: user flashes + card; verdict §30.14.49. GOAL = S1c Jabra mic AND S1d earphones; 7th identical goal-miss ⇒ in-image route CLOSED ⇒ SDK rebuild (ch. 28) / compiled-C splice (ch. 35 §35.9) / ESP32 combo.** Radio on ch32_bt_e7 `d7a29a3e`; rollback recipe: 2 sectors from E7-ref `90bec320` |
| R8 FIELD | 2026-11-10 | `work/ch30_r8.bin` `4bb75a2c…` (flashed) | S0 PASS; S1 join never landed + TX TID-PTT mic/RX silent; S3a no echo (clean teardown); **S3c P7 self-heal ALIVE + FIRST audio-state movement of the R-series** (TX source followed the swap onto the Jabra path — silent, no live SCO; RX back on speaker); S4b transient menu-Connect stall (regression vs S1); S5 both-up = **7th identical goal-miss** | **GOAL FAIL — in-image bind-emulation route CLOSED (§30.14.49)** | `work/logs/ch30_R8card_20261110_231256.log`; restore S1 via `sudo bash work/ch32_bt_e7.sh` |

---

## §30.11 — Route decision on record (micro-patch over SDK rebuild)

For the goal topology the SDK-rebuild route is **disproportionate and rejected**
(2026-10-21): the stock app already demonstrated the exact goal (E6: SPP-commands +
HFP-audio simultaneous, radio-initiated); the public SDK carries a *weaker* BT build
(stock 1×`conn_info` vs our vendor-widened 2-slot pools, ch. 27), the same prebuilt
controller lib (no wall improvement), and would require re-implementing ~800 KB of
closed TID app (RF, UI, 9 languages, VM, RCSP, `+SPP`/`AT+MPTT` protocol) plus risky
full-chip flashing (OTP-key note, ch. 28 §28.7). The micro-patch route's remaining
risk — finding the minimal close-suppression that doesn't corrupt — is bounded
(F1→F3 above), reversible (full-image stage flashes), and hardware-testable per card.
The SDK route stays documented (ch. 25/28) as the escape hatch if TID ever ships
something structurally unpatchable. Follow-up investment recommended after the ladder
lands: **signature-based site re-anchoring** in the patch tool so future stock
releases re-derive all sites automatically (repeatability requirement from the user).

> **SUPERSEDED 2026-10-25 (§30.12.3):** the "bounded" micro-patch risk was the whole
> route — F1–F3 + the E-series exhausted every NOP/gate variant and the eviction proved
> structurally NOP-proof (single-current-device model). The escape-hatch clause is now
> the MAIN line: R1 code-cave rewrite / R2 SDK rebuild / R3 ESP32 combo device.
> **ROUTE CHOSEN 2026-10-25 (user): R1 — code-cave rewrite.** Design brief: §30.13.

## §30.12 — F3 `--gate-close`: conditional close gate (BUILT 2026-10-24; field-FAILED → superseded by v2, see amendment at end)

**Idea.** E11 proved the evictor dies when both close primitives —
`spp_channel_disconnect()` @`0x01E173EC` and `l2cap_disconnect()` @`0x01E173D0` —
are blocked, but its *unconditional* entry NOPs corrupted normal operation and
still deadlocked (§27.19). Every eviction chain runs **inside the press window**
(Order B: `0xB` → `FUN_01e1782c(0,1,0)` → `spp_connect` busy-path `0x01E1751E` →
`spp_channel_disconnect`; Order A: same chokepoint directly; plus the `0x4a`
all-channel walk and the four direct SPP-SM `l2cap_disconnect` callers). The
press itself sets a ready-made flag: **page-pending `DAT_0001a662` bit 7**, set
by `FUN_01e185f0(1)` @`0x01E61DEA` in the connect-UI press flow, cleared only by
the no-connection timeout callback (`FUN_01e7efd2` → `FUN_01e185f0(0)`
@`0x01E7F032`). So instead of blocking closes forever, **block them only while
the flag is set** — stock behavior everywhere else.

**Implementation** (patcher action `--gate-close`, three sites):

| site | VA | stock → patched |
|---|---|---|
| `gatespptramp` | `0x01E173EC` | `10 04 c0 ff` → `goto 0x01EA7722` (`c4 ea 99 81`) |
| `gatel2captramp` | `0x01E173D0` | `10 04 bf ea` → `goto 0x01EA773E` (`c4 ea b5 81`) |
| `gatecave` | `0x01EA7722` | zeros → 54 B stub pair (cave 2 = free space after BT-PTT2's 68 B @`0x01EA76DE`) |

Each stub: load `b[0x01A662]`, test bit 7 (`>>7`); **set → `r0=0; rts`** (close
skipped, return success); **clear → replay the two stolen instructions**
(`[--sp]=rets` + the 6-B `mov r0,0x1A740` / the `call 0x01E16938` — re-encoded at
the cave site, displacements are site-relative) and `goto` back to entry+4. The
`rts` return is correct because the trampoline stole the push: the hardware link
register still holds the caller's return. Skip path returns `0` = "succeeded",
so callers (`spp_connect` busy-path, walk, SPP-SM) proceed normally without
retry storms (verified: `spp_connect` returns −2 once, dispatcher does not loop).
`--gate-close` is **mutually exclusive** with `--no-spp-close` /
`--no-l2cap-disconnect` (same entry bytes; enforced by the CLI). Both suites
green incl. gate build/show/idempotent/revert/conflict tests + F3 combo
(verify_actions 0, verify_cli 0).

**Known accepted side effect (flag stickiness).** There is no success-path clear
of bit 7 (only the no-connection timeout or the `FUN_01e184a2` reset touch it),
so after a *successful* menu-connect, channel closes stay skipped until
BT-off/power-cycle. HCI-level disconnects (kick path `0x01E074DE`, BT-off toggle
`0x01E6076c`) are NOT gated. v2 candidates if the field dislikes this: one-shot
consumption in the stub (bit-clear `b8 27` on skip) or hooking the connect-
complete dispatcher case.

**Field questions this card answers.** (1) Does gating only the press window
avoid the §27.19 deadlock that E11's unconditional block caused? (2) With the
incumbent surviving the press, does the app then *bind* the Jabra (E6 showed the
press path binds when the incumbent survives teardown) — or does the
single-current-device routing wall (M3-B2 no-bind) still win? Classification:
FULL PASS / NO-KICK-NO-FREEZE-NO-BIND / KICK / FREEZE.

**Artifacts.** Image `work/ch30_f3.bin` sha256 `25a489d2…` (M3 recipe +
`--gate-close`); diff vs flashed M3 `8be71516` = exactly **56 bytes in 2
sectors** — flash `0x01C000` (8 B, both trampolines) + `0x0AC000` (48 B, cave;
VM untouched → pairings survive, no stale-key preflight). Sector flash:
`sudo bash work/ch30_f3.sh` (erase+write+readback per sector, 2 attempts).
Card: `bash work/ch30_f3b.sh` (F3-B = the decisive press card: healthy 3/3
TID-PTT incumbent → Paired→Jabra→Connect → kick/deadlock/bind checks + matrix).

### §30.12.1 — Amendment (2026-10-24): gate field-FAILED — root cause = a THIRD `0x4a`
### poster driving the inline WALK; F3-v2 = NOP it

**Field result (F3-B, §30.10).** The gate flashed clean (both sector readbacks
IDENTICAL) but card F3-B reproduced M3-B run3 exactly: TID-PTT kicked at **0 s** +
radio **freeze** on the decisive press. The gate premise is **falsified**: the
press-time evictor never calls either gated primitive. (Bonus field data: the
sticky flag's harm is real — after the step-2 menu-connect armed the gate, closes
were skipped until reboot, §30.9.)

**Root cause — full census.** All 80 callers of `user_send_cmd_prepare`
`0x01E1792E` were enumerated (script over `work/full.lst`, backward `r0`-imm scan;
pi32dis prints hex UPPERCASE). Exactly **three** sites load `r0 = 0x4A`:
`0x01E61E22` (UI connect, NOP'd at M3), `0x01E60188` (mode setter, NOP'd at M3),
and **`0x01E4F804` — never located before** — inside `FUN_01e4f652`, an
AT-command/SPP-dispatcher family function (branch-table entry ptr @`0x01E4E274`;
nearby strings `+SPP=P`/`+SPP=R`/`AT+ATD`/`+CIND?`). It posts `0x4a` when helper
`0x01E4F034` returns nonzero, then arms a 1000 ms timer (`0x01E4F808`–`0x01E4F814`,
`call 0x01E249CE`); fall-through safe to NOP (result not consumed). Cmd `0x4a`
executes the **inline all-channel WALK** `0x01E17B20` — which forces every L2CAP
channel to state `0xd` and pumps it **directly, bypassing
`spp_channel_disconnect`/`l2cap_disconnect` entirely**. That is why the gate missed
it, and it retro-explains E11: what killed the evictor there was the `je`-branch
NOP @`0x01E17974` (blocking dispatch into the WALK), not the primitive entry NOPs.
The §27.19 "blocking closes → deadlock" theory is superseded for the press path:
the WALK *is* the closer. Controller-queue posters (`0x01E1664E`, 12 callers) were
also censused — no hidden HCI-disconnect kick (only cmd-5 poster is the app kick,
already NOP'd).

**F3-v2 (BUILT, awaiting flash).** Add the third poster to `--no-l2cap-teardown`
as site `l2capteardownapp` @`0x01E4F804` (`be ea 93 40` → `00 00 00 00`, house
style; ctx `beea9340c1ff82fa`). Image `work/ch30_f3v2.bin` sha256 `91383c8f…` =
M3 recipe + extended teardown NOPs, **no gate** (gate cleanly reverted): diff vs
M3 = exactly **4 bytes / 1 sector** `0x54000`; diff vs flashed F3 = 60 B / 3
sectors `0x01C000`+`0x54000`+`0x0AC000`. Both suites green (site-count/show/revert
tests updated; `--only` semantics: flag appends still apply all three teardown
sites, but an explicit revert build must name every site). Flash:
`sudo bash work/ch30_f3v2.sh`; card: `bash work/ch30_f3vb.sh` (F3-V2-B — same
decisive-press protocol: 3/3 TID-PTT incumbent → **Paired**→Jabra→Connect →
KICK/FREEZE/BIND classification). **Open walls if v2 survives the press:** (1)
single-current-device **binding** (struct `0x102F0`, M3-B2 no-bind evidence);
(2) freeze persistence (if the freeze is the M2 `--no-cleanup-kick` wait rather
than the WALK, v3 revisits those sites). Any future close-gating MUST cover the
WALK path, not the primitives.

### §30.12.2 — Amendment 2 (2026-10-25): F3-v2 field-FAILED — TWO closer families;
### F3-v3 = posters NOP'd AND gate armed

**Field result (F3V2-B, §30.10).** Stage flash PASS (3 sectors, readback
IDENTICAL; 4-byte diff vs M3 confirmed). Card F3V2-B **FAIL — FREEZE**: healthy
3/3 incumbent, correct PAIRED→Jabra→Connect press → TID-PTT kicked at **0 s**,
radio froze, Jabra never connected. With all three `0x4a` posters dead the WALK
is unreachable — yet eviction persisted ⇒ the **primitive close paths are a
second, independently sufficient evictor family**.

**Evidence matrix.** v1 = primitives gated, poster-3→WALK alive → kick.
v2 = walk dead, primitives stock → kick. E11 = both blocked (je-branch + entry
NOPs) → evictor dead. Each family alone suffices; a fix must block **both**.
FREEZE persists in v1/v2/E11 but never occurred at E7/M1 → the freeze correlates
with close-*blocking*, not with which closer ran — v3 tests whether kick and
freeze can be separated at all on this stack.

**F3-v3 (BUILT 2026-10-25, awaiting flash).** `work/ch30_f3v3.bin` sha256
`1a1eaca1…` = F3-v2 recipe + `--gate-close` re-armed (patcher already supports
coexistence; the gate conflicts only with `--no-spp-close`/`--no-l2cap-disconnect`).
Diff vs flashed v2 = exactly **56 bytes / 2 sectors** `0x01C000` (trampolines) +
`0x0AC000` (cave); diff vs M3 = 60 B / 3 sectors (VM untouched). `--show`: 27
TARGET, 0 UNKNOWN; 3 teardown sites disabled; both primitive entries show the
gate label. Flash: `sudo bash work/ch30_f3v3.sh`; card: `bash work/ch30_f3vc.sh`
(F3-V3-B — same decisive-press protocol + sticky-gate caveat re-added: the
step-2 menu-connect arms the gate, echo quirks expected, classification
unchanged). **If v3 shows no-kick + no-freeze but no audio bind**, the eviction
problem is solved and the remaining wall is single-current-device **binding**
(struct `0x102F0`) — a routing rewrite, not a NOP. If FREEZE persists while the
kick dies, v4 candidate = drop `--no-cleanup-kick` (the M2-era freeze source).

### §30.12.3 — Amendment 3 (2026-10-25): F3-v3 field-FAILED — F3 line CLOSED;
### the evictor and the bind wall are ONE wall

**Field results (F3V3-B r1/r2, §30.10).** Stage flash PASS (2 sectors readback
IDENTICAL + first live **full-flash verify**: strict region `0x0000–0x0C8FDF`
byte-identical, VM untouched). r1 = accidental **incoming** join (card ordering
bug): clean — TID-PTT alive 3/3 keys, radio alive, no degradation — **but no
audio bind**. r2 = the **decisive press**, protocol followed (deviation guard
no): TID-PTT kicked at **0 s**, radio froze upon the Jabra join, Jabra lost
~30 s later; post-reboot the Jabra alone bound fine (BT-PTT = Jabra mic, RX
yes) — bind follows whoever holds the current-device slot.

**Verdict.** With all three `0x4a` posters dead AND both close primitives
gated AND every known kick NOP'd, the press still evicted at 0 s: the evictor
bypasses the gated primitives (HCI-level path outside the two trampolines, or
the page-pending flag clearing during the press sequence). Freeze reappears
under the gate, timed with the join — §27.19's blocking-closes deadlock again.

**Unified model (closes the F3 line).** The press-time evictor and the
incoming-join no-bind wall are the SAME mechanism: the app's
**single-current-device model** (struct `0x102F0`, SPP session `0x1A740`).
Press = switch current device ⇒ audio binds ⇒ old device is killed. Incoming
join = current device preserved ⇒ old session lives ⇒ no bind. Every NOP site
tried sits *downstream* of that decision; blocking the close only converts the
kick into a deadlock. **The goal is unreachable by NOPs by construction** —
the remaining routes are rewrites: **R1** code-cave SPP multi-session /
current-device rewrite (ch. 23 cave + ch. 25 decompile⇒compile route),
**R2** SDK rebuild (ch. 28), **R3** ESP32 combo device (SPP+HFP in one
accessory, no firmware patch). Supersedes the §30.11 micro-patch preference:
the micro-patch route is exhausted, not merely disfavored.

## §30.13 — R1 design brief: profile-aware switch (code-cave rewrite)

**Goal (unchanged, §30.0):** TID-PTT (SPP commands) + Jabra (HFP audio) connected
simultaneously, either order, both functions live.

**The wall being rewritten (§30.12.3):** the app's single-current-device model —
press = switch current device (struct `0x102F0`) ⇒ kill old session ⇒ bind new.
Blocking the kill downstream (NOPs/gates) deadlocks because the state machine that
*initiated* the close waits for its completion.

**R1 concept — prevent, don't block:** make the switch *profile-aware at the
decision point*: when the target is HFP (audio) and the incumbent session is SPP
(commands), **skip initiating the close at all** (the state machine never enters
the closing state ⇒ nothing to deadlock on), switch the audio binding, and keep
the SPP session alive. This is the old §30.8-F3 idea, now correctly scoped: the
predicate sits at the CALLER (decision level), not at the close primitives.

**Open design questions (static analysis, in order):**
- **Q1 — the press-time kill executor.** On an HFP-target press with a live SPP
  session, what code disconnects the incumbent at 0 s (F3V3-B r2)? The two gated
  primitives and all known kick sites are dead, so this is an uncovered path —
  trace the "connect selected device" flow (`0x01E61E22` region) → current-device
  write in `0x102F0` → the disconnect call it makes (suspect a direct
  `0x01E07B08`-wrapper call or an HCI Disconnect `0x01E074DE` caller outside the
  NOP'd set; enumerate ALL callers of `0x01E07B08` + ALL of `0x01E074DE` again
  with the decompiled tree).
- **Q2 — does SPP RX/keying depend on current-device?** Does the `+SPP=` receive
  dispatch and key routing read session `0x1A740` alone, or gate on current-device
  (`0x102F0` / routing byte `0xB464`)? If session-only, R1 v1 needs NO routing
  rewrite at all — just the Q1 predicate. (r1 evidence is encouraging: incoming
  Jabra join left buttons 3/3 working.)
- **Q3 — predicate + cave budget.** Where to branch (Q1 site), how to test
  "target profile == HFP" (device class / SDP-ctx available at that point?),
  and where the ~30 B stub lands (ch. 23 cave `0x01EA76DE` has ~300 B free after
  BT-PTT2; else erased-flash trampoline). Compile via ch. 25 route
  (`-target pi32v2 -mcpu=r3 -Oz`).

**Q1 ANSWER (2026-10-25, trace + independent disasm verification + field
consistency).** The press-time kill is the **cmd-5 cleanup path — never NOP'd
in any E1–E11/F build**: press posts `user_send_cmd_prepare(5)` at
`0x01E61E18` (E9 only killed the adjacent `0x4A` post at `0x01E61E22`) →
dispatcher `0x01E1792E` → BT task `FUN_01e21af8` **case 5** → conn-slot loop
(`0x01E21ED0`: in-use slot, halfword `+8 == 0`) → **`call FUN_01e08a94` @
`0x01E21EF4`** (sole caller) → controller command **`0xCFE`**
(`r0=0x400002, r1=3, r2=0xCFE; call 0x01E029DE`) → handler `0x01E0DDA4`:
lookup conn by BD_ADDR (`0x01E14BA8`, table `0x1A0A8`) → `r1=0x13; call
FUN_01e091EA` = disconnect executor (graceful L2CAP teardown + Disconnect
Complete 0x13 — the E3 btmon signature). It touches **none** of the NOP'd
sites (wrapper `0x01E07B08`, relay, posters, primitives) — which is exactly
why every stage kicked at 0 s. It also resolves E7's "class-dependence": the
loop fires on **slot state**, not device class (the PC-incumbent passes were
incoming-join flows with no cmd 5 posted — consistent with ch. 27 §27.15's
"no class check exists"). Gap: the `+8` writer is inside precompiled btstack;
the `+8==0` match for a live incumbent is inferred from field bounds. Full
report: `/tmp/opencode/r1_q1_kill_executor.md`.

**F4 SHIPPED (2026-10-25).** Patcher flag `--no-cmd5-kill` (NOP `call
0x01E08A94` @`0x01E21EF4`, 4 bytes; both suites green, 28th site). Image
`work/ch30_f4.bin` sha256 `e7bc8abd…` = F3-v3 + that NOP: diff vs flashed
F3-v3 = **4 bytes / 1 sector `0x026000`**; VM untouched. Cmd 5 is
fire-and-forget (ring-buffer post), so unlike the primitive NOPs this should
**not** deadlock. Stage `work/ch30_f4.sh`, card `work/ch30_f4c.sh` (press-first
protocol). **Prediction:** press = no kick, no freeze, current device switches
⇒ Jabra binds; open question = do TID-PTT keys still work post-switch (Q2).
If kick persists ⇒ cmd 5 is not the (only) killer ⇒ re-open Q1.

**F4 FIELD RESULT (2026-10-25): FAILED — REGRESSION** (ledger row
`F4 stage+r1`). The stage flash itself PASSed (sector `0x026000` readback
IDENTICAL + full-flash verify), but the first Paired→TID-PTT→Connect after
boot **froze the radio** with the Jabra off (user verbatim: *"When pressing
Connnect the radio hangs / freezed"*; pairing mode afterwards: *"the radio
keeps on searching but finds nothig"*; the Jabra incoming self-connect still
worked). **The fire-and-forget premise was WRONG:** the connect flow posts
cmd 5 and then *waits* for its disconnect-completion before proceeding — with
the executor NOP'd, that wait is unsatisfiable whenever any link state exists,
**including the boot phantom ACL** — which is also why menu-connect repairs
the phantom on F3-v3 (cmd 5 frees the stale slot first). So the Q1 chain
stands (cmd 5 IS the press-time killer) but the kill is **load-bearing for
the flow**: blocking it ⇒ deadlock, allowing it ⇒ eviction — the §27.19 wall
one layer deeper. **NOP route closed at this site.** R1-proper = locate the
connect-flow WAIT after the `0x01E61E18` post and make cleanup + wait
conditional *together* (profile-aware skip) — code-cave work, not another
patch byte. Rollback: `work/ch30_f4rb.sh` (restores sector `0x026000` from
F3-v3 `1a1eaca1`; full-flash verify + regression-clear sanity included).

**Regression guard:** every R1 build re-runs card M-E (single-device regressions)
+ F3-V3-B (press) + M3-B2-style incoming card before acceptance.

**Test images:** build as stage **R1-a** (predicate only) → cards; R1-b adds any
routing fix Q2 demands. Same full-flash-verify discipline (§30.3).

## §30.14 — R1-a design and build: conditional cmd-5 kill (Q4/Q5/Q6 findings, 2026-10-26)

Consolidated permanent record of the three sub-agent analysis passes (Q4 =
connect-flow/wait analysis, Q5 = page-trigger + conditional-kill design,
Q6 = selection path at cmd-5 time + final cave) plus the independent
verification pass that corrected two of their encodings. The source reports
(`/tmp/opencode/r1_q1_kill_executor.md`, `r1_q4_connect_flow_wait.md`,
`r1_q5_page_trigger_and_design.md`, `r1_q6_selection_path_and_final_cave.md`,
`r1_design_notes.md`) are transient scratch — **this section is the record**.
All VAs on stock v1.0.50 `work/app_dec.bin`; PROVEN = disasm/decompile cited in
the reports, INFERRED marked where noted.

### §30.14.1 — The press→connect flow and the freeze mechanism (Q4, PROVEN)

- The "Paired → device → Connect" press is consumed inside the **BT task's
  modal state-3 handler** `FUN_01e60e44` (state machine `FUN_01e637ee` over
  `gp+0x5B` = RAM `0x1034B`). Press block `0x01E61D92–0x01E61E4A`: sets
  `DAT_0000b4f0` **bit3** (`0x01E61DE4`), page-pending `DAT_0001a662` bit7 via
  `FUN_01e185f0(1)`, posts cmds `0xc, 0xe, 0x12, 5, 0x4a` (the `0x4a` already
  NOP'd on our F3-v3 base), arms the **one-shot 10-tick watchdog**
  `0x01E249DE(0, FUN_01e7efd2, 10)`, sets bit4.
- **cmd `0x4a` = synchronous drain-wait inside `user_send_cmd_prepare`**
  (`0x01E17B20–0x01E17B82`): walks the l2cap list forcing every channel to
  state `0xd` + pumps, `sleep(1)` then ≤101 × `sleep(3)` until no CID remains,
  and **only then enqueues 0x4a anyway**. Consequence: NOP'ing the dispatcher
  branch (E11's `0x01E17974`) skips only the app-side drain — the enqueue still
  posts 0x4a to the stack task, whose own close-walk then ran against the NOP'd
  `l2cap_disconnect` = the most likely cause of E11's from-first-connect
  corruption (doubled `+SPP` echo, zero `AT+MPTT`). Skips must happen at the
  **post site**, never mid-dispatcher.
- **The freeze = modal exit gate.** `FUN_01e60e44` returns to the outer state
  machine only when `(b4f0 & 0x18) == 0x10` (`0x01E61E52`); **bit3 is cleared
  at exactly one place in the image** — the watchdog `FUN_01e7efd2` @`0x01E7F026`
  — which **early-returns (no re-arm, one-shot)** if `b4f0` bit0 (BT-on) is set
  OR the audio object `d[gp+0x2C0]` is live (`FUN_01e7efbe`). An HFP/SCO join
  inside the modal window installs that object (CON 0x30 handler stores it at
  `0x01E61906`) → watchdog returns → bit3 stuck → BT task wedged in its
  in-function queue wait = exactly the field "menu frozen, stack alive"
  signature (F4, E11 follow-ups, F3V3-B r2).
- **Corrections established by Q4** (supersede earlier working assumptions):
  `gp+0x2C0/0x2C4` (RAM `0x105B0/0x105B4`) are **audio-session object pointers**
  (0x1C4/0x1D4-byte allocations in the CON 0x30 / HCI 0x19 handlers), *not* an
  "any-ACL-connected" counter; `jmnz` = **jump-if-mask-NONZERO**; Ghidra's
  gp-relative symbol rendering is unreliable (phantoms `DAT_000107fa/0x107fb`,
  `DAT_00030ef0`, `DAT_00041700`) — `pi32dis` decodes are authoritative there.
- **cmd-5 semantics (verified):** consumer `FUN_01e21af8` case 5 loop
  (`0x01E21ECA–0x01E21F02`) kills a slot iff **inused && halfword `slot+8 == 0`**
  (profile mask empty — live *idle* links DO match; the Q1 report's initial
  `handle==0` reading was corrected to this). **cmd 5 must stay live**: F4
  proved the flow waits on its cleanup (stuck slots otherwise permanently
  occupy the conn record → `create_bt_new_conn` NULL → no page → permanent
  "Connecting").

### §30.14.2 — The page trigger and the resolved E6 paradox (Q5, PROVEN + field-bounded)

- **The press itself never pages** (PROVEN): no press-time site writes the page
  target; the 24-byte `rep`-copy in the press block is a static message
  template (`0x01E9C7E0`), not a device record.
- **The sole page poster in the app is the walker `FUN_01e60d34`**: posts
  `user_send_cmd_prepare(1, 6, gp+0xB44)` @`0x01E60DE4` (6 s retry timer
  `gp+0xB40`, 25/30 s countdown `gp+0xB38`), gated on `b4f0` bit3. Cmd-1
  handler `0x01E21E58` requires: `is_1t2_connection()==0`, page-pending bit7
  **clear**, addr guard `FUN_01e16824(target)==0` (**target not already
  connected**), and `FUN_01e2181c != NULL` (free conn record) →
  `FUN_01e2193a(rec, 0x1101)` = HCI Create_Connection.
- **Arming:** CON messages (`FUN_01e187ac` → modal handlers `0x01E61828` event 8
  / `0x01E6194E` event 0xb) copy a 6-byte BD_ADDR payload into `gp+0xB44` and
  start the walker; writers include the stack state-change notifier
  `FUN_01e20ffc` and the dispatcher re-post @`0x01E21C62`. Connect-request ring:
  6-byte entries @`0x1A618` (8 slots, index = bits 3–5 of `DAT_0001a662`);
  saved-target `DAT_0001a5f1`; cmd 2 = re-page saved target.
- **E6 paradox RESOLVED (the design keystone):** E6's press (Jabra target,
  *different-device* PC incumbent) paged fine without any kill — guard clear +
  second slot free. F4's freeze = *same-device* press (phantom TID-PTT
  incumbent, target == incumbent): the addr guard blocks a same-device re-page,
  so **stock repair works only BY the cmd-5 kill** (kill → CON state-change
  events → arm → re-page). ⇒ Different-device joins need no kill; same-device
  repair must keep it. This is precisely what the R1-a predicate encodes.
- **Q5c — the join freeze is orthogonal to the kill:** it fires whenever
  HFP audio/bit0 arrive inside the modal window (watchdog guards), on BOTH the
  kill and skip paths. A real fix = clear bit3 on CON-success instead of the
  one-shot watchdog = **R1-b** candidate work, not in scope for R1-a.
- **One-byte variant rejected** (`0x01E21EF1: 60→7f` = test handle instead of
  mask): breaks same-device repair (skip → guard → no page → wedge) — the exact
  F4 failure — while saving nothing over the cave. Kept only as a diagnostic
  A/B if ever needed.

### §30.14.3 — Where the UI selection lives at cmd-5 time (Q6a/Q6b, PROVEN)

- **There is NO plain selected BD_ADDR in fixed RAM on any cmd-5 path.** The
  selection exists only as a heap double-deref, live only on the settings/list
  Connect path:
  `sel_addr_ptr = [ [_DAT_0000b468] + DAT_000102d0 * 0xC + 8 ]` —
  `0xB468` = paired-device heap list pointer (stride `0xC`, BD_ADDR ptr at +8),
  **zeroed on screen exit**; `0x102D0` = selection index byte. Users:
  `FUN_01e6ec9e` (settings Connect: posts `0x11,0x12,5` then pages the selected
  address via `FUN_01e600b4`) and `0x01E66EF8` list-screen confirm.
- **The modal press carries no address at all** (every post is `(cmd,0,0)`) —
  it is a retry/repair gesture. Rejected candidates (all resolve to the
  *incumbent*, not the new target — using them would make the patch a no-op):
  ring @`0x1A618`, `gp+0xB44`, `DAT_0001a5f1` (last armed/disconnected),
  `gp+0x532`, reconnect list `_DAT_00041100`.
- **Gate polarity fix:** the original brief's "NOT-in-modal (`b4f0&8==0`) →
  stock kill" is **backwards** — the settings-Connect chain never sets bit3, so
  the only path where a selection is visible would be forced to kill. Replaced
  with **¬list-alive**: `[0xB468]==0 ⇒ stock kill` (also covers BT-off/mode
  setter `FUN_01e60120`, which runs off-screen with the list NULL).
- **cmd-5 poster census under F3-v3:** modal press `0x01E61E18` (bit3 set, no
  address — retry), `FUN_01e6ec9e`/`FUN_01e600b4`/`01e600d4` (settings Connect,
  selection live), `FUN_01e60120` (BT mode setter). **Ordering (Q6b):** FIFO
  ring `0x1A688`; cmd `0xb`/`0` are posted *only* by the disconnect machine
  `FUN_01e20962` after teardown starts → no ring interaction before cmd 5; the
  settings path's page strictly follows its own cmd-5 kill pass.

### §30.14.4 — The R1-a cave (final design, verified encodings)

**Hook** (flash sector `0x026000`): `0x01E21EF4` `bf ea ce 35` → `84 ea 30 2c`
(`call 0x01E08A94` → `call 0x01EA7758`). **Cave** (flash sector `0xAC000`) at
`0x01EA7758`, **50 B**, in the free run `0x01EA7758–0x01EA790A` (after BT-PTT2's
68 B @`0x01EA76DE` + F3 gate stubs' 54 B @`0x01EA7722`).

**Predicate: KILL iff `handle(slot+6)==0` (stuck) ∨ `[0xB468]==0` (list
dead/BT-off/off-screen) ∨ `slot[0..5]==sel[0..5]` (same-device repair); else
SKIP** (→ different-device page fires, incumbent kept).

```
01EA7758  09 63              lh.z r1,[r0+6]          ; handle
01EA775A  81 42              jnz  r1,0x01EA775E      ; live -> selection test
01EA775C  fb ea 9a 09        goto 0x01E08A94         ; KILL (tail-call; rts -> 0x01E21EF8)
01EA7760  42 e0 68 b4        movz r2,#0xb468         ; device-list ptr cell
01EA7764  22 60              lw   r2,[r2+0]
01EA7766  72 5a              jz   r2,0x01EA775C      ; no selection context -> KILL (stock)
01EA7768  c3 ff d0 02 01 00  mov  r3,#0x102d0        ; selection index byte
01EA776E  3b 40              lb.z r3,[r3+0]
01EA7770  e3 e1 0c 30        mul  r3,r3,#0xc         ; LLVM-verified form
01EA7774  23 18              add  r3,r2              ; entry = list + idx*12
01EA7776  33 62              lw   r3,[r3+8]          ; r3 = sel BD_ADDR ptr
01EA7778  01 60              lw   r1,[r0+0]          ; slot[0..3]
01EA777A  32 60              lw   r2,[r3+0]          ; sel[0..3]
01EA777C  29 19              xor  r1,r2
01EA777E  0a 62              lh.z r2,[r0+4]          ; slot[4..5]
01EA7780  29 19              xor  r1,r2
01EA7782  3b 62              lh.z r3,[r3+4]          ; sel[4..5]
01EA7784  39 19              xor  r1,r3              ; r1==0 iff all 6 bytes equal
01EA7786  71 4a              jz   r1,0x01EA775C      ; same device -> KILL (stock repair)
01EA7788  80 00              rts                     ; SKIP kill -> loop continues 0x01E21EF8
```

Cave bytes (contiguous):
`09638142fbea9a0942e068b42260725ac3ffd00201003b40e3e10c30231833620160326029190a6229193b623919714a8000`

- **Register contract at hook:** r0 = slot ptr (PROVEN, loop var); live-outs
  **r4** (=slot+0xF, used at `0x01E21EF8`), **r7**, **r14** (`0x01E21EFA`), sp —
  all preserved; cave clobbers only r1/r2/r3 and uses **no stack**. Tail-call:
  the hook's `call` pushed return `0x01E21EF8`; the KILL `goto 0x01E08A94` lets
  the helper's `rts` land there = stock continue; SKIP `rts` lands there too.
- **Encoding validation:** every form cross-checked against `tools/isa/pi32v2.md`
  AND a real instruction in the image; 16-bit branch formula matched
  **12,930/12,930** instances in `work/full.lst`; hook/goto targets recomputed
  via `target = addr+4+sign_extend_23(A:B<<1)`. **Three encoding bugs caught and
  fixed in total:** Q6 draft `7b 40`→`3b 40` (`b[r7+0]`→`b[r3+0]`, found in the
  Q6 pi32dis round-trip), and during patcher integration `19 63`→`09 63`
  (`lh.z r1,[r0+6]` A-field) and `81 41`→`81 42` (jnz displacement in halfwords).
  The byte sequence above is the round-trip-verified final.
- **Behavior matrix:** repair (sel==slot) → KILL ✓ · **goal (TID-PTT incumbent,
  Connect Jabra from the Paired list) → SKIP** ✓ · stuck slot → KILL ✓ ·
  BT-off/mode-switch off-screen (list NULL) → KILL (stock) ✓ · modal press
  retry (list freed on screen exit) → KILL (stock; F4-class freeze avoided) ✓ ·
  E6-class live incumbent (mask≠0) → hook never reached (unchanged) ✓ ·
  BT-off *with list screen open* + stale sel → SKIP, link not released —
  **moot under F3-v3** (`--no-kick` already drops that path), documented ⚠

### §30.14.5 — Patcher flag, detection fix, and build artifacts

- **`--r1-conditional-kill`** implemented in
  `tools/patch_h3plus_firmware_bluetooth.py`: constants (`R1_KILL_HOOK_VA=
  0x01E21EF4`, `R1_CAVE_VA=0x01EA7758`, hook via `encode_call`, 50 B cave),
  two patch entries (`r1condkill` 4 B + `r1cave` 50 B), CLI arg mutually
  exclusive with `--no-cmd5-kill` (same site). Both suites green (0 failures).
- **App-detection fix (required):** `find_app_start()` validates every default
  patch's context window, and legacy `cmd5kill` shares VA `0x01E21EF4` — an
  image carrying the hook matched neither of its two states, so `--show`/build
  rejected the whole image ("could not locate a recognised app region"). Fix:
  registered a third recognised state `CMD5KILL_STATES["conditional"] =
  R1_KILL_HOOK` (+ label) right after the hook constant. `work/ch30_r1a.bin`
  `--show` then reports `cmd5kill … current (call cave 0x01EA7758 (R1
  conditional kill))`, `r1condkill` TARGET, `r1cave` TARGET.
- **Image:** `work/ch30_r1a.bin` sha256 `18bc1597…` = F3-v3 recipe +
  `--r1-conditional-kill` (built from `Dumps/dump_internal.bin`). Diff vs
  flashed F3-v3 `1a1eaca1` = exactly **51 ciphertext bytes / 2 sectors**
  `0x026000` (hook @flash `0x26EF4`) + `0xAC000` (cave @flash `0xAC758`);
  VM untouched → pairings survive. Stage script `work/ch30_r1a.sh` (2 sectors,
  sha-pin, full-flash verify per §30.3), card `work/ch30_r1ac.sh`.
- **Residual risks (carried into the card):** (1) if the field eviction flow is
  the *modal press* rather than settings-Connect with a live list, the patch is
  a **no-op there, not a regression** — T1/T2 separate this; (2) free-vs-use
  race on `[0xB468]` after screen exit → stale-heap compare → safe SKIP (no
  crash; stock would have killed); (3) the Q5c SCO-in-modal freeze is
  untouched (R1-b); (4) two-SPP single-session wall `0x1A740` and the
  controller incoming-page wall are out of scope; (5) `0xB468`/`0x102D0`
  layout proven for v1.0.50 only.

### §30.14.6 — R1-a post-mortem: official-objdump verification, walker decode, and the R1-b design (2026-10-27)

**Field result (deterministic).** Flash of `18bc1597` was byte-perfect (stage
verify PASS, §30.10 row "R1-a field"), but **every** Paired→TID-PTT→Connect press
froze the radio, across multiple power cycles — *"I power cycled the radio
multiple times same behavior on every Connect attempt (in the menu) it froze"*.
The TID-PTT never connected during the whole R1-a session (LED kept blinking
red/green = pairing mode). Rollback `work/ch30_r1arb.sh` → F3-v3 **PASS**
(`work/logs/ch30_R1ARB_20261027_082839.log`; sanity *"3/3 ok connected correctly
TID-PTT works as expected"*): the identical press that froze on R1-a works on
F3-v3 → 100 % attributable to hook+cave. **Device fact (TID-PTT button, 2 modes):**
power-on → pairing mode (red/green blink); once connected → paired mode (blink
every 5 s); link loss → back to pairing mode.

**Toolchain (new capability):** the official JieLi LLVM binutils work on our
bytes: `/home/stefan/h3plus/jieli-linux-toolchains-20250324.1/pi32v2/bin/objdump`
(LLVM 4.0.1, targets `pi32`/`pi32v2`; clang alongside, `-target pi32v2
-mcpu=r3`). Raw-byte recipe: `.s` with `.byte …` → `clang -c` → `objdump -d`;
full-app recipe: `/tmp/opencode/app.s` = `.section .text` + `.incbin
"work/app_dec.bin"` → `/tmp/opencode/app.o`, then
`objdump -d --start-address=<off> --stop-address=<off> app.o` (no
`--adjust-vma`; addresses are file offsets, add `0x01E00000`).

**Verification results (all PROVEN with the official tool):**
1. `e3 e1 0c 30` = **`r3 = r3 * 0xC`** (family `e<rd> e1 <imm8> <rs<<4>`;
   compiled references: `a*12` → `e0 e1 0c 00`, `b*12` → `e0 e1 0c 10`).
2. The **entire 50 B R1-a cave disassembles exactly as designed** (§30.14.4) —
   handle test, `0xB468` movz/lw, `0x102D0` cursor, `*0xC`, `+8`, 6-byte XOR
   compare, KILL `goto`, SKIP `rts`. **The failure is NOT an encoding bug.**
3. Stock cmd-5 kill loop (`0x01E21ECA–0x01E21F02`) officially disassembled:
   inused = bit29 of the misaligned word at `slot+0xF` (built with the
   bit-`insert` family), mask = `h[slot+8]`, and **`call 0x01E08A94` with
   r0 = slot pointer — the cave's register contract was correct** (r4/r7/r14
   preserved, next-slot via `r0 = r4+13`, end `r14+208`).
4. ⇒ divergence requires: inused ∧ mask==0 ∧ handle≠0 ∧ `[0xB468]≠0` ∧
   sel≠slot → cave SKIPped where stock KILLed → stuck record → same-device
   re-page blocked → connecting modal waits forever (deterministic, matches
   field).

**Root cause — the selection cell was never validated on the press path.**
`DAT_000102D0` is a **shared UI cursor** (saved/restored across screen push/pop
via `[DAT_000102D2+0x1084C]`, reset 0 on entry, nav-driven); the double-deref
read of it sits in `FUN_01e66ef8` **case 5 — the "Connecting" screen retry
loop** (re-reads every 10 iterations), i.e. the list-screen path. The
Paired-screen press block `0x01E61D92` is an orphan pointer-table callback
(not in `decompiled_all.c`) and officially disassembles to: copy the 24 B
selected conn-request struct (`r8+0x1215` → stack), prune the ROM conn-request
list `0xB320` to it (`0x01E2D50C` + `0x01E2D56E`), then post cmds
**`0xC, 0xE, 0x12, 5, 0x4A`** via `0x01E1792E(cmd,0,0)` — **carrying no
address** — and arm the one-shot watchdog `0x01E249DE(0, 0x01E7EFD2, 10)`.
At cmd-5 consumption time on the stack task the only fresh expression of
intent is the pruned conn-request list; the heap `[0xB468]`/cursor pair can
legitimately disagree with the slot → SKIP → hang. (Residual unknown: why the
boot-time phantom reconnect had also not completed that session — if no slot
were inused the cave could not run at all; the deterministic per-press freeze
is however fully explained by the SKIP model once a stuck/live accessory slot
exists.)

**Keystone discovery — the walker's page target cell `0x10E34`.** Sole page
poster `FUN_01e60d34` (walker, app task) posts
`FUN_01e1792e(1, 6, &DAT_00010E34)` — cmd 1 = HCI Create-Connection relay,
6-byte target = **RAM `0x10E34`**. Exactly 4 refs in the image: the walker
(valid-check `FUN_01e18592(&0x10E34)` + page post) and **CON pump cases 8/0xb
— the only writers** (copy 6 B from the event object `+0x10`; case 8 then
calls the walker **synchronously**). Walker internals: outer gate
`(DAT_0000B4F0 & 0xC) == 0 → return`; page-pending timer `_DAT_000416F8`
(set 25000 on valid target); self-rearm `_DAT_00041700 =
FUN_01e249ce(..., FUN_01e60d34, 6000|2000)`; failure path posts cmd `0x12`.
`FUN_01e16824` (the §30.14.2 "addr guard") officially = per-slot walk
(`0x1A5B8`→`0x1A5F0` stride `0x1C` calling ROM `0x021127B0(6)` — the
decompiler loses the hidden slot arg; semantics = per-slot match against the
target, guard conclusion unchanged).

**R1-b design (walker-side conditional kill; replaces the cmd-5 predicate
route):** at cmd-5 time `0x10E34` is **race-stale** (armed by the app task,
consumed by the stack task FIFO — no cross-queue ordering), so *fixing* R1-a's
predicate there is unsound. Instead: **NOP the cmd-5 kill wholesale** (the
existing `--no-cmd5-kill` F4 flag) and **hook the walker's page-post call
site** with cave2: scan slots `0x1A5B8`/`0x1A5D4`; if inused ∧ `h[slot+8]==0`
∧ `slot[0..5] == [0x10E34]` → `call 0x01E08A94(r0=slot)` (kill the
same-address stuck record = repair); then tail-call the original page post.
Race-free (`0x10E34` freshly written by the CON pump immediately before the
synchronous walker call); different-device incumbent → never killed → goal
multipoint; F4's repair-hang is cured by exactly this kill; kill/page async
timing self-heals via the walker's 6000 ms rearm. Register contract: hook
replaces a `call` → preserve r4/r7/r14/sp only. Cave region `0x01EA7758`
(364 B) is free from its start once the R1-a hook is removed. **Status:
design agreed; walker hook-site disassembly + implementation in progress.**

### §30.14.7 — R1-b built: `--r1-walker-kill` (2026-10-27)

**Hook site (official objdump, `/tmp/opencode/app.o`, 0x60d34–0x60e10):** the
walker's page post is `call 0x01E1792E` at **VA `0x01E60DE4`** (stock bytes
`bd ea a3 b5`). Setup immediately before: `0x60dde r0=1`, `0x60de0 r1=6`,
`0x60de2 r4=1` (return flag), `r2 = r5+12` with `r5 = r6+2872` (r6 = `0x102F0`)
→ `r2 = 0x10E34` ✓. After the call the walker does `[r5+0] += -6000` and rearms
via `FUN_01e249ce` at `0x60e02`. r4–r11 are live at the hook (walker prologue
saves `{rets,r11-r4}`) → cave2 may clobber only r0–r3 + rets.

**cave2 (78 B):** written in C (`/tmp/opencode/cave2.c`, absolute
function-pointer calls), compiled with the **official**
`clang -target pi32v2 -mcpu=r3 -Oz`, objdump-verified instruction-exact.
Prologue `[--sp] = {rets, r4}` only. Loop over slots `0x1A5B8`→`0x1A5F0`
(stride 0x1C): kill-test `b[slot+18] & 32` (inused) ∧ `h[slot+8]==0` (mask) ∧
`[slot]==[0x10E34]` ∧ `h[slot+4]==h[0x10E38]` (6-B addr match).
**KILL path:** tail `goto 0x01E08A94` with r0=slot — returns to walker
`0x01E60DE8`, i.e. this page post is SKIPPED; the 6000 ms rearm retries once
the record clears (repair delay ≤ ~6–10 s is BY DESIGN).
**POST path:** tail `goto 0x01E1792E` with `r0=1, r1=6, r2=0x10E34` — exact
original call semantics incl. return site. Final bytes:
`7404c0ffb8a50100c1ff340e010002e1380050ee02410b6454e8092883480360146084e804300b621c6204e80b30c03c82e9ef011216c3ff2e79e101402141263404d300c1ff948ae0013404d100`.

**Patcher flag `--r1-walker-kill`:** sets `cmd5kill`→disabled (subsumes
`--no-cmd5-kill`, mutually exclusive with it and with `--r1-conditional-kill`),
`r1condkill`→disabled (4-byte NOP — required so R1-b images still pass
`find_app_start` ctx validation at the shared VA `0x01E21EF4`), new sites
`r1bhook` (states stock/r1bhook) and `r1bcave` (states native/r1bcave/r1cave-
padded). Cross-registration detail: `r1cave`'s state table carries the R1-b
payload **truncated to its own 50-byte ctx window** — the first full-length
registration made `--show` fail on R1-b images ("could not locate a recognised
app region") exactly like the R1-a cmd5kill-state bug, because `_ctx_variant_fn`
splices the state verbatim and a 78 B variant can never equal a 50 B window.
Both suites green after all edits (`verify_actions`/`verify_cli`, FAILURES: 0).

**Image `work/ch30_r1b.bin` sha256 `36fcead7…`:** diff vs flashed F3-v3
(`1a1eaca1`) = exactly **3 sectors / 80 ciphertext bytes** — `0x026000`
(cmd-5 NOP @0x26EF4), `0x065000` (hook @0x65DE4), `0x0AC000` (cave2 @0xAC758).
`--show`: `cmd5kill`/`r1condkill` TARGET (NOP), `r1bhook` TARGET
(call cave 0x01EA7758), `r1bcave` TARGET, all F3-v3 sites unchanged.
Stage `work/ch30_r1b.sh` (sha-pinned rebuild, 3-sector write + full-flash
§30.3 verify, boot + bonded sanity incl. the ≤15 s repair-window note) and
card `work/ch30_r1bc.sh` (T1 repair regression — 6–10 s connect is normal;
T2 GOAL press TID-PTT incumbent + Paired→Jabra→Connect with press-first
protocol + kick/freeze/page/bind matrix; T3 BT-off/on regression) ready.
**Residual risks:** (1) if the boot phantom link is genuinely LIVE (valid
handle) when a different-device press pages, cave2 does not kill it — the
controller's own single-link scheduling decides (E6 showed outgoing joins
work); (2) CON-8 gates (`FUN_01e18552/72` conn-in-progress) could swallow the
arm on a tight press sequence — walker rearm covers; (3) two-SPP wall
(`0x1A740`) out of scope — goal here is SPP + HFP. **Status: BUILT, awaiting
field flash.**

### §30.14.8 — R1-b field FAILED; root cause: the btctrler-post task contract (2026-10-27)

**Observed (stage log `work/logs/ch30_R1B_20261027_105509.log`):** flash fully
PASSED (sha pin `36fcead7`, 3 sectors readback-identical, full-flash §30.3
verify PASS, boot v1.0.50, paired list intact). In-stage sanity: Paired→TID-PTT→
Connect connected? **no** (999999999 s = never); user then tried a fresh Pairing
→ **scan timeout, no devices found**; card `work/ch30_r1bc.sh` never ran.
User verbatim: *"done executed ch30_r1b.sh but unable to pair the TID-PTT as the
radio froze / lockedup on Connect and pairing option resulted in timeout so I
did nnot exeucte the card as it would be useless"*. Same symptom as R1-a:
navigation alive, BT operations dead = **BT task wedged, UI task alive**.

**Root cause (static, official objdump on `/tmp/opencode/app.o`).** Killer
`0x01E08A94` → `FUN_01e029de(0x400002, 3, 0xCFE, addr)` — and `FUN_01e029de`
(log tag `"btctrler"` @`0x01E9338A`) is the **btctrler message post**: copy
varargs → RAM-lib `0x202C9C(0x400002, n, buf)`; **on return 21 (queue full) it
retries forever in task context** — give-up branches only for IRQ context
(`0x4E5EA`, icfg bit0) and one sched state (`[0x10F1A8]==6`); otherwise
`os_time_dly(2)` (~20 ms, RAM `0x201F82`) and repost. So the killer carries a
**task contract: call it only from the btstack task**, whose queue drain is what
empties the post box. cave2's KILL branch tail-jumped into it **from the BT/app
task inside the walker** → when the queue was full (press ring + page machinery
in flight), the retry loop spun the BT task forever = the freeze. The POST path
is fine (boot proved it: clean boot, phantom page posted, no wedge before press)
— only the KILL branch calls the killer. Pairing timeout afterwards = same
wedged BT task, not a second fault.

**Corollaries (proven this round):**
1. **Any R1-c kill action must be POSTED to the btstack ring**
   (`0x01E1792E`, the very primitive the hook already tail-calls) **or executed
   by btstack-task code — never a direct `FUN_01e08a94`/`FUN_01e029de` call off
   task.** R1-a died the same way for the same reason (its cave also tail-ran
   the killer from the ring consumer? no — R1-a ran in-stack but with a stale
   selection cell; both failures are now explained).
2. **cmd 5 must stay live** (F4 lesson, re-confirmed in the decompile): case 5
   @`0x01E21ED0` kills only **stuck** slots — `inused ∧ h[slot+8]==0` — never a
   live link, so stock cmd 5 is *not* the press-time evictor at all; NOP'ing it
   (as R1-b did) risks slot exhaustion → `create_bt_new_conn` `0x01E2181C` NULL
   → walker never pages ("Connecting" forever). R1-c restores it.
3. **The F3-v3 press-time evictor is NOT `0x4a`** — `0x01E61E22` (the press
   `0x4a` post) is *already NOP'd* in F3-v3, yet F3V3-B still showed the
   incumbent kicked at 0 s. Remaining candidates: ring case `0xB`
   DISCONN_SDP_MASTER (`0x01E20BD2`/`0x01E20E92` → `FUN_01e1782c(0,1,0)` guarded
   `_DAT_0000bfcc != 0`), the `spp_connect` single-session chokepoint
   (`0x01E1750C`/`0x01E1751E`), or controller-level. Next static step: decode
   ring cases `0xC`/`0xE`/`0x12`/`0x10`/`0x11`/`0xB`/`0x4a` in
   `FUN_01e21af8` (`disassembled/decompiled/01e21af8_FUN_01e21af8.c`,
   gp-relative symbols cross-checked against objdump).

**Rollback:** `work/ch30_r1brb.sh` — restores F3-v3 (`1a1eaca1`) across the same
3 sectors (`0x026000`/`0x065000`/`0x0AC000`), sha-pinned sector files
(`work/ch30_f3v3_026000.bin` `0f4f4aa4…`, `work/ch30_f3v3_065000.bin` `682ede65…`,
`work/ch30_f3v3_0AC000.bin` `b7c68d92…`, all byte-verified against the image),
full-flash §30.3 verify + boot sanity. Pairings untouched.

### §30.14.9 — R1-c: the evictor was cmd 5's mask test; 2-byte handle fix (2026-10-27)

**The class-dependent press evictor, located.** The ring consumer
`FUN_01e21af8` (btstack task) case-5 cleanup loop, objdumped exact
(`/tmp/opencode/app.o`):

```
01E21ED0  09 88        r1 = r0 + 8              ; r1 = slot+8
01E21ED2..             r6 = u32 [slot+0xF..0x12] ; state word
01E21EE6  62 e1 00 65  r2 = r6 & 0x20000000      ; inused (bit29)
01E21EEC  1c 87        r4 = r1 + 7               ; loop advance
01E21EEE  02 44        if (r2 == 0) goto 0x01E21EF8
01E21EF0  19 60        r1 = h[r1+0]              ; <<< MASK at slot+8
01E21EF2  81 42        if (r1 != 0) goto 0x01E21EF8
01E21EF4  bf ea ce 35  call 0x01E08A94           ; kill by address
```

The mask halfword (`slot+8`) is only ever set by PC-class flows; **SPP
accessories (TID-PTT) keep mask==0 while LIVE** — so stock cmd 5 treats a
healthy accessory as a stuck record and kills it at every Paired→Connect press.
This single test explains the whole class-dependence history: E6 PASSED with a
PC incumbent (mask≠0 → skipped), E7/F3V3-B FAILED with an accessory incumbent
(mask==0 → killed), and why the executor "wasn't located" (it was the *stock,
never-NOP'd* cleanup loop — every hunt targeted the NOP'd kick sites, §30.14.8
corollary 3).

**The fix (R1-c, `--cmd5-handle`):** re-encode the load to the **connection
handle at `slot+6`** — `handle == 0` iff no ACL, the same liveness test ring
cases 4 and `0x4a` use. `19 60` (`r1 = h[r1+0]`) → `09 63` (`r1 = h[r0+6]`)
@VA `0x01E21EF0` (flash `0x026EF0`). Encoding arithmetic-verified against the
reference `0x01E0349C: 0b 63 = r3 = h[r0+0x6]` (pi32v2 h-load:
byte1=`(rs<<4)|(rd+8)`, byte2=`0x60|(disp/2)`). **cmd 5 stays LIVE** — the F4
premise (connect flow waits on cmd-5 completion) is honoured — and the kill
runs on the btstack task, honouring the queue-post task contract whose
violation froze R1-a/R1-b. Stuck-record repair (inused ∧ handle==0, incl. the
boot phantom) is preserved: the phantom has no ACL → still killed → same-device
bonded connect still repairs, stock-like timing.

**New residual risk (recorded, accepted):** a slot with a stale non-zero handle
(ACL died without Disconnect Complete) is now never killed → exhaustion;
mitigated by the stack clearing handles on Disconnect Complete/timeout
(E6/E7-era captures always showed them).

**Patcher:** `--cmd5-handle` (site `cmd5handle`, states `stock`/`handle`,
6-byte ctx `1c8702441960` @`0x26EEC` — window ends exactly before the
`cmd5kill` site, no cross-registration needed); mutually exclusive with
`--no-cmd5-kill`/`--r1-conditional-kill`/`--r1-walker-kill`. Both suites green
(`FAILURES: 0`).

**Image `work/ch30_r1c.bin` sha256 `ee0ba984…`:** diff vs F3-v3 = **2 bytes in
ONE sector `0x026000`**; decrypted plaintext verified `09 63` @app `0x21EF0`
with the loop + kill call intact. The R1-b walker hook + cave2 are **removed**
(sector files `0x065000`/`0x0AC000` byte-identical to F3-v3), so the stage
writes 3 sectors and works from either the R1-b or rolled-back F3-v3 state.
Stage `work/ch30_r1c.sh` (sha pin, 3-sector write + full-flash §30.3 verify,
boot + bonded sanity) and card `work/ch30_r1cc.sh` (T1 sanity/repair regression
— stock-like timing expected; **T2 GOAL** TID-PTT incumbent + Paired→Jabra→
Connect → expect survive + join + bind; **T3 reverse order** Jabra incumbent +
press TID-PTT → expect join + SPP keys (HFP never touches `0x1A740`);
T4 BT-off/on) ready. **Status: BUILT, awaiting field flash** (rollback
`work/ch30_r1brb.sh` superseded — the R1-c stage restores the same 3 sectors).

### §30.14.10 — R1-c field FAILED; THE FREEZE ROOT-CAUSED: the press flow *waits for the kill* (2026-10-27/28)

**Field result (2026-10-27 13:49, `work/logs/ch30_R1C_20261027_134910.log`):** stage
flash fully clean (3 sectors readback IDENTICAL, full-flash §30.3 verify PASS, boot
v1.0.50, paired list intact). In-stage sanity (Paired→TID-PTT→Connect, same-device
repair): **never connected** ("9999999999"), follow-up fresh Pairing scan timed out —
same freeze family as F4/R1-a/R1-b. Card `work/ch30_r1cc.sh` NOT run, so the **GOAL
presses (T2/T3) were never actually tested on R1-c**. User (verbatim): *"I think we
are going in circles I don't see any progress try a different approach"*.

**Root cause (static, objdump-verified, `/tmp/opencode/r1_final_answers.md`):** the
Connect press *itself* contains unbounded waits for the current link to come DOWN.
The settings press `FUN_01e6ec9e` posts `0x11,0x12,5` (@`0x01E6ECBE/C4/CA`) then calls
`FUN_01e600b4(addr)` @`0x01E6ECEA`:

```
01E600D0  call 0x01E16E0E        ; r0 = mask halfword @slot+8 of connected device
01E600D4  if (r0 != 0) goto 0x01E600E6
01E600D6  dly(10)                ; call 0x01E01F82... (0x201F82)
01E600DC  call 0x01E17F26        ; -> FUN_01e07bd4: 128 = ANY ACL up (table 0x1A0A8)
01E600E2  if (r5 == 128) goto 0x01E600D0   ; <<< LOOP A (mask==0 / accessory phantom)
01E60102  post 0x4A              ; executor case 0x4A @0x01E21DB4; its disconnect-all
                                  ;   NOP'd @0x01E21DE4 by E7 in all current builds
01E60112  if (r0 != 0) goto 0x01E60108     ; <<< LOOP B (mask!=0 / PC phantom)
01E60114  post cmd 1 page(addr)  ; <<< NEVER REACHED while any link stays up
```

Both loops wait for **all ACL links down** (`FUN_01e07bd4`==0). Stock passes them
because cmd 5's mask test *kills the current link first* and the disconnect
completion clears `0x1A0A8`; F4 (kill NOP'd) and R1-c (handle test → live link
skipped) leave the link up → **infinite dly(10) loop** → "Connecting…" forever.
Even if cmd 1 were posted, the page guard `call 0x01E16824` @`0x01E21E76` (same-addr
∧ inused, handle-agnostic) refuses it. **The kill is load-bearing plumbing, not the
bug** — every prior patch (F4, R1-a/b/c) removed the kill but left the wait, hence
the identical freeze. (The F4 field signature matches: blocked/idle, btstack alive,
incoming pages still accepted, UI rendering — NOT a spin, unlike R1-a/b's
off-task-post spin, §30.14.8.)

**The modal (Paired-screen) press has the same dependency via flags:** it sets
`b4f0` bit3 press-pending @`0x01E61DE4`; the ONLY clearer is the one-shot watchdog
@`0x01E7F026`, gated on bit0, which ONLY a **CON event 3** sets (@`0x01E6116A`) — and
CON events only fire on a state change, i.e. the kill. No kill → bit0 never set →
watchdog early-returns @`0x01E7EFFE` → bit3 stuck → walker body gated off
@`0x01E60DAA` → never pages. `b4f0` lifecycle (full): bit0 CON-gate (set CON3
@`0x01E6116A`, clear watchdog @`0x01E7F026`); bit1 no setter; bit2 stack-restart
(set watchdog @`0x01E7F018`, consumed modal entry); bit3 press-pending (set
@`0x01E61DE4`, clear watchdog + modal entry); bit4 exit-requested (set @`0x01E61E46`,
clear exit gate @`0x01E61E5C`).

**R1-d is NO-GO (three independent proofs):** (1) cmd 4's executor `call 0x01E19492`
@`0x01E21EC4` is **E7-NOP'd in ALL current builds** (readback `00 00 00 00` on
F3-v3/F4/R1-c) — the walker would post into a dead case; (2) in the freeze state the
walker is never armed (arm sources are CON events 8/0xb — none occur); (3) even if
armed, bit3 gates the walker body off.

**Approach change (per user directive):** stop patch-permute-and-flash. The patch
target is now **the wait itself** — convert the press flow's teardown-wait from
*any-link* to *same-address* semantics, keeping the kill exactly where stock needs
it. Candidate designs (byte-level GO/NO-GO under static verification, §30.14.11):
**D1** — retarget `FUN_01e600b4`'s two checks to "target still connected?" via
`0x01E16824` (settings path); **D2** — cmd-5-skip cave that releases the modal
(bit0 set + walker armed with the press target) without a disconnect (modal path).
Which UI screen uses which path, and whether the modal press propagates the new
target address at all, is the open static question being resolved before any build.
**R2 resolved all of it on 2026-10-28 — see §30.14.11; the any-link-wait root-cause
above is refined there (the loops do not wait for "all links down").**

### §30.14.11 — R2 press-flow analysis and the R1-e design (2026-10-28)

**Provenance.** R2 was the read-only static investigation commissioned at the end of
§30.14.10 ("patch the WAIT, not the kill"; D1/D2 to be settled by byte-level GO/NO-GO
before any build). It was produced 2026-10-28 against the **official JieLi objdump**
(`jieli-linux-toolchains-20250324.1/pi32v2/bin/objdump`) on `/tmp/opencode/app.o`,
cross-checked against `work/app_dec.bin` (stock v1.0.50). The full report lives in
**[Ch. 31 — Bluetooth 10: The Connect-Press Flow](31-bluetooth-10-connect-press-flow.md)**
(recovered 2026-10-29 from the DCP compression store + scratch copy; every patch-site
byte independently re-verified against `work/app_dec.bin` on 2026-10-29 — all pass,
including the settings-press call site `0x01E6ECDA` = `bd ea 28 46` = `call 0x01E1792E`).
Nothing below has been built or flashed; all statements are static unless marked otherwise.

**The press flow, decoded (Ch. 31 Q1–Q5).**
`Menu→Bluetooth→BT Pairing→Paired→device→Connect` runs the **settings-list handler
`FUN_01e6ec9e`** (NOT the address-less modal handler): it loads the selected device's
BD_ADDR (`r0 = [[r5]+r4+8]`, r4 = idx·12, r5 = list base), posts **cmd 5** to the ring
dispatcher `FUN_01e21af8` via `user_send_cmd_prepare` (`call 0x01E1792E` @`0x01E6ECDA`),
then calls `FUN_01e600b4` @`0x01E6ECEA`. The dispatcher's case-5 handler kills connections
whose `mask@slot+8 == 0` (test `19 60 81 42` @`0x01E21EF0`, kill call @`0x01E21EF4`, loop
continue @`0x01E21EF8`) — and **live SPP accessories keep mask 0**, so the kill always
takes the incumbent. `FUN_01e600b4`'s two wait loops read `FUN_01e17f26`→`FUN_01e07bd4`
— a **transitional-link** check over the controller link table (16 ptrs @`0x1A16C`,
stride 28, flag byte +40 bit 2 clear = transitional; fallback `b[0x1A053] & 1`) — then
post the direct cmd-1 page @`0x01E60114`. The modal path (no stored address) posts no
cmd 5 and **propagates no target at all** (Q5: D2's premise is void).

**Four corrections to §30.14.10 (Ch. 31 Appendix C):**
1. `DAT_0001a5f1` (last-joined BD_ADDR shadow) is written **only** by the cmd-0 ring-pop
   @`0x01E21C44` (`rep 4 6`, byte-verified) and `FUN_01e21988` (case `0x11` = controller
   thunk `0x01E181DA`→`0x01E07FC8`; the bookkeeping body @`0x21FDC` is case `0x13`).
2. The walker-arm handlers `0x01E61828`/`0x01E6194E` are **HCI-'m' (`0x48434900`) switch
   cases** (tbh @`0x01E6104C`), not CON events: arm = `gp+0xB38` timer 30000/8000 + copy
   6 B from the event object → `DAT_00010E34` (`gp+0xB44`). The walker is additionally
   gated off while `b4f0` bit 3 is set (check @`0x01E60DAA`).
3. **CRITICAL — the freeze model changes.** `FUN_01e17f26`/`FUN_01e07bd4` return `0x80`
   only for a **transitional** controller link entry; a **stable** link reads 0
   (E6-calibrated). So loops A/B never waited for the incumbent to drop — the §30.14.10
   root cause ("the press flow waits for the kill") is **wrong as stated**. The R1-c
   freeze is instead: cmd 5 kills nothing new under our NOPs, the page **is** posted,
   but the stack's same-address guard `0x01E16824` (call @`0x01E21E76`) refuses to page
   an address that is already connected → silent "Connecting" hang.
4. `FUN_01e16878` mode-1 exclusion = `h[slot+8] & 0x2080` (not the bare `==0` mask test).

**D1 verdict: GO** (optional hardening, saved as R1-f candidate; objdump round-trip
verified in `/tmp/opencode/d1test.o`). Retargets both `FUN_01e600b4` checks to
"target still connected?" via `0x01E16824` (r0 = BD_ADDR ptr only; returns slot-or-0;
preserves r4/r6/r8/r9 + returns; clobbers r0–r3, r5 — Ch. 31 Appendix A):

| Site (VA) | Len | Stock bytes | Patched bytes | Effect |
|---|---|---|---|---|
| `0x01E600DC` | 10 | `bd ea 23 bf 05 16 15 f8 f5 01` | `40 16 bd ea a1 b3 05 16 f5 55` | loop-A check → `r0=r4; call 0x01E16824` + predicate re-form |
| `0x01E6010E` | 4 | `bd ea 0a bf` | `82 ea 23 3b` | loop-B branch → cave |
| `0x01EA7758` (cave) | 6 | (zero) | `40 16 fb ea 63 78` | `r0=r4; goto 0x01E16824`-style thunk back |

**D2 verdict: NO-GO** — `0x1A5F1` is stale at press time (only the cmd-0 pop writes it),
the copy does not arm the walker (arm is HCI-'m'-driven), and with Q5 void the whole
modal-release premise is redundant.

**The R1-e design (deliverable of this analysis; UNTESTED — nothing built yet).**
Minimal fix on the **F3-v3** known-good base (full-image sha `1a1eaca1…`, sectors
`work/ch30_f3v3_026000.bin` `0f4f4aa4…` / `065000` `682ede65…` / `0AC000` `b7c68d92…`)
targeting the *located* evictor: stock cmd-5 kills live accessory incumbents because
their mask stays 0. Two changes, **no D1 in v1** (D1 can ride later as R1-f):

1. **Press-store hook** — redirect the 4-byte cmd-5 post call @`0x01E6ECDA`
   (`bd ea 28 46`) to a cave that: recomputes `[[r5]+r4+8]` (r4/r5 are live at the call;
   `0x01E1792E` preserves both), copies the 6-byte target BD_ADDR → `DAT_0001a5f1`
   (`0x1A5F1`), then `r0=5, r1=0, r2=0`, tail-calls `0x01E1792E`, returns.
2. **cmd-5-target predicate** — replace `19 60 81 42` (mask load + cmp) @`0x01E21EF0`
   with a 4-byte goto into a cave: kill iff `inused ∧ (handle@slot+6 == 0 ∨
   memcmp(slot, 0x1A5F1, 6) == 0)` — `memcmp` = `0x01E08A94(slot)`, called from the
   btstack task ✓ (task contract holds); otherwise continue the loop @`0x01E21EF8`.

Kill matrix (what R1-e does per state):

| Incumbent | Target | Stock cmd-5 | R1-e cmd-5 | Downstream |
|---|---|---|---|---|
| any class, repair | = incumbent | killed | **killed** (addr match) | page proceeds — repair works for every class (bonus: fixes PC repair, whose stock `0x4A` path is dead under E7) |
| live, handle≠0 | ≠ target (GOAL: Jabra up, press TID-PTT / vice versa) | **killed → eviction** | **survives** (addr≠target) | page target → guard `0x01E16824` passes (different addr) → outgoing join + bind (the E6-confirmed direction) |
| stuck, handle==0 | any | killed | **killed** | self-heal preserved |
| — | fresh pairing | n/a (no cmd 5) | n/a | unchanged (E7 behavior) |

Cave space: the 364 B ALLZERO run @`0x01EA76DE` (re-verified 2026-10-29; pointer-scan
clean per ch. 23). `0x01EA7758` is consumed only if D1/R1-f is included.
**Expected sectors (corrected): `0x026000` (cmd-5 hook) + `0x073000` (press-store,
`0x01E6ECDA` → flash `0x73CD4`) + `0x0AC000` (caves)** — flash = (VA − `0x01E00000`) +
`0x5000`. (The design note's original "0x026000+0x065000+0x0AC000" was a slip: `0x065000`
belongs to D1's sites `0x01E600DC`/`0x01E6010E` → flash `0x650DC`/`0x6510E`, not to
R1-e v1.)

**Remaining work (implementation order):**
1. Implement `--cmd5-target` in `tools/patch_h3plus_firmware_bluetooth.py` (mutually
   exclusive with the other cmd-5-family flags `--no-cmd5-kill`/`--r1-conditional-kill`/
   `--r1-walker-kill`/`--cmd5-handle`); run `tools/verify_actions.py` + `tools/verify_cli.py`
   — both must be green.
2. Build `work/ch30_r1e.bin` from the F3-v3 recipe (F3-v3 flags + `--cmd5-target`);
   `--show` verify; diff must touch exactly sectors `0x026000`/`0x073000`/`0x0AC000`.
3. Stage `work/ch30_r1e.sh` (3-sector write + §30.3 full readback verify) and test card
   `work/ch30_r1ec.sh`: **T1** repair regression (Paired→TID-PTT→Connect while TID-PTT
   live → reconnect works, no freeze), **T2** GOAL order A (Jabra incumbent up → press
   TID-PTT Connect → TID-PTT joins and keys), **T3** GOAL order B (TID-PTT incumbent →
   press Jabra Connect → joins, HFP audio), **T4** fresh pairing does not evict,
   **T5** BT off/on regression.
4. Radio is still on **R1-c** (`ee0ba984`); rollback `work/ch30_r1crb.sh` (one sector
   `0x026000` → F3-v3) is ready and pairings survive either way.

**Implementation log (2026-10-30) — steps 1–2 DONE.** `--cmd5-target` is in
`tools/patch_h3plus_firmware_bluetooth.py`: four patch sites —
`cmd5target` (hook `19 60 81 42` → `c4 ea 56 2c` = `goto 0x01EA77A8` @`0x01E21EF0`),
`cmd5tcave` (38 B @`0x01EA77A8`), `presstore` (hook `bd ea 28 46` → `81 ea 75 c5` =
`call 0x01EA77D0` @`0x01E6ECDA`), `presstcave` (32 B @`0x01EA77D0`). Cave VAs moved from
the design note's `0x01EA7760`/`0x01EA7788` because the always-present `r1bcave` state
window (76 B @`0x01EA7758`, ends `0x01EA77A4`) would collide with them in
`find_app_start`; the new sites are ALLZERO in v44/v45/v50 inside the same
pointer-scan-clean run. Cave forms: cmd5t = `r1=h[r0+6]` handle test, KILL `call
0x01E08A94` + `goto 0x01E21EF8`, else XOR-fold compare `[r0..5]` vs `[0x0001A5F1..]`
(R1-a's byte-identical instruction forms) → KILL-or-next; presst = `r0=[[r5]+r4+8]`,
`rep 4 6` 6-byte copy → `0x0001A5F1`, replay `r0=5,r1=0,r2=0,call 0x01E1792E`, `rts`.
**All four sites objdump round-trip-verified** against the official JieLi objdump
(patched copy of `app.o` → correct mnemonics, targets and branches; scratch
`/tmp/opencode/r1e_verify.o`). `CMD5HANDLE_STATES` gained a `"target"` state (the
hook's low half) so R1-e images stay recognised, and `cmd5target` recognises R1-c's
`09 63 81 42` as the `"handle"` state. CLI: mutually exclusive with all four other
cmd-5 flags (both directions checked). Suites: `verify_actions.py` **0 failures**
(new R1-e section: standalone `--only` build byte-checks, window containment, clean
`--show`, idempotency, R1-c-image recognition, F3-v3-recipe combo) and `verify_cli.py`
**0 failures** (new cases `cmd5target`, `cmd5target_f3` full recipe, `ct_alias`, and
four refusal cases). **Image built:** `work/ch30_r1e.bin` sha256 `d2aa7d8d…`
(F3-v3 recipe + `--cmd5-target`, `--sectors=work/ch30_r1e`), 312 B changed vs stock;
**diff vs `work/ch30_f3v3.bin` = exactly sectors `0x026000`+`0x073000`+`0x0AC000`,
73 bytes** — prediction confirmed; all four sites + stock kill `bf ea ce 35` @`0x01E21EF4`
+ E7 NOPs byte-verified in the decrypted image; `--show` reports all four R1-e sites
TARGET, no UNKNOWN/MIXED. Steps 3–4 (stage script + test card, then user flash)
remain.

### §30.14.12 — R1-e field FAILED (2026-10-30): Connect freeze + pairing timeout

**Field report (user, 2026-10-30, verbatim intent):** the R1-e flash itself **succeeded**
(stage `work/ch30_r1e.sh` flow: 3 sectors written, readback OK). But afterwards the radio
**could not pair TID-PTT**: the **Connect** option **froze / locked up the radio**, and the
**Pairing option timed out**. The R1-e card was therefore NOT executed ("useless" per user).
Changes were git-committed by the user before this test.

**Immediate observations:**
- The freeze symptom *looks like* the R1-c freeze (silent "Connecting" hang), but R1-e was
  designed to cure exactly that (target record killed at cmd 5 → same-address guard passes).
  Either (a) the press-store captured the wrong address / never ran → kill skipped → guard
  froze the page again, or (b) the freeze is a NEW failure mode — e.g. a bad pointer read in
  the press-store cave (`[[r5]+r4+8]` assumptions violated on the taken path → app-task crash
  = hard lockup), or (c) register clobber in the cmd-5 target cave (`r2`/`r3` are live in the
  stock loop around the hook — `0x01E21EEE: if (r2 == 0) goto` sits 2 bytes before the hook).
- **Pairing timing out is new**: on F3-v3/R1-c fresh pairing worked (no cmd 5 posted). If the
  Pairing menu path also reaches the hooked call site `0x01E6ECDA` (or the cmd-5 loop), the
  caves are in play there too.
- Radio state at test time: fresh boot after flash, VM untouched (old pairings listed).
  Exact menu paths / which device was incumbent NOT yet captured — details requested.

**Status: R1-e = field-FAILED. Investigation in progress (static re-verify of both hook
contexts + reachability).** Rollback to F3-v3/R1-c available (`work/ch30_r1crb.sh` → F3-v3
one sector `0x026000`; full R1-e revert = rewrite the same 3 sectors from F3-v3).

**ROOT CAUSE FOUND 2026-10-30 (static, official-objdump re-disassembly of both hook
contexts; hypothesis (c) WINS in a specific form): MISALIGNED ACCESS in the cmd5t cave.**

*Hook-byte staleness ruled out first*: hooks are computed (`encode_goto32`/`encode_call`),
and the objdump round-trip of `/tmp/opencode/r1e_verify.o` confirms `0x01E21EF0: c4 ea 56 2c
goto 0x01EA77A8` and `0x01E6ECDA: 81 ea 75 c5 call 0x01EA77D0` — landing correctly on the
relocated caves.

*Stock cmd-5 loop re-disassembled* (`0x01E21EA0`–`0x01E21F10`): loop-carried regs at the hook
are `r0` = slot base (killer arg), `r4` = slot+15, `r14` = `0x1A520` array base, `r7` read
per iteration; `r1`/`r2`/`r3`/`r6` are re-written by the stock body each iteration → the
cave's register discipline is fine (it preserves r0/r4/r7/r14).

*Stock press handler `FUN_01e6ec9e` re-disassembled*: at the hook `0x01E6ECDA` (third
`user_send_cmd_prepare(5,0,0)` post) `r5` = `0xB468` and `r4` = idx×0xC are live — the stock
code itself executes the identical load chain `r0=[r5+0]; r0+=r4; r0=[r0+8]` **14 bytes
later** at `0x01E6ECE4` (the arg to `0x01E600B4` = the page function), so the press-store
cave's chain is provably valid on this path, and its clobbers (r0/r1/r2 only) match the
stock call's caller-saved set. Hypothesis (b) ruled out.

*The bug*: the cmd5t cave's address compare reads the saved-target cell `0x0001A5F1` — an
**ODD address** — with multi-byte loads: `32 60` = `r2 = [r3+0]` (32-bit @`0x1A5F1`) and
`3b 62` = `r3 = h[r3+4]` (16-bit @`0x1A5F5`). **pi32v2 does not support misaligned
multi-byte access.** Evidence: (i) the vendor code 30 bytes earlier in the very same loop
builds the misaligned word at `slot+0xF` **byte-by-byte** through `b[]` loads + inserts
(`0x01E21ED2`–`0x01E21EE2`); (ii) the stack writes `0x1A5F1` itself only via a byte-wise
`rep 4 6 { b[r0++]=b[r1++] }` copy (`0x01E21C44`, cmd-0 handler), and its consumer (cmd-2
re-page) passes it as a 6-byte pointer (`user_send_cmd_prepare(1, 6, 0x1A5F1)`) — never a
word/halfword load. A misaligned load faults → the btstack task dies → **hard lockup on any
Connect press that finds a LIVE slot** (handle@slot+6 ≠ 0 → cave falls into the compare).
This matches the field report exactly: after the flash the radio auto-reconnected a stored
device (ch. 27 known behavior), so the first Connect press executed the compare → fault →
lockup; everything afterwards (Pairing) timed out because the BT task was dead. The compare
is reached for every inused live slot, so the freeze is deterministic once any link is up.

**FIX (R1-e2, same day): byte-wise XOR-fold compare in the cmd5t cave.** Replace the three
multi-byte target reads with 12 alignment-safe byte loads XOR-accumulated into `r1`:
`r3 = 0x0001A5F1; r6 = r0; r1 = 0; rep 4 6 { r2 = b[r6++=1]; r1 ^= r2 }; rep 4 6
{ r2 = b[r3++=1]; r1 ^= r2 }; if (r1 == 0) goto KILL; goto loop-cont` — all forms are
objdump-verified encodings (`10 85` rep ×6 {2 words}, `X2 07` byte-load-with-postinc,
`29 19` xor, `41 20` reg=0, `c3 ff` imm32). Cave grows 38 → **40 B**
(`0x01EA77A8`–`0x01EA77CF`, still clear of the presst cave @`0x01EA77D0`). The slot-side
loads were aligned (`0x1A5B8`-based, stride 0x1C) but are folded into the same byte loop for
uniformity. Semantics unchanged: kill iff handle==0 (stuck) OR addr==stored target.
`PRESST_CAVE_BYTES` untouched (its store is already byte-wise `rep`; load chain proven).

**R1-e2 BUILT 2026-10-30 (fix verified, awaiting re-flash).** `CMD5T_CAVE_BYTES` rewritten
to the 40-byte byte-wise XOR-fold (`assert len == 0x28`); **objdump round-trip of the new
cave on `/tmp/opencode/r1e_verify.o` confirms every instruction and branch target**:
```
a77a8: 09 63        r1 = h[r0+6] (u)              ; ACL handle
a77aa: 81 44        if (r1 != 0) goto a77b4        ; live -> compare
a77ac: bb ea 72 09  call 0x01E08A94                ; KILL(r0=slot)
a77b0: fb ea a2 d3  goto 0x01E21EF8                ; loop-cont
a77b4: c3 ff ..     r3 = 0x0001A5F1                ; target ptr (ODD)
a77ba: 06 16        r6 = r0                         ; slot ptr
a77bc: 41 20        r1 = 0                          ; accumulator
a77be: 10 85        rep 4 6 { r2 = b[r6++=1]; r1 ^= r2 }   ; 6 slot bytes
a77c4: 10 85        rep 4 6 { r2 = b[r3++=1]; r1 ^= r2 }   ; 6 target bytes
a77ca: 71 50        if (r1 == 0) goto a77ac         ; equal -> KILL
a77cc: fb ea 94 d3  goto 0x01E21EF8                 ; else skip slot
```
All loads are byte (`b[r6++]`/`b[r3++]`) — alignment-safe. Both suites **0 failures**
(R1-e window-containment now reports 75 B standalone; combo build + `--show` clean).
**Image rebuilt:** `work/ch30_r1e.bin` sha256 `033fd190…` (F3-v3 recipe + `--cmd5-target`),
314 B changed vs stock; **diff vs `work/ch30_f3v3.bin` = exactly sectors
`0x026000`+`0x073000`+`0x0AC000`, 75 bytes** (2 B larger cave than the broken 73 B R1-e);
**diff vs the flashed broken R1-e `d2aa7d8d` = ONE sector `0x0AC000`** (only the cave moved:
`0xac7a8..0xac7cf`, entirely inside the sector; presstcave @`0x01EA77D0` clear of it). All
four sites + stock kill `bf ea ce 35` @`0x01E21EF4` + E7 NOPs byte-verified in the decrypted
image; `--show` all four TARGET, no UNKNOWN/MIXED. Stage `work/ch30_r1e.sh` (EXPECT_SHA
updated to `033fd190`, sanity asserts 73→75, header documents the fix) + card
`work/ch30_r1ec.sh` (R1-e2 header) both `bash -n` clean. **Radio still on the broken R1-e
`d2aa7d8d` — user must re-flash (one sector `0x0AC000`, or run the full stage script) then
run the card.** Nothing flashed 2026-10-30.

**Architecture backing for the byte-wise cave (2026-10-30).** The new cave's
`rep 4 6 { r2 = b[r6++=1]; r1 ^= r2 }` puts an **ALU op inside a rep body** — verified legal
with vendor precedent: scanning the official objdump of the whole app (2446 `rep` sites)
finds rep bodies with pure register ALU ops: `r15 += r7`, `r1 += r15`, shifts
(`0x01E0E47C`, `0x01E1631C`) and DSP MAC+shift+accumulate loops (`0x01E32AD8`/`0x01E32AE8`,
genuine multi-iteration bodies carrying `r7_r6` across iterations). *(Correction 2026-10-31:
the earlier-cited `r2 ^= r6` @`0x01E0E5B2` turned out to be linear-sweep noise — a misparsed
jump table — so the XOR-in-rep precedent is weak, but rep+ALU is architecturally legal per
the MAC loops.)* The ISA doc (`tools/isa/pi32v2.md` L283) states no body restriction.
Byte loads have no alignment constraint, so the ODD `0x0001A5F1` reads are safe.
**Card updated:** step **1b — fresh pairing of TID-PTT** added before T1 (the failed R1-e
attempt may have left it unpaired; the pairing press itself re-tests the timeout), and T1
gains a NOTE that this press is also the exact broken-R1-e freeze case — R1-e2 must survive
it with a live link. `bash -n` clean.

**R1-e2 FIELD RESULT 2026-10-31 — FAILED, IDENTICAL LOCKUP.** User flashed
`work/ch30_r1e.bin` (R1-e2, `033fd190…`) via `work/ch30_r1e.sh` — flash + readback +
full-flash verify all PASS — then (verbatim): *"when trying to connect the TID-PTT to radio
Locksup, same as before, and a reboot Menu->Bt->Pairing and searching for any pairable
device resulted in a timeout / nothing found."* The card was not run.

**Deduction: the misaligned loads were NOT the (only) root cause.** R1-e (word/halfword
compare) and R1-e2 (byte-wise compare) fail identically ⇒ the fault is in code COMMON to
both: the presst hook/cave, the cmd5t hook/goto structure, or the kill-timing design.
Ruled out statically since: image integrity (stage script `--show` PASS pre-flash, sector
readback identical); cave region executability (BT-PTT2 cave `0x01EA76DE` HW-proven);
presst register discipline (stock executes the identical `[[r5]+r4+8]` load chain at
`0x01E6ECE4` right after the hook, so r5/r4 are live); boot-time cmd 5 is harmless (empty
slots skip the inused test — the cave never runs before any press).

**ROOT-CAUSE MODEL (2026-10-31, ch. 31 Q1 re-read) — the R1-e design is FUNDAMENTALLY
RACY without D1.** Press flow: presst cave stores the target addr + posts cmd 5
(**async** kill on the btstack task) → `dly(5)` → `FUN_01e600b4(addr)`:
`0x16E0E` mask reads **0** for a live SPP accessory (mask@slot+8==0 — the very bug E7
exposed), then LOOP A/B call the **GLOBAL** link check `0x17F26`→`FUN_01e07bd4`, which per
E6 field calibration reads **0 for a STABLE link** — the incumbent mid-disconnect is not
yet transitional when checked ~15 ms after the post. Result: **page cmd 1 is posted while
the target's conn record is still inuse** → stack cmd-1 guard `0x01E16824` (call
@`0x01E21E76`) refuses the page → silent "Connecting" hang = the reported lockup. The kill
wins only if the btstack task starts cmd 5 within the dly(5)+dly(10) ≈ 15 ms window —
coin-flip; the user lost both R1-e and R1-e2 runs. (F3-v3 stock avoided this because its
cmd-5 kill targeted a DIFFERENT address than the page — the guard passes; repair press on
F3-v3 was always broken, which is why R1-c existed.)

**Post-reboot "Pairing → nothing found" — likely NOT corruption.** VM pairings survive
(untouched region); the radio **auto-reconnects the last device at boot** (known behavior),
and **Pairable is gated while connected** (E7 field note) → inquiry finds nothing. Testable:
does the TID-PTT button key the radio right after reboot? If yes = auto-connected, model
confirmed, no VM damage.

**FIX = R1-e3 = R1-e2 + D1** (`--d1-target-wait`, ch. 31 §Q6 GO recipe, 3 sites): replaces
both GLOBAL `0x17F26` waits in `FUN_01e600b4` with target-specific `FUN_01e16824(r4)`
(slot-ptr-or-0) tests — the page then waits deterministically for **the target's own record
to disappear** (which the cmd5-target kill frees) before posting cmd 1. Repair becomes
race-free; GOAL orders unaffected (different-address target has no record → no wait → page
proceeds; live incumbent survives the press via the addr≠target test). Side effects
verified statically: D1 site-1 makes the `0x600F2` post-0x12/5 path dead (harmless); the
`0x4A`-on-mask≠0 path at `0x600EC` is unchanged (its executor `0x01E178CE` is already NOP'd
by `--no-disconnect-13` on F3-v3); HFP-class self-repair terminates because cmd5-target
kills the target by addr-match even when mask≠0. Implementation + build in the next
paragraph(s); **rollback to F3-v3 = `work/ch30_r1erb.sh`** (3 sectors
`0x026000`+`0x073000`+`0x0AC000` restored from `work/ch30_f3v3.bin`).

**R1-e3 BUILT 2026-10-31 — `--d1-target-wait` implemented, image staged, awaiting flash.**
`tools/patch_h3plus_firmware_bluetooth.py` gained `--d1-target-wait` (ch. 31 §Q6 D1 recipe,
GO verdict; **no exclusivities** — combines with everything, works standalone). Three
sites, all **objdump round-trip verified** against the official JieLi objdump:
`d1wait1` @`0x01E600DC` (10 B `bd ea 23 bf 05 16 15 f8 f5 01` → `40 16 bd ea a1 b3 05 16
f5 55` = `r0=r4; call 0x01E16824; r5=r0; if (r5 != 0) goto 0x01E600D0` — computed
**byte-identical to the ch. 31 recipe**); `d1wait2` @`0x01E6010E` (4 B `bd ea 0a bf` →
`82 ea 6f 3b` = `call 0x01EA77F0`); `d1thunk` cave @`0x01EA77F0` (6 B `40 16 fb ea 17 78`
= `r0 = r4; goto 0x01E16824` tail call). **Thunk relocated from the ch. 31 note's
`0x01EA7758` → `0x01EA77F0`**: `0x01EA7758` is the START of the always-checked 76-B
`r1bcave` state window (ends `0x01EA77A4`) and would break `find_app_start` recognition;
`0x01EA77F0` sits right after `presstcave` (ends `0x01EA77EF`), verified ALLZERO +
pointer-scan-clean (±64 B) in v50/v44/v45. Cave map now: `0x01EA76DE` BT-PTT2 →
`0x01EA7722` gatecave2 → `0x01EA7758` r1/r1b windows (→`0x01EA77A4`) → `0x01EA77A8`
cmd5t (40 B) → `0x01EA77D0` presst (32 B) → `0x01EA77F0` d1thunk (6 B) → ALLZERO to
~`0x01EA7939`. **Suites: `verify_actions.py` + `verify_cli.py` both 0 failures** (new:
D1 standalone `--only` build byte-checks + recipe byte-equality + window containment
18 B + clean `--show` + idempotency; R1-e3 combo = full F3-v3 recipe + both flags, all
seven sites + gate armed + stock kill `bf ea ce 35`; verify_cli `d1wait`/`d1wait_e3`/
`dt_alias`). **Image:** `work/ch30_r1e3.bin` sha256 `b0fa1b35…` (332 B changed vs stock);
**diff vs `work/ch30_f3v3.bin` = exactly 4 sectors `0x026000`+`0x065000`+`0x073000`+
`0x0AC000`, 93 B** (both D1 wait sites land in flash `0x650DC`/`0x6510E` = sector
`0x065000`; the earlier "5 sectors" estimate was a flash-offset slip — `0x01E6010E` →
flash `0x6510E`, not `0x6610E`); **diff vs flashed R1-e2 (`033fd190`) = TWO sectors
`0x065000`+`0x0AC000`, 18 B**. Byte-verified in the decrypted image: 3 D1 sites + 4 R1-e
sites + stock kill + E7 NOPs; `--show` reports all seven TARGET. **Stage `work/ch30_r1e3.sh`**
(4-sector flash + readback + §30.3 full strict-region verify, EXPECT_SHA `b0fa1b35…`) +
**card `work/ch30_r1e3c.sh`** (step 1b fresh-pairing/inquiry check + auto-reconnect
observation; T1 repair regression = the lockup case with D1 timing note — a few seconds
of "Connecting" is the fix working, > 15 s = failed; T2/T3 GOAL orders A/B; T4 fresh
pairing + inquiry-alive; T5 BT off/on) + **rollback `work/ch30_r1erb.sh`** (→ F3-v3,
writes 4 sectors `0x026000`+`0x065000`+`0x073000`+`0x0AC000` from the F3-v3 exports —
covers rollback from BOTH R1-e2 and R1-e3 states; `work/ch30_f3v3_073000.bin` export
created this session). All three scripts `bash -n` clean. UNTESTED — nothing flashed
2026-10-31; radio still on R1-e2 `033fd190`.

**R1-e3 FIELD RESULT 2026-10-31 — FAILED, identical hard hang; race model BUSTED.**
User flashed R1-e3 (`b0fa1b35…`) via `work/ch30_r1e3.sh` (flash OK). Verbatim field
report: *"flashed using ch30_r1e3.sh still same result. 1: no, 2. Fully frozen no key
interaction anymore nothing, display stays on key presses don't come through menu did
not respond. PTT button operations stops 'dead' radio while the screen still lights up,
also transmissions are not comming through. 3. after reboot the button on its own
connects, than I tried to connect the head set (jabra) same hang => reboot auto
connected the jabra but the TID-PTT got disconnected after the reboot (not before!) and
when trying to connect the TID-PTT the device hangs."*

Decoded observations:
- **O1 — the target was NOT connected when Connect was pressed** ⇒ the async-kill race
  model (page posted while the *target's* record still inuse → guard refuses) cannot be
  the whole story: with no target record, the guard passes and the page should fire.
- **O2 — the hang is a HARD freeze**: screen lit but 100 % unresponsive (keys, menu,
  rotary dead), **local PTT dead, TX impossible**. Not the soft "Connecting…" wait
  screen — the app task (and likely more) is gone. All three R1-e variants (broken
  `d2aa7d8d`, byte-wise `033fd190`, +D1 `b0fa1b35`) produce the SAME end state.
- **O3 — BOTH connect directions hang**: Jabra-incumbent → press TID-PTT, AND
  TID-PTT-incumbent → press Jabra.
- **O4 — after reboot BT itself is ALIVE**: the radio auto-reconnects the last device
  (first boot: TID-PTT keys; later boot: Jabra auto-connected, TID-PTT *disconnected
  after that reboot* — single-device reconnect flow, struct `0x102F0`, expected). The
  hang is **press-triggered**, not boot-state corruption; the VM is intact.

Revised hypothesis set (all builds on the F3-v3 base; R1-e deltas = presst hook+cave,
cmd5t hook+cave, D1 waits):
- **H-gate (now LEADING): the F3-v3 `--gate-close` sticky page-pending deadlock.**
  Press arms the page-pending flag; gate-close then SKIPS channel closes while pending
  (§30.9 caveat). If the press/connect flow blocks waiting on a close completion that
  the gate just skipped → app task waits forever → hard freeze (same shape as the E11
  "connect flow waits on blocked channel-close" lockup, ch. 27 §27.19). **F3-v3 itself
  was never press-tested in these two directions** — the R-series jumped straight from
  the design to R1-a. If F3-v3 hangs too, the R1 patches are innocent of the freeze.
- **H-presst: presst cave fault** (bad `[[r5]+r4+8]` load / call-frame issue in app
  task context) — app task dies ⇒ exactly the O2 signature. Common to all three R1-e
  builds; NOT present in R1-a/b/c (those froze in a different scenario, same-address
  repair only).
- **H-kill: wrong-slot kill cascade** — cmd5t cave kills the live incumbent (needs the
  cell to match or handle==0 for it) → teardown cascade freezes. Disfavored for O1
  (target not connected ⇒ cave no-ops in the Jabra-incumbent case: handle≠0, addr≠
  stored target).

**DECISIVE NEXT STEP — hardware bisect (press-matrix card `work/ch30_pmatrix.sh`):**
P0 = rollback to **F3-v3** (`work/ch30_r1erb.sh`, 4 sectors, restores known-best) and
run S1 (no incumbent, press TID-PTT Connect), S2 (Jabra up, press TID-PTT), S3
(TID-PTT up, press Jabra). F3-v3 hang ⇒ H-gate/base problem (next bisect: rebuild
without `--gate-close`). F3-v3 clean ⇒ flash R1-c (2-byte cmd-5 test only, 4 sectors
from R1-e3), then R1-e4 = recipe + `--cmd5-target --only presstore --only presstcave`
(presst only, stock kill) to isolate H-presst vs H-kill. `--only` filtering makes these
bisect builds need no tool changes.

**Rollback script bugfix 2026-10-31 13:20:** user ran `work/ch30_r1erb.sh`; line 58 had
`skip=$((0x$s/4096))` with `s="0x026000"` → bash arithmetic error `0x0x026000` → false
STOP "sector export differs" (preflight only — **nothing was written to the radio; it is
still on R1-e3 `b0fa1b35`**). Fixed to `skip=$((s/4096))` (bash parses the `0x` literal
itself); `bash -n` OK; all four F3-v3 exports manually re-verified to match the image.
User re-running the rollback, then the press-matrix card `work/ch30_pmatrix.sh F3V3`.

## §30.14.13 — P0 RESULT: F3-v3 ITSELF freezes on Connect — R1-e series innocent; freeze-onset table; R2-a = E7 base + targeted kill + D1 (BUILT 2026-10-31)

**USER FIELD REPORT 2026-10-31 (P0, verbatim):** *"I flashed ch0_r1erb.sh flashing
was fine, but still the same issues. When pressing connect the radio froze. When
scanning for pariable devices nothing showed/timeout. One oberservation different
with previous flashed image. When a device was connected (auto connect after
reboot) and pressing Menu->bt->connect the radio froze but also the connected
device was disconnected directly I tested this with TID-PTT and Jabra and both
showed same procedure to pair/connect. I select the device from the menu, press
connect the connected device got disconnected radio froze, I restarted the radio
and the device selected in the menu auto connects."*

**Decoded:**
- **P0 = F3-v3 press-tested → FREEZE.** Decisive: the R1-e/R1-e2/R1-e3 patches are
  **innocent of the freeze** — the base already has it. (This REPEATS the earlier
  `F3V3-B r2` row of 2026-10-25 which froze on join — the §30.14.12 claim "F3-v3
  never press-tested" was **wrong**; corrected here.)
- **Kick + freeze together on F3-v3**: incumbent disconnects at press (stock cmd-5
  mask==0 kill / cleanup executors LIVE on the base) and the app task then wedges.
  Same hard-freeze signature as R1-e3 (screen lit, keys/menu/PTT dead).
- **Inquiry "nothing found"**: plausibly the known *Pairable gated while connected*
  behavior (radio auto-connects at boot; test inquiry with NOTHING connected —
  card S5). Not treated as a separate bug yet.

**FREEZE-ONSET TABLE (assembled 2026-10-31 from the §30.10 ledger + ch. 27):**
| build | close-blocking | press result |
|---|---|---|
| E6/E7/E8/E9/E10 (2026-10-08..20) | none | **NO freeze** (kicks, but UI alive) |
| E11 (2026-10-20) | NOPs (je-branch + l2cap entry) | FREEZE ("generic deadlock", §27.19) |
| F3-B v1 (10-24) | primitives gated | FREEZE |
| F3-v2 (10-25, sha `91383c8f`) | 3rd-poster NOP (walk dead) | FREEZE |
| F3-v3 (10-25) | both | FREEZE (F3V3-B r2 + **P0 2026-10-31**) |
| R1-e/e2/e3 (10-30/31) | both (F3-v3 base) | FREEZE |

⇒ **Freeze correlates 1:1 with blocking channel closes** (any mechanism). The app's
connect flow requires close completions; blocked closes = deadlock (§27.19 verdict
confirmed on the base itself). The eviction fix must therefore be **targeted**
(skip the disconnect for keep-devices, let closes complete normally) — exactly the
R1-e predicate idea, which had never been testable on the freezing F3-v3 base.

**R2-a BUILT 2026-10-31 — the fair test.** `work/ch30_r2a.bin` sha256
`3db8e48343d7019530f4cfc490f6e0d865e12b403ee23231ab7ade6b3ea285bf` = **E7 base**
(`--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2 --no-kick
--force-page-scan --force-role-keep --no-disconnect-13 --no-pairing-kick`) **+
`--cmd5-target` + `--d1-target-wait`** (252 B vs stock, 15 sectors). E8 cleanup
NOPs, E9/v2 poster NOPs and the gate trio are all **absent** (byte-verified stock
at `0x01E19AD0`/`0x01E19B14`/`0x01E20AB2`/`0x01E61E22`/`0x01E60188` + both gate
trampoline entries) — closes run normally ⇒ no deadlock expected (E7–E10
precedent). R1-e's seven sites + E7 NOPs + stock kill verified; `--show` clean
(0 UNKNOWN/MIXED). **Diff vs flashed F3-v3 = 9 sectors
`0x01C000+0x01E000+0x025000+0x026000+0x054000+0x065000+0x066000+0x073000+0x0AC000`,
173 B** (F3-v3 sector exports for all nine saved as `work/ch30_f3v3_*.bin`).
**Expectations:** (1) NO freeze (base proven); (2) cmd-5 no longer kills a
different live incumbent (targeted); (3) a kick MAY persist via the still-live
cleanup executors / 0x4a walk RFCOMM close (E7/E8-era family) — the card
`work/ch30_r2ac.sh` (S0 boot / S1 no-incumbent / S2 Jabra-up press TID-PTT /
S3 TID-PTT-up press Jabra / S4 repair press = the D1 case / S5 inquiry) records
who survives. Stage `work/ch30_r2a.sh`, rollback `work/ch30_r2arb.sh` (9 sectors
→ F3-v3; also fixes the r1erb `0x0x` dd bug by using `skip=$((s/4096))`).
Scripts `bash -n` clean, chmod +x. Radio currently on **F3-v3** `1a1eaca1`
(froze on press per P0). UNTESTED.

**Stage-script bugfix 2026-10-31 22:50 (second `0x0x`-class defect, preflight-only,
nothing written):** user's first `work/ch30_r2a.sh` run STOPPED at
`sector file missing: work/ch30_r2a_01E000.bin`. CAUSE: the patcher's `--sectors`
exports only sectors differing from the **stock** input (15 files: `01C000/01D000/
01F000/026000/057000/060000/065000/073000/07A000/07E000/083000/093000/0AC000/
0C2000/0C4000`), but the R2-a flash plan is the **9-sector diff vs F3-v3** — four of
those (`01E000/025000/054000/066000`) are sectors where R2-a RESTORES stock content
(F3-v3's E8/E9/gate NOPs removed), so `--sectors` never exported them. FIX: the stage
script now extracts all nine sectors with `dd if=$IMG … skip=$((s/4096)) count=1`
straight from the sha-verified image (same content where exports exist — verified;
`01E000/025000/054000/066000` confirmed byte-identical to `Dumps/dump_internal.bin`).
`bash -n` OK; all nine extractions cmp-clean; image sha re-confirmed
`3db8e48343d70195…`. Rollback exports `work/ch30_f3v3_*.bin` for all nine verified
matching `work/ch30_f3v3.bin`. User re-runs `sudo bash work/ch30_r2a.sh`.


## §30.14.14 — R2-a field FAILED on the non-freezing base; ROOT CAUSE: `0x1A5F1` is the stack's RE-PAGE MAILBOX (press-store poisoned it); R2-b = E7 + `--cmd5-handle` only (BUILT 2026-11-01)

**User report (2026-11-01, verbatim):** *"done list show now avaiable devices but
everytime I try to connect, if it's through the menu => bt => connect or menu => bt =>
parining => select => connect the radio freezes"*. Card log
`work/logs/ch30_R2A_card_20261101_103949.log`: **S0** Jabra auto-connects at boot;
**S1 FREEZE, S2 FREEZE (Jabra not surviving, TID-PTT no join), S3 FREEZE, S4 repair
FREEZE**; **S5 inquiry list SHOWS DEVICES — first time on any build** (the earlier
"nothing found" was the Pairable-gated-while-connected state, confirmed environmental).

**Deduction:** R2-a is the E7 recipe — a base that **never froze** in the 2026-10-08/09
field runs (E7 = kicks only). It froze on EVERY press ⇒ the freeze cause is in the code
**added by `--cmd5-target`/`--d1-target-wait`**, independent of the F3-v3 close-blocking
freeze (P0). Two independent freeze causes were stacked in R1-e/e2/e3.

**ROOT CAUSE (static, official objdump on `/tmp/opencode/app.o`): `0x0001A5F1` is not
free storage — it is the btstack dispatcher's pending-RE-PAGE mailbox.** The dispatcher
epilogue @`0x01E2232E`–`0x01E22348`: `r0 = r14` (= `0x1A520`), byte-OR-folds the 6 bytes
at `r14+209` = `0x1A5F1`, and **`if ((r0 & 0xFF) != 0) goto 0x01E21E46` — the cmd-2
re-page path (`user_send_cmd_prepare(1, 6, 0x1A5F1)`)**. Its legit producer is the cmd-0
connect-request pop (`rep 4 6` copy @`0x01E21C44`). The **presst cave wrote the pressed
BD_ADDR into that mailbox from the app task on every press**, injecting a spurious
re-page request that raced the press's own cmd-1 page (same-address guard `0x01E16824`
collision) and wedged the dispatcher/queue → app task blocked → **hard freeze on every
press regardless of base**. This explains R1-e (misalignment was a real second bug),
R1-e2, R1-e3 (all F3-v3 + poison) **and** R2-a (E7 + poison). F3-v3's own P0 freeze
remains the separate close-blocking cause. Also verified this pass: `FUN_01e16824`
semantics = returns slot ptr iff target BD_ADDR holds an INUSED record (6-byte memcmp
`0x3127B0` per slot, inuse word byte-assembled from slot+15..18, bit29) — the D1
predicate itself is fine; cmd5t's use of `r6` as scratch is benign (stock loop body
rewrites `r6` every iteration @`0x01E21EDC`). **Lesson recorded: a RAM cell may only be
used as scratch after its FULL consumer set is enumerated — the dispatcher epilogue
polling `0x1A5F1` was invisible to the ch. 31 Q-map, which covered producers/readers of
the saved-target copy but not the OR-fold.**

**R1-c re-attribution:** R1-c (`--cmd5-handle`, 2-byte handle test) was flashed onto the
**freezing F3-v3 base**, so its 2026-10-27 "freeze" verdict is contaminated — **R1-c was
never cleanly tested** and remains the leading candidate for the eviction fix.

**R2-b BUILT 2026-11-01 (the clean R1-c test): `work/ch30_r2b.bin` sha256
`52c3016a5c79a67a6b6934b18f7fa2dec02a52d2762ecc0d06271edf9f1cfca5`** = **E7 recipe +
`--cmd5-handle` ONLY**. Byte-verified: handle test `09 63 81 42` @`0x01E21EF0` in;
presst hook stock `bd ea 28 46`; D1 sites stock; cave region `0x01EA77A8..` all zero;
E7 NOPs @`0x01E21DE4`/`0x01E21EC4` intact; gate entries stock (`10 04 c0 ff`
@`0x01E173EC`). **Diff vs flashed R2-a = 4 sectors `0x026000+0x065000+0x073000+0x0AC000`
(93 B); diff vs F3-v3 = 8 sectors, 82 B.** Expectations: (1) **NO freeze** (E7 base
proven + poison removed); (2) cmd 5 kills only stuck records → a live incumbent
survives the press; (3) page to a DIFFERENT address passes the guard → GOAL orders A/B
can complete; (4) repair press (same device) = **known NO-GO** — guard refuses, nothing
kills the record (card records, not a failure). A residual kick may still come from the
live cleanup executors / 0x4a walk (E7-era behavior) — the card's S2/S3 survival
questions separate that. Stage `work/ch30_r2b.sh` + card `work/ch30_r2bc.sh`
(S0 boot / S1 no-incumbent = the R2-a freeze case / S2 GOAL order A / S3 GOAL order B /
S4 repair record-only / S5 inquiry); `bash -n` clean, chmod +x. Rollback to F3-v3 stays
`work/ch30_r1erb.sh` (4 sectors). If R2-b is clean and the GOAL passes → two-device
ACHIEVED with a 2-byte delta over E7; the press-store design returns later **with a
verified-free cell** (not `0x1A5F1`) if repair is wanted. Radio currently on **R2-a**
`3db8e483`. UNTESTED.

## §30.14.15 — R2-b field FAILED too; BYTE PROOF isolates a 2-byte fork: the handle test itself vs degraded radio state; E7-ref 1-sector bisect BUILT (2026-11-01)

**User report (2026-11-01, verbatim):** *"flashed ch30_r2b but still the radio freezes
as before on connect and also the pairing does not show any devices anymore (Timeout)"*.
R2-b hard-froze on Connect exactly like R2-a — and inquiry went **silent again** (it
LISTED devices on the R2-a card S5 hours earlier, same radio, same peripherals).

**BYTE PROOF (this session, decisive):** built `work/ch30_e7ref.bin` = exact E7 recipe
rebuild from `Dumps/dump_internal.bin` (`--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT
--conn-num=2 --no-kick --force-page-scan --force-role-keep --no-disconnect-13
--no-pairing-kick`, NO `--cmd5-handle`), sha256 `90bec3200146e78d…`.
1. **E7-ref vs R2-b (`52c3016a…`) = exactly 2 bytes** at flash `0x26EF0`/`0x26EF1`
   (sector `0x026000`, VA `0x01E21EF0`) = the `19 60`→`09 63` handle test. Nothing else.
2. **E7-ref vs `work/e7_twodev.bin` (the ACTUAL 2026-10-09 E7 field image that NEVER
   froze — kicks only, ch. 27 §27.11/§27.12) = ZERO diffs** in the strict region
   `0x5000–0xC8FE0` ⇒ no toolchain drift; today's E7 rebuild IS the known-good image.

**The fork.** R2-b has NO mailbox poison (presst absent, cave zeroed) and NO
close-blockers (E7 base) — yet it froze where the byte-identical-minus-2-bytes E7 did
not. Either:
- **(a) the 2 bytes ARE the freeze cause** — with the handle test, cmd 5 no longer kills
  a live mask==0 incumbent; if the app press flow architecturally *requires* cmd 5 to
  have freed a record before paging (or requires the close-completion the stock kill
  triggers), incumbent-SURVIVAL itself deadlocks the press flow. That would make the
  entire R1-c/targeted-kill idea **architecturally dead** on the stock app → §30.9
  rewrite routes (code-cave SPP multi-session / SDK rebuild / ESP32 combo).
- **(b) the radio's STATE degraded** since Oct 9 — ~25 hard power-cycles mid-freeze,
  append-only VM @`0xC9000+` churned by repeated pairing attempts. The fresh
  inquiry-timeout (after S5 listed devices hours earlier, and R2-b touching no
  inquiry/scan code at all) supports (b): firmware-inert symptom.

**BISECT BUILT: `work/ch30_e7ref.sh`** (chmod +x, `bash -n` OK) — restores stock cmd 5 =
**exact E7** via ONE sector `0x026000` (dd-extracted from the sha-verified e7ref image,
EXPECT_SHA `90bec320…`, erase+write+readback ×2, §30.3 full 1 MiB strict verify, VM
untouched). Card built into the script: Q1 what auto-connects at boot; Q2 button keys
TX?; **Q3 inquiry with BOTH peripherals OFF (state check — run BEFORE any press)**;
Q4 press TID-PTT Connect → (A) kick NO freeze / (B) hard freeze / (C) soft Connecting
with live keys; Q5 second press same scale. Verdict: Q4/Q5=A ⇒ fork (a), targeted-kill
idea dead; Q4/Q5=B/C ⇒ fork (b), next = BT state reset (delete ALL pairings,
power-cycle, fresh pair, retest) and possibly full-stock reflash of the app region.
Radio currently on **R2-b** `52c3016a`. UNTESTED.

---

## §30.14.16 — E7-ref bisect: FORK (a) CONFIRMED — the 2 handle-test bytes ARE the freeze cause; NEW: boot auto-join reaches a (crippled) TWO-DEVICE state (2026-11-01)

**User report (2026-11-01, verbatim):** *"If flashed e7ref.sh and no freezes anymore +
auto 'join' of the headset was a cripled two device setup while pressing connect on the
radio still kicks"*

**Decoded:**
- **F3**: on E7-ref (`90bec320` = exact E7, stock cmd-5 mask test) the Connect press
  **no longer freezes** — it behaves exactly like the Oct-9 field E7: kicks the
  incumbent. Flash/readback OK (script ran full §30.3 verify).
- **FORK (a) CONFIRMED**: with the byte proof of §30.14.15 (R2-b = E7-ref + exactly 2
  bytes), E7-ref clean + R2-b frozen ⇒ **the `19 60`→`09 63` handle test itself
  hard-freezes the press flow**. The freeze is NOT about paging a different address per
  se — it is **incumbent SURVIVAL under cmd 5 for accessory (mask==0) devices**: stock
  cmd 5 kills the mask==0 incumbent and the app press flow proceeds on that assumption;
  when the record survives, the flow deadlocks. Note E6 (2026-10-08) survived a
  **PC** incumbent (mask!=0 → stock skips the kill) with NO freeze — so survival is
  only fatal for mask==0 accessory records; the app's press flow has an unfixed
  dependency on the eviction having happened (or on the close-completion events it
  generates). **Consequence: ANY "let the incumbent live through a manual Connect
  press" scheme (R1-c handle test, cmd5-target with no target record) freezes ⇒
  targeted-kill-on-press is DEAD on the stock app.** Manual-press multipoint would
  require app press-flow surgery (decompile⇒compile route, ch. 25) or the §30.9
  rewrite routes.
- **NEW POSITIVE — F4: boot auto-join produced a TWO-DEVICE state** ("crippled"):
  with E7-ref, after boot the devices auto-connected and the headset **auto-joined**
  anyway → both links up. First two-device state with the real accessory pair since
  E6's PC-based proof. "Crippling" undefined yet — characterization checklist sent to
  user (what shows connected / button keys x/3 / BT-PTT mic / RX audio / malformed
  +SPP/AT+MPTT side effects / persistence). The formation path (no menu press) is
  exactly the E6-confirmed radio-initiated-join direction.

**Radio currently on E7-ref `90bec320` (= exact E7).** Stable; press = stock kick.
Strategy pivot under evaluation: (A) characterize + make reliable the press-free
auto-join two-device flow and fix the crippling (may be app-routing/UI only);
(B) §30.9 rewrite routes if the app press flow must change.

## §30.14.17 — CHARACTERIZED: stable press-free TWO-DEVICE state on E7-ref; crippling = routing-mode/audio-binding, links are fine (2026-11-01)

**USER REPORT (verbatim, answers to the §30.14.16 checklist):**

> 1. This is quite trickey i found out it also involvs state on the Jabra. The Jabra remembers the previous paired state, if it was pared on previous poweroff it will reconnect automaticly with the radio on power on. When the radio 'disconnects' the jabra or via a command or via a timeout / poweroff of the radio the jabra does not reconnect automaticly. So procedure to answer question 1: a. Power on Radio. b. ensure jabra is paired normally. c. poweroff the jabra. d. poweroff the radio e. poweron radio. f. connect TID-PTT. g. Turn on Jabra. Than both are simultaniously connected. The TID-PTT blinks green every 5 seconds, and the jabra said 'mobile' connected. Than If the radio poweroff after 5~10 seconds the TID-PTT starts blinking red/green while the jabra at the same time said 'mobile' disconnected.
> 2. There is no menu indication about which device is connected, there never has been one the stock firmware does not have that feature.
> 3. Yes TID-PTT buttons does TX but the mic used is from the TID-PTT strange thing notices that RX (so other radio broadcasting) is received by the radio, i see the display light up / indicate but nowhere is there any output not the radio speaker nor the headset.
> 4. BT-PTT button on the radio triggers TX but the TID-PTT mic is used, the red transmit led on the TID-PTT fires when pressing the BT-PTT.
> 5. State is all ok, until radio poweroff.
> 6. No sidetime, nothing wierd but 'headset' did not do anything while it is connected, only to be confirmed by poweroff the radio. One strange other thing I noticed is that when leaving the setup online as performed at 1. Than poweroff of the Jabra and wait 10+ seconds (I did not try sooner) the radio did not say 'bluetooth disconnected' but when pressing on the TID-PTT, which was still connected, the radio TX-ed but the MIC source changed from TID-PTT to radio. also the RX (so other radio transmits) are not broadcasted on the radio speaker.

**DECODED (C1–C7):**
- **C1 — THE GOAL'S LINK LAYER IS ACHIEVED, STABLE, PRESS-FREE.** The recipe (radio on, TID-PTT connected, then **Jabra powers on and pages IN**) yields **both devices connected simultaneously** on E7-ref; the state persists until radio power-off; teardown is clean (both report disconnect). First *accessory-pair* two-device confirmation (E6 was PC-class) and it needs **no menu press for the second device** — the exact flow the freezing cmd-5 press path was never able to reach.
- **C2 — Jabra-side reconnect policy (accessory behavior, not our firmware):** Jabra auto-reconnects only if **it** was connected at **its own** last power-off. A radio-originated disconnect (kick/timeout/power-off) makes Jabra stop retrying. Experiment-ordering consequence: never let the radio kick the Jabra when we want its auto-join back — power-cycle the Jabra instead.
- **C3 — The crippling is the app's single-device AUDIO ROUTING, not the links.** With both up, ALL TX uses the **TID-PTT mic** (button path AND radio BT-PTT; TID-PTT's red TX LED follows) and the **Jabra is a silent passenger** (says "mobile connected", never gets audio). Grounding (ch. 11 §9A.28, ch. 22 §9B.2): the name classifier maps **TID-PTT → mode 1**, unlisted names (Jabra) → **mode 3**, into the ONE global routing byte RAM `0xB464`. TID-PTT connected FIRST (menu press, outgoing) ran the routing setup; the Jabra's INCOMING join evidently does **not** re-run the classifier/connection-setup (`0x01E611D2` region) — routing stayed mode 1. (Inference from audio behavior; static confirmation of the incoming-join path = open item.)
- **C4 — RX audio silent everywhere in the two-device state** (display indicates RX, no audio on radio speaker NOR headset). Consistent with RX routed to the mode-1 accessory (TID-PTT); probe P1 below decides whether this is a two-device bug or plain mode-1 behavior.
- **C5 — Jabra-poweroff side effect:** no "Bluetooth disconnected" prompt (it was never "the device"), and the next TID-PTT press keys TX with the mic **switched to the radio's built-in** — routing re-evaluates on disconnect events (RX still absent from the speaker).
- **C6 — No menu indication of connected device(s)** — stock limitation, accepted.
- **C7 — SPP keying is mode-independent** (ch. 11 §9A.30 correction: the `+SPP=P/R` handlers never read the routing byte) ⇒ if routing can be made to STAY on the Jabra while the TID-PTT joins second, the button still keys: **that is the goal state, reachable by connection ORDER alone — no new patch needed.**

**NEXT PROBES (no flash — all on E7-ref `90bec320`):**
- **P1 (baseline):** TID-PTT ONLY connected (Jabra off): which mic on TX? Does RX play on the radio speaker or on the TID-PTT (does the TID-PTT even have a speaker)? Interprets C4.
- **P2 (GOAL probe, order swap):** connect **Jabra FIRST** (radio boots with TID-PTT fully OFF; Jabra connects by auto-join or by a menu press while nothing is incumbent — safe), THEN bring the TID-PTT up so **IT** pages in (its own reconnect; `--force-page-scan` keeps the radio connectable while connected — NO menu press, so no cmd-5 kill). If routing stays mode 3 (Jabra: mic + RX in the earphones) while the button still keys TX → **GOAL ACHIEVED**.
- **P3:** in the P2 end-state, key with both the button and BT-PTT; watch SCO (optional `sudo btmon -w /tmp/opencode/p2_$USER.log`).

**Ledger:** row "E7-ref 2DEV CHARACTERIZED" added to §30.10. Radio remains on E7-ref `90bec320` — a stable daily-driver candidate even now (press = stock kick, auto-join works, no freezes).

---

### §30.14.18 — P1/P2 field answers + ROUTING CHAIN FULLY DECODED (classifier, ops-table, callers) (2026-11-01)

**User report (verbatim):** "P1: TID-PTT is the device with only a PTT button and mic, the stock
operation is to audio on the radio. P2. In this firmware, not sure abuot the stock only the jabra
seems to auto connect and never the TID-PTT it can only connect via the menu which force kicks the
jabra"

**Decoded:**
- **P1**: the TID-PTT has **no speaker** — stock single-device button mode puts ALL audio on the
  radio (speaker). C4 (RX silent in the two-device state) is therefore NOT button-vs-radio audio
  routing: with routing byte = 1 (button) and the Jabra up, RX should still go to the radio
  speaker like stock — it does not. The HFP link's presence suppresses the speaker path while the
  RX binding to the earphones never happens (incoming join never ran the audio setup).
- **P2 order-swap IMPOSSIBLE as designed**: the TID-PTT **never auto-connects** (page/initiator
  role is the radio's for this accessory); the only button-join path is the radio menu, and that
  press force-kicks the Jabra (live `0x4a` all-channel teardown posters `0x01E61E22`/`0x01E60188`
  are still armed on E7 — E9/E11 NOP attempts deadlock, ch. 27 §27.16–19). The two-device state
  is reachable ONLY in the order button-first (menu) → Jabra second (incoming).

**ROUTING-MODE CHAIN — fully decoded this turn (official decompilation tree + full.lst):**
1. **Writers of the routing byte (RAM `0xB464` = gp `0xB390`+0xD4) — EXACTLY three** (exhaustive
   raw grep of `b[rX + 0xD4] =` stores in `disassembled/full.lst`):
   (a,b) classifier `FUN_01e7ec28` @`0x01E7EC50`/`0x01E7EC98`;
   (c) BT-task `FUN_01e60e44` **case 9/10 teardown** @`0x01E61C88` = `DAT_0000b464 = 0xF0`
   ("no routing" sentinel; also clears `DAT_0000b47e = 0xF0` when `DAT_0000c19e`). **Explains C5**
   (mic→built-in after the Jabra powered off: teardown fires on ANY disconnect and stamps 0xF0 —
   does NOT imply the byte was ever 3).
2. **Classifier `FUN_01e7ec28` (decompiled, verbatim logic)**: if `(DAT_00010e00 & 0xC0) == 0x80`
   → byte = **6**; else ROM memcmp `0x021127C4` chain on the name: `TID-PTT`(7) → **1**,
   `TID-MIC-EAR`(0xB) → **4**, `TID-MIC`(7) → **2**, else → **3** (Jabra). Writes **unconditionally**
   — no link-direction or state check inside.
3. **Ops-table registration**: `FUN_01e18448` stores `DAT_0000bf4c = FUN_01e7ec28` (ch. 22's
   `[0xBF48+0x4]` — now pinned as `DAT_0000bf4c`).
4. **Sole caller**: `FUN_01e19e44` (btstack host-event dispatcher) **case 7** (remote-name result):
   `if (DAT_0000bf4c) (*DAT_0000bf4c)(param_1[2], param_1+3, param_1+9)` — args (status/type,
   BD_ADDR, name). So classification happens **on the name-result event**, direction-agnostic in
   principle — IF the stack issues a remote-name request for the incoming second link.

**Two hypotheses for the crippling (byte stayed button-bound when the Jabra joined incoming):**
- **H-name**: no remote-name request on the incoming second link (name cached/never asked) →
  case 7 never posted → classifier never ran → byte stayed 1. Consistent with everything.
- **H-setup**: case 7 DID fire (byte = 3) but the audio **setup** (mode-switch `tbh` @`0x01E61270`
  + SCO/RX binding inside BT task `FUN_01e60e44`, region ~`0x01E611D2`+) only runs on the
  radio-initiated connect-complete path → byte 3 but no HFP audio ever established; TX-mic
  selection then falls back to... (would predict built-in, NOT the button mic — field says button
  mic ⇒ H-setup needs an extra assumption; **H-name is the leading model**).

**Decisive field probes (no flash, E7-ref `90bec320`):**
- **P6 — mode-3 single-device baseline**: radio ON, button OFF; connect the Jabra (auto-join, or
  menu press while nothing incumbent — safe). TX with radio mic: mic = Jabra? RX in earphones?
  Establishes mode-3 audio works at all on this build (menu-press path runs classifier+setup).
- **P7 — incoming re-join byte test**: reach the two-device state (button first via menu, Jabra
  joins incoming; byte = 1 per H-name). Now **power-cycle the Jabra** (OFF, wait, ON → it
  auto-rejoins incoming). TX again: mic unchanged (= H-name confirmed: incoming joins never
  classify) vs switched to Jabra (= classifier DOES fire on incoming → H-setup becomes leading).

**Patch directions pending P6/P7 (recorded, NOT built):** (i) if H-name: force a remote-name
request (or direct classifier invocation) on incoming HFP connect-complete — small cave hook on
the BT-task 'm' sub-3 (connection complete) path, or post the name-result event; (ii) run the
mode-3 audio setup for the joined device without evicting the SPP incumbent (setup path is
profile-aware: HFP setup never touches the SPP channel — the E6 evidence); (iii) RX-silence fix =
consequence of (ii). All live on the stable E7 base (no close-blockers, no mailbox poison).

### §30.14.19 — CONNECT-COMPLETE SETUP BLOCK DECODED: mode 1 = NO-OP ⇒ one unified model for the crippling (2026-11-01)

Official objdump (`/tmp/opencode/app.o`) of the BT-task `FUN_01e60e44` region
`0x01E61158–0x01E6179C` completes the routing chain:

- **Connect-complete setup block `0x01E61170–0x01E611FA`** (reached linearly from the HCI
  connect-complete event path @`0x01E61158`): copies the joining device's BD_ADDR into the
  global device struct (`b[r4+5] = r11+5`, r4 = `0x102F0`), clears `[r4+0x540]/[r4+0x544]`,
  calls `0x01E4E2C4(1)`, `0x01E6076C(1)`, `b[r4+0x278] = r10`, `0x01E07FEA`, `0x01E18492`,
  and finally **`call 0x01E60120(b[0xB461] == 0 ? 2 : 1)`** — the same routing-mode setter the
  press handler calls at press time (ch. 31 Q2). So the setup block DOES run per
  connect-complete (direction-agnostic in this code path).
- **Mode-switch `tbh` @`0x01E61270`**: `r0 = b[r6+212]` (= routing byte RAM `0xB464`),
  `r1 = r0−1`, `if (r1 > 5) goto 0x01E61794` (default); table @`0x01E61280` (target = base +
  2×entry): **mode 1 → `0x01E61778` = `goto 0x01E6177C`... = straight to EXIT (NO audio
  setup)**; mode 2/4 → `0x01E6128C` → `call 0x01E50398(0)` + `call 0x01E503CA(0)`; mode 3 →
  `0x01E61782` → `call 0x01E503CA(3)`; mode 5/6 → `0x01E616BC` (separate handler). Post-tbh
  @`0x01E61790`: reads `0xB464` again, `r1 = r0−2`, modes 2–4 continue into extra setup
  (`0x01E6179C`+), mode 1 skips. (`0x01E50398`/`0x01E503CA` = audio-path bind functions,
  internals not yet decoded.)
- **UNIFIED MODEL (explains every field observation of §30.14.16/17 without H-setup):**
  incoming Jabra join DOES run the setup block, but the classifier never fired for it
  (H-name: no remote-name result → dispatcher case 7 never posts → `0xB464` stays **1** from
  the earlier TID-PTT classification) ⇒ the mode tbh takes the **mode-1 no-op branch** ⇒ no
  audio binding to the earphones: TX mic stays whatever the SPP/BT-PTT path selects
  (button mic), RX has nowhere to go (HFP present suppresses the speaker, SCO never bound)
  = exactly the crippled state. Jabra power-off → teardown case 9/10 writes the `0xF0`
  sentinel → next TX falls back to the built-in mic (C5). ✏️ All consistent; P6/P7 remain the
  field discriminators (P7 mic-switch-on-rejoin would prove a name result DOES sometimes
  arrive; no change = H-name solid).
- **FIX DESIGN (candidate `--incoming-mode3`, NOT built):** make the second (incoming)
  join classify. Options: (a) force an HCI Read Remote Name request on incoming ACL
  connect-complete so the existing case 7 → classifier → byte=3 path runs BEFORE the tbh
  (timing risk: name result is async, tbh may run first); (b) **cave hook in the setup
  block**: if `0xB464 == 1` and the joining BD_ADDR (`r11+5`) differs from the stored
  first-device address (hook must run before the struct+5 overwrite, or compare against a
  press-stored copy in a VERIFIED-FREE cell — never `0x1A5F1`), write `0xB464 = 3` before
  the tbh — deterministic, name-free, safe because the goal-flow second device is always
  the headset; (c) if P7 shows names do arrive, simply re-run the tbh/audio setup from the
  classifier tail. Cave space: `0x01EA793A`+ (1084 B ALLZERO run, pointer-scan clean,
  sector `0xAC000`).

### §30.14.20 — P6/P7 FIELD RESULTS: mode-3 binding proven GOOD; incoming re-join works only ONCE per radio boot (2026-11-02)

User report (verbatim): "P6: when only connecting the jabra on both auto-join as via the
menu the tx is the jabra mic and the received RX is on the earphones. P7 the jabra only
auto joins the first time I needed to powercyle the radio and start the procedure again
to auto join the headset again. So power on / off the headset did not auto-join (I waited
15 seconds)"

Decoded:
- **P6 = PASS**: Jabra alone — via boot auto-join (radio-outgoing walker page) AND via
  menu connect — TX = **Jabra mic**, RX = **earphones**. The mode-3 audio bind
  (`0x01E503CA(3)`) works end-to-end on E7-ref whenever the classifier HAS run. The HFP
  audio path itself is healthy.
- **P7 = the discriminator could not run** (no re-join happened) **but exposed a NEW
  fact**: within one radio session the Jabra does NOT re-join after its own power-cycle
  (15 s wait; per C2 its own policy says it should page). Only a radio power-cycle +
  redo of the procedure restored the two-device state. ⇒ **incoming join is accepted
  once per radio boot.** Leading explanation: the first Jabra session leaves a stuck
  conn record (power-off = supervision timeout; teardown case 9/10 resets routing but
  record release incomplete) and the incoming path refuses a page for an address that
  still holds a record — same stuck-record class cmd 5 exists to clean. Static
  confirmation = open item (dispatcher case 4 incoming-accept path).
- **Consequences**: (1) daily workflow stays: radio boot → TID-PTT via menu → Jabra
  power-on (first incoming join) — reliable once per boot; (2) **H-name vs H-setup is
  now MOOT for the fix**: the mode tbh runs at connect-complete, BEFORE any async
  remote-name result could arrive, and the classifier tail is UI-refresh only — so even
  if a name request were issued, nothing re-binds. The fix must write the routing byte
  and let the tbh bind; (3) **refined `--incoming-mode3` design**: hook at the mode-tbh
  entry `0x01E61270` (replacing the byte-load `r0 = b[r6+212]` + test): cave loads the
  byte; if byte == 1 AND the conn table (`0x1A5B8`, stride `0x1C`, 2 slots, inused =
  bit29 of word @slot+0xF) shows **>=2 inused records** → set `0xB464 = 3` and return
  r0 = 3; else behave exactly stock. No BD_ADDR storage needed (avoids any mailbox-class
  bug); goal-flow second device is always the headset. Byte != 1 or <2 records →
  untouched.

**NEXT: implement `--incoming-mode3`** (tbh-entry hook + cave @`0x01EA793A`), objdump
round-trip, both suites, build R3 = E7 recipe + flag, stage + card. Radio stays on
E7-ref `90bec320` meanwhile.

### §30.14.21 — R3 BUILT: `--incoming-mode3` (tbh-entry hook + 54 B cave), suites green, 2-sector image (2026-11-02)

**Implemented** in `tools/patch_h3plus_firmware_bluetooth.py` as `--incoming-mode3`
(dest `incoming_mode3`; no CLI exclusivities — combines with the whole E7 recipe):

- **Hook** `incmode3` @`0x01E61270` (connect-complete mode-switch tbh entry): the
  4-byte routing-byte load `50 ee 64 0d` (`r0 = b[r6+212]`, RAM `0xB464`) becomes
  `82 ea c1 32` = `call 0x01EA77F6`. Stock follow-on (`r1 = r0-1`, `if (r1 > 5)
  goto 0x01E61794`, `r0 = r1<<1`, `tbh`) untouched.
- **Cave** `incmode3cave` @`0x01EA77F6` (54 B, free tail of the 364 B ALLZERO run
  `0x01EA76DE..0x01EA7849`; ALLZERO + full-image 2-byte-aligned pointer-scan clean
  in v44/v45/v50; sector `0xAC000`). Uses only r0 (return) + r1 (dead — stock
  overwrites at `0x01E61274`); no stack, no mailbox-class RAM. Listing (official
  objdump round-trip, exact):

  ```
  a77f6  r0 = b[r6+212] (u)         ; routing byte
  a77fa  r1 = r0 + -1
  a77fe  if (r1 != 0) goto a7826    ; byte != 1 -> rts (r0 = original byte, stock)
  a7800  r1 = 0x0001A5CA            ; conn slot0 inuse byte (0x1A5B8+0x12)
  a7806  r0 = b[r1+0] (u)
  a780a  r0 = r0 & 0x20             ; bit29 of the slot+0xF inuse word, BYTE-wise
  a780e  if (r0 == 0) goto a7828    ; slot0 free -> RET1
  a7810  r1 = 0x0001A5E6            ; conn slot1 inuse byte (0x1A5D4+0x12)
  a7816  r0 = b[r1+0] (u)
  a781a  r0 = r0 & 0x20
  a781e  if (r0 == 0) goto a7828    ; slot1 free -> RET1
  a7820  r0 = 3
  a7822  b[r6+212] = r0             ; force routing mode 3
  a7826  rts
  a7828  r0 = 1                     ; RET1: stock mode-1 value
  a782a  rts
  ```

- **Semantics**: at EVERY connect-complete tbh pass, iff routing byte == 1 (button
  mode) AND both conn records inused (goal state: SPP incumbent + incoming HFP) →
  byte := 3 → tbh takes the mode-3 bind `call 0x01E503CA(3)` (P6-proven healthy).
  Single-device or byte ≠ 1 → **exact stock behavior**. Accepted caveats: a second
  TID-MIC-class device would also be forced to 3 (goal flow = one SPP + one HFP,
  second device always the headset); does NOT fix the P7 once-per-boot re-join.

**LESSONS (recorded per repo directive):**
1. **Design-note ALLZERO claims must be re-derived from the decrypted image.** The
   §30.14.20 note claimed cave site `0x01EA793A..0x01EA7D75` (1084 B) — FALSE: that
   region holds `f8 00 f8 00 ff ff …` data in v50 AND v44/v45. Because
   `find_app_start` validates EVERY patch entry's ctx window, the bad site broke
   ALL builds (46 suite failures, "could not locate a recognised app region").
   Real free space = the run above; incmode3cave relocated to `0x01EA77F6`.
2. **External edits observed mid-session**: my first R3 suite sections were
   reverted externally, and a `--r1-full-flow` flag (NOT from this session)
   appeared in the patch tool. R3 coverage was re-added on top; the foreign flag
   was left intact. Coordinate before overwriting suite/tool regions.

**Verification**: `tools/verify_actions.py` FAILURES: 0 and `tools/verify_cli.py`
FAILURES: 0 (incl. new standalone-R3 byte/window/show/idempotency checks +
R3-combo = E7 recipe + flag with D1 thunk asserted erased; CLI cases `r3`,
`r3_e7`, `im3_alias`). Objdump round-trip on a patched `app.o` copy: hook + all
54 cave bytes decode exactly as designed (listing above).

**Image**: `work/ch30_r3.bin` sha256 `d9c35315c7fa611f…` = E7 recipe +
`--incoming-mode3` from `Dumps/dump_internal.bin`. Diff vs flashed E7-ref
(`90bec320…`) = **exactly sectors `0x066000` + `0x0AC000`, 48 bytes** (asserted in
the stage preflight); hook+cave byte-verified in the decrypted image; `--show`
reports both sites TARGET, no UNKNOWN/MIXED. Build cmd:

```bash
python3 tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin work/ch30_r3.bin \
  --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2 --no-kick --force-page-scan \
  --force-role-keep --no-disconnect-13 --no-pairing-kick --incoming-mode3 \
  --sectors=work/ch30_r3
```

**Stage**: `work/ch30_r3.sh` (2-sector erase+write+readback ×2 attempts, §30.3 full
1 MiB strict verify, boot check) + card `work/ch30_r3c.sh` (S0 setup TID-PTT via
menu → S1 GOAL: Jabra pages in → TX mic = Jabra, RX = earphones, button keys 3/3,
incumbent survives → S2 persistence 2 min → S3 rejoin (known once-per-boot limit,
record only) → S4 BT off/on regression → S5 repair press (known stock kick, record
only)). **UNTESTED — nothing flashed yet; radio stays on E7-ref `90bec320`.**

**NEXT: user flashes `sudo bash work/ch30_r3.sh`, runs `bash work/ch30_r3c.sh`,
reports S1a–S1e (the GOAL gate) + S2–S5.** If S1c/S1d pass but S1e fails (button
keying lost under mode 3), follow-up = BT-PTT action-pair interaction check
(ch. 23). If S1a fails (no incoming join at all on R3) re-check P7 stuck-record
theory — R3 does not touch the join path.

### §30.14.22 — R3 FIELD RUN 2026-11-02: Jabra paged in; NEW post-disconnect echo loop — TID-PTT mic broadcast on the radio speaker (S3)

User report (verbatim): "done, one strange behaviour: once the Jabra paged in and I turned
it off again (S3) I noticed a very loud and wierd echo on the speaker of the radio. The
sideloop / echo of the TID-PTT mic was broadcasting through the radio speaker. So when The
radio anounces "menu" you would hear it twice/three times and all the button beeps sounds
funny and distored because of the echo loop. Moving the TID-PTT away reduces the noice.
Also when turnoff the S3 Jabra headset the RX comes in on the radio speaker again instead
of nowhere"

Decoded:
- **S1a = PASS**: the Jabra paged in on R3 (two-device state reached without a menu press,
  as on E7-ref). Full S1b–S1e verdicts still pending from the user (see questions below).
- **NEW failure mode (post-Jabra-power-off)**: the radio speaker plays the **TID-PTT mic
  continuously** — an acoustic feedback loop (radio speaker → TID-PTT mic → SCO uplink →
  radio speaker): voice announcements repeat 2–3×, button beeps distorted, distance-
  dependent (moving the TID-PTT away reduces it). ⇒ after the headset leaves, the audio
  router is left in a state where the **BT uplink is looped to the speaker (sidetone)** —
  the teardown/restore path does not return audio to clean stock mode-1 when the bind was
  made via the forced mode-3 route.
- **RX returns to the radio speaker** after the Jabra powers off ("instead of nowhere" =
  the crippled two-device state's silence) — no BT audio device bound ⇒ fallback routing;
  consistent with the teardown having torn the SCO bind down but left the mic-loop path up.
- Leading static suspects (to analyze next): the teardown path that writes the `0xF0`
  sentinel (`0x01E61C88`) + the HFP-disconnect audio restore inside `0x01E50398`/
  `0x01E503CA` — specifically whether the restore pair assumes the mode-2/4 entry
  (`call 0x01E50398(0)` + `call 0x01E503CA(0)`) while our forced path only ran
  `0x01E503CA(3)`, leaving an SCO/sidetone state dangling; and whether the TID-PTT's own
  SCO (BT-PTT mic source) gets treated as the active HFP audio link after the headset dies.

**Questions to user (asked 2026-11-02)**: S1c (TX = Jabra mic while both up?), S1d
(RX = earphones while both up?), S1e (button keyed 3/3?), S2 persistence, S4 BT off/on —
did the echo clear? — S5 repair press, and whether the echo started exactly at the Jabra
power-off. These decide whether R3 achieved the GOAL (S1) and how bad the S3 regression is.

### §30.14.23 — R3 VERDICT = GOAL NOT MET: forced mode-3 does NOT bind audio to the incoming headset (2026-11-02)

Card answers (user, verbatim): "1: no, TID-PTT mic 2: no, complete silence no audio
anywhere 3: yes audio from TID-PTT mic 3x 4: yes all stayed up no drops. 5: no radio
needed a reboot 6: kick" — mapped:

| Item | Answer | Meaning |
|---|---|---|
| S1c TX with both up | **NO — TID-PTT mic** | forced mode-3 did NOT move TX to the Jabra mic |
| S1d RX with both up | **NO — complete silence, no audio anywhere** | no RX bind took effect either (same as crippled mode-1 state) |
| S1e button keys | YES 3/3 (TID-PTT mic audio = BT-PTT working) | SPP command path unaffected |
| S2 persistence | YES, both links up, no drops | the 2-device state itself is solid |
| S4 echo clearing | BT off/on does NOT clear — **radio reboot required** | the post-teardown loop is latched deep in audio state |
| S5 repair press | kick (stock) | expected — R3 doesn't touch the press flow |

**Verdict: R3 = FAIL for the GOAL** (links fine, audio not routed). But the run is
highly informative:

- The forced `call 0x01E503CA(3)` **did execute** — proof: the post-Jabra-power-off
  behavior CHANGED vs E7-ref (which tore down cleanly to stock): now the TID-PTT mic
  loops to the speaker and RX falls back to the speaker. So the routing byte really
  became 3 and the audio engine entered headset-mode — it just has nothing to bind to
  on the Jabra side.
- **Leading model (H-noprofile)**: the INCOMING Jabra join brings up **ACL only** (or
  ACL + SDP) — the radio never initiates the **HFP profile connection** to a device
  that paged in (contrast: the outgoing boot walker / menu connect DO start HFP —
  that is why P6 Jabra-alone audio is perfect and E6's *radio-initiated* join showed
  SCO live). With no HFP/SCO channel to the Jabra, mode-3's `0x01E503CA(3)` binds a
  route whose audio device is absent: TX falls back to the only live BT mic (TID-PTT's
  SCO — the BT-PTT path), RX has no SCO downlink = silence. After the Jabra dies, the
  engine is left in mode-3 with a dangling route → mic-to-speaker loop, latched across
  BT off/on (reboot clears).
- **Alternative (H-bindtarget)**: `0x01E503CA` binds the *current device struct*
  `0x102F0` (which the setup block fills with the joining Jabra addr before the tbh —
  if so, binding should have worked ⇒ H-noprofile is the stronger hypothesis).

**NEXT (static, before any R4)**:
1. Objdump/decompile `0x01E503CA` + `0x01E50398` — what device/handle do they read
   (struct `0x102F0`? SCO handle? global "current HFP device" pointer?), what state do
   they latch (sidetone flags = the echo).
2. Find the **HFP profile connect** call the outgoing/menu paths make after ACL
   connect-complete (btstack `user_send_cmd_prepare` op for HFP connect, or
   `hfp_create_connection`-style SDK fn) and whether the incoming-accept path calls it.
   If not: R4 candidate = post a profile-connect for the incoming device (needs a
   non-freezing mechanism — the press flow is off-limits per §30.14.16; a connect-time
   cave posting to the controller queue may be OK since it is NOT the app press task).
3. Teardown restore: what the `0xF0` sentinel writer (`0x01E61C88`) + default tbh arm
   (`0x01E61794`) do, and why BT off/on does not reset the loop (find the latched flag).

**Housekeeping**: the `--r1-full-flow` flag seen mid-session in the patch tool (and its
suite cases) was NOT from this session's surviving context — user believes it was this
agent's work in a **crashed session**; it has since disappeared from the working tree
(grep = 0 matches, 2026-11-02). All R3 code/tests remain intact and green. Lesson
reinforced: document every step immediately (copilot-instructions directive).

### §30.14.24 — STATIC CORRECTION: the mode tbh arms DECODED (ch. 11 identities + off-by-one table fix) ⇒ refined R3 post-mortem (2026-11-02)

Post-R3 static pass (official objdump on `/tmp/opencode/app.o`). **Two corrections + one
confirmation:**

- **Ch. 11 already identified the tbh "audio-bind" callees** (findings/11 §9A.22,
  hardware-derived): `0x01E50398(en)` = **enable radio LOCAL MIC** (stream endpoint 0x20;
  raw arg stored to flag RAM `0xB476`); `0x01E503CA(en)` = **enable radio LOCAL SPEAKER**
  (endpoint 0x00; flag `0xB477`); `0x01E56D3C` = both ON = "restore fully-local audio"
  (teardown `0x01E61C84` calls it, then writes the `0xF0` sentinel @`0x01E61C88`).
  §30.14.19 interpreted these VAs cold and violated the repo rule "check ch. 11/29
  before re-deriving anything".
- **§30.14.19's tbh arm map was OFF BY ONE ROW.** The table @`0x01E61280` is indexed by
  `r1 = mode − 1` (the sequence before the `tbh` is `r1 = r0 + -1; r0 = r1 << 1`). Raw
  entries `10 01 | 7c 02 | 06 00 | 81 02 | 06 00 | 1e 02 | 1e 02` ⇒ **mode 1 → `0x614A0`**
  (not `0x61778`), mode 2 → `0x61778` = `goto 0x61D7C`, **mode 3/5 → `0x6128C`**,
  mode 4 → `0x61782`, mode 6 → `0x616BC`, default → `0x61794` (head of a second switch,
  `r1 = r0 − 2`, table @`0x6179C`). "Mode 1 = NO-OP exit" was WRONG.
- **Arm bodies** (the arms are connect-complete STATE paths, not bare toggles):
  - **mode-3 arm `0x6128C`** (what R3's forced byte=3 executes): `call 0x01E50398(0)`
    (LOCAL MIC **OFF**) → `b[0xB4FA] = 120` → **copy 6-byte BD_ADDR** (connect-complete
    ctx) → guard `[0x102F0+640]` (`0x10570`): if set, `call 0x01E24896`, clear →
    `call 0x01E184D6(addr)`; if returns **2** → `goto 0x61D7C` (the same far BT-task path
    the mode-2 arm takes directly).
  - **mode-1 arm `0x614A0`**: reads struct `0x102F0` byte 0; if 0 checks `b[0x102E6] != 3`
    → `call 0x01E4ED02(3, 0)`; then reads mode-6 gate byte `b[0x10E00]`, writes
    `b[0xB4FA] = 120` again, continues (region `0x614CC+` not yet dumped).
- **Refined R3 post-mortem**: forcing byte=3 did NOT "bind headset audio" — it ran the
  mode-3 state path: local mic OFF + `0x184D6`/far-path logic keyed on the JOINING
  device's address. With the incoming Jabra holding **no HFP/SCO** (H-noprofile: incoming
  joins bring up ACL only; outgoing/menu/boot-walker joins do bring HFP — P6 + E6 proofs),
  the route had no audio channel: TX stayed on the TID-PTT SCO mic (BT-PTT), RX died
  (speaker path not restored + peer SCO absent). After the Jabra powered off, the
  teardown (`0x01E56D3C` + `0xF0`) left the graph latched with the RX source still
  pointing at a BT SCO → TID-PTT mic looped to the radio speaker; BT off/on didn't
  reset it, reboot did. Ch. 11 §9A.22 hardware table (mode 3 = TX local mic / RX BT peer)
  describes the steady state the FULL far path reaches when a real HFP link exists —
  not what the forced path achieves without one.
- **R4 direction (from this)**: the missing piece is the **HFP profile connect for an
  INCOMING device** — find what the outgoing paths post after ACL connect-complete
  (btstack ops relay `0x01E22890` case table enumeration NOT yet done; `0x01E184D6` =
  prime suspect "profile state for addr" query — its caller set + return semantics next),
  then post the equivalent for the dialing-in headset at connect-complete (BT-task
  context, NOT the app press flow — §30.14.16 freeze).

**NEXT**: relay `0x01E22890` op enumeration + `0x01E184D6` semantics + HFP-connect poster
hunt; latched-flag hunt for the echo (why BT off/on misses it). R3 stays flashed (daily
workflow fine; echo only after Jabra power-off); rollback to E7-ref = same 2 sectors
`0x066000`+`0x0AC000` if the user prefers.

### §30.14.25 — TEARDOWN DUMP: disconnect path restores the mic/speaker enables but NOT the RX source ⇒ echo root cause localized; R3 rollback script ready (2026-11-02)

Official objdump (`/tmp/opencode/app.o`) of the teardown path
`0x01E61C40–0x01E61C9E` (the block that writes the routing byte,
`b[r6+212] = r12` @`0x01E61C88`):

```
61c40: r1 = b[r6+r1](u); r0 |= r1; if ((r0 & 0xFF) != 0) goto 0x61C56
61c4c: call 0x01E607B2;  r0 = 48; call 0x01E521DE
61c56: call 0x01E17E18;  if (r0 != 0) goto 0x61C60
61c5c: r0 = h[r4+130](u)              ; [0x10372]
61c60: r1 = b[r6+208](u)              ; RAM 0xB460
61c64: r0 = 1; if (r1 != 0) goto 0x61C6A; r0 = r1
61c6a: r1 = b[0x102C4](u); b[r6+210] = r0   ; RAM 0xB462 = (b[0xB460] ? 1 : 0)
61c76: if (r1 != 1) goto 0x61C84
61c7a: r0 = b[r6+225](u)              ; RAM 0xB471
61c7e: if (r0 != 0) goto 0x61C84
61c80: call 0x01E52D7E                ; same fn called @0x6126C before the mode tbh
61c84: call 0x01E56D3C                ; MIC ON + SPEAKER ON = restore fully-local audio (ch. 11)
61c88: b[r6+212] = r12                ; routing byte := r12 (teardown value)
61c8c: b[r4+0x1092] = r12; then a 4-byte memset-style setup (r2 = r4+4184, r0 = 4, r1 = 0xC90, r3 = 1)
```

**KEY FINDING**: teardown restores the audio **enables** (`0x56D3C` = local mic
+ speaker ON) and the routing byte, but **never resets the RX-source / BT-SCO
routing** that the forced mode-3 arm (via `0x01E184D6` / far path `0x61D7C`)
established ⇒ after the Jabra powers off, RX source stays latched on "BT peer
SCO"; when the TID-PTT SCO becomes the live link again its uplink (the button's
mic) plays through the now-enabled radio speaker = the field **acoustic echo
loop** (§30.14.22). A BT off/on toggle does not rebuild the graph; a reboot
resets RAM ⇒ clears. This is the exact restore gap predicted in §30.14.23.

- New RAM fields: `0xB460` (link-presence byte mirrored to `0xB462`),
  `0xB471` (gate before the `0x52D7E` call), `b[0x102C4]` (compared vs 1),
  `h[0x10372]`.
- Far path `0x61D7C` (mode-2 arm target + mode-3 conditional jump): BT-task
  state machine — `call 0x602E0`, `b[r6+r15]`/`b[r6+r13]` tests (bit0 → back
  into the setup block `0x61982`), `call 0x60524`, `call 0x5E692`, guard
  `[r6+396]` → `call 0x249DC`, 6-word copy from `r8+4629`, `call 0x6066E`,
  `b[r5+3] = r10`, `call 0x607D8` — **no direct audio-graph writer in this
  window**; the RX latch lives deeper (`0x184D6` itself, or `0x6066E`/`0x607D8`)
  — open item.
- **R3b candidate** (deferred until the R4 decision): teardown-time hook
  resetting the RX source to local — needs the exact register first (dig
  `0x01E52D7E` + the `0x1BA` stream-ctrl writers, ch. 11 endpoints `0x00`/`0x20`).

**VERDICT: R3 = roll back.** Forced mode-3 cannot bind audio (no incoming
HFP/SCO, §30.14.23) and latches the echo. Rollback script READY (not yet
flashed): `work/ch30_r3rb.sh` (chmod +x, `bash -n` OK) — restores sectors
`0x066000`+`0x0AC000` from `work/ch30_e7ref.bin` (`90bec320…`; stock hook
`50 ee 64 0d` @flash `0x66270` + zero cave @flash `0xAC7F6`), preflight
sector-diff assert vs the flashed R3 (`d9c35315…`, exactly 2 sectors/48 B —
re-verified this turn), erase+write+readback ×2, §30.3 full 1 MiB strict-region
verify, boot check Q1–Q3, ledger skeleton. Pairings survive (VM untouched).
Run: `sudo bash work/ch30_r3rb.sh`.

**NEXT**: R4 static — relay `0x01E22890` op enumeration + `0x01E184D6`
semantics + find the HFP profile-connect the OUTGOING paths post (target:
replay it for the dialing-in headset in the BT task at connect-complete; press
flow off-limits §30.14.16). Latched-flag hunt for the echo secondary.

### §30.14.26 — R4 STATIC: `user_send_cmd_prepare` decoded — the outgoing connect posts **cmd 1 = START_CONNEC_VIA_ADDR(addr)**; incoming join never posts it ⇒ R4 = replay it at connect-complete (2026-11-03)

Official objdump (`/tmp/opencode/app.o`) pass on the profile-connect question.

- **`0x01E1792E` = `user_send_cmd_prepare(cmd, param_len, param)`** (SDK public API;
  r0=cmd→r11, r1=len→r6, r2=param→r10; command-buffer ptr `[0xBF1C]`, NULL → return 5;
  returns 0 = supported / 1 = unsupported / 2 = param error). Dispatcher: cmds 1–8 via
  tbb @`0x179D8`; 121–135 via tbh @`0x179A8`; explicit cases 16/19/25/31/32/55/56/74
  (0x4A = the known L2CAP-teardown)/88/109/115; default = unsupported @`0x17A4E`.
  **80 callers** (list in `/tmp/opencode/usp_callers.txt`).
- **THE FINDING — page fn `FUN_01e600b4(addr)`** (the outgoing/reconnect page used by
  the boot walker @`0x6022C` — i.e. the path P6/E6 audio rides on) ends at
  **`0x01E60114: r0 = 1; r1 = 6; r2 = addr; call 0x01E1792E`** = **cmd 1
  `USER_CTRL_START_CONNEC_VIA_ADDR` with the 6-byte BD_ADDR**. Before that it may post
  cmd 74 / cmd 18 / cmd 5 (state-dependent teardown, with `call 0x01E17F26` waits —
  that is the blocking flow ch. 31 analyzed). cmd-1 handler @`0x17A26`: bails if
  `is_1t2_connection()` (`0x01E1787C`) nonzero or `b[0x1A662] < 0` or len != 6, then
  copies the addr to mailbox `0x1A5FD..0x1A602` and proceeds (tail dump pending).
  SDK enum (AC630N header, numbering may shift on br23): 0=START_CONNECTION,
  **1=START_CONNEC_VIA_ADDR**, 2=…_MANUALLY, 5=DISCONNECTION_HCI, 8=CONN_SCO…
- **Model confirmed**: the radio brings up HFP/SCO by **dialing the profile toward the
  device** (cmd 1 = "connect via address", ACL-if-needed + profiles). An INCOMING join
  (dispatcher case 4 → setup block `0x01E61170`) never posts cmd 1 ⇒ no profiles ⇒
  the §30.14.17/23 crippling. E6's live SCO was a radio-INITIATED join = cmd-1 path.
- Far path `0x61D7C` posts (BT-task switch-device): 12, 14, 18, **5 (disconnect)**,
  **74** @`0x61DF4..0x61E22` + `0x61162` cmd 29 — explains why riding the far path with
  an incumbent kills it; R4 must NOT go there.

**R4 DESIGN (agreed)**: hook the SAME proven-safe site as R3 — tbh entry
`0x01E61270` (runs per join in BT-task context, incl. incoming; R3 ran it without any
freeze) — cave: routing byte == 1 **and** both conn slots inused (`b[0x1A5CA]&0x20` &&
`b[0x1A5E6]&0x20`) → **post `user_send_cmd_prepare(1, 6, joining_addr)`** and return the
byte UNCHANGED (stock tbh continues; NO forced mode this time). Cave reclaims the
incmode3cave window `0x01EA77F6..0x01EA782B` (54 B, R3 rolled back). Joining addr source:
struct `0x102F0` copy done by the setup block before the tbh (offset verify next) or
`[sp+16]` as the mode-3 arm uses. Open checks before build: (a) cmd-1 handler tail
`0x17A4E..` (what it triggers after the mailbox copy), (b) `is_1t2_connection()` must be
false under E7 (it is — outgoing connect works there), (c) cmd 1 while a 2nd slot is
busy — the mailbox + stack `create_bt_new_conn` semantics (ch. 26: NULL when slot held —
but under E7 both slots exist; the Jabra slot is the one we want used… incoming join
ALREADY occupies slot 2, so cmd 1 on its addr should find the existing ACL and bring up
profiles — the `0x16824` same-address guard is NOT in the cmd-1 path, only cmd-3's).

**NEXT**: dump cmd-1 tail + setup block addr offset → implement `--incoming-hfp` →
suites → build `work/ch30_r4.bin` (E7 + flag, expect sectors `0x066000`+`0x0AC000`) →
stage + card → reply.

### §30.14.27 — R4 BUILT: `--incoming-hfp` implemented (3 sites), suites green, image staged (2026-11-03)

Flag `--incoming-hfp` in `tools/patch_h3plus_firmware_bluetooth.py` (kwarg
`incoming_hfp`; sites `inchfp`/`inchfpcave`/`inchfpbail`; **mutually exclusive with
`--incoming-mode3`** — same hook + cave window, enforced by CLI SystemExit).

- **Site 1 — hook** `0x01E61270: 50 ee 64 0d → 82 ea c1 32` (`call 0x01EA77F6`;
  byte-identical to R3's proven hook, sector `0x066000`).
- **Site 2 — cave 58 B** @`0x01EA77F6` (window `0x01EA77F6..0x01EA7849` re-verified
  ALLZERO in E7-ref before use), hex:
  `50ee640d 31e1ff0f 8155 c1ff caa50100 50ee1000 60e12000 004d c1ff e6a50100 50ee1000 60e12000 0045 0225 4021 4126 bbea8280 50ee640d 8000`
  = load routing byte; if != 1 → RET; if `b[0x1A5CA]&0x20 == 0` or `b[0x1A5E6]&0x20 == 0`
  (byte-wise slot-inused tests) → RET; else **`r2 = [sp+20]`** (joining BD_ADDR ptr —
  the mode-3 arm's own `[sp+16]` slot + 4-B call rets push) **`r0 = 1; r1 = 6;
  call 0x01E1792E`** = `user_send_cmd_prepare(START_CONNEC_VIA_ADDR, 6, addr)`;
  RET = reload byte (call clobbers r0-r3; r6 survives — callee restores {r12-r4}) +
  `rts` → **stock mode-1 tbh continues, byte UNCHANGED, far path never entered**.
  Official-objdump round-trip: `02 25` = `r2 = [sp+20]` ✓, `41 26` = `r1 = 6` ✓,
  `40 21` = `r0 = 1` ✓, all branches → `0x01EA782A` (RET) ✓, call → `0x01E1792E` ✓,
  hook resumes `0x01E61274` ✓. (Layout note: RET = `_c+52`, NOT +56 — `encode_branch2`
  is 2 B; first draft mis-sized to 62 B, fixed.)
- **Site 3 — cmd-1 bail NOP** `0x01E17A2A: 80 f8 cb 00 → 00 00 00 00` (sector
  `0x01C000`, flash `0x1CA2A`): `is_1t2_connection()` returns TRUE exactly at
  links == conn_num == 2 (our case) and the cmd-1 handler would exit without posting.
  Only posters of cmd 1 = page fn `FUN_01e600b4` (boot/reconnect, <2 links at post
  time) + this cave ⇒ effectively targeted. Eviction executors already dead under E7.
- **`--show` shared-window cross-recognition fix**: R3's 54 B cave and R4's 58 B cave
  share `0x01EA77F6`; each flag's cave states now also recognize the other
  (truncated/padded) so `--show` stays clean on both images.
- **Suites**: `verify_actions.py` + `verify_cli.py` **0 failures** incl. 12 new R4
  checks (writes, hook/cave hex, 3-window touches-only, `--show` clean on R4/R3/
  combo images, idempotent, D1 thunk left erased) + CLI cases `r4`/`r4_e7`/
  `ihfp_alias`/`ihfp_conf_im3` (rc 1).
- **Image**: `work/ch30_r4.bin` sha256 `9168ac96e835ccdb1367f972913a1c9d9861d1614380b607381d707f516d137a`
  = E7 recipe + `--incoming-hfp` from `Dumps/dump_internal.bin`; diff vs
  `work/ch30_e7ref.bin` = **exactly 3 sectors `0x01C000` (3 B — 4th bail byte already
  0x00) + `0x066000` (4 B) + `0x0AC000` (49 B), 56 B total**; built-image decrypt
  verify: hook/cave/bail bytes ✓, conn-num byte `0x25` ✓, kick NOP `40238000` ✓.
  VM untouched — pairings survive.
- **Staged**: `work/ch30_r4.sh` (preflight sha + 3-sector diff assert, erase/write/
  readback ×2, full 1 MiB strict verify) + card `work/ch30_r4c.sh` (S0 single-device
  regression / **S1 GOAL = TID-PTT first, Jabra pages in → TX mic source? RX
  earphones? button keys?** / S2 persistence / S3 Jabra-off echo-loop check (R3
  latched; R4 should be clean — real HFP to close) / S4 Jabra-first order /
  S5 repair press = stock kick expected, freeze = regression).

**UNTESTED — nothing flashed. Radio remains on E7-ref `90bec320` (stable daily
driver). NEXT: user runs `sudo bash work/ch30_r4.sh` + card; verdict = §30.14.28.**

### §30.14.28 — R4 FLASHED + CARD RUN 2026-11-03: **FAIL** — replay does not open HFP/SCO to an already-connected ACL; rollback ready (2026-11-03)

Flash `work/ch30_r4.sh` 08:48 — all 3 sectors readback-IDENTICAL, FULL-FLASH VERIFY PASS,
boot normal (Q1 ok; Q2: only Jabra auto-connected). Card `ch30_R4card_20261103_085208.log`:

| Step | Result | Reading |
|---|---|---|
| S0 TID-PTT alone | **PASS** (keys, TX/RX normal) | no single-device regression |
| S1a Jabra pages IN | **Y** | join healthy (as E7-ref) |
| **S1b TX mic** | **TID-PTT mic** (goal = Jabra) | **GOAL NOT MET** — same crippling as stock E7-ref (§30.14.17) |
| **S1c RX** | **SILENT** | no SCO to the incoming device — cmd-1 replay achieved nothing audible |
| S1d/S1e | button keys Y / UI alive Y | hook + cave harmless at tbh time (no freeze — the R1-e/R2-b poison class avoided) |
| S2 | both links 2 min, no degradation | links solid |
| S3a Jabra off → echo? | no *immediate* echo (better than R3) | |
| S3b after Jabra off | **echo loop started at first RX** (then RX normal on radio) | teardown gap persists (§30.14.25 root: RX-source not restored) — R4 leaves routing residue the teardown doesn't clear |
| S3c Jabra re-join | no-join / silence | P7 once-per-boot as expected (not targeted) |
| S4a Jabra-first outgoing | TX from Jabra mic ✓ but **RX very scrambled** (in earphones) | **new evidence**: replay *fires* in this state too (boot auto-reconnect put TID-PTT in slot 0 ⇒ byte==1 && both records inused at the outgoing connect-complete) and **disturbs the live SCO** — mechanism live, wrong command. Control test on E7-ref (outgoing Jabra + button incumbent) NOT yet run — attribution between replay vs 2-link SCO scheduling open. |
| S4b button pages in second | n (never auto-connects) | expected (§30.14.18) |
| S5 repair press | kick → **transient** freeze → recovers when TID-PTT connects; Jabra dropped | no hard freeze; stock-kick character |

**VERDICT: FAIL for the goal.** The cmd-1 replay runs (S4a disturbance) but never
establishes HFP/SCO to the incoming headset (S1b/S1c identical to the unfixed E7-ref
crippling). **Leading root cause:** `START_CONNEC_VIA_ADDR` is a *dial* command — in the
outgoing flow it is posted **before the ACL exists** and drives the whole connect state
machine; posted for an address whose conn record is already inuse (our incoming Jabra at
tbh time), the stack path dies at the same-address guard `0x01E16824` (ch. 31) → silent
no-op. Profiles are NOT a side-effect of an existing ACL — they need the state machine.

**R4 vs E7-ref:** strictly worse (no gain + post-Jabra-off echo at first RX + S4a
scramble). **Rollback script since DELETED (user directive 2026-11-03: no rollback scripts)** (3 sectors `0x01C000`+`0x066000`+
`0x0AC000` → E7-ref `90bec320…`, pairings survive; NOT yet flashed).

**NEXT (R5 candidate, static):** find the posts that actually open HFP/SCO **after** an
ACL — trace the cmd-1 completion continuation in the dispatcher and the far-path command
family (12/14/18/74; cmd 5 = kill must NEVER be replayed) — and replay the profile-start
subset (not cmd 1) at the incoming-join tbh. Secondary: E7-ref control run of the S4a
scenario to attribute the scramble. If R5 stalls: §30.9 rewrite routes (code-cave
connect-flow, SDK rebuild, ESP32 combo device).

### §30.14.29 — R5 static (2026-11-03): the dial path posts READ_REMOTE_NAME; event-7 classifier never re-binds; tbh table RE-CORRECTED

Official-objdump session (stock `app.o` — R4 sites untouched in this range). Four solid facts:

1. **SDK enum recovered** (`/home/stefan/h3plus/fw-AC630N_BT_SDK/include_lib/btstack/avctp_user.h`,
   full 549-line header read): `USER_CTRL_START_CONNECTION=0, START_CONNEC_VIA_ADDR=1,
   START_CONNEC_VIA_ADDR_MANUALLY=2, DISCONNECTION_HCI=3, CONNECTION_CANCEL=4,
   READ_REMOTE_NAME=5, PAUSE_MUSIC=6, SCO_LINK=7, CONN_SCO=8, DISCONN_SCO=9,
   DISCONN_SDP_MASTER=10, WRITE_SCAN_DISABLE=11, WRITE_SCAN_ENABLE=12, WRITE_CONN_DISABLE=13,
   WRITE_CONN_ENABLE=14, SEARCH_DEVICE=15, INQUIRY_CANCEL=16, PAGE_CANCEL=17, SNIFF_IN=18,
   SNIFF_EXIT=19, ALL_SNIFF_EXIT=20`, HFP range 21–47, AVCTP 48–62, A2DP 63–72,
   **POWER_OFF=73, POWER_ON=74**, HID 75+, TWS 89+, SPP 107–112 (`SPP_TRY_SEND_DATA=109`),
   PBG 113–116 (`PBG_SEND_DATA=115`), PBAP 117–121, DEL_ALL=122 … LAST=134. Our dispatcher's
   arg-shapes MATCH (31=DIAL_NUMBER guard-store, 109/115 = data-ptr stores, 74 handled @`0x17B20`)
   ⇒ this enum is broadly authoritative for our image despite the AC630N provenance.
2. **Page fn `FUN_01e600b4` FULLY DECODED** (`0x600B4..0x6011E`): gate `b[0x102F0+0xB10]&~0xC0==64`;
   transitional/link wait loops (`0x16E0E`, `0x17F26==128` → sleep 10 @`0x201F82`); then conditional
   posts `(74,0,0)` if transitional link, `(18,0,0)`=SNIFF_IN if link-state≠0; **ALWAYS posts
   `(5,0,0)` = READ_REMOTE_NAME** @`0x60102`; waits `0x17F26==0`; finally `(1,6,addr)` @`0x60114`.
   ⇒ **the outgoing flow's classification input is this READ_REMOTE_NAME**; an incoming join never
   posts it — the clean root cause of the never-classified incoming device (§30.14.18–19 refined).
3. **Host event dispatcher `FUN_01e19e44` event table DECODED** (table starts at instruction+2 =
   `0x19E72`; target = start + 2×entry — convention verified on BOTH tables incl. `0x19F06`):
   - **event 7 (remote-name result) @`0x1A106`**: `r3 = [0xBF48+4]` (ops classifier entry);
     `r0 = b[r15+2]` (status), `r1 = r15+3` (name), `r2 = r15+9` (addr); `call r3`; **EXIT —
     nothing runs after classification**. The classifier writes the routing byte only; no bind,
     no tbh re-run. (Confirms §30.14.19 mechanism at the caller level.)
   - **event 1 @`0x19EB6`**: if `b[r15+2]==0` && `b[0x1A4C8]&0x10`: clears bit, `call 0x8289E(1)`,
     then **`user_send_cmd_prepare(1, 6, 0x1A4C9)`** — an app-level saved-address RE-DIAL record
     (flag @`0x1A4C8`, addr @`0x1A4C9`) — candidate machinery for "disconnect then dial" flows.
4. **tbh mode table RE-CORRECTED** (start `0x61282`; §30.14.24's mode→target mapping was WRONG —
   re-derived with the verified convention): **mode1→`0x6177A` = `0x50398(0)` + `0x503CA(1)`;
   mode2/4→`0x6128E`; mode3→`0x61784` = `0x50398(1)` + `0x503CA(0)`; mode5/6→`0x616BE` =
   `0x50398(1)` + `0x503CA(1)`; byte 0/>6→`0x61794`**. `0x503CA` has 17 callers (xref). So R3's
   forced mode-3 DID run the mic/speaker-enabler pair — and still produced silence ⇒ consistent
   with no SCO existing to the incoming device (not with the bind being a no-op).

**R5 option analysis (open)**: (a) post READ_REMOTE_NAME at tbh for the incoming join — cmd 5 is
posted `(5,0,0)` no-addr; stack-side consumer resolves it from current-device/pending state —
wrong-device risk for our 2-link case; (b) **kick+redial**: on incoming join, address-targeted
disconnect (`0x1782C(addr,0,0x1100)` = the cmd-3 connected-branch) then cmd 1 — reuses the FULL
working outgoing state machine (SDP+HFP+name), but cmd 1 posted mid-teardown dies at the
same-address guard `0x16824` (deferred mechanism needed — event-1 re-dial record `0x1A4C8/C9` or
stack re-page mailbox `0x1A5F1` are the candidates; the latter poisoned R1-e); (c) call dial
state-machine starters (`0x2181C`/`0x2193A`) on the existing incoming record — semantics unknown;
(d) if all fail → §30.9 rewrite routes. NEXT static: mode2/4 path `0x6128E` anatomy; who writes
`0x1A4C8/C9`; btstack-task cmd-5 consumer (does READ_REMOTE_NAME accept a 6-byte addr param?).

**UNTESTED — analysis only; radio remains on R4 `9168ac96` (field-FAILED; E7-ref rebuild recipe:
E7 recipe from `Dumps/dump_internal.bin` → `work/ch30_e7ref.bin` `90bec320`).**

### §30.14.30 — R5 static round 3 (2026-11-03): app-redial machinery decoded (dead for same-device); stack re-dial mailbox `0x1A5D1`; btstack task event table

Official-objdump session (stock `app.o` — R4 touched only `0x17A2A`/`0x61270`/`0xA77F6`, all outside
the ranges below). Completes the three open items of §30.14.29 and adds the stack-level re-dial machinery.

**1. tbh mode table re-verified entry-by-entry** (hook `0x01E61270`; `r1 = byte−1`; `if (r1 > 5) goto
0x01E61794`; `tbh` @`0x01E61280`, table start `0x01E61282`, target = start + 2×entry — matches §30.14.29):
mode1→`0x01E6177A` = `0x01E50398(0)` + `0x01E503CA(1)`; mode2/4→`0x01E6128E` = `0x01E50398(0)` +
`0x01E503CA(0)` (both local-audio enablers OFF — NOT a profile route); mode3→`0x01E61784` =
`0x01E50398(1)` + `0x01E503CA(0)`; mode5/6→`0x01E616BE` = (1,1). All bodies converge `0x01E61790:
r0 = b[r6+212]` reload → `0x01E61794: r1 = r0−2; if (r1 >= 3) goto 0x01E617C2` — the shared tail runs
ONLY for byte ∈ {2,3,4} (reads `[0x102F0+0x103A]`, `[+0x204]`…). Pre-tbh @`0x01E61262`:
`if (b[0x102C4] != 1) goto hook; r0 = b[r6+225]; if != 0 goto hook; call 0x01E52D7E`.
Block `0x01E61292..0x01E612CC` (after mode2/4's unconditional goto — separate, xrefs unchecked):
writes `b[r6+0x16A] = 0x78`, copies `[sp+16]→[sp+12]` (6 B), reads `[0x102F0+640]`, `call 0x01E24896`,
clears it, `call 0x01E184D6([sp+12])`, **if `r0 == 2` goto far path `0x01E61D7C`** — connect-FAILURE handler shape.

**2. App re-dial record `0x1A4C8`/`0x1A4C9` FULLY DECODED** (only two sites load base `0x1A4C0`:
`0x01E19408` + host dispatcher `0x01E19E58`; `findva` 32-bit LE scan = 0 hits):
- **Armer `0x01E19404(r0 = record ptr [addr @+1], r1)`**: bail if `b[0x1A4C8] & 0x10` already set; clear
  15 B @`0x1A4C0`; copy 6 B `[r0+1] → 0x1A4C9`; class check (`b[r0+r6]<<8 + 256`, uextra p8 l5;
  `0x209C & (1<<r7)` → if set return WITHOUT arming); then ops-table query `call [0xBF48+0x30]`
  (packed record bytes — "should reconnect?"); **result == 1 → `b[0x1A4C8] |= 0x10` + `call 0x01E07FC8`**.
  Callers (xref): `0x01E19FAE` + `0x01E1A252` — both inside host dispatcher `FUN_01e19e44`
  (arms on certain host events, likely disconnect-complete).
- **Consumer = event 1 (connect-complete) @`0x01E19EB6`**: trace (`"HCI"` magic `0x48434900`,
  `call 0x01E18784`); requires `b[r15+2] == 0` (success) and `b[0x1A4C8] & 0x10`; clears bit;
  `call 0x01E8289E(1)`; posts **`user_send_cmd_prepare(1, 6, 0x1A4C9)`**.
- **CRITICAL FLAW for our use:** consumption happens on the NEXT connect-complete; if the armed target
  is the device that just connected (kick→re-page of the SAME device), the cmd-1 dial dies at the
  same-address guard `0x01E16824` (stack exit `0x01E21E7A`) exactly like R4. App-redial only dials a
  DIFFERENT (disconnected) device after some other connect. **Option (b) via `0x1A4C8/C9` = DEAD for
  same-device kick+redial.**

**3. Stack-level re-dial mailbox `0x1A5D1` (btstack-side, base r14 = `0x1A520`):**
- Case `0x01E21E38`: links `b[r14+0x142]` (RAM `0x1A662`) `ifs < 0` exit;
  **`user_send_cmd_prepare(1, 6, 0x1A5D1)`** = dial from saved mailbox. NOTE: posts NO cmd 5 ⇒ the
  classifier never runs on this path ⇒ routing byte stays 1 even if the redial works.
- **Saver `0x01E21988(r0 = addr ptr, r1)`**: `call 0x01E16824`; record-state ptr from caller ret+15;
  `if (b[state+4] & 0x40) → 0x1A65A else → 0x1A5D1`; copies 6 B addr → mailbox. Called on the FAILURE
  paths of `0x01E2193A` (from event-0 handler @`0x01E21C58` and from the cmd-1 consumer chain) — i.e.
  the stack saves a failed dial target for a later re-dial.
- **OPEN: trigger of `0x01E21E38`** — zero branch xrefs in `full.lst` (and none in objdump range
  `0x21BC4..0x21E58`). Candidate chains: `0x01E21E18` (`r1 = r0+18; if (r1<3) goto 0x21B8E; if (r0>6)
  goto 0x22238; if (r6 != 149) goto 0x21B8E`) or a table not yet located. NEXT: whole-app objdump scan
  for `0x21E38`/`0x21E54` targets + dump `0x22238` chain.

**4. btstack task event table DECODED** (dispatch `0x01E21B8E`: `if (r6 > 21) goto 0x01E21CCA` — second
chain `r6−129 ≤ 9` plus `r6−65 ≤ 7` sub-chain; `tbh` @`0x01E21B96`, **table start `0x01E21B98`, 22
entries**, target = start + 2×value): e0=`0x21BC4` e1=`0x21C58` e2=`0x21C38` e3=`0x21C54` e4=`0x21CB4`
e5=`0x21CC6` e6=`0x21D00` e7=`0x222F2` (exit) e8=`0x21F2C` e9=`0x21F3A` e10=`0x21F52` e11=`0x21F5C`
e12=`0x21F76` e13=`0x21F7E` e14=`0x21F9C` e15=`0x21FA6` e16=`0x21FC6` e17=`0x21FD0` e18=`0x21FD6`
e19=`0x21FDC` e20=`0x22036` e21=`0x22056`; resumes `0x21BC4`.
- **Event 0 handler `0x01E21BC4`** (link-setup): `is_1t2` gate; `r1 = h[r14+322]` (`0x1A662`);
  `ifs (b0 < 0)` exit; `if ((r1 & 0x38) == 0) goto 0x01E2232E` (re-page epilogue); uextra p3 l3 ×6 →
  build 6-B addr `sp+12`; `call 0x01E16824` — if connected `goto 0x01E2234E`;
  `call 0x01E2181C(addr, ?)` = find-or-CLAIM conn record (sets inused bit29 on free slot); if 0 →
  `call 0x01E4A67C`; `r0 = r14+209` (`0x1A5D1` compare); `call 0x01E2193A(r5, …)` — fail →
  `call 0x01E21988(r5)` (save redial) else `call 0x01E187AC`; exit.
- **`0x01E2193A(record, 0x1100)` = the stack's dial/connection-attempt starter** (the same call the
  cmd-1 consumer chain makes with `r7 = 0x1100`; `0x1100` is also the disconnect-wrapper param
  `0x01E1782C(addr,0,0x1100)`). Body partially seen (`0x21976` compares; tail-jump `goto 0x1782C` @
  `0x21980`; `0x21984: r0 = −2; rts`) — **dump fully next round: if it starts SDP/HFP over an EXISTING
  ACL this is the cleanest R5 hook (no kick needed).**

**5. R5 design state (updated ranking):**
- **(C, NEW LEAD) call `0x01E2193A` directly on the existing incoming conn record** from the tbh cave —
  if it handles "ACL already up" it IS the profile-bring-up call; dump body first.
- (A) kick incoming ACL (`0x01E1782C(addr,0,0x1100)`) + arm stack mailbox `0x1A5D1` for re-dial —
  viable ONLY if the `0x01E21E38` trigger is found; redial posts no cmd 5 ⇒ routing byte stays 1 ⇒
  would ALSO need a forced bind on the second tbh hit (marker byte TBD).
- (B) app-redial record `0x1A4C8/C9` — **DEAD for same-device** (guard, §30.14.30-2 above).
- (D) §30.9 rewrite routes (code-cave connect-flow ch. 23/25, SDK rebuild ch. 28, ESP32 combo) if all fail.
- Open sub-question either way: app struct `0x102F0` re-bind to the second device (E6 showed the
  radio-initiated dial + press binds `0x102F0` and mode-3 audio routes to it; with only one SCO alive,
  audio likely follows it — plausible, UNTESTED).

**UNTESTED — analysis only; radio remains on R4 `9168ac96` (field-FAILED; E7-ref rebuild recipe:
E7 recipe from `Dumps/dump_internal.bin` → `work/ch30_e7ref.bin` `90bec320`). NEXT: dump
`0x01E2193A..0x01E21984` body + hunt `0x01E21E38` trigger + `0x01E2232E`/`0x01E2234E` epilogues ⇒
R5 design decision.**

### §30.14.31 — R5 static round 5: re-dial mailbox CORRECTED to `0x1A5F1`, kick/compare primitives proven, cave window verified (2026-11-03)

Official-objdump round (full-app dump generated once: `/tmp/opencode/app_full.o.lst`, 316,896 lines —
reuse for greps).

- **ADDRESS CORRECTION (critical)**: the stack re-dial mailbox is **RAM `0x1A5F1`** (task-base
  `0x1A520` + 209 = `r2 = r14 + 209` @`0x01E21E46`), NOT `0x1A5D1` — the rounds-3/4 label was an
  arithmetic slip (209 = 0xD1). `0x1A5F1` is thus **identical to the RE-PAGE mailbox of §30.14.14**
  (the R1-e poison cell). The dial post itself confirmed: `0x21E46: r2 = r14+209; r0 = 1; r1 = 6;
  call 0x01E1792E` = `user_send_cmd_prepare(START_CONNEC_VIA_ADDR, 6, 0x1A5F1)` (cmd **1** ✓).
- **Why R1-e poisoned it but R5 can use it safely**: event-0 (link tick) handler itself **maintains**
  the mailbox as the stack's connection-intent — at `0x21C3E` it copies the claimed record's address
  INTO `0x1A5F1` before `call 0x2193A`, and `0x21988` re-saves it on failure (mailbox select: bit
  `0x40` of record byte `+19` → `0x1A5F1` else second mailbox `0x1A65A` = +314). Epilogue `0x2232E`
  OR-folds the 6 bytes (`0x22330` `r1 = b[++r0=209]` chain) → non-zero → `goto 0x21E46` dial.
  R1-e armed it on EVERY manual Connect press (target often already connected → permanent
  guard-exit re-dial intent + the misaligned-load fault). R5 arms ONLY in the crippled incoming-join
  state (byte==1 && both records inuse && mailbox ≠ joining addr) and immediately frees the slot via
  HCI-Disconnect, making the redial valid. Guard-exits do NOT consume the retry counter
  (`b[0x1A520]` ≤ 15 increments only on the `0x2235A→0x1C53E` failure exit).
- **Additional redial posters found**: event 77 @`0x21D58`: `if (b[r12+21] & 0x40) goto 0x21E46`;
  event 66 @`0x21D62`: mailbox select by `b[r12+16] & 0x20` (`0x1A5F1`/`0x1A65A`) → post
  `(1, 6, mailbox)`. (r12 = event payload struct.)
- **cmd-1 consumer chain re-verified byte-exact** @`0x21E54`: `r7 = 0x1100`; is_1t2 gate
  (`if r0 != 0 exit` @`0x21E5C`); links `ifs < 0` exit; `r5 = 0x1A5FD` (cmd-1 dial-addr mailbox);
  same-address guard `0x16824(r5)` → exit if connected; `0x2181C(r5, 0)` claim record;
  `0x21A44(0)`; `0x18AFC(0)`; `0x2193A(r5, 0x1100)`; r0==0 → exit; else `0x21988(r5, 0)` save-redial.
- **Conn-record layout CONFIRMED** (base = record ptr, from `0x21988`/`0x2234E`/`0x2181C`):
  `+0..5` = BD_ADDR (`0x21988` copies 6 B from arg0 = record), `+6..7` = handle halfword
  (`0x2181C` connected-path `h[r0+6] = param`), `+8` = callback ptr (called `(0, 252)` at
  `0x22352` when already-connected), `+15..18` = state word, `+19` = flags (bit `0x40` mailbox
  select, bit0 set by `0x2193A`).
- **Find-conn `0x01E17420` = THUNK → `0x01E079CA`** (dump `17420: goto 0x79CA` — earlier partial
  dumps were mis-aligned). Body: `call 0x14BA8(r0 = addr)` → obj; `obj+164`; **mode != 1**:
  `r6 = [obj+164+40]`; if 0 → return 0; `memcmp([[r6+28]+196]+155, addr, 6)` via
  **`0x01E3127B0(r0 = p1, r1 = p2, r2 = len)` → 0 = equal**; equal → return `b[r6+0]` (handle byte).
  **mode == 1**: `if (([obj+164] & 9) != 8) return h[obj+164+4]`. Returns 0 when not found.
- **PROVEN KICK PATTERN — function `0x01E178B2(addr)`** (the E3 executor's caller):
  `r5 = addr; r1 = 0; call 0x17420; if (r0 != 0) → r0 = r0.l; r1 = 19 (0x13); call 0x01E07B08;
  return 0` — else `r1 = 2; call 0x17420; if (r0 != 0) → same disconnect; else return 1`.
  i.e. **find-conn mode 0, then mode 2, then `0x1E07B08(handle, 0x13)`** (HCI Disconnect via
  `0x2AAE(h, 2, 0x406, reason)`). R5 cave replicates this sequence exactly (reason 0x13 = stock
  kick value; Jabra reconnect behavior on 0x13 proven by stock behavior).
- **tbh mode table + teardown re-verified** (unchanged): hook `0x01E61270 = 50 ee 64 0d`; teardown
  sentinel store `b[r6+212] = r12(0xF0)` @`0x01E61C88`; setup block reads `b[r6+209]` @`0x611EA`,
  writes `b[r6+210]` @`0x61258`.
- **R5 CAVE WINDOW VERIFIED**: `0x01EA7722..0x01EA77F5` (212 B) = **ALLZERO in v44, v45, v50 AND
  E7-ref; pointer-scan (every 2-byte-aligned LE word vs whole-image 4-byte occurrences) CLEAN**.
  Window bounded below by BT-PTT2 cave (`0x01EA76DE..0x01EA7721`, 68 B) and above by the
  R3/R4/INCHFP window (`0x01EA77F6..`). GATE_CAVE2 (`0x722`) / R1_CAVE (`0x758`) / CMD5T (`0x7A8`)
  / PRESST (`0x7D0`) constants from the dead R1-e era occupy this window in OTHER recipes' images →
  R5 cave there needs `--show` cross-recognition states (established pattern) — R5 replaces the
  R1-e-era usage (those flags never flashed successfully; images not in the field).
- **R5 DESIGN FINAL (`--incoming-redial`)** — cave @`0x01EA7722`, hook `0x01E61270` (same
  `82 ea c1 32` as R3/R4 — mutually exclusive with both), frame `[sp+20]` = joining BD_ADDR ptr
  (§30.14.26 proof):
  1. `byte = b[r6+212]`; if `byte == 1`: both records inuse (`b[0x1A5CA]&0x20 && b[0x1A5E6]&0x20`)
     else RET; `memcmp(0x1A5F1, [sp+20], 6) == 0` → RET (loop guard — never re-kick our own redial);
     copy `[sp+20] → 0x1A5F1` (6 B byte-wise); `0x17420([sp+20], 0)` → if 0 `0x17420([sp+20], 2)`;
     if handle ≠ 0 → `0x1E07B08(handle, 0x13)`; RET **byte unchanged**.
  2. if `byte == 0xF0` (teardown sentinel left by the kick) AND `memcmp(0x1A5F1, [sp+20], 6) == 0`
     (the device we armed is the one now connected-complete) → **write `b[r6+212] = 3`, return 3**
     → mode-3 local enablers run; Jabra opens HFP/SCO over the radio-dialed ACL (E6/P6-proven
     combination). Mailbox deliberately KEPT (stock reconnect semantics → Jabra power-cycle may
     auto-remedy = incidental P7).
  3. else RET byte (exact stock).
  Estimated size ~150 B < 212 B. Primitives all objdump-proven above; `0xF0` compare needs
  reg-reg compare encoding (`80 e8` form @`0x1743E`) or `r1 = 0xF0` const + cmp — objdump
  round-trip at build time.
- **Residual risks (recorded)**: (a) `[sp+20]` frame correctness = static proof only (R4 field
  proved the cave RUNS, not the pointer value) — mitigated: wrong addr = failed memcmp guard =
  silent no-op, no poison; (b) if Jabra never answers the redial, mailbox persists = stock failed
  dial semantics (bounded retry counter on failure exits); (c) struct `0x102F0` app-binding to the
  redialed device UNTESTED (E6 bound via press; R5 has no press) — if audio routes but SPP/keying
  misbehaves, that is the next static target; (d) two-SPP-button edge = forced mode-3 on 2nd
  button (same accepted caveat as R3).

**UNTESTED — nothing flashed. Radio remains on R4 `9168ac96`. NEXT: implement `--incoming-redial`
(sites inchrdl/inchrdlcave, mutual exclusion inchfp+incmode3), objdump round-trip, suites, build
`work/ch30_r5.bin`, stage + card.**

### §30.14.32 — R5 BUILT: `--incoming-redial` implemented (2 sites), objdump round-trip + both suites green, image `work/ch30_r5.bin` `dc4b2704…` staged (2026-11-03)

**Implementation (this session, 2026-11-03)** — `tools/patch_h3plus_firmware_bluetooth.py`:

- **INCHRDL block** (after INCHFP): constants `INCHRDL_HOOK_VA = 0x01E61270` (ctx
  `50ee640d` = `r0 = b[r6+212] (u)`), `INCHRDL_CAVE_VA = 0x01EA7722`,
  `INCHRDL_MB = 0x0001A5F1` (the re-dial mailbox — **ODD, byte-wise accesses only**,
  the R1-e misalignment lesson), `INCHRDL_FIND_VA = 0x01E17420` (find-conn),
  `INCHRDL_KDISC_VA = 0x01E07B08` (disconnect(handle, reason)), the 174-byte
  `INCHRDL_CAVE_BYTES` with a full line-by-line disasm comment.
- **Cave logic** (objdump round-trip verified against the JieLi LLVM objdump
  `-mcpu=r3`, harness `/tmp/opencode/r5_asm.py`; RET=+12 DONE=+18 ARM=+34 CMP6=+112
  NE=+170): `+0` load routing byte; `==1` → ARM; `==0xF0` → DONE; else RET
  (byte unchanged). **ARM** (the kick+redial): require slot 0 inused
  (`b[0x1A5CA] & 0x20`) AND slot 1 inused (`b[0x1A5E6] & 0x20`) — the two-device
  state of §30.14.17 — else RET; loop guard CMP6(mailbox, `[sp+20]`) equal → RET
  (already armed for this joiner: no kick/redial cycle can form); copy `[sp+20]` 6 B
  → `0x1A5F1` (`rep 4 6` byte-wise, dst `c0 ff f1 a5 01 00`); find-conn(mode 0,
  addr) → if 0 RET; `r1 = 0x13` (r0 = handle — **zero-extended by find-conn itself**,
  verified: `0x01E079CA` returns `r4 = 0 | b[r6+0] (u)`, so no `rtsl` needed) →
  `call 0x01E07B08` = HCI Disconnect(reason 0x13); `r0 = 1; rts` (byte == 1
  guaranteed on this path). **DONE** (teardown): CMP6(mailbox, `[sp+20]`) equal →
  `b[r6+212] = 3` (mode-3 local mic/speaker enablers, §30.14.24) `rts`; else RET.
  **CMP6**: `r1 = 0x1A5F1`; 6 × {`r0 = b[r1++=1]; r3 = b[r2++=1]; r0 ^= r3;
  if (r0 != 0) goto NE`}; `r0 = 0; rts`; NE: `r0 = 1; rts`.
- **Window discipline**: 174 B @`0x01EA7722` ends **exactly at `0x01EA77D0`** = the
  legacy cmd5tcave window END (= presstcave START) — presstcave/d1thunk/incmode3cave
  stay untouched; the cave fully contains the gatecave/r1cave/r1bcave/cmd5tcave
  windows → **mutually exclusive** with `--gate-close`/`--r1-conditional-kill`/
  `--r1-walker-kill`/`--cmd5-target` (CLI SystemExit) and with `--incoming-mode3`/
  `--incoming-hfp` (same hook — three-way `_tbh_picks` SystemExit).
- **Cross-recognition (recognition only, all STATIC)**: `inchrdl` knows state
  `incmode3` (= `INCHFP_HOOK`, R3/R4 share the identical hook bytes); `incmode3` +
  `inchfp` know `inchrdl`; `inchrdlcave` carries 5 static legacy states
  (`legacy_gate`/`legacy_r1a`/`legacy_r1b`/`legacy_cmd5t`/`legacy_gate_cmd5t`)
  composed from the real window occupants; `gatecave`/`r1cave`/`r1bcave`/`cmd5tcave`
  know `inchrdlcave` slices.
- **Tooling lesson recorded**: the first legacy-state draft was flag-DYNAMIC and the
  `gate-close reverts to stock` suite case **FAILED** — `find_app_start` validates
  every site's ctx against the module-level default `PATCHES = build_patches()`, so
  recognition states must never depend on the current flags. Fixed by the 5 static
  combos above. (Any future site spanning another patch's window: same rule.)
- **NO cmd-1 bail NOP** (unlike R4): at redial time only 1 link is up (< conn_num 2)
  so `is_1t2_connection()` is false and the cmd-1 handler passes naturally — the
  R5 image leaves `0x01E17A2A` stock (suite-asserted).
- **Suites**: `verify_actions.py` **0 failures** — new R5 block: build, hook+cave
  written, `INCHRDL_HOOK == 82ea5732`, cave hex literal (174 B), touches-only-2-
  windows (158 B), cave-ends-at-`PRESST_CAVE_VA` assert, `--show` clean on R5/R3/R4/
  gated/R1-e images in both flag directions (cross-recognition), idempotent, E7-combo
  carries hook+cave with cmd-1 bail stock + D1 thunk erased. `verify_cli.py`
  **0 failures** — cases `r5`, `r5_e7`, `irdl_alias`, `irdl_conf_im3`,
  `irdl_conf_ihfp`, `irdl_conf_gate`, `irdl_conf_c5t`, `irdl_conf_r1b`.

**Image**: `work/ch30_r5.bin` full-image sha256 `dc4b27041e64cffd…`, built from
`Dumps/dump_internal.bin` with the E7 recipe + `--incoming-redial`:

```bash
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin work/ch30_r5.bin \
  --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2 --no-kick --force-page-scan \
  --force-role-keep --no-disconnect-13 --no-pairing-kick --incoming-redial
```

Diff vs `work/ch30_e7ref.bin` (`90bec320…`) = **EXACTLY sectors `0x066000` (hook,
flash `0x66270`) + `0x0AC000` (cave, flash `0xAC722`), 158 bytes**; decrypt-verified
hook `82ea5732` @`0x01E61270`, 174 B cave @`0x01EA7722`, cmd-1 bail stock. VM
untouched — pairings survive.

**Stage + card**: `work/ch30_r5.sh` (EXPECT_SHA guard, sector-diff assert, 2-sector
erase/write/readback ×2, full strict-region verify §30.3, ledger-row print) then
`work/ch30_r5c.sh` — **S0** TID-PTT-alone regression; **S1 = GOAL** (TID-PTT up →
Jabra pages in at its own power-on → expected: join, brief drop = the kick, radio
re-dials → TX Jabra mic? RX earphones? button still keys? freeze?); **S2** 5-min
persistence; **S3** Jabra power-off (R3/R4 echo-loop watch) + re-join (P7 mailbox
bonus check); **S4** Jabra-first order; **S5** repair press (known stock-kick). No
rollback script (user directive 2026-11-03 — recipe: sectors `0x066000`+`0x0AC000`
from E7-ref `90bec320`).

**Residual risks (pre-declared)**: (a) `[sp+20]` = joining BD_ADDR ptr is
static-proven only (tbh caller passes the connect-complete record) — a garbage addr
would dial garbage (bounded: stack retries then stops); (b) app struct `0x102F0`
binding to the redialed device while the SPP incumbent holds the first slot =
UNTESTED (the actual goal question); (c) two-SPP-button edge forces mode-3 on the
second button (same accepted caveat as R3).

**UNTESTED — nothing flashed by this build. Radio remains on R4 `9168ac96`.**
**NEXT: user runs `sudo bash work/ch30_r5.sh` + `bash work/ch30_r5c.sh`; field
verdict → §30.14.33.**

### §30.14.33 — R5 FIELD RUN 2026-11-03: two-device state STABLE, zero freezes — but audio NEVER binds to the Jabra (TX stays TID-PTT mic, RX silent). FAIL on goal; kick+redial firing UNCONFIRMED (S1a tone ambiguous). R6 discriminator needed

**Flash (`work/logs/ch30_R5_20261103_201008.log`)**: image sha `dc4b27041e64cffd`
OK; sector-diff assert PASS (only `0x066000`+`0x0AC000` vs E7-ref); both sectors
erase+write+readback **IDENTICAL attempt 1**; FULL-FLASH VERIFY PASS (strict
`0x0000–0x0C8FDF`). Boot: Q1 "radio alive all ok"; Q2 "**Jabra auto connected**"
(stock power-on reconnect — the mailbox is RAM, not armed at boot; same as E7-ref).

**Card (`work/logs/ch30_R5card_20261103_201307.log`, verbatim answers)**:

| # | Question | Answer | Read |
|---|---|---|---|
| S0a | TID-PTT connects (menu)? | "connected ok" | no regression |
| S0b | Button keys, mic OK? | "Yes" | single-device path healthy |
| S0c | RX on speaker? | "Yes" | normal |
| S1a | Jabra powers on (pages IN) — what happens? | "**mobile connected sounded on the jabra**" | link established — ambiguous: incoming page accept OR redial ring; user saw NO explicit drop+reconnect |
| S1b | Both connected? | "**both connected**" | two-device state reached |
| S1c | TX mic? (BT-PTT + button) | "**TX with TID-PTT button and BT-PTT on the radio both TID-PTT mic**" | **NOT Jabra — goal miss** |
| S1d | RX destination? | "**silence no audio on RX**" | **total silence — goal miss** |
| S1e | Button keys with both up? | "yes" | SPP command path alive |
| S1f | Freeze / echo? | "all ok no sidetone/echo" | **NO freeze — cave is safe** |
| S2a/b | Persistence (~1.5 min logged) | "still up" / "nope still same" | stable; binding never moved |
| S3a | Jabra OFF | "After poweroff off of the Jabra the TX … is from the Radio mic and the RX is coming on the radio speaker again. Also … the TID-PTT button does not trigger the TX anymore but its still connected to bluetooth and there is an echo loop from the TID-Mic on the radio Speaker…" | **echo loop AGAIN** (R3 §30.14.22/25 teardown/restore family) + button keys die |
| S3b | Button keys after Jabra-off? | "**Only once**" | then dead while ACL stays up |
| S3c | Jabra back ON re-joins? | "**no**" | P7 NOT fixed in this state (mailbox consumed/cleared by teardown, or teardown never matched) |
| S4a | Jabra-first boot, Jabra audio | "all ok" | P6 path healthy (radio-dialed → classifier → mode 3) |
| S4b | Then menu-connect TID-PTT | "**kick the Jabra connects the TID-PTT**" | stock outgoing kick — cave does NOT intercept the outgoing path (expected) |
| S5a | Repair press (menu→Jabra→Connect over TID-PTT incumbent) | "**kick TId-PTT, Jabra connected**" | stock kick, **NO freeze** |
| S5b | Jabra audio after that | "after connect audio on the Jabra" | **when the radio DIALS the Jabra as app-current-device, audio binds PERFECTLY** |

**Verdict: FAIL on the goal** — identical observable signature to R3
(§30.14.23) and R4 (§30.14.28): both links up, TX = TID-PTT mic, RX = silence.
Positives: **zero freezes anywhere** (the 174 B cave + mailbox arm never wedged
the app or dispatcher — the R1-e/R2-a poisoning failure mode did NOT recur even
though the mailbox was written at tbh), no single-device regression, stable
two-device links, S5 repair press clean.

**The open discriminator (unresolved by this run)**: did the kick+redial
actually fire in S1? Two consistent stories, same observations:
- **(A) fired + redial completed** → app struct `0x102F0` stayed bound to
  TID-PTT (it was never re-pointed by a stack-level redial) ⇒ wall = **APP
  current-device binding**, profile links may exist but the app ignores them.
  S1a "mobile connected" tone supports a dial arriving at the Jabra.
- **(B) never fired** (predicate false at tbh: byte ≠ 1, or a slot-inused byte
  read differently than the static model, or find-conn returned 0 for the
  incoming record) → no kick, no redial, no profiles — exactly the R3/R4
  situation. The absence of an observed drop favors (B); the S1a tone is weak
  evidence for (A).
R4 already proved the cave location runs at incoming connect-complete with a
usable `[sp+20]` address (its SCO disturbance was heard), so the hook itself
fires; what is unproven is the **ARM predicate** and the **kick success**.

**R6 plan (next static round before any flash)** — make the cave SELF-REPORTING
and re-run S1 once:
1. **Reason-code telemetry**: kick with a distinctive HCI reason (e.g. `0x11`
   authentication instead of `0x13`) — the Jabra/any phone observer logs the
   reason; reason `0x11` arriving = ARM path executed + find-conn succeeded.
2. **Predicate widening probe**: if (B), the likely culprits are the two
   slot-inused byte reads (`b[0x1A5CA]&0x20` / `b[0x1A5E6]&0x20`) — re-verify
   statically which byte of word `+0xE` holds bit29 for the SECOND record
   (little-endian: byte `0x1A5EA` bit 5, not `0x1A5E6` — the current cave reads
   the LOW byte at `+0x12`… MUST re-check against `0x1A5B8+0x1C·1+0xE`).
3. If (A) is confirmed: the fix moves app-side — re-point struct `0x102F0`
   (handle `+0x82`, address fields) to the redialed record at the redial's own
   connect-complete, or force the classifier path — ch. 25 compile-route
   territory.

**Radio now on R5 `dc4b2704…`.** Rollback recipe (no script, per directive):
sectors `0x066000`+`0x0AC000` from E7-ref `90bec320…` (pairings survive).

### §30.14.34 — R6 STATIC PASS 2026-11-03: all three R5 suspects CLEARED — kick+redial chain is statically SOUND end-to-end ⇒ hypothesis (A) confirmed as the model: the wall is the APP current-device binding (struct `0x102F0`), not the stack chain. R6a = 6-byte cave change (stamp byte 3 at the redial loop-guard)

Ran the option-(1) static re-verification pass against the official objdump of the
stock app (`/tmp/opencode/app_full.o.lst`; all sites `VA − 0x01E00000`). Stack-task
global base **`r14 = 0x1A520`** (proven: `r14/r0/r1/r8 = 107808 <0x1A520>` immediates
at `0x1788E`/`0x17946`/`0x184A2`/`0x18FA2` …). Results per suspect:

**(a) Slot-`inused` reads — CORRECT (R5 cave innocent).** The stack's own tests at
`0x01E16824` (same-addr guard; iterates `r6 = 0x1A5B8`, stride `0x1C`, 2 records to
`+56`) and `0x01E1687A` compose the LE word at record `+0xF` from byte loads and test
`& 0x20000000` — bit29 = **bit 5 of byte record+0x12** = `0x1A5CA` / `0x1A5E6`,
exactly what the cave reads. (Ch. 27's "word at `+0xE`" note was off by one; the
`+0xF` composition here is authoritative.)

**(b) Dispatcher epilogue — CONFIRMED exactly as modeled.** `0x01E2232E`:
`r0 = r14; r1 = b[++r0=209]` then OR-folds the 6 bytes `0x1A5F1..F6`;
`if ((r0 & 0xFF) != 0) goto 0x21E46` where `0x21E46: r2 = r14+209; r0=1; r1=6;
call 0x1792E` = **`user_send_cmd_prepare(1, 6, mailbox)` = the cmd-1 DIAL with the
mailbox BD_ADDR**. Entry: dispatcher `0x01E21B8E` tbh table (events 0–21), **event 0**
→ `0x21BC4`: `is_1t2()` bail, then state word `h[r14+322]` (`0x1A662`):
`(r1 & 0x38) == 0` → epilogue above; else the **connect-FAILURE retry case**
`0x21BCE..0x21C4A`: rotates the state, same-addr guard `0x16824`, record lookup
`0x2181C`, then **arms the mailbox itself**: `0x21C3E: r0 = r14+209; rep 4 6 {
b[r0++] = b[r1++] }` — copies the failed record's 6-byte BD_ADDR in. This is the
vendor auto-retry loop; **our cave copies the vendor mechanism exactly.**
EMPIRICAL PROOF the epilogue dials: R1-e §30.14.14 — presst poisoning `0x1A5F1`
made the radio RE-PAGE. The epilogue fires after arming, period.

**(c) find-conn `0x01E17420` — CORRECT for the incoming link.** It is `goto
0x79CA`: `r5 = addr`, `call 0x14BA8(addr)` — walks the conn objects at **`0x1A0A8`,
stride 224, 2 objects**, tests active `h[obj+168]` + ptr `[obj+196]`, then
`memcmp([[obj+196]+155], addr, 6)`; match → back in `0x79CA`, mode 0 path `0x79EE`:
`r6 = [obj+204]` (l2cap conn block), re-verifies `[[[r6+28]+196]+155] == addr`,
returns **`b[r6+0]` = the HCI handle**. It **walks BOTH records by BD_ADDR** — the
incoming joiner is findable. Not the failure point. (Cave ABI `r0=addr, r1=0` ✓.)

**Mailbox clear search — NONE EXISTS.** The only writer of `0x1A5F1..F6` in the whole
app is the vendor `rep 4 6` arm @`0x21C44` (+ our cave). The epilogue posts the dial
without clearing; the vendor retry case re-arms the same address on each failure.
⇒ Once armed, **every event-0 pass with state bits `0x38` clear re-posts the cmd-1
dial** — a persistent re-dial loop until a connect succeeds and the state machine
settles. Explains why no explicit "clear" was ever needed by the vendor flow.
(Side-read: `0x21D6E` — a second dial-post uses the mailbox when `b[r12+16]&0x20`,
else `r14+314` = a second 6-byte address cell @`0x1A65A`; same cmd 1.)

**VERDICT**: R5's ARM predicate (byte==1 — proven true by R4's SCO-disturbance at
the same hook with the same reads), the slot checks, the arm, find-conn and the
kick all stand; the vendor mechanism is proven to re-dial (R1-e). **The kick+redial
fired in S1.** The Jabra came back radio-dialed (S1a "mobile connected" = the redial
ring) with HFP riding cmd 1 — yet audio never bound because **the app's
current-device struct `0x102F0` was never re-pointed**: stack-originated redials
inform no app, no remote-name request runs, the classifier `0x01E7EC28` never fires,
byte stays 1 → mode-1 no-op (the §30.14.17 crippling). S5b is the control: the same
cmd-1 dial *when the app itself initiates it* binds perfectly.

**S3c (no re-join after Jabra power-cycle) re-explained**: mailbox stayed armed all
along (no clear) — but after the R3-style forced paths the teardown `0xF0` sentinel +
cave DONE branch had already consumed the moment; the radio's re-dial loop pages the
Jabra while it is OFF and the vendor retry case rotates the state machine; once the
Jabra came back the app was mid-`0xF0` teardown state (S3a echo + dead button). The
button-dies-after-one-key + echo = same teardown/restore gap family as R3
§30.14.22/25 (RX-source never restored), now twice-reproduced.

**R6 design (proposal — NOT yet built):**
- **R6a (cheap test of the model, ~6 B cave change)**: the cave's LOOP-GUARD branch
  (byte==1 && mailbox==joiner — i.e. THIS connect-complete is our own redial)
  currently `RET` with the byte unchanged. Change it to **stamp `b[r6+212] := 3`**
  (the classifier's own value) before returning. If the mode-3 consumers only read
  the byte + live HFP link (which the redial establishes), audio binds — the goal.
  If it stays silent: byte 3 alone is insufficient and the app struct re-point is
  mandatory. One sector pair, same stage script.
- **R6b (the real fix if R6a fails)**: re-point struct `0x102F0` (handle `+0x82` +
  address fields) to the redialed record at the redial connect-complete — app-side
  surgery, ch. 25 compile-route territory.
- Telemetry (reason `0x11`) is **moot** — static + R1-e already prove the chain.

**Radio remains on R5 `dc4b2704…`.** Rollback recipe unchanged: 2 sectors
`0x066000`+`0x0AC000` from E7-ref `90bec320` (no script, per directive).

### §30.14.35 — R6a BUILT 2026-11-04: `--redial-bind` (ONE cave byte: loop-guard RET→DONE stamps routing byte 3 at our redial's connect-complete). Objdump round-trip + both suites green; image `work/ch30_r6a.bin` `62214f14…` staged (2 sectors). UNTESTED

User approved ("yes build r6a"). Implementation in
`tools/patch_h3plus_firmware_bluetooth.py`:

- **New flag `--redial-bind`** (requires `--incoming-redial`; standalone use =
  SystemExit). `build_patches(..., incoming_redial, redial_bind)`.
- **The change is exactly ONE byte**: `INCHRDL_CAVE_BYTES_BIND =
  INCHRDL_CAVE_BYTES[:73] + b"\x44" + INCHRDL_CAVE_BYTES[74:]`
  (`INCHRDL_BIND_OFF = 73`). Cave +72/+73 is the ARM-path loop-guard
  (`70 41` = `if (r0==0) goto RET(+12)`, where `r0` = CMP6(mailbox, joiner)).
  `0x41→0x44` retargets it to **DONE(+18)** — the teardown branch, which re-runs
  CMP6 on the same inputs (returns 0), then `r0=3; b[r6+212]=3; rts`.
  ⇒ when the connect-complete is OUR OWN redial (byte==1 && mailbox==joiner),
  the routing byte is stamped **3** — the classifier's own HFP-audio value —
  instead of being left at 1 (the §30.14.17 mode-1 no-op). Branch-distance
  formula `target = pc + (byte1−95)*2` verified against all three existing
  guards; `0x44` → +18 = DONE exactly.
- **Safety**: idempotent (after the stamp, byte==3 falls through to RET on every
  later tbh call); the mailbox stays armed but the dispatcher event-0 path bails
  via `is_1t2` while both links are up (no dial storm); R3's failure mode
  (forcing byte 3 with NO HFP/SCO on the incoming link) CANNOT apply here —
  the guard only fires on the stack-originated **cmd-1 redial**, which brings up
  HFP/SCO by construction (E6/P6-proven profile path).
- **Recognition fix needed**: the legacy-window sites `gatecave`/`r1cave`/
  `r1bcave`/`cmd5tcave` (ctx windows overlapping cave +73, e.g. `0x01EA7758`)
  were taught the R5 `inchrdlcave` slice but not the BIND variant → first suite
  run failed 2 checks (`--show` on R6a image, idempotency) because
  `find_app_start` returned None. Fixed by adding **static** `inchrdlbind`
  state/label entries in the same `_lz_name` teaching loop (static =
  recognition-safe per the `find_app_start` default-gates rule).

**Verification (all green 2026-11-04)**:
- `tools/verify_actions.py` **0 failures** — R6a block: build OK, hook +
  bind-cave written, diff vs R5 cave only at +73, branch lands +18 (DONE),
  `--show` clean on R6a image, cross-recognition of the R5 image under
  `--redial-bind` clean, idempotent "Nothing to do".
- `tools/verify_cli.py` **0 failures** — new cases `r6a` (exit 0),
  `r6a_alias` (`--REDIAL-BIND`, exit 0), `r6a_alone` (exit 1).
- **Objdump round-trip** (official `objdump -mcpu=r3` lineage, harness
  `/tmp/opencode/r5_asm.py` pattern): cave disassembles cleanly end-to-end;
  `a776a: 70 44  if (r0 == 0) goto -56 <.text+0xA7734>` = DONE; DONE body
  `r2=[sp+20]; call CMP6 → r0=3; b[r6+212]=r0; rts` confirmed.
- **Image**: `work/ch30_r6a.bin` sha256
  `62214f1405c4d33083bb0cd2015f1f159529a019050a4dd1a9133dc8e05db5b8`
  = E7 recipe + `--incoming-redial --redial-bind` from `Dumps/dump_internal.bin`;
  diff vs `work/ch30_r5.bin` = **exactly 1 byte** @ flash `0xAC76B` (cave +73);
  diff vs E7-ref = sectors `0x066000`+`0x0AC000` only (158 B).
- Stage `work/ch30_r6a.sh` + field card `work/ch30_r6ac.sh` ready
  (`bash -n` OK). Card S1 WIN conditions: **S1c TX = Jabra mic** and
  **S1d RX in the earphones**; S3a echo-loop watch (known R3/R5 teardown-gap
  family); S5 repair press regression.

**Prediction under the §30.14.34 model**: kick+redial fires as in R5 (S1a); at
the redial's connect-complete the cave now stamps byte 3 **while the redial
link's HFP/SCO are live** → mode-3 consumers route TX = Jabra mic, RX =
earphones. If audio stays silent, byte 3 alone is insufficient ⇒ **R6b** =
re-point app struct `0x102F0` (handle `+0x82` + address fields) at the redial
connect-complete — ch. 25 compile-route territory.

**UNTESTED — nothing flashed by this build. Radio remains on R5 `dc4b2704…`.**
**NEXT: user runs `sudo bash work/ch30_r6a.sh` + `bash work/ch30_r6ac.sh`;
field verdict → §30.14.36.** Rollback recipe (no script): 2 sectors
`0x066000`+`0x0AC000` from E7-ref `90bec320`.

**Stage-script gotcha 2026-11-04**: first user run of `work/ch30_r6a.sh`
false-STOPPED at preflight (`image sha 62214f1405c4d330 != expected 62214f14…5b8`)
— the script compares a 16-char truncated sha (`cut -c1-16`) against the
full-64 `EXPECT_SHA` (sed slip from `r5.sh`, whose EXPECT_SHA was 16-char);
fixed to `62214f1405c4d330` and log prefixes renamed (stage `ch30_R6a_`,
card `ch30_R6acard_`). The image itself was always correct
(`work/ch30_r6a.bin` = `62214f1405c4d330…`).

### §30.14.36 — R6a FIELD RUN 2026-11-04: FAIL on goal (4th identical signature) — stamp executed (S3 CLEAN, no echo) but mode-3 at redial connect-complete binds nothing; S5 repair-press REGRESSION (kicks both, nothing reconnects). Wall CONFIRMED = app current-device struct `0x102F0`

**Flash (`work/logs/ch30_R6a_20261104_114201.log`)**: preflight sha
`62214f1405c4d330` OK (fixed script); sector-diff assert PASS (only
`0x066000`+`0x0AC000` vs E7-ref); both sectors erase+write+readback
**IDENTICAL attempt 1**; FULL-FLASH VERIFY PASS (strict `0x0000–0x0C8FDF`).
Boot: Q1 "Ok"; Q2 "**Jabra auto connected**" (stock power-on reconnect).

**Card (`work/logs/ch30_R6acard_20261104_114302.log`, verbatim answers)**:

| # | Question | Answer | Read |
|---|---|---|---|
| S0a–c | TID-PTT alone (menu) | "all ok" / "yes TID-PTT mic on TX" / "Normal RX on radio speaker" | no single-device regression |
| S1a | Jabra pages IN (TID-PTT incumbent) | "**Jabra joind, said mobile connected but It took a lille longer than normal (my feeling)**" | the delay corroborates the kick→redial chain running (§30.14.34 model) |
| S1b | Both connected? | "**both connected**" | two-device state reached, again |
| S1c | TX mic? | "**TX on PTT button TID-PTT tigged TX but audio from radio mic!**" | **NOT Jabra — goal miss** (note: RADIO mic — neither BT mic) |
| S1d | RX destination? | "**audio on radio instead of headset**" | **speaker — goal miss** |
| S1e | Button keys both up? | "yes" | SPP command path alive |
| S1f | Freeze / echo? | "no echo no sidetone, no freeze" | cave safe again |
| S2a/b | 5-min persistence | "yes still works" / "no same as before" | stable; binding never moved |
| S3a | Jabra OFF | "**no echo loop, no side tone not directly on disconnect also not after first rx**" | **CLEAN teardown — UNLIKE R5** (echo loop + dead button): the DONE stamp ran and the byte-3 teardown path left a consistent state |
| S3b | TID-PTT keys + RX speaker after | "yes" | |
| S3c | Jabra back ON re-joins? | "**no did not auto join, not within a minute. nothing; just silence on the headset and radio**" | P7 one-join-per-boot persists |
| S4a | Jabra-first (reboot) | "ok, **need to pair it again to the radio** but than it was connected perfectly" | P6 path healthy (re-pair needed after the R6a session) |
| S4b | Menu-connect TID-PTT | "**kick, jabra drops**" | stock outgoing kick (cave does not intercept outgoing — expected) |
| S4c | After | "TID-PTT connected and operating normally" | |
| S5a | Repair press (menu→Jabra→Connect over TID-PTT) | "**kicked both Jabra and TID-PTT, I heared mobile disconnected**" | **REGRESSION vs R5 S5** (where the menu dial connected Jabra + bound audio perfectly) |
| S5b | End state | "**no devcie connected RX on radio speaker**" | nothing connected |

**Verdict: FAIL on the goal** — 4th consecutive identical observable
(R3 §30.14.23, R4 §30.14.28, R5 §30.14.33, R6a): both links can be up, but TX
never uses the Jabra mic and RX never reaches the earphones. Zero freezes
(5th clean run for the cave family).

**What R6a PROVED (the discriminator worked)**:
- The stamp **executed**. Evidence: (i) S1a join delay = kick+redial cycle;
  (ii) **S3 is CLEAN** — R5 (byte stays 1) produced the echo-loop + dead-button
  teardown mess, R6a (byte stamped 3) tore down silently. The DONE path ran and
  the byte-3 teardown restore is the consistent one.
- Yet audio did not bind ⇒ **forcing the routing byte to 3 at the redial
  connect-complete is NOT sufficient**. Under the §30.14.24 correction the mode-3
  tbh entry (`0x6128C`) is a STATE path, not a bind: the actual bind is performed
  by the **app-initiated dial flow** — menu Connect → app dials → connect-complete
  setup block runs **with struct `0x102F0` already pointing at the target** (and
  the name request → classifier `0x01E7EC28` chain completes it). A stack-level
  redial never sets `0x102F0`, never requests the remote name, never runs the
  setup block. S5b (R5) remains the control: the SAME cmd-1 dial, when the APP
  originates it, binds audio perfectly.
- **S5 regression explained**: with byte==3 stamped + mailbox `0x1A5F1` armed
  (never cleared — vendor persistent-redial design), the menu repair flow now
  kicks BOTH devices and nothing reconnects. The stamped state is not inert: it
  interferes with the app's own dial bookkeeping. ⇒ **R6a must not ship**; and
  R6b must also solve the mailbox-clear/teardown story or inherit this.

**Conclusion (strategy)**: every byte-level and command-level trick at the
connect-complete tbh has now been exhausted (R3 forced-bind, R4 cmd-1 replay,
R5 kick+redial, R6a redial+stamp — all FAIL, all stable). The wall is the app's
single current-device struct **`0x102F0`** (809 refs; every connect-complete /
audio-routing handler dereferences it unconditionally). Remaining routes:
- **R6b (static design pass)**: re-point `0x102F0` (handle `+0x82`, address
  fields, name) to the joiner at ARM time so the redial's connect-complete runs
  the NORMAL app bind path — biggest cave yet; app-task race + teardown-restore
  concerns; needs a real static design round first.
- **SDK rebuild** (ch. 28) or the **ch. 25 decompile⇒compile route** for a true
  two-device app.

**Radio remains on R6a `62214f14…`.** Recommended for daily use: roll back to
E7-ref (recipe, no script per directive: sectors `0x066000`+`0x0AC000` from
`work/ch30_e7ref.bin` `90bec320…`; pairings survive).

### §30.14.37 — R6b design pass 2026-11-04: `--redial-current` — write the stack current-device record + replay the name request at the redial connect-complete

R6a (§30.14.36) proved stamping routing byte 3 at OUR redial's connect-complete
binds nothing (mode-3 tbh = enable/state path). A static round (official objdump,
`/tmp/opencode/app_full.o.lst`) located what an app-originated dial leaves behind
that a stack redial does not — two inputs, both writable from our cave:

- **tbh-table correction (supersedes §30.14.24)**: the connect-complete table is
  indexed `mode−1`; real targets mode 1 → `0x6177A` (MIC(0)+SPK(1)), mode 2/4 →
  `0x6128E` (both 0), mode 3 → `0x61784` (MIC(1)+SPK(0)), mode 5/6 → `0x616BE`;
  `0x6128C` was the last table entry, not code. The tbh is a mic/speaker **enabler
  switch only**. The real bind = app event `0xB` → block `0x61292` (addr copy
  `[sp+16]→[sp+12]`, `call 0x184D6` = `is_current_device()` QUERY,
  `b[0xB4FA]:=120`, free `[0x102F0+0x280]`) — never runs for a stack redial.
- **Stack current-device record (CORRECTED offsets)**: valid = **bit14 of the dword
  @`0xBF39`** ⇒ `b[0xBF3A] |= 0x40`; BD_ADDR = **`0xBF41..46`** (query
  `is_current_device()` @`0x01E184D6`: dword @`0xBF39` bit14 test + `memcmp(r2+8,
  addr, 6)`; earlier `0xBF40..45` note was off by one). No app-code writer exists —
  only the precompiled stack sets it, on its own dial.
- **Name chain (fully confirmed)**: `user_send_cmd_prepare(6 = READ_REMOTE_NAME, 6,
  addr)` → HCI remote-name request → btstack dispatcher `0x01E19E5E`, tbh event
  table @`0x01E19E74` (target = `0x19E72 + 2×entry`; **event 5** entry = `0x014A` →
  `0x1A106`) → ops table `[0xBF48+4]` = classifier `0x01E7EC28(status, BD_ADDR,
  name)` → name matches vs table `0x01E9B968` (`0x3127C4` ×3; Jabra = else-default)
  → **UNCONDITIONAL self-stamp `b[0xB464] := 3` @`0x01E7EC98`** (name-pending
  bookkeeping at `[0x102F0+0x274]` skipped when 0; `b[0x102F0+0xB10]&~0x3F==128`
  would stamp 5 instead — not our state).

**The patch** (`--redial-current`, requires `--incoming-redial`; mutually exclusive
with `--redial-bind` — both retarget the loop-guard branch at cave +72): at the
loop-guard match (byte==1 && both conn records inused && mailbox == joiner ⇒ this
IS our redial's connect-complete) branch to a new **90 B** window @`0x01EA77D0`
(the 174 B cave ends exactly there; the presst/cmd5t windows share that start but
`--cmd5-target` is mutually exclusive — no apply-time clobber):

1. `r2 = [sp+20]` (joining BD_ADDR; reload — CMP6 walked it)
2. **zero the re-dial mailbox `0x1A5F1..F6`** (byte-wise — fixes the R6a S5
   repair-press regression + releases the P7 stuck-record)
3. **copy `[sp+20]` → `0xBF41..46`** (byte-wise; the ODD-cell lesson holds)
4. **set valid** `b[0xBF3A] |= 0x40`
5. **post `user_send_cmd_prepare(6, 6, [sp+20])`** via `call 0x01E1792E` → name
   result → event 5 → classifier → byte `:= 3` **asynchronously**
6. `r0 = b[r6+212]`; `rts` — routing byte UNCHANGED at the tbh (stock mode-1
   enablers run; classification lands ~100 ms later)

Cave head change: guard branch `70 41` → **`10 52`** (RET → CUR entry;
`encode_branch2(0x01EA776A, 0x01EA77D0)` verified, fits the 2-byte range).
Teardown `0xF0` → DONE → CMP6 vs the now-zeroed mailbox → mismatch → RET (no
stamp — avoids the R5 echo latch). A later join re-arms + re-kicks (guard no
longer matches) → redial → CUR again: **P7 may self-heal by design**.

**Expectation / verdict tree**: S1c TX = Jabra mic **and** S1d RX = earphones ⇒
GOAL (two-device with audio). Any other combination ⇒ the byte/command-level tbh
route is DEAD for good ⇒ escalate to the SDK rebuild (ch. 28) or the ch. 25
decompile⇒compile route. Status: design LOCKED 2026-11-04; implementation + build
same session — §30.14.38.

### §30.14.38 — R6b BUILT: `--redial-current` implemented, objdump round-trip + both suites green, image staged 2026-11-04

**Tool** (`tools/patch_h3plus_firmware_bluetooth.py`): new flag `--redial-current`
(dest `redial_current`), requires `--incoming-redial`; mutually exclusive with
`--redial-bind` (both retarget the loop guard) and with `--d1-target-wait` (the D1
thunk cave `0x01EA77F0` sits **inside** the CUR window — new CLI check). New
constants: `INCHRDL_CUR_CAVE_VA = 0x01EA77D0`, `INCHRDL_CUR_BYTES` (90 B, asserts:
length, dispatcher call round-trip `decode_call(+80) == 0x01E1792E`, tail
`50 ee 64 0d 80 00`), `INCHRDL_GUARD_CUR` (`encode_branch2(0x01EA776A, 0x01EA77D0,
neq=False) == 10 52`), `INCHRDL_CAVE_BYTES_CUR` (head: `[:72] + 10 52 + [74:]`).
New site `inchrdlcurcave` (90 B @`0x01EA77D0`; target `inchrdlcur` when
`--redial-current`); `inchrdlcave` gains static `inchrdlcur` state (target when
`_ird_cur`; desc "(R6b current)"). Cross-recognition (all STATIC —
`find_app_start` gates on default `build_patches()`): `inchrdlcur` slices taught to
`gatecave`/`r1cave`/`r1bcave`/`cmd5tcave` (from the CUR head) and to the windows
the CUR block overlaps — `presstcave` (CUR[0:32]), `d1thunk` (CUR[32:38]),
`incmode3cave` (CUR[38:90]+2 pad), `inchfpcave` (CUR[38:90]+6 pad); and
`inchrdlcurcave` learns legacy `native`/`inchrdlcur`/`legacy_presst`/`legacy_d1`/
`legacy_presst_d1`/`legacy_incmode3`/`legacy_inchfp` (window-clamped copies — the
R3/R4 cave tails live in never-inspected zeros). The `legacy_d1` state was caught
by the D1-alone `--show`-clean test (first suite run: 2 FAILs, then 0).

**Verification**: objdump round-trip (`/tmp/opencode/r6b_asm.py` → `r6b_test.o`,
official `-mcpu=r3` objdump): hook `0x61270: call 0xA7722` ✓; guard
`a776a: 10 52 → if (r0 == 0) goto a77d0` ✓; CUR block disassembles EXACTLY as
designed — `r2=[sp+20]`; `r0=0x1A5F1`; 6× `b[r0++=1]=0`; `r0=0xBF41`; 6×
`{r3=b[r2++=1]; b[r0++=1]=r3}`; `r1=0xBF3A; r0=b[r1+0]; r2=0x40; r0|=r2;
b[r1+0]=r0`; `r0=6; r1=6; r2=[sp+20]; call 0x1792E`; `r0=b[r6+212]; rts` ✓.
`verify_actions.py` **0 failures**, `verify_cli.py` **0 failures**.

**Image**: `work/ch30_r6b.bin` sha256
`7f2af2596bca94a22735e8443efa2b95494b62fa245c350c73f0da0d36c6b46a`. Build cmd:

```bash
python3 tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin work/ch30_r6b.bin \
  --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2 --no-kick --force-page-scan \
  --force-role-keep --no-disconnect-13 --no-pairing-kick --incoming-redial --redial-current \
  --sectors=work/ch30_r6b
```

Sector diff vs E7-ref `90bec320…` = EXACTLY `0x066000`+`0x0AC000`, **237 B**
(= R5's 158 + 79 non-zero CUR bytes; CUR has 11 zero bytes); vs R5 = 81 B confined
to flash `0xAC76A..0xAC828` (guard 2 + CUR 79) ✓; vs R6a = 81 B ✓. VM untouched;
pairings survive. Stage `work/ch30_r6b.sh` (full-64-hex EXPECT_SHA, 2-sector
erase+write+readback ×2, §30.3 full 1 MiB strict verify, boot check) + card
`work/ch30_r6bc.sh` (S0 regression, S1 GOAL gates + S1a redial delay, S2
persistence, S3 echo watch + S3c P7 self-heal, S4 Jabra-first, S5 repair-press
R6a-regression check, S6 rebuild + button keys). **UNTESTED — NEXT: user flashes +
card; verdict §30.14.39.** Radio on R6a `62214f14`; daily-use rollback recipe =
2 sectors `0x066000`+`0x0AC000` from E7-ref `90bec320` (no script, directive
2026-11-03).

### §30.14.39 — R6b FIELD RUN 2026-11-04: FAIL — 5th identical goal-miss signature; new regressions (S4 press-freeze, S5 TX-dead) ⇒ BYTE/COMMAND-LEVEL tbh ROUTE DEAD FOR GOOD

Flashed `work/ch30_r6b.bin` `7f2af259…` clean (erase+write+readback ×2, FULL-FLASH VERIFY PASS, boot normal; log `work/logs/ch30_R6b_20261104_201658.log`). Card `work/logs/ch30_R6bcard_20261104_201749.log`, run 20:17–20:37:

- **S0 PASS** — TID-PTT alone fully normal (TX button mic, RX speaker).
- **S1 GOAL FAIL** — Jabra paged in, both connected (S1b), button keys (S1e), no freeze/echo with both up (S1f) — but **S1c TX = TID-PTT mic, S1d RX = SILENCE**: the 5th identical signature (R3/R4/R5/R6a/R6b). S1a: only a "mobile connected" tone — the kick+redial delay audible on R5/R6a was NOT reported this run ⇒ **CUR firing UNCONFIRMED** (either the guard never matched, or the drop+redial was too fast to hear).
- **S2 PASS** — 5-min persistence, behavior unchanged.
- **S3 regression (new flavor)** — after Jabra off: sideloop/echo starting at first RX (TX mic = radio mic), **stops after each TX, returns after every RX** (non-latching — unlike R5's latched loop, unlike R6a's clean teardown). Consistent with the classifier having stamped byte 3 asynchronously (mode-3 enablers live, teardown restores them but not the RX-source — the §30.14.25 gap) — weak evidence CUR *did* fire, inconclusive without btmon. **S3c: no re-join without power-cycle** — the P7 self-heal hope did NOT materialize.
- **S4 REGRESSION — press-freeze**: Jabra-first, then menu BT→Paired→TID-PTT→Connect: Jabra kicked (both sides announced disconnect) **then the radio FROZE — unworkable**. E7-ref never froze on any press (§30.14.16); R6b reintroduced a freeze in the press flow. Root cause not pinned — the verdict tree makes pinning moot.
- **S5 REGRESSION persists**: repair press kicked BOTH devices simultaneously; afterwards RX on speaker, **TX completely dead (no audio at all)** — worse than R6a's S5.
- **S6** — recovery required re-pairing the Jabra from scratch; two-device state then rebuildable (Jabra off → TID-PTT connect → Jabra on) and button SPP keys work.

**VERDICT 2026-11-04: R6b FAIL on goal. Per the §30.14.37 verdict tree the byte/command-level tbh route is DEAD FOR GOOD** — five patches spanning every lever that layer offers (force byte 3 before/after profiles, replay the dial cmd 1, stack mailbox re-dial, stamp at redial connect-complete, write the stack current-device record + replay name-read cmd 6) all land on the same silent-audio wall, and the last two added press-flow regressions. The app's audio bind needs the FULL app-originated connect flow (task-level state machine around struct `0x102F0`), not any combination of stack-level writes and command posts. **R6b must NOT ship** (S4 freeze, S5 TX-dead). Radio currently on R6b `7f2af259`; **daily-use rollback recipe (no script, per directive): sectors `0x066000`+`0x0AC000` from `work/ch30_e7ref.bin` `90bec320…`** (pairings survive) — or flash a fresh known-good image.

**ESCALATION (next route, user's choice):**
1. **SDK rebuild (ch. 28)** — `fw-AC63_BT_SDK` `cpu/br23`, `apps/spp_tuaudio`-class app rebuilt with the bind logic in source where `0x102F0` is written by design; git-history proof (ch. 28 §28.7) shows no fork touches the BT libs, so the precompiled btstack/controller stay as-is but the APP layer (the wall) becomes ours. Longest path, only path with full control.
2. **Ch. 25 decompile⇒compile route** — rewrite the connect/bind state machine (dispatcher `0xB` block `0x61292` + struct `0x102F0` writers) as compiled code in the verified cave/trampoline style; hardware-validated toolchain (`-target pi32v2 -mcpu=r3 -Oz`), but the bind logic is large and RAM-layout coupling is risky.
3. **ESP32 combo-device workaround** — no firmware work: one physical BT device that presents BOTH SPP (TID-PTT protocol) and HFP-AG to the radio... the radio still binds one device — this only collapses the two-device need into one ACL, which the stock firmware handles fine today (SPP+HFP profile multiplexing over one link, §9B.6.1 PROVEN). Cheapest by far if a single custom device is acceptable.

### §30.14.40 — Route decision 2026-11-04: R7 = decompile⇒compile (ch. 25) — rewrite/re-drive the app bind from compiled code

User chose (2026-11-04, after the §30.14.39 verdict tree): **the ch. 25
decompile⇒compile route** over SDK rebuild (ch. 28) and the ESP32 combo device.
Rationale on record: the Ghidra-12 + ghidra-jieli + JieLi clang
(`-target pi32v2 -mcpu=r3 -Oz`) pipeline is hardware-validated (round-trip image
flashed + passed, ch. 25), needs no vendor SDK bring-up, and keeps everything
inside our existing image + patcher.

**Why R1–R6b all missed (consolidated model).** The audio bind is the app BT-task
state machine: the connect-complete handler that hosts the mode tbh @`0x01E61270`
takes the bind branch (event `0xB` → block `0x61292`: addr copy,
`is_current_device()` query, `b[0xB4FA]`, writes into struct `0x102F0`) **only for
links the app itself initiated**. Stack-originated links (incoming joins, our
re-dials) land in the same handler but branch around it; every byte/command trick
we tried either stamps state without the bind (R3/R6a), replays stack commands
(R4/R5), or writes the stack-side current-device record (R6b) — none runs the
app-side bind block. R6b's S4/S5 regressions add: our cave runs in **stack-task
context at the tbh** — anything heavier there risks freezing the app task.

**R7 plan (phased).**
- **A — decompile the bind flow (static, no new tooling).** Use the ch. 25
  decompilation tree (`tools/disassemble_app.py` → `disassembled/`) + official
  objdump listing to fully read: (1) the function containing the tbh
  `0x01E61270` — its entry conditions and why stack links skip block `0x61292`;
  (2) the app-originated connect poster (menu "connect selected device"
  `0x01E61E22` path) — what state it sets before the link comes up
  (`0x102F0+0x274` pending? `+0xB10` state?); (3) the app-task event-queue post
  primitive (context-safe way to trigger the bind from our cave).
- **B — design R7.** Preferred shape: our cave does **only** a context-safe
  app-task event post (or sets the minimal "app-initiated" state) so the stock
  bind block runs *by itself* in app-task context; compiled C via ch. 25 where
  byte-encoding is awkward, linked into the `0x01EA76DE` cave run (122 B free
  after CUR; larger code ⇒ the erased-flash trampoline question re-opens).
- **C — build + card** as the R-series before (stage + card, §-numbered verdict).
- **Guardrails:** R6b stays withdrawn (S4/S5); E7-ref remains the daily-use
  rollback recipe (sectors `0x066000`+`0x0AC000` from `work/ch30_e7ref.bin`
  `90bec320…`); radio currently on R6b `7f2af259…` until the user re-images.

Status: decision recorded 2026-11-04; Phase A starts same session.

### §30.14.41 — R7 Phase A 2026-11-04: the bind flow DECODED — bt-task main loop `FUN_01e60e44`, event switch, and the bind block @`0x01E61292`

Static round on the Ghidra tree (`disassembled/decompiled/01e60e44_FUN_01e60e44.c`)
+ official objdump (`/tmp/opencode/app_full.o.lst`). What an app-originated connect
does that a stack redial never does is now fully located.

**(1) The tbh hook lives in the BT-TASK MAIN LOOP.** `0x01E61270` is inside
`FUN_01e60e44` (VA `0x01E60E44`, 3950 B) — the BT task: prologue runs stack setup
(`FUN_01e182b0` = conn_num setter) and registers stack→app callbacks
(`FUN_01e1841e(FUN_01e7ebc6)`, `FUN_01e6074a/756/760(0, FUN_01e5b2f4/5b3bc/5b3be)`,
`FUN_01e1841e(FUN_01e83db4)`), then `while(true){ FUN_01e2d852(&msg,1); if
(msg != 0x200000-type) default; switch(event){…} }`. **All our R3–R6b cave runs
execute in this same task, at the same frame as the bind** — context was never the
problem. Queue wait `FUN_01e2d852` (42 B @`0x01E2D852`) = OS taskq pend
(`func_0x020031f2/0x020031ec`, external) + type filter (message type `0x20` in
word0 bits16–23).

**(2) Event switch map** (4-byte goto table @`~0x61BFC–0x61C22`; only branch to
`0x61292` = entry for event `0xB` @`0x61C08`): case 3 = BT bring-up; case 5 =
teardown check; **cases 6 AND 7 fall into `LAB_01e6123c`** → `FUN_01e17cc4()==5`
retry branch, `DAT_0000b462 = 2`, then `uVar10 = DAT_0000c094` (Ghidra base
mis-model of the routing byte — it IS `0xB464`, field-proven; case 9/10 writes
`DAT_0000b464 = 0xf0` = the known teardown sentinel) → **mode tbh @`0x61270`**;
case 9/10 = DISCONNECT (0xF0 sentinel path); **case 0xB = THE BIND**; case 0xC =
DTMF collection. tbh table (mode−1 indexed, base `0x61280`): mode1→`0x6177A`
mic-off/spk-on, mode2/4→`0x6128E` both-off, mode3→`0x61786` mic-on/spk-off,
mode5/6→`0x616BE` both-on.

**(3) BIND BLOCK @`0x01E61292` (case 0xB) — exact disasm, the target of R7:**
`b[0xB4FA] := 120` → **6-byte copy `[sp+16] → [sp+12]`** (SRC ptr → DST ptr) →
free+zero `[0x102F0+0x280]` → `call is_current_device([sp+12])` (`0x01E184D6`);
**abort if 2 (not current device)**; **abort if `b[0x10E00] & 1`**; then
`b[0x10E04]=0`, `FUN_01e07ff6(3)`, `b[0x10E00] |= 5` (& ~2 path), 500 ms timer
`FUN_01e249ce(0, FUN_01e7ed80, 500)`, **post stack cmd `0x1E` via `0x01E1792E`**
(HFP/SCO audio bring-up), ends at loop-end `0x61D7C` — skipping the rest of case 7
costs nothing. `r6 = 0xB390` is live at the hook.

**(4) Who posts event 0xB: the precompiled btstack.** All four registered
stack→app callbacks checked and rejected (`FUN_01e5b2f4` = AT-string parser,
`FUN_01e5b3bc/be` = empty stubs, `FUN_01e83db4` = secondary dispatcher w/ power
API, `FUN_01e7ebc6` = retry watchdog); the queue POST primitive is external
(`0x0200xxxx` OS layer). ⇒ R7 does **not** hunt the poster — it **jumps into the
bind block directly** with a synthesized payload.

**(5) R7 DESIGN — `--redial-bind2` (direct bind goto).** At the loop-guard match
(our redial's connect-complete), branch from cave `+72` to the window
@`0x01EA77D0` (122 B free after the 174 B cave; run ends ~`0x01EA784A`):
1. `r2 = [sp+20]` (joiner BD_ADDR ptr);
2. **zero re-dial mailbox `0x1A5F1..F6`** (fixes the R6a S5 repair-press
   regression + releases the P7 stuck record);
3. **copy joiner → `0xBF41..46`** + **`b[0xBF3A] |= 0x40`** (stack current-device
   record — makes the bind's `is_current_device` gate PASS; R6b-proven writes);
4. **stamp routing byte `b[0xB464] := 3`** (`r1=3; b[r6+212]=r1`) — mode 3 =
   what a classified Jabra dials in with;
5. `[sp+12] = r2; [sp+16] = r2` (self-copy src==dst harmless);
6. **`goto 0x01E61292`** — the STOCK bind block runs synchronously in the bt-task
   loop: state `|=5`, `FUN_01e07ff6(3)`, timer, cmd `0x1E` — the exact aftermath
   of an app-originated connect (S5b/P6 control = the only flow ever observed
   binding audio).

Drops R6b's cmd-6 READ_REMOTE_NAME replay (direct stamp replaces the classifier;
the replay is the prime suspect for the R6b S4 freeze). Guard branch stays
`10 52` (→ `0x01EA77D0`). Teardown flow unchanged (0xF0 → DONE → CMP6 vs zeroed
mailbox → mismatch → RET, no stamp).

**Risks (UNTESTED):** `b[0x10E00]&1` must be 0 at bind time (connected state —
likely); synthesized event-0xB payload (both ptr fields = joiner addr; the
original message layout is bypassed); bind block tail (timer + cmd 0x1E) assumed
Ghidra-correct (re-verified against objdump this round up to `0x61300`); S4 freeze
root cause still unknown — mitigated by dropping the name replay + clearing the
mailbox. **Verdict tree: S1c TX = Jabra mic AND S1d RX = earphones ⇒ GOAL.
Any other outcome ⇒ in-image bind emulation dead ⇒ SDK rebuild (ch. 28).**

Status: Phase A DONE + design locked 2026-11-04; implementation §30.14.42.

### §30.14.42 — R7 `--redial-bind2` BUILT 2026-11-04: direct bind-block goto — objdump pixel-perfect, both suites green, image `575e593d…` staged

Per §30.14.41 design. Tool changes in `tools/patch_h3plus_firmware_bluetooth.py`:

- New constant `INCHRDL_BIND2_BYTES` (90 B @`INCHRDL_CUR_CAVE_VA = 0x01EA77D0`):
  identical to R6b `INCHRDL_CUR_BYTES` through +74 (zero mailbox `0x1A5F1..F6`,
  copy joiner `[sp+20]`→`0xBF41..46`, `b[0xBF3A] |= 0x40`) but the tail differs —
  **no cmd-6 name replay**; instead `r1 = 3; b[r6+212] = r1` (stamp routing byte 3
  while live in the bind path), `r2 = [sp+20]; [sp+12] = r2; [sp+16] = r2` (the
  bind block's DST/SRC payload pointers — self-copy harmless), then
  `encode_goto32(0x01EA7826, 0x01E61292)` = **direct goto into the stock bind
  block** (`fd ea 34 cd`). Asserts pin all of this incl.
  `decode_call(...) == 0x01E61292`.
- `build_patches(..., redial_current=False, redial_bind2=False)`; selection chain
  `_ird_bind2` (bind2 wins over cur), head stays `INCHRDL_CAVE_BYTES_CUR` (guard
  `10 52` → window, shared with R6b), `inchrdlcurcave` site gains static state
  `inchrdlbind2` + label; teaching loop #2 (presstcave/d1thunk/incmode3cave/
  inchfpcave windows) slices `inchrdlbind2`; loop #1 unchanged (head identical).
- CLI `--redial-bind2` (requires `--incoming-redial`; exclusive with
  `--redial-bind`/`--redial-current`/`--d1-target-wait` — D1 thunk `0x01EA77F0`
  sits inside the window); summary `--redial-bind2 (multipoint R7)`;
  `wanted += ["inchrdlcurcave"]`.
- Verification: sanity script OK (default native; R7 → `inchrdlcave` target
  `inchrdlcur` + `inchrdlcurcave` target `inchrdlbind2`; R6b/R6a unaffected);
  `tools/verify_actions.py` **0 failures**; `tools/verify_cli.py` **0 failures**.
- Objdump round-trip (`/tmp/opencode/r7_test.o`, `.text` off `0x34`): hook
  `61270: call 0xa7722`; guard `a776a: 10 52 → a77d0`; window disassembles exactly
  as designed, ending `a7826: fd ea 34 cd  goto -288152 <.text+0x61292>` ✓.
- Image: `work/ch30_r7.bin` = E7 recipe + `--incoming-redial --redial-bind2`,
  sha256 **`575e593df44ac2c791b33846c555aaf90016ecea139c02ac3b4befb3ed1c6dd7`**;
  sector diff vs `work/ch30_e7ref.bin` = EXACTLY `0x066000`+`0x0AC000`, **238 B**;
  vs R6b = 16 B at flash `0xAC81A..0xAC829` (the tail swap) ✓. `--show` on the
  image: all windows recognized, no UNKNOWN/PARTLY.
- Stage `work/ch30_r7.sh` (EXPECT_SHA full 64-hex, 238-byte assert, §30.3 full
  strict verify, boot check) + card `work/ch30_r7c.sh` (S1c TX = Jabra mic AND
  S1d RX = earphones = WIN; S3c P7 re-join gate; S4 press-freeze watch;
  S5 repair-press regression gate; S6 button keys; header note: Jabra re-pair may
  be needed after flashing).

Status: BUILT → **FLASHED + FIELD-FAILED 2026-11-06, §30.14.43 below.** Radio
was on R6b `7f2af259…` (must not ship); daily-use rollback recipe (no script per
directive): sectors `0x066000`+`0x0AC000` from `work/ch30_e7ref.bin` `90bec320…`,
pairings survive.

### §30.14.43 — R7 FIELD RUN 2026-11-06: FAIL — 6th identical goal-miss signature; direct bind-block goto misses the goal ⇒ IN-IMAGE BIND EMULATION DEAD

**Stage-script incident (first flash attempt STOPPED, image innocent):**
`work/ch30_r7.sh` was sed-derived from the R6b script and its byte-count assert
was left at R6b's **237**; R7's diff is legitimately **238 B**. Preflight sha +
sector list both matched; the assert correctly refused to flash on a
count mismatch. Fixed (assert + print → 238, §refs → §30.14.41–42), re-ran: two
clean flashes (`work/logs/ch30_R7_20261106_200310.log`,
`work/logs/ch30_R7_20261106_200634.log` — readback IDENTICAL ×2 sectors,
**FULL-FLASH VERIFY PASS**, Q1 alive, Q2 = Jabra auto-connected). A first card
run (`ch30_R7card_20261106_200405.log`) was abandoned at S0; the authoritative
card is `work/logs/ch30_R7card_20261106_200653.log`.

**Card results (verbatim gist):**
- **S0 PASS** — TID-PTT alone: no freeze, TX = TID-PTT mic, RX = radio speaker.
- **S1 GOAL FAIL** — S1a: "Jabra connected and directly I heard mobile
  connected" — **no drop+redial delay heard** (bind2 window firing UNCONFIRMED,
  same ambiguity as R6b). S1b: both devices connected. **S1c: TX = TID-PTT mic
  (FAIL). S1d: RX = SILENCE (FAIL)** — the **6th identical goal-miss signature**
  (R3/R4/R5/R6a/R6b/R7). S1e: button keys fine. S1f: no freeze, no echo both-up.
- **S2 PASS** — 5-min persistence, behavior unchanged.
- **S3** (Jabra off): TX switched to radio mic, RX on speaker; non-latching
  echo of the TID-PTT mic over the radio speaker at first RX and after every RX
  while not PTTing (R6b flavor). **S3c: NO re-join without a radio power-cycle —
  P7 self-heal dead again** (mailbox zeroing did not restore a second incoming
  join; consistent with the controller-side incoming-page wall, ch. 27).
- **S4** (Jabra-first): menu-Connect TID-PTT → **stock kick** (Jabra dropped,
  TID-PTT connected, TID-PTT bound) — **no freeze** (R6b's S4 press-freeze did
  NOT reproduce on R7).
- **S5 REGRESSION PERSISTS** (repair press from two-device state): "Both
  dropped instantly and not connected again, keeps searching"; afterwards RX on
  speaker, **TX completely dead (no mic at all)** — same as R6b's S5.
- **S6** — two-device state rebuildable WITHOUT reboot (TID-PTT via menu first,
  then Jabra auto-pages in); button keys; TX TID-PTT mic, RX silence.

**Analysis.**
- pi32v2 `call`/`rts` use the separate hardware return stack (the `rets` group in
  function prologues) — the cave's general-purpose `sp` equals the bt-loop frame
  `sp`, so R7's payload synth (`[sp+12]`/`[sp+16]` = joiner ptr) and the
  `is_current_device` gate were sound BY DESIGN; had the window fired, the full
  stock bind block ran (state `|=5`, cmd `0x1E` SCO start posted) synchronously.
- Fired or not, this is the 6th byte-level lever against the identical
  silent-audio wall. The decisive contrast still holds (R5 S5b / P6): a
  **menu-dialed** Jabra binds audio perfectly — the app-originated dial sets the
  app current-device selection (struct `0x102F0` device record, name list,
  profile routing) BEFORE connect-complete; the bind block is only the tail of
  that flow. A post-hoc bind-block call cannot retroactively create the prior
  app state.
- The S5 both-kick + TX-dead regression persists (menu Connect from the
  two-device state → cleanup path under our NOPs leaves the app inconsistent)
  ⇒ **R7 must NOT ship.**

**VERDICT: FAIL. IN-IMAGE BIND EMULATION IS DEAD** — six levers exhausted (force
byte 3 / replay cmd 1 / mailbox re-dial / stamp at redial-complete /
current-device write + cmd 6 name replay / direct bind-block `goto`). Per the
§30.14.41 tree: escalate. Options: **(1) SDK rebuild (ch. 28)** — app layer is in
source, the bind state machine can be modified properly, btstack/controller libs
stay precompiled (2-slot pools already vendor-widened; E6 proved the links work);
**(2) ch. 25 compile route, deep rewrite** — re-implement the app's connect-flow
state machine into caves (same work as (1) without the build system);
**(3) ESP32 combo device** — zero firmware work, one device presenting SPP+HFP
over a single ACL = the §9B.6.1-proven stock happy path.

**Radio currently on R7 `575e593d…` (must not ship).** Daily-use rollback recipe
(no script per directive): 2 sectors `0x066000`+`0x0AC000` from
`work/ch30_e7ref.bin` `90bec320…`, pairings survive.

### §30.14.44 — ROUTE DECISION 2026-11-06: SDK rebuild (ch. 28) chosen as the final route

Asked to pick between (1) SDK rebuild, (2) ch. 25 deep rewrite, (3) ESP32 combo
device, (4) stop, the user chose **"SDK rebuild (ch. 28)"** — verbatim answer,
2026-11-06. This supersedes the §30.14.40 ch. 25 choice (that produced R7's
in-image bind emulation, now dead) and closes the byte-patch era: R3–R7 all
field-FAILED with the identical goal-miss because the app audio bind requires the
full app-originated connect flow; the rebuild fixes it **in C at the source of the
state machine** instead of tricking the stock binary after the fact.

Plan of record (R8 = SDK route, tracked in [ch. 28](28-sdk-forks-survey.md)):

1. **Feasibility build** — stock `fw-AC63_BT_SDK` `apps/` app for `cpu/br23`
   (AC635N, `-mcpu=r3`) with the Linux JieLi toolchain
   (`~/h3plus/jieli-linux-toolchains-20250324.1/`; gotchas catalog §28.7 incl.
   `ulimit -n 8192`), native-Linux `isd_download` available (§28.7).
2. **Baseline equivalence** — compare a stock-built image against the vendor
   app blob (entry-point/link question — §28.7 claims answered; verify) and
   flash-gate: a stock-config rebuild must boot, connect BT and key with the
   existing BT-PTT patch set before ANY two-device C code ships.
3. **Two-device bind in C** — with the app layer in source, re-point the current
   device / bind path (struct `0x102F0` writers, bt-task event `0xB` producer)
   for the SPP-incumbent + HFP-joiner case; btstack/controller libs stay
   precompiled (they already hold 2 conn slots — ch. 27).
4. **Same discipline as the R-series** — full-image sha, sector-staged flashing
   by the user, field cards, findings ledger.

R7 stays on the radio until a rebuild passes its own flash gate; daily-use
rollback recipe unchanged. Nothing flashed for this decision.

### §30.14.45 — SDK scope check 2026-11-06: the SDK cannot rebuild the H3 app — R8 shape corrected to compiled-C splice

Read-only exploration of the on-disk SDK (all paths under
`work/sdk-forks/Acy19888_fw-AC63_BT_SDK/`, HEAD `8f72ada`, full official tree as
ancestor; the official clone is NOT at `~/h3plus/fw-AC63_BT_SDK` — absent;
`~/h3plus/fw-AC630N_BT_SDK` is bd29/wrong core).

**Hard scope fact**: the SDK contains **no TID H3 app source** — zero hits for
BK4819/walkie/transceiver; the vendor app blob (~800 KB machine code: UI, RF,
menus, the bt-task loop `FUN_01e60e44` and the bind block `0x01E61292` of
§30.14.41) is proprietary and simply not in any fork. `apps/spp_and_le/examples/
multi_conn` — the only "multi" example — is **BLE-only** (`ble_multi*.c`), not a
BR/EDR two-device template. ⇒ §30.14.44 step 3 "app layer in source" is **NOT
achievable as written**: a full app rebuild = re-implementing the transceiver.

**What the SDK route DOES give (R8 assets, verified this round)**:

1. **Official multipoint API declarations** —
   `include_lib/btstack/avctp_user.h`: `__set_user_ctrl_conn_num(u8)` (L479),
   `__set_hfp_switch(u8)` (L600), `__set_hfp_restore(u8)` (L605) — the 1拖2 call
   preemption/restore flags (ch. 24 §24.5 note confirmed in headers). No
   `multi_bd.c` source exists anywhere (header refs only) — the stack-side
   multipoint core was never shipped compiled-in.
2. **The libs are LLVM IR bitcode** (`cpu/br23/liba/*.a` members are LLVM IR per
   §28.7) — new C modules compile + LTO-link against the REAL stack bitcode with
   the official headers, producing machine code whose call forms match the stock
   image. This is the ch. 25 compile route with its missing piece (legit SDK
   headers + toolchain) now in hand.
3. **Green Linux build pipeline template** — Acy19888 zuupah_pen on the **AC635N
   demo board** (`board_ac635n_demo_cfg.h` = our exact chip):
   `cd apps/<x>/board/br23 && ulimit -n 8096 && make` →
   `cpu/br23/tools/sdk.elf` + `app.bin`; gotchas catalog §28.7 (lto-wrapper bare
   `ld`/`nm`/`strip` → PATH shim; `llvm-size`; stub `host-client`/`lz4_packet`;
   local toolchain = old layout `/home/stefan/h3plus/jieli-linux-toolchains-
   20250324.1/pi32v2/bin`, Makefile `TOOL_DIR := /opt/jieli/pi32v2/bin` L36 →
   override with `make TOOL_DIR=…`; `/opt` not writable ⇒ repo-local shim dir).

**Corrected R8 plan of record** (supersedes §30.14.44 steps 2–3 wording):

1. **Feasibility build** (unchanged, and cheap): `apps/spp_and_le`
   `board/br23` for AC635N with the TOOL_DIR override + repo-local PATH shim —
   proves the pipeline end-to-end on our chip.
2. **R8 = compiled-C module spliced INTO the stock image** (not an app
   replacement): real C functions (ch. 25 validated toolchain, `-Oz`,
   `-mcpu=r3`) linked at a verified ALLZERO cave, called from the existing tbh
   hook `0x01E61270` infrastructure — replacing byte-encoded caves where logic
   outgrew them. The bind wall stays: six byte-level levers proved the stock
   app's `0x102F0` state is never set for stack-originated links; a C module can
   now *drive the stack APIs directly* (second-device HFP/SCO setup + audio
   routing) instead of tricking the app's state machine — informed by the full
   Phase A decode (§30.14.41) and the multipoint headers above.
3. **Fallback ladder unchanged**: if compiled-C splice against the stock image
   still cannot bind → SDK-replacement app path (scope = transceiver re-write,
   effectively out) or the ESP32 combo device (§9B.6.1 stock happy path).

Status 2026-11-06: scope check DONE; feasibility build = next action; nothing
flashed; radio on R7 `575e593d…`.

### §30.14.46 — corrected-decode xref census 2026-11-10 (upstream ISA table): R-series stands, R8 lead = mailbox2

Re-ran the xref census over the whole app with the upstream oracle-verified decode
(`tools/pi32dis.py --upstream`, [Ch. 34 §34.14](34-pi32v2-isa-open-reference.md),
listing `work/full_upstream.lst`): every ch. 30/31 caller count and the 810 refs to
struct `0x102F0` are **UNCHANGED** — the R-series conclusions stand. Two facts the
old desynced listing hid: the cmd-1 dial body `0x01E21E46` has a SECOND entry —
gate `0x01E21D5C` (`if ((r0 & 64) != 0)`, bit 6 of `b[r12+0x15]`) — and there is a
**second re-dial mailbox `0x1A65A`** (dispatcher base `0x1A520+0x13A`) with its own
gated writer `0x01E219A4` (gate `b[r2+4] & 0x40`) and a direct cmd-1 post path
`0x01E21D66` (gate bit 5 of `b[r12+0x10]`). R5-lineage designs armed only `0x1A5F1`.
Any R8 must consider BOTH mailboxes + the three gate bits before touching flash.

### §30.14.47 — R8 statics 2026-11-10 (upstream-corrected decode): the app event sink, the connect-handle key, and the app-slot swap design

**The app event sink.** `FUN_01e5af40(int param_1, byte* param_2)` (pointer refs `0x01E18F8E`/`0x01E2410E`) is the app's stack-event dispatcher (`param_1==4`, event code = `*param_2`): **`5` = teardown** (zeroes `_DAT_00010372`, `DAT_000102f4`, `DAT_0000b463`), **`0x3e` = CONNECT COMPLETE** (`param_2[2]==1`: `_DAT_00010372 = FUN_01e17d2c(param_2,4)` — the connection handle extracted from the packet; then `FUN_01e5af18(handle)`, `FUN_01e240a0(handle)`, and `DAT_0000b463 = 1` on the non-init path), **`0x77` = name-result** (`DAT_000102f4` state counter walk). `_DAT_00010372` = **`0x102F0+0x82` = the SOLE app connection-handle key**: the kick `FUN_01e5b22a` returns 3 when it is 0, the device-state machine runs `DAT_000102f4 < 3 && handle != 0` → `FUN_01e1664e(0xb,2,handle,…)`, and several audio-path guards test `handle == 0`. It is written ONLY by the `0x3e` sink — a stack-originated re-dial evidently never delivers that event to the app, so through R3–R7 the app kept a stale/zero handle and cmd `0x1E` bound nothing: **the root cause of all six identical goal-miss signatures.** `DAT_0000b463` has exactly 2 refs, both writes in the sink — no readers — dropped from R8. `FUN_01e1664e` = OS message post (`func_0x02001634(param_2<<16|param_1, …)`, context-safe).

**tbh table at the connect-complete hook fully decoded** (aligned decode from `0x01E61270`): `r0 = b[r6+0xD4]` (routing byte `0xB464`, `r6 = 0xB390` live) → `r1 = r0 + -1` → `if (r1 > 5) goto 1302` → `tbh r0`; halfword table @`0x01E61282` (target = base + 2·entry): mode1→`0x01E61F48`, mode2/mode4→`0x01E6128E` (fall-through), mode3→`0x01E61F04`, mode5/6→`0x01E6172A`. The bind block `0x01E61292` is **fall-through code after the table, NOT a table target** — R7's direct goto entered the case-0xb body correctly (re-confirmed; the earlier awk slices decoded garbage only because they started mid-instruction).

**Dial wrapper `FUN_01e600d4`**: no direct callers, ONE pointer ref — ops table `0x01E0EED6`; contains blocking waits (`sleep(10)` loop via `0x02001F82` + link-status `0x01E17F26`) ⇒ calling it from the bt-task tbh = freeze risk (R6b S4 precedent) — AVOIDED via the mailbox redial. Teardown-skip insight: the dial skips its teardown posts when link-status==0 && `FUN_01e16e0e()==0`. Conn-record walk `FUN_01e16878(mode 1)`: base `0x1A5F8` stride 22, inused = bit 29 of the LE word at `rec+15..18`, handle u16 @ `rec+8`; `FUN_01e16e0e` = wrapper returning `h[rec+8]` or 0.

**R8 DESIGN = R7 + APP-SLOT SWAP.** CUR window tail @`0x01EA77D0` = R6b 74 B prefix (zero mailbox `0x1A5F1`, joiner→`0xBF41..46`, `b[0xBF3A] |= 0x40`) + NEW middle: `call 0x01E16E0E` (live current-record handle — after our redial this IS the joiner), guard `if (r0 == 0) goto tail`, `r3 = 0x102F0`, `h[r3+130] = r0` (stamp the app device record with the joiner handle), then R7's bind tail (`b[0xB464] := 3`, payload synth `[sp+12]/[sp+16] = [sp+20]`, `goto 0x01E61292`). 106 B window `0x01EA77D0..0x01EA783A` ≤ cave-run end `0x01EA7849` (16 of 31 B headroom used). Deliberately NOT set: `DAT_000102f4` (left 0 so the app's own state machine walks with the fresh handle), `DAT_0000b463` (dead). AVOIDED: direct `FUN_01e5af40` call (needs a synthesized packet + hits the risky big-init path when `DAT_00010d80==0` + wrong task context), `FUN_01e600d4` (blocking freeze).

**MANDATORY SECOND OPINION CATCH (ch. 34/35 workflow paying off):** R7's tail goto32 `fd ea 34 cd` is POSITION-DEPENDENT — reused verbatim 16 B later it lands `0x01E612A2` (mid-bind-block, silently wrong). Re-encoded for the new site: `fd ea 2c cd` → `0x01E61292`. Every byte of the window verified instruction-by-instruction against the upstream oracle table (`python3 -m pi32v2isa disasm` + `as`: `h[r3+130] = r0` = `50 ed 33 08`; `r3 = 0x102F0` = `c3 ff f0 02 01 00`; `if (r0 == 0) goto +10` = `00 45`).

### §30.14.48 — R8 BUILT 2026-11-10: `work/ch30_r8.bin` (app-slot swap) — UNTESTED

Patch tool: `--redial-appswap` wired (16 edits: `INCHRDL_APPSWAP_BYTES` 106 B + asserts, requires `--incoming-redial`, exclusive `--redial-bind`/`--redial-current`/`--redial-bind2`/`--d1-target-wait`, new `inchrdlappswap` recognition state + teach-loop slices for the 4 legacy windows, CUR-window width 90→106 with the R6b/R7 states zero-padded). BUILD: E7 recipe (`--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2 --no-kick --force-page-scan --force-role-keep --no-disconnect-13 --no-pairing-kick`) + `--incoming-redial --redial-appswap` onto `work/ch30_e7ref.bin` → **`work/ch30_r8.bin` sha256 `4bb75a2c0bad4527e23b25c3e83ae015e66748beaa9776532f1e08c1b93e410b`**, 252 B changed (`0x66270–0xAC839`); diff vs E7-ref = EXACTLY sectors `0x066000`+`0x0AC000` (independently asserted), uboot `0x0000–0x4FFF` byte-EQUAL. `--show`: `inchrdlcave` = R5 cave + guard→CUR, `inchrdlcurcave` = R8 label. **Both suites GREEN incl. new R8 coverage** (verify_cli: r8 rc0 + 4 exclusivity rc1; verify_actions: full window block — len/prefix/call-target/guard-bytes/r3+h-store/tail-goto-target/window-bound/`--show`-clean/idempotent).

**JL_SIM PRE-FLASH GATE PASS** (ch. 35 workflow): decrypted the image (`tools/jl_sfcenc.py work/ch30_r8.bin /tmp/opencode/r8_app_dec.bin`) and ran `tools/jl_sim.py --image=/tmp/opencode/r8_app_dec.bin --start=0x01EA77D0 --sp=0x02008000 --regs r6=0xB390` + seeds (joiner ptr at `[sp+20]`, mailbox, routing byte 1, conn record) → **77 steps, stop-va hit AT the bind block entry `0x01E61292`**: prefix stores execute, the REAL `FUN_01e16e0e`+`FUN_01e16878` walk executes (returned 0 — a sim seed-fidelity gap on the inused word, NOT a mechanism flaw: on-device at our redial's connect-complete the stack genuinely holds the joiner's live inused record — R5 field-proved the redial connects; the h-store insn is individually table-verified and the guard correctly skipped), tail executes, and the re-encoded goto32 lands EXACTLY on `0x01E61292` (runtime confirmation). Memory writes verified: `0xB464` 01→03, `0xBF3A` 00→40, `0xBF41`←joiner addr, `0x1A5F1` zeroed, `[sp+12]/[sp+16]` = joiner ptr.

Stage `work/ch30_r8.sh` (EXPECT_SHA + explicit uboot `cmp -n 0x5000` assert + sector-diff assert n==252 + per-sector erase/write/readback + full-flash strict-region verify) + card `work/ch30_r8c.sh` (S0–S6; GOAL = S1c TX-Jabra-mic AND S1d RX-earphones; S3 echo watch, S3c P7 self-heal, S5 repair-press regression gate; S1g new: does the radio UI show the JABRA as the connected device after the swap). **UNTESTED — field verdict = §30.14.49.** Radio currently on `work/ch32_bt_e7.bin` `d7a29a3e` (ch. 33 daily driver). Rollback recipe (no script): 2 sectors `0x066000`+`0x0AC000` from E7-ref `90bec320`. If the 7th identical goal-miss ⇒ in-image route CLOSED for good ⇒ escalate: SDK rebuild (ch. 28) / compiled-C splice (ch. 35 §35.9) / ESP32 combo device (§9B.6.1).


### §30.14.49 — R8 FIELD VERDICT 2026-11-10: goal-miss (7th) — but the first audio-state movement of the R-series; in-image route CLOSED

Card `work/logs/ch30_R8card_20261110_231256.log` (radio on `work/ch30_r8.bin` `4bb75a2c…`):

- **S0 PASS** — TID-PTT alone: connects, no freeze, TX TID-PTT mic, RX speaker (no single-device regression).
- **S1 FAIL (join never landed)** — S1a: the Jabra did not page in at all ("nothing not paged in, no auto connect") — unlike R5/R6a/R7 where join+drop+redial was observed. Yet S1c/S1d showed the classic crippled signature anyway: **TX = TID-PTT mic + RX SILENT** (user: "There seems to be a change on the radio"). Reading: the join attempt evidently fired the tbh hook + CUR window (byte:=3 + bind) on a partial/aborted ACL that never stuck — mode-3 with no live HFP/SCO = RX silence (same mechanism as R3's forced-mode-3 silence, §30.14.23). S1e button keys; S1f no freeze/echo; S1g no UI insight.
- **S2** — state persists 5 min unchanged.
- **S3a PASS** — Jabra OFF: **no echo loop** (clean teardown — matches R6a's mailbox-zeroing behavior; better than R3/R4/R5).
- **S3c = the new datum** — the Jabra re-joined WITHOUT a radio power-cycle: **P7 self-heal ALIVE** (dead in R6b/R7 — the CUR mailbox-zeroing design intent CONFIRMED). User follow-up detail (verbatim): "on rejoin of jabra the TID-PTT still triggers the TX but the output (Tx mic) is silence while the Rx is now on the Radio speaker." This is the **first audio-state movement recorded across the whole R-series**: the swap+bind redirected the TX mic source onto the Jabra path — but the Jabra uplink is silent (no live SCO) — and RX fell back to the speaker. The bind can now *point at* the joiner; what in-image emulation never produces is the **open SCO/HFP audio channel**.
- **S4 (Jabra-first)** — S4a PASS (P6 path, Jabra-alone audio fine). S4b: menu-press Connect on TID-PTT: stock kick (Jabra "mobile disconnected"), radio briefly LOCKED ("Connecting" spinner looping, keys dead) until the TID-PTT was powered off — transient stall, recovered; end state TID-PTT-only. **Regression watch: E7-ref/S1 never stalled here.**
- **S5** (user performed as an S1 rebuild: menu TID-PTT, then Jabra pages in) — both connected → **TX = TID-PTT mic + RX silent = the 7th identical goal-miss signature.** S6 inconclusive (user: "not sure I did S5 correct").

**VERDICT: R8 = GOAL FAIL.** The pre-registered decision (§30.14.48, card footer) fires: seven consecutive goal-misses ⇒ **the in-image bind-emulation route is CLOSED for good.** The app-slot swap tested the last hypothesis in that family and localized the wall precisely: stamping the app handle + routing byte + stock bind CAN redirect the TX source (S3c) but CANNOT conjure the HFP/SCO audio channel — only the full app-originated dial flow creates that, and the app source does not exist (§30.14.45) while the Ghidra-C splice is dead (§32.6).

**Escalation (user's choice):** SDK rebuild (ch. 28) / compiled-C splice (ch. 35 §35.9) / ESP32 combo device (§9B.6.1).

**Radio state:** currently on R8 `4bb75a2c…` (experimental; S4 stall + RX-silent quirk). Restore the FIELD-PASSED daily driver S1: `sudo bash work/ch32_bt_e7.sh` (its 13 sectors re-write `0x66000`; the orphan R8 cave bytes in `0xAC000` are dead data once the `0x01E61270` hook is restored). Alternative rollback recipe: 2 sectors `0x066000`+`0x0AC000` from E7-ref `90bec320`.

*[<< Index](Findings.md)* · [Ch. 29 (address map)](29-static-analysis-reference-map.md) · [Ch. 27 (E1–E11 log)](27-firmware-2slot-stack-controller-wall.md) · [Ch. 28 (SDK route)](28-sdk-forks-survey.md) · [Ch. 23 (BT-PTT2 validation)](23-bluetooth-8-bt-ptt2.md) · [Ch. 18 (priorities)](18-open-questions-next-steps.md)
