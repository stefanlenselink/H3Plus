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
> `--cmd5-target` (four sites, objdump round-trip verified, both suites green) and
> **BUILT**: `work/ch30_r1e.bin` sha256 `d2aa7d8d…`, diff vs F3-v3 = exactly sectors
> `0x026000`+`0x073000`+`0x0AC000` (73 B). Stage `work/ch30_r1e.sh` + card
> `work/ch30_r1ec.sh` ready — **awaiting user flash** (radio still on R1-c;
> rollback `work/ch30_r1crb.sh`).
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

---

*[<< Index](Findings.md)* · [Ch. 29 (address map)](29-static-analysis-reference-map.md) · [Ch. 27 (E1–E11 log)](27-firmware-2slot-stack-controller-wall.md) · [Ch. 28 (SDK route)](28-sdk-forks-survey.md) · [Ch. 23 (BT-PTT2 validation)](23-bluetooth-8-bt-ptt2.md) · [Ch. 18 (priorities)](18-open-questions-next-steps.md)
