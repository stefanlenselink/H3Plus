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

**Run A result (2026-11-17, field): PASS — §9A.19/20 reproduced.** Bonded + trusted
button, PC-originated `bt_ag_capture.py --connect`: `+SPP=P`/double `+SPP=R` streams
freely (16 presses logged, raw `2b 53 50 50 3d 50 00` …). Channel: **2** on the clean
run. Two new observations:
1. **State-dependent channel:** while the button was still in pairing-blink (red/green)
   the first probe opened **channel 10** instead (no events logged there — user
   interrupted before pressing; blink state may expose a second SPP-like service,
   OTA/DFU candidate). After the blink ended (idle/bonded) channel 1 refused and
   **channel 2** opened immediately — the PTT service.
2. **No HF/SLC traffic at all:** the button never sent `AT+CIND`/`AT+BRSF` — it only
   streams raw `+SPP=` frames once the channel is open. Confirms §9A.20 "no handshake
   at all"; predicts Run C (raw rfcomm, bonded, no AG) will also PASS → SLC irrelevant,
   bond state = the discriminator. §38.7's failure = unbonded blink link + no SLC
   combined; the ACL even survived the tool's Ctrl-C (`Connected: yes` in the next
   snapshot) — the button keeps an idle bonded ACL up.
**Run A security evidence (btmon, 2026-11-17):** stored **Link Key Request/Reply**
(key `8f4c9672…`, bond reuse — no new pairing on the data link) followed by
**Encryption Change** → the event-carrying link was **authenticated + encrypted**.
One transient `MGMT Authentication Failed` at +13.6 s during the initial probe storm
(recovered on retry — the button rejects some auth attempts while settling). Bond-state
discriminator: CONFIRMED for Run A (encrypted bonded link = events; §38.7's unencrypted
blink link = silence).

**Follow-up idea (user, 2026-11-17):** `bt_ag_capture` stops probing at the FIRST open
channel — the button's full channel map (esp. the blink-state ch-10 service) is
unenumerated. New tool `tools/bt_ptt_channel_probe.py` (BUILT 2026-11-17): probes all
channels, **keeps every opener connected**, holds N s while the user presses, then
reports per-channel status + event counts; closes all at once (a single close could
trigger the button's ACL-drop quirk mid-test).

### §39.4.1 Full channel map + corrected button state model (2026-11-18, field)

**User correction of the button's state machine** (supersedes my "idle vs blink" split —
the two probe runs are therefore the SAME state, and the Run A "state-dependent channel"
observation above was WRONG): the puck has ONE button. Long-press (>1 s) = POWER ON →
the button boots straight into **pairing/advertising mode** and stays there while no
link exists; on connect it leaves pairing mode; on link loss it returns to pairing mode.
There is no separate idle-unconnected state. Run A's first invocation hitting ch 10 was
just probe-order luck (transient Host-down/timeout on 2/4 while the link kept
re-forming between attempts), not a mode difference.

**Channel map (bonded, unconnected, `bt_ptt_channel_probe.py --hold 15`, runs identical
2026-11-18 08:43 and 08:44):** channels **2, 4, 10 OPEN; 1, 3, 5–9, 11–30 all REFUSED**.

| Ch | Verdict | Evidence |
|---|---|---|
| 2 | **PTT SPP service** — carries `+SPP=P`/double `+SPP=R` (15 + 21 events across the two runs) | raw `2b 53 50 50 3d 50 00` … |
| 4 | **HFP HF-role control channel** — on connect the button immediately sends `AT+BRSF=671\r` (`41 54 2b 42 52 53 46 3d 36 37 31 0d`) = SLC initiation as HF device, feature bits `0x671`; went silent when unanswered; 0 PTT events | new discovery |
| 10 | **Unknown service — accepts, mute** (0 bytes both runs, no press response) | identity TBD |

**Implications:**
1. **Run C is implicitly PASSED**: the prober is a raw-socket client with NO AG
   handshake, bonded link → events flowed on ch 2. SLC is irrelevant to PTT events;
   the button's HF SLC lives on its own ch 4 and the PTT data does not wait for it.
   §38.7's failure = **unbonded link** (bond state = sole discriminator so far;
   Run B still confirms).
2. §9A.20's "no handshake at all" REFINED: the button DOES want an AG on ch 4
   (sends `AT+BRSF=671` unprompted) — that is likely what the RADIO connects to when
   it dials the button (and what `bt_ag_capture` should drive with `--channel 4`);
   PTT events ride ch 2 regardless.
3. ch 10 = candidate vendor/OTA service (JieLi RCSP-style) — needs an identity probe
   (see card P0.2b below/§39.11).

### §39.4.2 Run B result (2026-11-18, field): hypothesis REFUTED — bond is NOT the discriminator

`bluetoothctl remove` + power-cycle (fresh unbonded advertising) + full 1–30 sweep:
**channels 2, 4, 10 OPEN exactly as bonded** — and **`+SPP=P/R` events flowed on ch 2
(15 events)** with no bond on the PC side at all. LED observation confirms the state
model: red/green blink before → solid (connected) while the prober held the links →
red/green again after all sockets closed.

**Corrected conclusions (2026-11-18):**
1. **Bond state: irrelevant.** Direction: irrelevant (already disproved). AG SLC:
   irrelevant (prober is raw). The button streams PTT events to ANY host that holds a
   live RFCOMM session on ch 2, paired or not, encrypted or not.
2. **§38.7's "no events" is now the anomaly to explain, and its script shows how.**
   Section 5 was `timeout 18 rfcomm connect /dev/rfcomm8 $PTTB 2 2>&1 | head -30`:
   `rfcomm connect` binds the node (data visibility on stdout is BlueZ-version
   dependent — a reader on `/dev/rfcomm8` was never opened), and the `| head` +
   `timeout` kill discards any buffered stdout. Prime suspect: **the events arrived and
   were never printed.** Secondary confound: sections 2–3 had earlier touched the LE
   identity (GATT) and forced an SDP page storm on the same single-link device.
3. §9A.20 (bonded, working) and P0.2 Run A/B (bonded AND unbonded, working) are now
   consistent: the link was never the problem — §38.7's *capture method* was.
4. **Confirmation test issued (card P0.2c, §39.11):** re-run §38.7 section 5 verbatim
   (expect silence = artifact reproduced), then the same command WITHOUT the pipe
   (expect live `+SPP=` = artifact confirmed).

### §39.4.3 Ch 10 REVISITED (2026-11-18, field): NOT mute — live device-originated ASCII console

Run E (`sudo rfcomm bind 0 6F:E5:E7:FB:12:4F 10` + `timeout 30 cat /dev/rfcomm0 |
hexdump -C`) returned **~4.3 KB in 30 s, entirely device-initiated** (nothing had been
sent — the `printf 'AT\r'` step was never executed):

- Repeating `41 54 0a` = `"AT\n"` prompt lines.
- Runs of literal `5e 4a` = the two characters `"^J"` (caret + J), **growing by one per
  cycle and never resetting** within the capture — a console echoing line-feed in caret
  notation / timeout-tick spam, not binary protocol.

**Anomaly vs earlier runs:** the 1–30 prober twice logged ch 10 as 0 bytes (mute).
Two candidate explanations, to be separated: (a) the prober's ch-10 socket read path
missed data (same class of capture bug as §38.7 — now twice in one day), or (b) the
stream is STATE-dependent: it began after the ch-4 probes left the button's HF/AT
engine retrying an unanswered SLC — ch 10 may be a debug console LOGGING that retry
loop. Fresh-power-cycle + immediate ch-10 bind (before any ch-4 touch) settles it.

**Significance for Route A:** if ch 10 is an interactive console, the puck exposes a
diagnostic path over Bluetooth — potentially chip/log info without opening the case,
and a way to observe the patched connect policy live. Card P0.2d (§39.11) probes it
interactively with harmless AT queries only (no flash-ish commands).

### §39.4.4 Ch 10 = INTERACTIVE echo console (2026-11-18, field, card P0.2d D1)

Sent `AT\r`, `ATI\r`, `AT+GMR\r` while capturing (`/tmp/p02_d1.log`). Results:

1. **Echo CONFIRMED — the channel is bidirectional.** `ATI` (offset 0x18d) and
   `AT+GMR` (0x311) appear in the received stream, CR echoed as LF.
2. **History redraw:** each sent line then repeats in EVERY subsequent periodic frame
   (`ATI` recurs ~once/cycle) — the console re-displays its accumulated line buffer per
   tick. The growing `^J` runs are that buffer's empty lines; occasional `J^` byte-pair
   misalignment = the redraw window sliding byte-wise.
3. **No modem semantics:** no `OK`/`ERROR`/version reply to `ATI`/`AT+GMR`. This is a
   debug-style echo console, not an AT interpreter with a result-code layer.

**Route A significance:** the puck exposes an interactive console over Bluetooth. If it
parses ANY commands (vendor dialect), it may yield identity/log info — and later, a
live observation point for the patched connect policy. Vocabulary unknown; next probe
tries the standard discovery forms (`AT+?`, `AT+HELP`, `AT+CMD`) — all safe read-only
queries. **Still UNVERIFIED whether anything executes at all (pure echo remains
possible).**

### §39.4.5 Ch 10 VERDICT (2026-11-18, field, card P0.2d D1b): self-feeding ECHO loopback — CLOSED

Sent `AT+?`, `AT+HELP`, `AT+CMD`, `ATV1` (`/tmp/p02_d1b.log`): **no command list, no
result codes, no banner, no format change.** Every sent line simply joins the per-tick
history redraw and circulates forever (e.g. `AT+?` and `AT+HELP` both repeat in every
subsequent frame). The console executes NOTHING.

**Root-cause model of the original "mute→spam" mystery — self-feeding loopback:** the
device emits an `AT\n` prompt whose own output re-enters its input path (factory-style
UART/RFCOMM loopback); each pass escapes the LF as literal `^J` and re-prints, adding
one more `^J` per cycle — exactly the observed monotonic growth from boot, with no
external input required. Our commands just enter the circulating buffer.

**Consequences:**
1. Ch 10 = **test/loopback channel, no diagnostic value** as a command interface.
   Route A stays on the USB_KEY dongle plan (§39.6); ch 10 investigation CLOSED.
2. It DOES confirm: the puck accepts RFCOMM on a factory-test channel from any host,
   unencrypted — consistent with the overall zero-security accessory profile.
3. Earlier "0 bytes" prober readings on ch 10: the loopback oscillation may start
   slowly (one `^J` per tick) — a 15 s hold with late bind can legitimately see
   near-zero data. Prober read-path NOT proven buggy; anomaly downgraded.
4. D2 (virgin-boot stream test) demoted to optional — the loopback model already
   predicts the observed startup signature (`AT\n AT\n` then growth).

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

- **P0.2b** (2026-11-18, follow-ups from §39.4.1; radio stays OFF):

  Run B — NO bond (last open leg of the hypothesis; the only remaining variable):
  ```bash
  bluetoothctl remove 6F:E5:E7:FB:12:4F
  # power-cycle the button (long-press >1 s) so it advertises fresh
  sudo python3 tools/bt_ptt_channel_probe.py 6F:E5:E7:FB:12:4F --only 1-12 --hold 15
  # press repeatedly at the prompt; then re-pair+trust to restore yesterday's state
  bluetoothctl pair 6F:E5:E7:FB:12:4F && bluetoothctl trust 6F:E5:E7:FB:12:4F
  ```
  Expect: channels refuse, or open but MUTE → bond state confirmed as THE
  discriminator. If events flow UNBONDED too → security is not it; escalate.

  Run D — ch 4 as a real AG (complete the HF SLC, see what the button is):
  ```bash
  sudo btmon -w /tmp/p02_d.pcap &
  sudo python3 tools/bt_ag_capture.py --connect 6F:E5:E7:FB:12:4F --channel 4
  # press 3x, watch which channel the events take; then pkill btmon
  ```
  Expect: `AT+BRSF=671` then the tool's SLC answers; learn whether the button then
  also wants `AT+CIND`/`AT+CMER` (and whether PTT events move to ch 4 or stay ch 2).
  This is likely the exact conversation the RADIO has with the button.

  Run E — ch 10 identity, PASSIVE ONLY (unknown service — do NOT send firmware-ish
  bytes; no writes beyond a plain `AT\r` probe):
  ```bash
  exec 3<>/dev/rfcomm0  # after: sudo rfcomm bind 0 6F:E5:E7:FB:12:4F 10
  ```
  i.e. `sudo rfcomm bind 0 6F:E5:E7:FB:12:4F 10`, `cat /dev/rfcomm0` for 30 s
  (expect silence), then optionally `printf 'AT\r' > /dev/rfcomm0` and watch for any
  reply; `sudo rfcomm release 0`. Record: any bytes at all. Deeper probing (RCSP
  discovery) only after we decide it's safe.

- **P0.2c** (2026-11-18, from §39.4.2 — §38.7 capture-artifact confirmation; radio OFF,
  button state does not matter — bonded or not, both work):

  E1 — §38.7 section 5 VERBATIM (expect: NO output = the artifact reproduces):
  ```bash
  timeout 18 rfcomm connect /dev/rfcomm8 6F:E5:E7:FB:12:4F 2 2>&1 | head -30
  # press the button 3x during the window; then:
  sudo rfcomm release 8
  ```

  E2 — same WITHOUT pipe (expect: live `+SPP=P`/`+SPP=R` text = artifact CONFIRMED):
  ```bash
  timeout 18 rfcomm connect /dev/rfcomm8 6F:E5:E7:FB:12:4F 2
  # press 3x; watch for live output; Ctrl-C to end, then:
  sudo rfcomm release 8
  ```
  If E1 silent + E2 live → §38.7 conclusion formally dead (capture bug, not link
  policy). If E2 also silent → `rfcomm connect` never displays received data on this
  BlueZ → even stronger artifact (nobody ever read the socket). Either way §38.7's
  "events only on PTT-originated links" is replaced by: events flow on ANY live ch-2
  session. Record both outputs verbatim.

- **P0.2d** (2026-11-18, from §39.4.3 — ch 10 console probe; SAFE queries only: plain
  AT commands, no flash/OTA-ish verbs). Node 0 is already bound to ch 10.

  D1 — interactive query (does it answer?):
  ```bash
  sudo timeout 60 cat /dev/rfcomm0 > /tmp/p02_d1.log 2>&1 &
  sleep 2; printf 'AT\r'      > /dev/rfcomm0; sleep 3
  printf 'ATI\r'     > /dev/rfcomm0; sleep 3
  printf 'AT+GMR\r'  > /dev/rfcomm0; sleep 3   # unknown-command probe → expect ERROR-style reply
  wait
  hexdump -C /tmp/p02_d1.log | head -60
  ```
  Record: any reply to OUR commands (OK / ERROR / version / prompt change), and whether
  the `AT`/`^J` spam pattern changes after input (echo? reset of the `^J` counter?).

  D2 — state-dependence of the stream (separates explanations (a)/(b) of §39.4.3):
  power-cycle the button fresh, bind ch 10 IMMEDIATELY (no ch-4 touch this boot):
  ```bash
  sudo rfcomm release 0
  # power-cycle the button (>1 s press), then at once:
  sudo rfcomm bind 0 6F:E5:E7:FB:12:4F 10
  timeout 20 cat /dev/rfcomm0 | hexdump -C | head -20
  ```
  Stream present on a virgin boot → ch 10 always spams (prober read-path was the bug).
  Silent on virgin boot but returns after a ch-4 probe → the console logs the HF/AT
  engine (then Run D becomes doubly interesting).
  Finally: `sudo rfcomm release 0`.

## §39.12 Stack command executor decoded (2026-11-18, static, stock v1.0.50)

Opportunistic statics while awaiting the S1 decision. The vendor/HCI command executor
is **`FUN_01e195bc` @`0x01E195BC`** (app VA; decompiled
`disassembled/decompiled/01e195bc/FUN_01e195bc.c`): a param-length switch over BOTH
vendor cmds `0x2001–0x2012` and HCI-direct subcodes `0x0C03–0x0C37`, dispatching via a
32-bit jump table @`0x01E19756`; default branch `goto 0x01E197C2` (no-op, return
`0x1004` @`0x01E197CE`). HCI commands reach the controller through senders
`0x01E07474(op, …)` (1–2 params), `0x01E07498(op, len, …)` (param blob),
`0x01E07900` (variant).

Key handlers (all statically inferred, UNTESTED):

| Subcode | Handler | Action |
|---|---|---|
| `0x0C05` | `0x01E197D2` | **HCI_Write_Scan_Enable `0x0C1A`**: `r1 = DAT_0000c02b & 0xff00; r1 |= b[0xBF3C]` → `call 0x01E07474(0xc1a, r1)` — scan-enable byte = stack-config RAM `0xBF3C` (blob base `0xBF24`, +0x18; NOT the `0xBF39` conn-num byte) |
| `0x0C13` | `0x01E197E6` | HCI_Write_Page_Scan_Activity `0x0C1C`: `(0xc1c, h[0xBF3E], h[0xBF40])` — interval/window = blob +0x1A/+0x1C |
| `0x0C14` | `0x01E19810` | HCI_Write_Inquiry_Scan_Activity `0x0C1E` (same pattern) |
| `0x0C17` | `0x01E19856` | HCI_Write_Page_Timeout `0x0C18`: `(0xc18, b[0xBF38])` — page-timeout byte = blob +0x14 |
| `0x0C18` | `0x01E19890` | `call 0x01e07900(…)` + `b[0xBF24] |= 0x40` |
| `0x2001` | `0x01E19AA4` | **HCI_Create_Connection `0x0409` (THE DIAL)**: `call 0x01E07498(0x409, 7, [sp+12], r2, r3)` — 7-byte params (BD_ADDR + pkttype + reserved + allow_role_switch) |
| `0x2002` | `0x01E19AC2` | HCI_Accept_Connection_Request `0x040F` (role byte `[sp+12]`) |
| `0x2003` | `0x01E19AE0` | HCI_Reject_Connection_Request `0x040C` (reason) |
| `0x2004` | `0x01E19AF4` | HCI_Link_Key_Request_Reply `0x040B` (23-byte params) |
| `0x2005` | `0x01E19B0E` | HCI_Link_Key_Request_Negative_Reply |
| `0x2006` | `0x01E19B1E` | HCI_PIN_Code_Request_Reply `0x040D` |
| `0x2007` | `0x01E19B2E` | HCI_PIN_Code_Request_Negative_Reply `0x040E` |
| `0x2008` | `0x01E19B3E` | HCI_Authentication_Requested `0x0411` |
| `0x2009` | `0x01E19B54` | HCI_Set_Connection_Encryption `0x0413` |
| `0x200A–0x200D` | `0x01E19B6E/7E/92/A4` | not yet decoded |

Param sizes (from the C): `0x2001/2/3/5/7`→7 B, `0x2004/6`→23 B, `0x0C05`→1,
`0x0C13`→5, `0x0C17/18`→2, `0x0C19`→10, `0x0C1A`→2, `0x0C1F`→3, `0x0C20`→5,
`0x0C22`→1, `0x0C24/25/27/28`→7, `0x0C31`→2, `0x0C33`→7, `0x0C35`→1, `0x0C36/37`→2.

**Relevance:**
1. Route B 3.4 (stack-level button dial): the dial executor is cmd `0x2001` →
   `0x01E07498(0x0409, 7, …)` @`0x01E19AA4`. A cave can post `0x2001` (or call the
   sender directly) with a BD_ADDR blob — the same primitive the radio uses for its
   own dials, without touching the app `0x102F0` state.
2. Scan policy: Write_Scan_Enable reads the 1-byte cell `0xBF3C` at EXECUTE time; the
   stock `--force-page-scan` patch (`0x01E18B0E`, ch. 26 §26.9) gates the bit WRITERS,
   not this executor — consistent with E4/E7 field results (forced scan still died at
   LL: the controller, not the scan byte, refuses the 2nd incoming ACL).
3. `0x0409` sender has exactly ONE caller (`0x01E19AA4`) — every radio-originated dial
   funnels through cmd `0x2001` on this executor.

Open: who posts `0x2001` (xref pending); relation to the R5 re-dial mailbox `0x1A5F1`
(epilogue `0x01E2232E`→`0x01E21E46` posts cmd 1); handlers `0x200A–0x200D`,
`0x0C19/1A/1F/20/22/24/25/27/28/31/33/35/36/37`.

**Correction (late 2026-11-18, §39.14): the `0x2001` framing above is DISPUTED and
partly wrong.** Full-tree grep finds NO literal `0x2001` post and no `|0x2000`/`+0x2000`
construction anywhere; `0x01E19AA4` lies inside `FUN_01e19a78` case 5
(Create-Connection-COMPLETE cleanup walk), not a dial-posting handler; and upstream-clean
disasm shows `0x01E195BC–0x01E196D6` is the tail of a conn-record-walking function, not a
vendor-cmd executor. The real dial chain is decoded in §39.14. Re-verify any §39.12
handler-table claim with `pi32dis.py --upstream=../pi32v2-isa` before using it in a
Route B design. The scan-policy rows (`0xBF3C` read at execute time, page-timeout
`0xBF38`, scan activity `0xBF3E/0xBF40`) are unaffected.

## §39.14 USP command relay fully decoded — the dial chain (2026-11-18, static, stock v1.0.50)

Source: `disassembled/decompiled_all.c` (Ghidra 12 tree, 6491 functions). Closes the two
Route B open items from §39.12 (who posts `0x2001`; the `0x200A–0x200D` handlers).

**1. Sole stack-command post primitive:** `FUN_01e029de(target, nargs, cmd, args...)`
(line 2157). Targets: `0x400002` = controller HCI sender, `0x400006` = vendor controller
task. HCI Create Connection wrapper: **`FUN_01e07988` @`0x01E07988`** =
`FUN_01e029de(0x400002, 7, 0x405, addr6, pkttype, 0, 0, param_3)`; its ONLY caller is
**`FUN_01e16f60` @`0x01E16F60`** — the DIAL EXECUTOR (walks pending conn records; also the
tail call of the HCI event dispatcher, so it fires after every event round).

**2. USP relay = the decoder ring.** `FUN_01e22890` @`0x01E22890` (ch. 26's known
controller-queue relay) drains the USP queue at RAM `0x1A694` (record: word[8] = cmd,
word[3] = arg0, payload at +0x28; read via RAM-code `func_0x02003bba/func_0x02003bf2`)
and switches on the **small-integer USP cmd** (the `user_send_cmd_prepare` family):

| USP cmd | Relay action | HCI post |
|---|---|---|
| **1** START_CONNEC_VIA_ADDR | `FUN_01e07386(arg0)` | vendor **`0x200A`** (1 arg) — the DIAL request R4 replayed |
| 2 / 0x11 | shared tail → `FUN_01e07398(a,b,c)` | wrapper, HCI word TBD |
| 3 | `FUN_01e073f4(a,b)` | wrapper TBD |
| 4 | `FUN_01e07440(a,b)` | wrapper TBD |
| **5** KICK | `FUN_01e074de(h)` | **`0x0406` Disconnect(h, 0x13)** — ch. 26 ✓ |
| 6 | store callback `_DAT_0001a738` | — (falls into 7) |
| 7,9,0xd,0xe,0x14,0x18,0x19,0x1a | no-op in relay | consumed elsewhere |
| 8 | `FUN_01e1651a(); FUN_01e22772(payload+0xc)` | — |
| 0xb | conn-param fill rec+0x1a..0x20, rec+0x14=1, then `FUN_01e16f60()` | → DIAL executor |
| 0xc | = case 0x16 body (payload=1) | `0x200C` |
| 0xf | `FUN_01e074fc(arg0+6)` | wrapper TBD |
| 0x10 | `FUN_01e075b6()` | vendor **`0x200E`** (0 args) |
| 0x12 | `FUN_01e075c6(a, b&0xff)` | wrapper TBD |
| 0x13 | `FUN_01e075e6(a, b&0xffff)` | wrapper TBD |
| 0x15 | scan-config: 2-bit/slot into RAM `DAT_0000c54c` | — (no HCI) |
| 0x16 | `FUN_01e074be(a, b&0xff)` | vendor **`0x200C`** (2 args) |
| 0x17 | `thunk_FUN_01e24090()` | — |
| 0x1b | `FUN_01e22772(a, b&0xffff)` | — |
| 0x82 | `FUN_01e07350(a,b,c,d)` | vendor **`0x2013`** (8 args) |

Relay tail second block (`code_r0x01e22a90`): link-supervision walk over conn records at
`_DAT_0001a684` → `FUN_01e22814(handle, u16>>12, u16, +0xac)` per record.

**3. Answers:** (a) "who posts `0x2001`" — NOBODY; the vendor `0x200x` words are what the
RELAY posts to the controller, not app-level commands. (b) `0x200A` = dial (via USP 1),
`0x200C` = via USP 0xc/0x16, `0x200E` = via USP 0x10, `0x2013` = via USP 0x82; `0x200D`
wrapper ~`0x01E075xx` (0 args) called outside the relay (caller open). The actual ACL
page = conn record → `FUN_01e16f60` → `FUN_01e07988` → HCI `0x0405`.

**4. Relevance to Route B / R-series:** R4's `--incoming-hfp` replayed USP 1 → relay case
1 → `0x200A` — consistent with §30.14.28 (no-ops on the already-connected same-address
guard: `0x200A` is a vendor *request*, the controller ignores it for a live same-addr
link). **B3.4 (stack-level button dial) now has a clean primitive: create/seed a conn
record and call `FUN_01e16f60` (or post USP 0xb which ends there), bypassing app
`0x102F0` entirely.** Event side: `FUN_01e19a78` router (type 2 → event dispatcher
`FUN_01e196d8`; type 4 → cmd-complete: case 3 stores the created handle into the record,
case 5 cleanup, teardown via event case 5 reason 0x13 → `FUN_01e5af40`); pending-cmd list
`FUN_01e19496` (max 3 entries, `_DAT_0001a4e0+0xc`, count +0x24). All UNTESTED.


## §39.13 USB_KEY dongle design (2026-11-18, Route A step 2.1 — static, UNTESTED)

Firmware for the RP2040 dongle: **`tools/jl_usbkey_dongle.py`** (MicroPython,
`main.py`). Protocol authority: kagaimiq/jielie `isp/usb/usb-key.md` (fetched
2026-11-18). **Line assignment CORRECTED: D+ = CLOCK (chip latches D− on the clock
RISING edge), D− = DATA** — ch. 32 §32.10 had these swapped (dated fix applied there).

Protocol facts (from the authoritative doc):
- Key = 16-bit `0x16EF`, MSB-first, ~50 kHz; no strict timing (chip RX is software
  with a timer catching clock rising edges).
- Stream the key REPEATEDLY until the chip ACKs by pulling BOTH lines low ~1–2 ms.
- ACK sensing requires EXTERNAL pull-ups ≤4.7 kΩ: during key RX the chip enables its
  15 kΩ USB pulldowns; MCU-internal ~20 kΩ pull-ups would form a false-ACK divider,
  and a directly-attached PC adds another 15 kΩ (→ 7.5 kΩ effective pulldown).
- After ACK the chip inhibits key RX, then BEFORE USB init pulls D+ high and measures
  falling-edge periods to calibrate its PLL/reference clock (expects 1 ms SOF pulses;
  cannot distinguish SOF from noise — other FS/LS devices on the same hub corrupt it →
  wrong clock → watchdog reset into flash app).
- Mitigation (adopted): after ACK the dongle pulses D+ low ~10 µs every 1 ms until D+
  is held low ≥2 ms (chip finished calibration), THEN connects the PC side.

Architecture (in-line dongle, RP2040 Zero/Pico):

| Signal | RP2040 | Target side (puck) |
|---|---|---|
| CLK (D+) | GP0, open-drain | 4.7 kΩ pull-up to 3V3; to puck USB-C D+ via analog switch |
| DATA (D−) | GP1, open-drain | 4.7 kΩ pull-up to 3V3; to puck D− via analog switch |
| SW_EN | GP2 | gate on 2× SPST analog switch (TS5A3166 / DG411 / D74CBTLV3126 class, normally open) |
| LED | GP25 | blink = key streaming, solid = PC bus connected |
| GND | GND | common with puck + PC |

PC side = USB-A receptacle (D+/D− through the switches; VBUS pass-through — puck is
battery-powered, VBUS only charges). Puck POR is the USER's >1 s power-button press
while the key streams (no VBUS trick needed).

State machine (`jl_usbkey_dongle.py`): `KEY_STREAM` (packet, 2 ms idle gap, release
both lines and sense ≥800 µs sustained both-low = ACK) → `SOF_PULSE` (10 µs low every
1 ms, exit on D+ held low ≥2 ms, 300 ms timeout → re-stream) → `CONNECT` (GP2=1, LED
solid, forever). Design notes: manual hot-plug is impractical (chip calibration window
is short, watchdog on failure) hence the switch; 4.7 kΩ pull-up || chip 1.5 kΩ FS
pulldown during enumeration = 1.13 kΩ Theveny deviation — out of spec, works in
practice per JieLi community designs, **UNTESTED**; CH552 variant possible but needs
SDCC 8051 toolchain + open-drain care — RP2040 recommended.

**Card P2.1 (first contact — hardware build required; UNTESTED; user runs when
equipped):**
1. Flash `jl_usbkey_dongle.py` to the RP2040 as `main.py`; verify LED blink.
2. Wire per table; leave puck UNPOWERED; PC `dmesg -W` + `watch -n1 lsusb` running.
3. Power the puck (>1 s button) while the dongle streams.
4. Record: does enumeration happen? VID:PID + descriptor dump (`lsusb -v`). The puck
   MaskROM face is UNKNOWN — do NOT expect `4c4a:4155` (that is the radio's
   fw-Bootloader app face, ch. 32 §32.10.1).
5. If enumerated: try `sudo python3 tools/jl_hidboot.py info`, then
   `jl-uboot-tool` against the face (read-only `info`/dump first — §38.3 propose-
   don't-flash; full dump backed up TWICE with hashes before ANY write).
6. Abort criteria: EPROTO/error-71 loop (key not ACKed or calibration corrupted) →
   retry on a dedicated hub with ONLY the puck; no ACK ever → verify pull-ups,
   line swap, GP0/GP1 open-drain config.

**Field-report addendum (2026-11-21, findings/38 §38.26 — tmon.ch BR28 hack
independently proved this exact route).** Deltas adopted here:
(a) **preferred simpler build = SWITCHLESS** — PC permanently parallel with the MCU
on D+/D− (issue-#12 diagram), no analog switch, no SOF injection; after ACK the MCU
releases and the host's real SOFs calibrate the chip. MANDATORY ordering: PC attached
BEFORE the target reset. `jl_usbkey_dongle.py` gained a `SWITCHLESS = True` config
flag for this; the switched design above stays as the isolated-bus fallback.
(b) Card step 4 expectation refined: a BR28-generation ROM face is a **fake
mass-storage device driven by custom SCSI commands** (`jl-uboot-tool` uploads a RAM
loader → flash shell); `dmesg` prints `<FAMILY>UBOOT<ver>` = free family ID.
(c) At the shell: **read the chip key + flash ID** (trailing ID byte = log2 size;
beyond-capacity reads wrap/repeat) — then decrypt with `tools/jl_sfcenc.py` using
that key. (d) Recovery: ROM UBOOT survives ANY flash wreck, and a non-booting flash
auto-enters download mode — but only after our FIRST successful entry + pristine
dump does that become our safety net (§38.26-4). (e) If the PTT board exposes **PB1**,
holding it low 8 s is the SDK-default clean reset to re-enter the ROM window
(battery boards otherwise hide whether a reset really happened). (f) Look for
labeled **DP/DM test pads** by the SoC (JieLi reference flashing points; never 5 V on
VBAT, VBAT < 4.5 V while flashing).

## §39.15 B3.4 `--jabra-keep` — FIRST radio-hardware experiment with the UNMODIFIED button (2026-11-19, built, UNTESTED)

**Concept.** Keep the native Jabra-first audio bind untouched and add ONE thing:
after the Jabra is up, the radio *dials the button itself* (radio-originated
second link — the E6-proven direction), then **restores the app current-device
handle** so audio stays on the Jabra while the button's SPP ch2 session keys the
radio (SPP RX `FUN_01e5b2f4` has no current-device gate; single SPP cell
`0x1A740` is free because the Jabra is HFP ch6). This is NOT a bind attempt —
every dead lever in §39.3 tried to *force* a bind; this one *preserves* the
native bind and only repairs a handle around our own dial.

**Why the handle needs restoring.** The 0x3e connect-complete sink
`FUN_01e5af40` rewrites `_DAT_00010372` (app current-device handle,
`0x102F0+0x82`) **unconditionally** on any successful connect-complete —
including our radio-originated button dial — so without repair the audio bind
would follow the dial onto the button (the mirror of the old problem). The
cave saves the handle before the dial and restores it when the dial lands.
Static decode of the sink: §39.14 + this session (event 0x3e success ⇒
`_DAT_00010372 = FUN_01e17d2c(ev,4)`; teardown event 5 zeroes it on ANY
disconnect — the §30.14.25 echo-latch root — hence the second restore below).

**Patch (patcher option `--jabra-keep`)** — base S1 `work/ch32_bt_e7.bin`
(`d7a29a3e…`), two sites, 200 B changed, sectors `0x066000` + `0x0AC000` only:
- tbh hook `0x01E61270`: `50 ee 64 0d` (`r0 = b[r6+212]`, routing byte RAM
  `0xB464`) → `call 0x01EA7722` (`82 ea 57 32`) — the R3–R8-proven
  connect-complete hook; joiner BD_ADDR ptr at `[sp+20]`; teardown sentinel
  byte `0xF0`.
- cave `0x01EA7722` (218 B of the 295 B window): 8 B thunk (`r0=[sp+20]`,
  call body, rts) + 208 B **compiled-C** body @`0x01EA772C`
  (source `work/ch39/jk_c.c`; clang `--target=pi32v2-unknown-unknown
  -mcpu=r3 -Oz -mllvm -pi32v2-large-program`, linked at fixed VA, ZERO
  relocations; symbol landed `0x01EA772C`).

**State machine** (RAM statics: state u32 `0x1C010` magic `0x4A4B…`, saved
handle u16 `0x1C014`, BTN addr scratch `0x1C018`; power-on garbage-tolerant —
only the exact magics act):
1. byte==1 && state==0 && joiner ≠ BTN(`6F:E5:E7:FB:12:4F`) ⇒ Jabra (or any
   non-button) connected: save `_DAT_00010372` → `0x1C014`, state:=`ST_DIAL`,
   post `USP(1, 6, &BTN)` **DIRECT** via dispatcher `0x01E1792E` — NEVER the
   dial wrapper `0x01E600B4` (its `0x4A` preamble = incumbent-SPP killer,
   §37.16). With conn-num=2 + 1 active link, `is_1t2_connection` is FALSE so
   cmd 1 PROCEEDS — no bail NOP (the v4 crash lever is untouched).
2. byte==1 && state==`ST_DIAL` && joiner == BTN ⇒ our dial landed; the 0x3e
   sink has just rewritten `_DAT_00010372` to the button handle: restore
   `_DAT_00010372` = saved (Jabra), state:=`ST_DONE`. Stock tbh path opens the
   button's SPP ch2 (mode-1 path); keys then work device-ungated.
3. byte==`0xF0` && joiner == BTN (button teardown): `ST_DIAL`→0 (re-arm
   retry); `ST_DONE`→restore handle again (echo-latch repair per §30.14.25).
4. Button-first joins at state 0 = pure stock passthrough (daily driver
   behaviour unchanged). Routing byte always returned unchanged.

**Evidence trail (all pre-flash gates).** llvm-objdump `-d --triple=pi32v2`
clean, zero relocs; upstream pi32v2-isa oracle decode of the whole cave stream
(thunk+gap+body) clean, hook resumes on instruction boundary; `jl_sim`
hardware-fitted CPU model **5/5 PASS** — T1 save+dial post (r0=1 r1=6 r2=0x1C018
at USP entry, state→ST_DIAL, handle saved, BTN const written), T2 restore +
ST_DONE, T3a re-arm, T3b teardown-restore, T4 passthrough; `verify_actions.py`
+ `verify_cli.py` **0 failures** (jkcave taught to recognize the gate-close
stub window + bind-c window — mutually exclusive payloads, recognition-only);
image `work/ch39_jk.bin` **sha256 220c500b34be6024e4f504faaca6118f3a0bae02c8242d6de98e9c0d623f0c42**
— plaintext-verified post-build (decrypt: hook `82ea5732` @app `0x61270`, cave
bytes @app `0xA7722`), uboot `0x0000–0x4FFF` byte-equal to
`Dumps/dump_pre_ch30.bin`, diff vs S1 = sectors `0x066000`+`0x0AC000` only.

**Risks / observations wanted (UNTESTED until field).** BTN byte-order at
`[sp+20]` assumed air order (R5 CMP6 precedent) — if reversed, the state
machine treats Jabra as "non-BTN" twice and never restores: symptom = audio
follows the button (old signature) — card S4a distinguishes this. 1–2 s audio
steal window while the button connects (S3a). Stale saved handle if the Jabra
drops before the button (S7/S8). USP cmd-1 SCO side-paths toward the button:
none expected (no HFP on button). P7 once-per-boot wall does NOT apply — the
dial is radio-originated (E6-proven direction).

**Field run.** Stage `work/ch39_jk.sh` (flash 2 sectors, PRECHECK + `WRITE`
gate + full readback + uboot assert + boot check). Card `work/ch39_jkc.sh`
(S0–S9, PASS per §39.1 goal). Verdict → new §39.16 dated record. Recovery if
needed: PTT+1+power-on → `sudo python3 tools/jl_hidboot.py` (stock uboot
intact).

## §39.16 JK-1 FIELD VERDICT: FAIL — catastrophic connect break (2026-11-19, field + static root-cause)

**Field report (user, bench).** Flashed `work/ch39_jk.bin` (`220c500b…`,
clean flash + readback). Result: **unable to connect or pair ANY device**.
The pairing menu still listed the two known devices but pressing Connect
timed out; selecting a device from *Paired devices* → **radio FREEZES HARD**
(restarting the TID-PTT does not unfreeze it). With the Jabra in pairing
mode (repeating "to connect the Jabra, go to the bluetooth menu…" voice
clip + music), pressing Connect on the Paired-devices menu made the clip
**stop instantly** (silence — something fired), the radio locked up, and the
headset also locked (normally "Mobile connected" is announced — not this
time). ⇒ JK-1 = connect-path killer, worse than a goal-miss. Not a daily
driver; must not ship.

**Root cause (static, same day).** The tbh byte load at `0x01E61270` is
reached from BT-task main-loop (`FUN_01e60e44`) **event cases 6 AND 7**
(case 7 falls through to `LAB_01e6123c`, case 6 `goto LAB_01e6123c` —
upstream disassembly `0x01E61240–0x01E612B8` + decompiled tree), i.e. on
*mode re-evaluations*, not only connect-complete. On those events `[sp+20]`
is **not** a BD_ADDR pointer. The compiled JK-1 body dereferenced the joiner
pointer **unconditionally at entry** (`r1 = h[r0+4]` + `r0 = [r0+0]` before
any routing-byte check — confirmed in its objdump) → wild/odd load → BT-task
fault/hang on real hardware. R5's field-proven cave read `[sp+20]` only
*under* the byte==1/0xF0 gates (zero freezes anywhere in the R5 field run);
bind-c v3 never dereferenced r0 at all (DIAL-stamp discriminator). Our
unconditional deref was the only never-field-validated behavior in the
design and it explains every symptom: freeze on Paired→Connect (events fire
while byte==0, before connect-complete), pairing timeouts, dead audio path
(clip silence), missing "Mobile connected" (HFP SLC never completes because
the BT task hung), and why restarting the button did not help.
`jl_sim` cannot reproduce it (the sim tolerates odd loads — byte=0 with
joiner=0x1 simply returned r0=0); hardware is the authority.

**LESSON (add to every future cave contract):** any consumer of the
`0x01E61270` tbh hook MUST gate on the routing byte (or event identity)
*before* touching `[sp+20]` or any frame slot beyond the displaced
instruction. The hook fires on more events than connect-complete.

## §39.17 JK-2 BUILT — gate-order fix (2026-11-19, UNTESTED)

One-cause fix in `work/ch39/jk_c.c`: early gate inserted immediately after
the routing-byte read —

```c
c = *b;
if (c != 1 && c != 0xF0)
    return c;   /* never touch the joiner pointer outside byte 1/0xF0 (R5 order) */
```

so every tbh event other than connect-complete/teardown returns the byte
unchanged without dereferencing anything (§39.16 lesson). Rebuilt with the
ch. 37 recipe: body 208 → **216 B**, symbol `jk` still @`0x01EA772C`, zero
relocations; objdump order verified (byte load → `if(r4==0xF0)` →
`if(r4!=1)` exit → *then* the `h[r0+4]`/`[r0+0]` derefs). Cave total = 8 B
thunk + 2 B gap + 216 B = **226 B** @`0x01EA7722..0x01EA7804` (≤ 295 B
budget).

**Gates (all green 2026-11-19).** Upstream pi32v2-isa oracle decode of the
full 226 B cave stream clean (no `???`, branch targets resolve, epilogue at
stream EOF); `jl_sim` **8/8 PASS** — T1 save+dial post, T2 restore+ST_DONE,
T3a re-arm, T3b teardown-restore, T4 passthrough, NEW **T5a/b/c** garbage-
pointer passthrough (byte 0/2/5 with joiner `0x1`/`0xFFFFFFFF`/`0x0` →
returns the byte, fast exit ≤40 steps); patcher `JK_BODY_BYTES` replaced +
asserts updated (216/226) + labels/CLI text; `verify_actions.py` PASS,
`verify_cli.py` **0 failures**.

**Image.** `work/ch39_jk2.bin` sha256
`ab68cf262ac187a36be16e66de41f1b559b3c26736270154330056cbc863204b` = S1
(`d7a29a3e…`) + `--jabra-keep`, 208 B changed in sectors `0x066000`+`0x0AC000`
ONLY; plaintext-verified post-build (hook `82ea5732` @app `0x61270`, cave
bytes @app `0xA7722`); uboot `0x0000–0x4FFF` byte-equal to
`Dumps/dump_pre_ch30.bin`.

**Field run.** Stage `work/ch39_jk2.sh` + card `work/ch39_jk2c.sh` — the
card adds **R1, the connect-regression gate FIRST** (Paired→Jabra Connect
and Paired→button Connect must work without freeze; fail = STOP, the
§39.16 bug is not fixed), then the JK-1 S2–S9 observation ladder (auto-dial,
TX mic source, RX location, keys, echo, button re-power, soak, second cold
boot). Verdict → §39.18. Radio currently holds JK-1 `220c500b…` (broken);
the stage PRECHECK skips the two written sectors, so flashing JK-2 from the
JK-1 state passes. Recovery if needed: PTT+1+power-on →
`sudo python3 tools/jl_hidboot.py` (stock uboot intact).

## §39.18 JK-2 FIELD VERDICT: PARTIAL — §39.16 freeze FIXED; button symptoms re-point AT THE DIAL WORKING (2026-11-19/20, field + static)

**Field report (user, bench).** Flashed `work/ch39_jk2.bin` (`ab68cf26…`,
clean). **"Better than JK-1"** — the connect paths are alive again:
- Jabra pairs fine via the radio's Pairing option + Jabra pairing mode.
- Jabra auto-joins after its power-off/on. ✅ (the §39.16 break is gone)
- **TID-PTT could NOT be paired "in any way"** — radio restarts, late power-on
  while the radio was connecting, pairing mode, direct Connect: nothing.
- **Pairable scan shows the Jabra but NOT the button** ("strange").
- Pressing Connect on already-paired devices: the red/green LED goes OFF
  ("connecting"), returns a few seconds later, ~10 s later goes off again and
  comes back — a repeated-attempt cadence. **Full freeze on the Connect press
  in MOST attempts.**

**Static corroboration (2026-11-19, `work/full.lst` + decompiled
`FUN_01e60e44`).** The routing byte `0xB464` has exactly ONE direct store in
the app: `0x01E61C88 b[r6+0xD4] = r12`, reached via the event-jump table at
`0x01E61C04..1E`; the `0xF0` sentinel is written by BT-task **event cases 9/10
(disconnect)** at decompiled line 96365 (`DAT_0000b464 = 0xf0`), and those
cases **break — they do NOT execute the mode tbh**. Consequences:
1. The cave sees `0xF0` only on a SUBSEQUENT event 6/7 (that is how R5's
   teardown branch worked too — consistent, field-proven).
2. Event 6/7 re-fires repeatedly while the byte stays `1`, and the cave's
   `0xF0`+BTN re-arm (ST_DIAL→0) can therefore close a **re-dial loop** with
   disconnect churn — matching the observed ~10 s LED dance.

**ALTERNATIVE (and preferred) hypothesis — the auto-dial FIRES and the button
CONNECTS SILENTLY.** It explains every button symptom without a loop bug:
- A connected peripheral leaves page/inquiry scan ⇒ **button invisible in
  Pairable** while the (disconnected, pairing-mode) Jabra shows. ✅
- The radio UI tracks only the current device (Jabra) ⇒ nothing on screen
  indicates the second link. ✅
- Pressing Connect on an ALREADY-CONNECTED device hits the stock same-address
  page guard `0x01E16824` — the §31 freeze mechanism ⇒ **freeze on MOST
  Connect presses** (the user was pressing exactly those entries). ✅
- Fresh pairing of the button is impossible while it is connected (it is not
  discoverable) ⇒ "unable to pair in any way". ✅
The card's decisive question — **does the button LED go SOLID on its own
~1–2 s after the Jabra joins?** (S3) — was not answered; the run went off-card
into pairing attempts. Also open: whether the cave's ST_DIAL→restore branch
fires at all (if the classifier stamps the button connect-complete with a byte
≠ 1, the early gate returns without restoring ⇒ `_DAT_00010372` stays on the
button ⇒ audio would follow the button path — must be observed via the TX mic
source).

**NEXT (no reflash — free discriminator, card `work/ch39_jk2d.sh`):** clean
state observation: power-cycle radio, button ON idle (blinking), Jabra ON →
watch the button LED (SOLID on its own = dial fired and landed), then button
PTT keying + mic source + RX location WITHOUT touching any menu. Verdict
branch: button solid + keys ⇒ JK is functionally close (fix = UX/freeze
surface + re-arm churn); button never solid ⇒ the dial/page path itself is the
suspect (next static pass: dispatcher cmd-1 bail state with 1 active link,
§39.14 re-check). JK-3 design (one-shot terminal state, no `0xF0` re-arm,
conn-record guard on ARM) is prepared but NOT built until D1/D2 discriminate.

## §39.19 JK-3 BUILT — classifier-store hook, one-shot terminal state (2026-11-20, UNTESTED)

**Why the hook moved.** The §39.18 analysis showed the tbh load at
`0x01E61270` (what JK-1/JK-2 hooked) fires on BT-task loop events **6 AND 7**
— *mode re-evaluations* — so the routing byte it reads can be stale with
respect to the connect flow being armed on. The **classifier store
`0x01E7EC98`** (`52 ee 54 1d` = `b[r5+0xD4] = r1`, `r5` = `0xB390`, inside
`FUN_01e7ec28`) is the single authoritative point where the routing byte
`b[0xB464]` is *decided and written* (name → mode, ch. 30 §30.14.18/24).
Hooking the store arms the machine exactly when a mode is assigned — under
BOTH §39.18 hypotheses (dial-never-fired and dial-fired-silently): if the
dial never fired, the correct trigger moment is now; if it fired and the
button connected silently, the one-shot terminal state + conn-record guard
eliminate the re-arm churn and the handle restore lands on the classifier's
own mode-1 write.

**Design (`work/ch39/jk3_c.c`, symbol `jkc` @`0x01EA7730`).** Cave
`0x01EA7722` = 14 B preamble (`7904 0516 1016 80ea0200 5016 5904`:
push `{rets, r9-r4}` — pairs with the classifier epilogue `59 04` =
`{pc,r9-r4}=[sp++]`; stash the classifier's saved `b[0x102F0+0x278]` in `r5`,
pass `r1` (the mode) as `arg0`, call body, restore `r0`, return) + 136 B
compiled-C body. Body logic:
1. `*b = (u8)mode` FIRST — replicates the stock store for *every* mode
   (behaviour-identical when not engaging; the hook replaces only the `0x98`
   store, the transient `5`-store @`0x01E7EC50` is untouched).
2. `mode==3 && state==0 && exactly one conn record inuse`
   (`((r[0x12]^r[0x2E]) & 0x20)` — slots `0x1A5B8`/`0x1A5D4`, stride `0x1C`,
   inused = bit `0x20` of byte `+0x12`; ch. 27 §27.1) → save
   `_DAT_00010372` → `0x1C014`, state := `0x4A4B0001` (ST_DIAL), stage BTN
   `6F:E5:E7:FB:12:4F` at `0x1C018`/`0x1C01C`, post `USP(1,6,BTN)` **DIRECT**
   @`0x01E1792E` (never the dial wrapper — `0x4A` preamble kills SPP,
   §37.16; no NOPs anywhere).
3. `mode==1 && state==ST_DIAL` (the button's own connect-complete) → restore
   `_DAT_00010372`, state := `0x4A4B0002` (ST_DONE, **terminal**).
4. Everything else: passthrough. **No `0xF0` handling, no re-arm** — a
   re-dial loop is structurally impossible. **Known gap:** no teardown
   repair; echo behaviour after a Jabra power-off is stock-unpatched (card
   S7 observes).

**Gates (all green 2026-11-20).** Body 136 B, zero relocations, objdump
order verified (store before branches; `r0=1 r1=6 r2=0x1C018 c3 00` call at
the dial site). Upstream pi32v2-isa oracle: 150 B cave stream decodes with
**0 `???`** (ends `0x01EA77B8` ≤ `0x01EA7849` budget). `jl_sim` **11/11
PASS** — T1 (mode-3 arm: dial posted with the FULL BTN address at `0x1C018`,
handle saved, `b[0xB464]=3`), T1b/T1c (both-slots / none-slot → no dial),
T2 (mode-1 restore + ST_DONE), T3–T6 (passthrough + one-shot guards: no
re-arm on mode-3 while ST_DIAL, no re-dial after ST_DONE), T7 (slot-1
variant), T8/T9 (mode-2/mode-6 store-only). Two sim-test bugs were found
and fixed on the way (`--seed` writes raw hex bytes, not LE words; `jkc` is
void — assert `--expect-mem`, not `r0`) and one REAL bug: the BTN u16 tail
was staged at `0x1A5C01A`, clobbering the u32 — fixed to `0x1C01C` (sim T1
now proves `6f e5 e7 fb 12 4f`).

**Patcher suite regression + fix (lesson).** The reworked `jkcave` site
(150 B ctx window) broke `find_app_start()` recognition for every
R5/R6a/R8/R1-e/LED-probe image (17 `verify_actions` failures): the ctx check
requires *some* state to match the whole window, and those images carry
other options' cave payloads there. Fixed with a recognition-only mirror
loop that slices every `inchrdlcave` state to 150 B into `jkcave.states`.
**General rule: any new site sharing the `0x01EA7722` cave run MUST mirror
the sibling options' states or image readback (`--show`, patching) breaks.**
After the fix: `verify_actions.py` + `verify_cli.py` **0 failures**.

**Image.** `work/ch39_jk3.bin` sha256
`66415d781536155526bc7e0c66a27f222e815887fa8a87168ba1c0ead3613ff7` = S1
(`d7a29a3e…`) + `--jabra-keep`, **141 B** changed in sectors `0x083000`
(classifier hook, flash `0x83C98`) + `0x0AC000` (cave) ONLY; plaintext
verified post-build (hook `81ea4345` @app `0x7EC98`, cave bytes @app
`0xA7722`); uboot `0x0000–0x4FFF` byte-equal to `Dumps/dump_pre_ch30.bin`.
The tbh site `0x01E61270` is **stock** again on JK-3 (`50ee640d`).

**Field run.** Stage `work/ch39_jk3.sh` (PRECHECK skips the written sectors
— passes from the JK-2 state) + card `work/ch39_jk3c.sh` (visible echoed
questions, answers tee'd to `work/logs/`). Decisive observations: **S3**
button LED solid on its own after the Jabra joins, **S3b** button ABSENT
from Pairable while connected (= dial landed), **S4a** TX mic source,
**S5** RX location, **S7** echo (known gap), **S8** one-shot behaviour on
button re-power. Verdict → §39.20. Radio currently holds JK-2 `ab68cf26…`.
Recovery if needed: PTT+1+power-on → `sudo python3 tools/jl_hidboot.py`
(stock uboot intact).

## §39.20 JK-3 FIELD VERDICT: PARTIAL — BREAKTHROUGH, the auto-dial fired (2026-11-20, field + static root-cause)

**Field report (user, bench).** Verbatim: *"TID-PTT auto-joined! … I had
the Jabra first paired and connected, after a TX the sideloop was Radio Mic
=> jabra headset, then I turned on the TID-PTT and it auto joined and the
radio said 'bluetooth connected' (through the radio speaker); after that
moment the sideloop echo loop was Jabra Mic => Radio speaker, and when doing
first TX the 'original' echo loop returned Radio mic => Jabra earphones. The
TID-PTT was all the time connected but never able to trigger TX … I tried to
power the radio then connect the TID-PTT and have the Jabra auto-connect —
was unable to do so."*

**What WORKED (first in the whole two-device effort):**
- **The classifier hook armed and the radio DIALLED the button by itself.**
  The TID-PTT is a pure peripheral that never pages (§37.19) — its join after
  the Jabra connected can only be our `USP(1,6,BTN)` post fired from the
  classifier store hook at mode-3. **B3.4 dial mechanism = LIVE on hardware.**
- Two ACLs up simultaneously, Jabra paired + auto-joined natively, no freeze
  in the main (Jabra-first) test, no reboot, pairings survived.

**What FAILED:**
1. **Button keying dead** — connected the whole time, never triggered TX.
2. **Audio sideloop transients around the join**: pre-join `Radio Mic →
   Jabra earphones` (normal duplex mode 4); at the BTN connect-complete the
   "bluetooth connected" announcement played on the SPEAKER and the loop
   became `Jabra Mic → Radio speaker`; the FIRST TX restored the original
   loop. (The stock mode-1 connect-complete machinery still ran for the
   button — local routing flip + announce — and self-recovered on TX.)
3. **Reverse order** (button first, Jabra second) could not be made to work.

**Root cause of the dead keying (static, same day) — the missing SPP
session.** A raw `USP(1,6,addr)` cmd-1 dial brings up the **ACL only** (+ the
name read that feeds the classifier). The **app** opens the SPP ch-2 session
*separately* on its own connect event: `FUN_01e17e62` (app BT event router,
gate `_DAT_0000bf1c != 0 && b[0xBF3B]&8`) **event code 3** @`0x01E17ED6`:
`if (FUN_01e16878(1) != 0) FUN_01e1782c(0, 0x1101)` — and `FUN_01e16878(1)`
@`0x01E16878` is the conn-record finder (walks `0x1A5B8..0x1A5EF` stride
`0x1C`: inused bit `0x20` of byte `+0x12`, handle `u16@+6 != 0`,
`u16@+8 & 0x2080 == 0`). Our stack-level dial never generated that app event
⇒ no rfcomm ch-2 session ⇒ no `+SPP=P/R` frames ⇒ the ungated key injector
`FUN_01e5b2f4` never ran ⇒ dead button. (Same signature as R5: ACL up,
profiles never bound — ch. 30.)

**Exact ABIs recovered (upstream-oracle disassembly, authoritative):**
- `FUN_01e1782C(r0, r1, r2)`: `r3 = _DAT_0001a740` (SPP cb; `==0` →
  return −1); `b[cb+6] != 0` → return −2 (pending); **r1 = mode**:
  `0` = open → `r1 = r2.l` then `spp_connect(r0, r2.l)` — **r0 passes
  through untouched**; `1` = close → `FUN_01e173ec`; `2` = reopen →
  `spp_connect(0x1200)` or `FUN_01e17702(cid,0x1200,0)`.
- `FUN_01e1750C` = **spp_connect(r0 = ptr to 6-byte BD_ADDR, r1 = u16
  service class)** (0x1101 = SPP, 0x1200 = HID): if `h[cb+2]` (CID) != 0 →
  `FUN_01e173ec` + return −2; `b[cb+6] = 1`;
  `FUN_01e1744C(0x01E2356E/*callback*/, r0/*addr ptr*/, 1, 0xFFFF)`;
  `h[cb+4] = class`; return 0.
- `FUN_01e1744C(callback, addr ptr, …)`: allocates the l2cap channel struct,
  handle lookup by BD_ADDR (`thunk_FUN_01e079ca(addr,1)`), **copies the 6
  addr bytes to `chan+0x16`**, then `FUN_01e16F60()` = the §39.14 dial
  executor. ⇒ the event-3 caller passed **r0 = the conn-record pointer =
  BD_ADDR at record+0..5** as the target address.

**JK-4 design (locked from this decode).** Keep the classifier hook +
preamble unchanged. (a) In the `mode==1 && st==ST_DIAL` branch (our dial's
connect-complete — the stock moment event 3 would fire while the new device
is current): call `FUN_01e1782C(0x1C018 /*BTN addr scratch*/, 0, 0x1101)`
**before** restoring `_DAT_00010372` — exact stock SPP-open replay with a
deterministic target (no record-walk ambiguity); its internal guards make it
a harmless −1/−2 no-op if the SPP cb is missing or busy. (b) Reverse-order
guard at arm: if the sole inused conn record's `BD_ADDR@rec+0..5` equals the
BTN (`6F:E5:E7:FB:12:4F`), SKIP the dial (never re-dial a connected device —
same-address page guard `0x01E16824` freeze, ch. 31). Cave budget: JK-3 uses
150 B of the 295 B run; additions ≈ 60 B fit. No new hooks, no NOPs.
Verdict → §39.22 after the JK-4 field run (§39.21 = build record).

## §39.21 JK-4 BUILT — SPP session open at connect-complete + reverse-order guard (2026-11-21, UNTESTED at build time)

**Design** (`work/ch39/jk4_c.c`, body 218 B @`0x01EA7730`, cave 232 B
`0x01EA7722..0x01EA780A`): JK-3's classifier-store hook and state machine kept
verbatim, plus the two §39.20 fixes:

1. **SPP open at mode-1 ST_DIAL** — the §39.20 keying-dead fix. Before restoring
   `_DAT_00010372`, replay the stock event-3 SPP-session open:
   `FUN_01e1782C(0x1C018, 0, 0x1101)` (r0 = BTN BD_ADDR scratch, r1 = 0,
   r2 = 0x1101 class — the exact args of the stock caller path
   `FUN_01e17e62` event 3 @`0x01E17ED6` → `FUN_01e16878(1)` → `FUN_01e1782c` →
   `spp_connect` `FUN_01e1750C` → `FUN_01e1744C` 6-byte addr copy → dial
   executor `FUN_01e16F60`). The raw `USP(1,6,addr)` cmd-1 dial brings the ACL +
   name read only; without an rfcomm ch-2 session no `+SPP=P/R` frames flow and
   the ungated key injector `FUN_01e5b2f4` never runs. Ordering: the SPP open
   runs BEFORE the handle restore so the session target resolves while the app
   record still points at the joiner; the SPP control block `_DAT_0001a740`
   alloc/idle guards return −1/−2 harmlessly if busy (Jabra-first leaves it idle
   — Jabra is HFP, never SPP).
2. **Reverse-order guard at arm** — if the sole inused conn record's
   `BD_ADDR@rec+0..5` equals the BTN (`6F:E5:E7:FB:12:4F`), SKIP the arm+dial
   (button-first = stock passthrough; never re-dial a connected device,
   same-address page guard `0x01E16824` freeze, ch. 31).

**Gates (all green)**: body 218 B, zero relocs; objdump shows the SPP-open
sequence `c0 ff 18 c0 01 00` / `c3 ff 2c 78 e1 01` / `41 20` / `42 e0 01 11` /
`c3 00` in order before the handle restore; cave 232 B ends `0x01EA780A` ≤
`0x01EA7849`; upstream oracle (`pi32dis.py --off=0 --upstream=pi32v2-isa`) 0
`???`; `jl_sim` 14/14 — T1 arm+dial (slot 0, stop `0x01E1792E`
r0=1/r1=6/r2=0x1C018, `0xB464`=3, ST_DIAL, saved handle), T1b both-inuse no-arm,
T1c none-inuse no-arm, T1d/T1e reverse-guard slot0/slot1 (sole record == BTN →
state stays 0), T2 full-run executing the REAL `FUN_01e1782C`
(`_DAT_0001a740`=0 → −1 harmless) + restore + ST_DONE asserts, T2b stop
`0x01E1782C` arg check r0=0x1C018/r1=0/r2=0x1101, T3/T4 mode-1 passthroughs,
T5/T6 one-shot (no re-arm under ST_DIAL/ST_DONE), T7 slot-1 dial, T8/T9
mode-2/mode-6 store-only; patcher asserts (len 218/232, presence `124f` /
`2e79e101` / `2c78e101`, end ≤ `0x01EA7849`); `verify_actions.py` +
`verify_cli.py` 0 failures.

**Image** `work/ch39_jk4.bin` sha256 `5f3e3de9959552293a464bc3fadd70b88428616ea37b9a4f23dffed511fc7d3a`
= S1 (`work/ch32_bt_e7.bin` `d7a29a3e…`) + sectors `0x083000`+`0x0AC000` ONLY
(217 B changed); hook `81ea4345` @app `0x7EC98` and cave plaintext-verified via
`jl_sfcenc.py`; uboot `0x0000–0x4FFF` == `Dumps/dump_pre_ch30.bin`. Stage
`work/ch39_jk4.sh` (EXPECT_SHA `5f3e3de9…`, diff-assert n=217, PRECHECK passes
from JK-3 state) + card `work/ch39_jk4c.sh` (S4 decisive keying, S4a mic
source, S10 reverse guard) on disk, `bash -n` OK.

**Process lesson (recorded per directive)**: two earlier "JK-4 built" claims
silently shipped **stale JK-3 bytes** (136 B; shas `66415d78…`/`08908562…`) —
caught only by sha comparison. Rule reinforced: after EVERY build, re-verify
image sha AND plaintext cave bytes AND grep `.md` edits on disk before claiming
done.

## §39.22 JK-4 FIELD VERDICT: PARTIAL — BREAKTHROUGH #2, keying works; NEW wall = Jabra drops after first TX (2026-11-21, field + static root-cause)

**User report (verbatim)**: "Radio works great, TX works with good audio, but
after TX the jabra disconnects. Power on radio, connect jabra, audio was routed
through radio speaker and mic, connected the TID-PTT, after first TX the audio
was routed to TID-PTT and then the jabra disconnected."

**Reading**:

- **S4 keying = PASS with good audio — first time in the entire two-device
  effort.** The §39.20 SPP-open fix is CONFIRMED live: the auto-dial +
  `FUN_01e1782C` session open makes the TID-PTT button key the radio.
- No freezes anywhere; connect paths, pairing, menu all normal (R1 gate clean).
- **NEW WALL**: after the FIRST TX the audio re-routes to the TID-PTT and the
  Jabra then disconnects. This matches the stock single-audio-policy signature
  observed in §39.18 D3 — the app tears down the HFP device when the SPP device
  becomes the active audio path — so it is the underlying wall surfacing, not a
  JK-4 connect regression.

**Root cause (high confidence, static)**: the `0x3e` connect-complete sink
`FUN_01e5af40` (`disassembled/decompiled_all.c` ~89203) rewrites the **whole**
app device record `0x102F0` on every connect-complete: `b[0x102F0]=0`,
`h[0x10372]=0` first, then `b[0x102F0]=1`, `h[0x10372]=new handle`,
addr → `0x102F1..6`, clears `0x10314..0x10337`, name memcpy → `0x10302..`,
`b[0x103C4..]`, `b[0x10E00]=0x40`, calls `FUN_01e59f64`/`FUN_01e508b0`,
`0x10356/0x1035A`, `b[0x10E01]`, `b[0x10339]=0x64`. JK-4 restored ONLY
`h[0x10372]` → the record ends up **BTN-addr + Jabra-handle = inconsistent**;
on the first TX the stock single-audio policy resolves the mismatch by
following the button (addr says TID-PTT) and tearing the Jabra. The TX-start
fn `FUN_01e5b174` (~91025) posts cmd `0xb` ONLY when handle==0 (not the drop
mechanism); the key handler ~91125 swallows 0x2A/0x2B when
`FUN_01e5b174()==1`; `+SPP`/`AT+MPTT` RX injector `FUN_01e5b2f4` ungated and
clean.

**JK-5 DESIGN (locked)** — keep everything in JK-4, add record-consistency:

1. At ARM, capture the sole inused record's BD_ADDR (`rec+0..5`) → RAM
   `0x1C020` (u32) + `0x1C024` (u16).
2. At mode-1 ST_DIAL restore, AFTER `*hd = *sv`, also rewrite the record addr:
   `*(volatile u32*)0x102F1 = *(volatile u32*)0x1C020;`
   `*(volatile u16*)0x102F5 = *(volatile u16*)0x1C024;`
   → handle AND address both point at the Jabra again; the app's current-device
   is fully consistent and the single-audio policy has no mismatch to resolve.

Budget: 63 B headroom (cave ends `0x01EA780A`, limit `0x01EA7849`); additions
≈ 30–40 B fit. Known residual risk: the sink-written name/profile-state bytes
(`0x10302..`, `0x10314..0x10337`) stay the BTN's — if the Jabra still drops,
extend the restore window or accept the stock single-audio policy
(escalation: targeted suppress vs Route A accessory-side patch vs Route C
ESP32 combo). Build record → §39.23; field verdict → §39.24.

## §39.23 JK-5 BUILT — record-consistency restore (2026-11-21, UNTESTED)

**Design** (`work/ch39/jk5_c.c`, body 238 B @`0x01EA7730`, cave 252 B
`0x01EA7722..0x01EA781E`): JK-4's classifier-store hook and state machine kept
verbatim; the §39.22 fix adds **record consistency**:

1. **At ARM** (mode-3, after saving `_DAT_00010372`): capture the sole inused
   conn record's BD_ADDR (`rec+0..5`) → RAM `0x1C020` (u32) + `0x1C024` (u16).
2. **At mode-1 ST_DIAL restore**, AFTER `h[0x10372] = saved`: rewrite the app
   device-record address too — `*(u32*)0x102F1 = [0x1C020]`,
   `*(u16*)0x102F5 = [0x1C024]` — so handle AND address both point at the
   Jabra again; the stock single-audio policy has no BTN-addr/Jabra-handle
   mismatch left to resolve (§39.22 root cause: the `0x3e` sink
   `FUN_01e5af40` rewrites the WHOLE record `0x102F0` on every
   connect-complete). SPP open `FUN_01e1782C(0x1C018, 0, 0x1101)` still runs
   BEFORE the restores; state then `ST_DONE` (terminal one-shot).

Hook unchanged: classifier `FUN_01e7ec28` routing-byte store `0x01E7EC98`
(`52ee541d` → `81ea4345`); cave = 14 B preamble + body `jkc`; tbh `0x01E61270`
stock; no NOPs; reverse-order guard + exactly-one-inuse gate intact.

**Gates (all green)**: body 238 B, zero relocs; objdump order confirmed
(capture precedes ST_DIAL; SPP-open → handle restore → addr rewrite → ST_DONE);
upstream oracle on the 252 B preamble+body stream: 0 `???`, decode ends exactly
at byte 252; `jl_sim` **14/14** (`work/ch39/jk5_sim.sh`) — T1/T7 arm capture
asserts `0x1C020:11223344`/`0x1C024:5566`, T2 full-run executing the real
`FUN_01e1782C` + restore asserts `0x102F1:11223344`+`0x102F5:5566`+
`0x10372:0700`+ST_DONE, T2b SPP-call args, T1b–T1e/T3–T6/T8/T9 as JK-4.

**Patcher + legacy-window resolver fix**: the patcher carries the JK-5 bytes
(JK_BODY_BYTES 238 B byte-exact == `work/ch39/jk5_c.bin`, cave 252 B, asserts
fire on import). Growing the `jkcave` window 150→232→252 B had orphaned the
legacy payloads that sit at NONZERO offsets inside the run (R1/R1B @54,
CMD5T @134, PRESST @174, D1_THUNK @206, INCMODE3/INCHFP @212): no strict
state/ctx-variant matched → `find_app_start` RC=1 "could not locate a
recognised app region" → **25 `verify_actions` failures** (the JK-4-era suites
were silently stale — the 232 B window already broke them). Fix: a static
payload registry `_jk_reg` + dynamic overlap loop `_jk_ov` + `_jk_resolve(cur)`
(overlay composition with a final `base == cur` check) attached to `jkcave`
with a `legacy` label, and resolve-acceptance wired into `show()`,
`apply_patch()`, `find_app_start()` and `check_context()`. Result:
`verify_actions.py` AND `verify_cli.py` **0 failures, RC=0**.

**Image** `work/ch39_jk5.bin` sha256
`614e4e01cb7906f8cd5cc9c97dcbc6b317bdf77631f22404067f3326618e2d75` = S1
(`work/ch32_bt_e7.bin` `d7a29a3e…`) + sectors `0x083000` (4 B hook) + `0xAC000`
(233 B) = **237 B changed**, plaintext-verified (hook `81ea4345` @app
`0x7EC98`, cave == `JK_CAVE_BYTES` @app `0xA7722` via `jl_sfcenc.py
--key=0xF181`), uboot `0x0000–0x4FFF` == `Dumps/dump_pre_ch30.bin`. Stage
`work/ch39_jk5.sh` (EXPECT_SHA `614e4e01…`, raw-sector PRECHECK → passes from
the JK-4 state on the radio) + card `work/ch39_jk5c.sh` (decisive **S4b**:
Jabra stays connected through 3 consecutive TX with audio staying in the
Jabra) on disk, `bash -n` OK.

**Correction (silent-claim class)**: §39.21 recorded stage `work/ch39_jk4.sh`
as on disk — it never existed; the JK-5 stage script was cloned from
`work/ch39_jk3.sh` (card cloned from the existing `work/ch39_jk4c.sh`).

Radio still on JK-4 `5f3e3de9…` — flash JK-5 + run the card; verdict → §39.24.

**2026-11-21 update:** radio flashed and RUNNING JK-5 `614e4e01…` (boot OK, user
confirmed). CARD BUG found + fixed same day: `ask()` echoed its question to
stdout while being called as `a=$(ask …)` — command substitution captured the
Q/A text instead of letting it reach the screen, so the question never printed
and `a` (containing `"Q: …"`) never equalled `y` ⇒ the card instantly took the
S0 STOP branch ("boot broken") on a perfectly healthy radio. The identical
latent bug existed in the JK-4 card (never caught because JK-4's verdict came in
free-form chat, not via the card). Fix = Q/A visible echo via
`tee -a "$LOG" >&2` (answer alone still returned on stdout); smoke-tested
(piped answers flow S0→R1a→R1b and branch correctly; log file captures all
Q/A). Re-run `bash work/ch39_jk5c.sh` and answer the printed questions;
verdict → §39.24.

**Card mode change + first field data (2026-11-21, user directive "make the card
'record and continue'")**: `work/ch39_jk5c.sh` converted to record-and-continue —
all four early-exit gates (S0/R1a/R1b/S2) now print `NOTED — …` and the card runs
through to VERDICT, which lists `FAILED GATES:`. `bash -n` OK; piped smoke run
with a failing R1b reaches VERDICT with `FAILED GATES: R1b`; no `exit 0`/STOP
branches remain. **R1b observation on JK-5 (user verbatim)**: "I powered off the
Jabra. On the radio selecteded connect. Than directly I powered on the Jabra and
the connect timed out. Also repeatative connects wont work. Powercycling the
Jabra have it connect again (auto-join) but as long as the Connect... progress
screen show this does not work." Reading: the page was launched while the Jabra
was OFF → page timeout (stock controller behavior, ch. 27); while the
"Connect…" progress screen is up, repeat Connect presses are refused; the
Jabra's own power-cycle auto-join then lands fine. S0 = y (boot healthy),
R1a = y (auto-join + audio in headset). NOT yet a JK-5 regression call — the
decisive steps (S3 auto-dial, S4 keying, S4b Jabra survival) had not run;
full-card pass in progress, verdict → §39.24.
