# 39 — Two-device master plan (ch39)

Started 2026-11-17. This chapter is the single authoritative plan for the
two-simultaneous-BT-devices goal. It consolidates the goal (§30.0), the dead-lever
register (E/F/P/R/ch37 series), and the three remaining routes into one phased plan
with observability FIRST. Chapters 30–38 remain the evidence ledger; this chapter
decides what runs next and in what order.

## §39.1 Goal (authoritative — never rescope, restated from §30.0)

Exactly two devices connected at the same time:

- **A = Jabra Evolve 65** `74:5C:4B:E2:73:34`, HFP/SCO bidirectional: radio RX →
  earphones, BT-PTT TX ← headset mic.
- **B = TID-PTT** `6F:E5:E7:FB:12:4F`, SPP RFCOMM ch2: `+SPP=P`/`+SPP=R` key the radio.

PASS requires ALL of:

1. Both devices up at the same time; **both orders** work (A then B, B then A).
2. B keys TX, and the **Jabra mic** is what gets transmitted.
3. **RX audio plays in the Jabra.**
4. Radio PTT / BT-PTT / BT-PTT2 / OD keys all still work.
5. No echo/sidetone after release (SCO closes or is muted, §27.13).
6. Survives a cold boot and a 10-min soak.

## §39.2 Baseline record (Phase 0.1, 2026-11-17)

User reports the radio currently holds `Dumps/dump_internal.bin`:

| Field | Value |
|---|---|
| File | `Dumps/dump_internal.bin` (1 MiB full-chip image, dated 2026-09-15) |
| sha256 | `bf86a705ae07c1558874a024b83f12e698eccc8bf9cfa31f91d7c40e311a5216` |
| uboot `0x0000–0x4FFF` | **byte-equal to `Dumps/dump_pre_ch30.bin`** (stock, asserted) |
| app region | decrypted (`work/di_app_dec.bin`) **byte-identical to `work/app_dec.bin`** = clean stock v1.0.50, 0 differing bytes over 802,784 |
| device-specific bytes `0x0C8FE0` | present (`0400…7800`) |
| patch state | **UNPATCHED stock** — no BT-PTT, no E7 kick-NOPs, no `-BT` name postfix |

Consequences:

- This is a CLEAN baseline — good for Phase 0.2 (PC↔button only, radio not involved)
  and for any future full-image reflash protocol (§30.3).
- It is NOT S1 (`work/ch32_bt_e7.bin` `d7a29a3e…`): BT-PTT, BT-PTT2 and the E7
  kick-NOPs are absent. **Phase 1.2 emulator validation and Phase 2.5 radio cards
  require S1**; flashing S1 is a user action queued at those steps.
- Sector exports for later cards must be re-derived against whatever image is on the
  radio at that moment (mission rule: verify current-image hash before exporting).

## §39.3 Dead-lever register (do NOT repeat without a genuinely new experiment)

| Lever | Series | Outcome |
|---|---|---|
| Global NOP of 0x4A posters `0x01E61E22`, `0x01E60188`, `0x01E600EC` | E9–E11, F3, P9 | lockup/freeze — posts are load-bearing |
| Global NOP `is_1t2` bail `0x01E17A2A` | v4 (§37.16) | reboot crash — removed stock cmd-1 safety check |
| Force routing byte 3 at incoming tbh | R3 | binds nothing, echo latch |
| Replay cmd 1 (START_CONNEC_VIA_ADDR) at tbh | R4 | no-ops on already-connected ACL (same-address guard `0x01E16824`) |
| Kick+redial via mailbox `0x1A5F1` | R5 | two-device stable, audio never bound |
| Stamp byte 3 at redial connect-complete | R6a | state path, not a bind |
| Current-device write + cmd 6 name replay | R6b | goal-miss + press-freeze + TX-dead |
| Direct `goto` bind block `0x01E61292` | R7 | goal-miss — bind needs app dial state BEFORE connect-complete |
| App-slot swap (`h[0x10372]`) + bind tail | R8 | goal-miss — wall is the app-originated HFP/SCO channel |
| Compiled-C bind v1–v4 (§37) | v1–v4 | 8th–10th identical goal-miss + regressions; IN-IMAGE BIND ROUTE CLOSED (12 levers) |
| LED execution probe (§36) | v1–v3 | impractical (RAM-blob render race) — dropped |

Common signature of all bind attempts: both up → TX on TID-PTT path/silence, RX
silent. Root cause (§37.5, §30.14.49): the audio bind ONLY happens through the
app-originated dial flow writing struct `0x102F0` state before connect-complete.

## §39.4 Phase 0.2 — the §38.7 vs §9A.19/20 contradiction (analysis + re-test)

**Contradiction.** §38.7 concluded "events only flow on PTT-originated links".
§9A.19/§9A.20 (2026-09) captured `+SPP=P/R` from the button over a **PC-originated**
link (`bt_ag_capture.py --connect`). Both cannot be right.

**Record comparison (static, 2026-11-17):** the two runs differed in every variable
that matters —

| Variable | §9A.19/20 (events ✅) | §38.7 (no events ❌) |
|---|---|---|
| Tool | `bt_ag_capture.py --connect` (full AG SLC: BRSF/CIND/CHLD/codec answers) | raw `rfcomm connect` — **no AG handshake** |
| Channel selection | brute-force 1–30, first opener | pinned ch2 (SDP returned nothing: `HFP=? SPP=?`) |
| Bonding | `bluetoothctl pair && trust` first | unpaired, button in pairing-blink |
| Link security | bonded → encrypted/authenticated | blink link, no bond |
| Radio state | off | off (same) |

**Hypothesis (UNTESTED until re-test returns):** the discriminator is the **link
security/bond state** (and possibly the AG SLC), NOT the connection direction. The
§38.7 conclusion "PTT-originated only" conflated direction with these variables.
§9A.20's own table says the button needs "no handshake at all" on the SPP channel —
consistent with events flowing once the LINK is right, regardless of who dials.

**Re-test card** = card `P0.2` below in §39.11 (issued to user 2026-11-17; rig ready).
It isolates: channel that accepts, bond state (paired vs blink), AG SLC (yes/no),
btmon security events. Verdict goes here when results return.

**Second correction (record fact, no test needed):** §38.8's "CHIPSET VERDICT =
JieLi (mfr 1494, LMP 5.3 subver 0x22bb)" was **already in the record** — §9A.20's
peer-identity snapshot (2026-09) lists "Manufacturer: Zhuhai Jieli Technology (1494),
LMP 5.3, subversion `0x22bb`". §38.8 re-derived it from `hcitool info` after the
round-3 log review missed the ch09 table. Dated correction added to ch38 §38.8.

## §39.5 Phase 1 — Observability FIRST

The R-series failed partly because patch firing was never confirmed on hardware
(§36 probe dropped). Before ANY new radio-side image, the rig must be able to SEE:

- **1.1 HFP stand-in** — PC as "Jabra": `tools/bt_hf_sim.py` / `tools/bt_be_headset.sh`
  + `btmon -w`. Answers per card: does the radio open HFP RFCOMM/SLC/SCO toward the
  audio device, and when does 0x4A tear things down.
- **1.2 TID-PTT emulator** — **BUILT 2026-11-17** as `tools/bt_ptt_emulator.py`
  (documented in `tools/Tools.md` §6.9): PC/BlueZ
  RFCOMM server reproducing the button's quirks: ch2 server, CoD `0x240404`, name
  `TID-PTT…`, never pages, drops ACL when SPP closes, sends `+SPP=P/R` (NUL-term.,
  double-release) on key/timer. Validated against the real button on S1 (kick + rejoin
  signature identical on btmon).
- **1.3 Audio truth** — second radio or RTL-SDR + signal source; reusable checklist to
  verify TX carries the Jabra mic and RX reaches the Jabra (the PASS criteria 2+3
  cannot be graded by btmon alone).
- **1.4 Radio telemetry** — investigate only (K-plug serial / BLE GATT ff00-ae00 /
  tone-LCD indicator) to expose RAM: handle `0x10372`, routing byte `0xB464`, SPP cell
  `0x1A740`, conn slots `0x1A5B8`/`0x1A5D4`. Build only if cheap+safe.

**Gate 1:** 1.1 + 1.2 working before any new radio-side image goes to the user.

## §39.6 Phase 2 — Route A (primary): make the TID-PTT page the radio

Rationale (§37.19, §38): if B pages in while A holds the app's current-device/audio
binding, the radio never runs a dial for B → no 0x4A, no rebind. SPP RX
(`FUN_01e5b2f4`) has no current-device gate → B still keys the radio. Remaining
obstacle = the P8 wall (incoming pages refused while HFP is up) → §39.6 step 2.5.

- **2.1 ROM loader without opening the puck** — JieLi **USB_KEY** boot mode
  (kagaimiq/jielie `isp/usb/usb-key.md`): at power-on, bit-bang 16-bit `0x16EF`
  MSB-first, D+ = clock (rising-edge latch, ~50 kHz), D− = data; chip ACKs by pulling
  both lines low 1–2 ms (pull-up ≤ 4.7 kΩ); then hand lines to PC USB (isolated xHCI
  or SOF-generating dongle); talk with jl-uboot-tool. Dongle: RP2040/CH552/Arduino +
  analog switch. Wiring doc + `tools/` script = deliverables. Fallbacks: UART_KEY,
  ISP_KEY. NOTE §38.21: earlier "USB-boot probe negative" only tested device-mode
  enumeration WITHOUT the USB_KEY handshake — this is genuinely new.
- **2.2 Identify chip + flash size; check read-protect; full dump; back it up TWICE,
  hash both; prove write-back before any patch.**
- **2.3 Decrypt + lay out the app** (chip key / jielie tooling): connection policy
  (reconnect-on-power-up, page scan, remembered-host table), SPP server setup,
  SPP-close→ACL-drop path. Reference: `fw-AC63_BT_SDK` app structure.
- **2.4 Patch, in preference order:** (a) page remembered host at boot + on
  disconnect; (b) keep ACL when SPP closes; (c) optionally act as SPP client to the
  radio's ch2. Verify on emulator/PC host first, then field-test against S1.
- **2.5 Radio card set against S1 with patched button** (each scenario ×5):
  1. Jabra first (holds HFP), button pages in → P8 wall, expect refusal.
  2. Button first, Jabra pages in → S1 behaviour; does audio stay bound to button?
  3. Cold boot with both remembered.
  - If (1) refused → scoped radio-side patch: keep page scan / accept second incoming
    ACL while HFP is up, gated on **second slot free only** (study `is_1t2` scan
    management, `--force-page-scan`, P7 once-per-boot). NO global NOPs (dead levers).
  - If (2) binds audio to button → classifier/0x3e-sink skip for SPP-only links, or
    app dial of the Jabra after button joins (safe iff 2.4b done).

**Gate A:** all §39.1 criteria → Phase 5 (§39.9). Chip read-protected/unflashable →
UART_KEY / ISP_KEY; opening the puck only as last resort with explicit user OK.

## §39.7 Phase 3 — Route B (parallel, radio-side; only with Phase 1 observability)

Pipeline per design: statics → `jl_sim` → `jl_oracle` → emulator card (btmon) →
real-device card.

- **3.1 Run card P10 "dial seesaw"** (§33.9, never run): does dialling B kick A and
  vice versa, on the CURRENT baseline.
- **3.2 §37.9 v2 "restore-after-rebind"** (designed, never built): snapshot
  current-device struct + handle + `0xB464` while Jabra is current; let B dial
  happen; restore Jabra as current once SPP is up. FIRST answer via btmon on the
  stand-in: does 0x4A close the Jabra's HFP RFCOMM?
- **3.3 Targeted 0x4A scope**: in the wrapper `0x01E600EC` path, skip/redirect 0x4A
  ONLY when dial target is the TID-PTT and another handle is the Jabra — conditional
  splice in the cave, all other paths stock.
- **3.4 Stack-level button dial**: open B without app dial flow — HCI create-link +
  `spp_connect` `0x01E1750C` to ch2 from the correct task context; app handle/current
  device stays on the Jabra. Trigger from auto-reconnect `FUN_01e66ef8` or a key.
- **3.5 Dual auto-reconnect**: app-path dial of the Jabra, then bare-path (3.4) dial
  of the button; retry whichever device is missing (covers both orders).

**Gate B:** whichever design passes ALL §39.1 criteria on emulator AND real devices wins.

## §39.8 Phase 4 — Route C fallback: ESP32 bridge

§9B.6.1 proves one ACL carrying SPP+HFP is the stock happy path. ESP32 presents to
the radio as ONE device with SPP+HFP; bridges SPP client → TID-PTT and HFP-AG →
Jabra (SCO bridge). Deliverable = design doc (latency, SCO bridging, power, BOM);
build only if Routes A and B are both blocked.

## §39.9 Phase 5 — Polish and acceptance

- **Echo (mandatory):** close SCO or mute mic path after BT-PTT release in the
  2-link state (§27.13).
- **Full matrix:** both pairing orders · power-cycle each device separately · radio
  cold boot · out-of-range/return · 10-min soak with periodic TX/RX · every radio key
  (PTT, BT-PTT, BT-PTT2, OD) with 0/1/2 devices up.
- Promote winner to daily driver: sha + patch-tool flags + tests in the suites.
- Docs: §39 verdict, README, Findings index, copilot-instructions current-state,
  user-facing how-to (pairing order + recovery: PTT+1+power-on → `tools/jl_hidboot.py`).

## §39.10 Decision gates (summary)

| Gate | Condition | Next |
|---|---|---|
| 0 | baseline recorded + §38.7 contradiction resolved by P0.2 re-test | Phase 1 |
| 1 | HFP stand-in + PT emulator working (btmon-validated vs real button on S1) | Phase 2/3 cards allowed |
| A | Route A meets all §39.1 criteria | Phase 5 |
| A′ | PTT chip read-protected | UART_KEY/ISP_KEY, then open-puck only with user OK |
| B | a Route B design passes emulator + real devices | Phase 5 |
| C | A and B both blocked | ESP32 design doc → build |

## §39.11 Cards issued from this chapter

- **P0.2** (2026-11-17, no radio needed — keep it OFF): TID-PTT link-mode capture.
  Isolates channel / bond state / AG-SLC as the §38.7-vs-§9A.20 discriminator.

  Run A — reproduce §9A.19/20 (bonded + AG SLC + brute-force channel):
  ```bash
  systemctl --user stop pipewire pipewire-pulse wireplumber
  bluetoothctl scan on          # wait for "TID-PTT0cd28a-B", then scan off
  bluetoothctl remove 6F:E5:E7:FB:12:4F   # clear stale bond if any
  bluetoothctl pair 6F:E5:E7:FB:12:4F     # blink the button if asked
  bluetoothctl trust 6F:E5:E7:FB:12:4F
  sudo btmon -w /tmp/p02_a.pcap &
  sudo python3 tools/bt_ag_capture.py --connect 6F:E5:E7:FB:12:4F
  # press the button 3x when it says NOW PRESS THE PTT BUTTON
  sudo pkill -f "btmon -w"
  sudo btmon -r /tmp/p02_a.pcap | grep -iE "encryption|authentic|link key|pairing" | head -40
  ```

  Run B — no bond, pairing-blink, same AG tool (isolates BOND):
  ```bash
  bluetoothctl remove 6F:E5:E7:FB:12:4F
  # blink the button (hold >= 1 s)
  sudo btmon -w /tmp/p02_b.pcap &
  sudo python3 tools/bt_ag_capture.py --connect 6F:E5:E7:FB:12:4F   # press 3x
  sudo pkill -f "btmon -w"
  ```

  Run C — bonded, NO AG handshake, raw rfcomm on the channel found in A
  (isolates SLC; reproduces §38.7 method on a good link):
  ```bash
  bluetoothctl pair 6F:E5:E7:FB:12:4F && bluetoothctl trust 6F:E5:E7:FB:12:4F
  sudo rfcomm bind 8 6F:E5:E7:FB:12:4F <chA>
  timeout 15 cat /dev/rfcomm8 | hexdump -C    # press 3x
  sudo rfcomm release 8
  ```

  Report per run: channel that opened; `+SPP=P/R` bytes seen?; btmon security lines;
  whether the button needed a blink to accept. Verdict matrix:
  A✅ B❌ → bond/security is the discriminator (hypothesis confirmed, §38.7 fixed);
  C✅ → SLC irrelevant (matches §9A.20 "no handshake"); A❌ → §9A.20 not
  reproducible — escalate (remembered-host binding?). Result recorded in §39.4.
