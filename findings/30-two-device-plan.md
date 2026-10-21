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

---

## §30.3 — Recording discipline (mandatory for every experiment)

Every experiment run produces a **record** appended to §30.10's ledger with ALL of:

1. **ID** (e.g. `B1`, `M1-A`), **date + clock times** (start/end).
2. **Build under test**: image filename + `sha256sum` + the exact build command line.
3. **Flash log**: every `erase`/`write` command + the `read … verify` result
   (`cmp` output — must be byte-identical, paste `IDENTICAL` or the diff).
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

| Stage | = | Extra options beyond previous | Known state from ch. 27 (PC-based) |
|---|---|---|---|
| **M1** | E7 | `--conn-num=2 --no-kick --force-page-scan --force-role-keep --no-disconnect-13 --no-pairing-kick` | SPP+HFP multipoint OK when radio-initiated; accessory-incumbent pairing-kick observed |
| **M2** | M1 | `--no-cleanup-kick` | HCI-level eviction fully dead (E8) — never tested with TID-PTT incumbent + HFP target |
| **M3** | M2 | `--no-l2cap-teardown` | E9 FAILED (close persisted) — co-actors only; included for completeness |
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
| Radio not connectable while connected (incoming pages die ~700 ms, 0x13) | §27.8 | goal flows are radio-initiated — do not test device-side initiation |

---

## §30.10 — Results ledger (append rows; never edit past rows)

| ID | Date | Build (sha8) | Stage | Card | Result | Evidence | One-line observation |
|---|---|---|---|---|---|---|---|
| B0 | | | base | full flash | | | |
| B1.1 | | | base | Jabra alone | | | |
| B1.2 | | | base | TID-PTT alone | | | |
| B1.3 | | | base | PC SPP ref | | | |
| B2.1 | | | base | A→B stock | | | |
| B2.2 | | | base | B→A stock | | | |
| M1-A/B/C/D/E/R | | | M1=E7 | … | | | |
| M2-A/B/C/D/E/R | | | M2=E8 | … | | | |
| M3-A/B/C/D/E/R | | | M3=E9 | … | | | |
| M4-A/B/C/D/E/R | | | M4=E10 | … | | | |

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

---

*[<< Index](Findings.md)* · [Ch. 29 (address map)](29-static-analysis-reference-map.md) · [Ch. 27 (E1–E11 log)](27-firmware-2slot-stack-controller-wall.md) · [Ch. 28 (SDK route)](28-sdk-forks-survey.md) · [Ch. 23 (BT-PTT2 validation)](23-bluetooth-8-bt-ptt2.md) · [Ch. 18 (priorities)](18-open-questions-next-steps.md)
