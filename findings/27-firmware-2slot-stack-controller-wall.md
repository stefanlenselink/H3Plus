# Ch. 27 — Bluetooth 10: The firmware already has TWO conn slots — the wall is the controller

*2026-10-06, static analysis of `work/full.lst` + `disassembled/` against the SDK
bitcode IR (`/tmp/bts/*.ll`), plus a full re-decode of the round-2 hardware capture
`/tmp/spp_reject.hcd`.*

> **Headline: the planned `conn_info` widening surgery is unnecessary.** The IR
> files that produced the `[1 x conn_info]` conclusion ([§9B.11](22-bluetooth-7-multipoint-architecture.md#9b11--the-real-cap-the-stacks-connection-data-model-is-1-x-conn_info))
> describe the **public SDK default build**, not the vendor's build. Our firmware's
> host stack was compiled with a **2-slot `conn_info` array, 2 RFCOMM multiplexers,
> 6 RFCOMM services and 6 RFCOMM channels** — twice the SDK defaults across the
> board. The host layer is ready for two devices. The second-link teardown
> (`0x13`) is issued by the **prebuilt controller library**, not by the host stack
> and not by the app.

---

## §27.1 — How the mistake happened

The SDK `.o` files are LLVM bitcode; `llvm-dis` output in `/tmp/bts/*.ll` shows
`user_info_t = {user_cmd_ctrl, run_loop, [1 x conn_info], user_core_data_t, …}`
and `stack_bredr_pool_t = {… [1 x rfcomm_multiplexer_t], [3 x rfcomm_service_t],
[3 x rfcomm_channel_t]}` with a 600-byte pool. Those are the **stock library
configuration values**. TIDRADIO ships a **recompiled stack with widened pools** —
the array dimension in the IR is a compile-time constant of that reference build,
not a law of the format. Verifying against our own image (§27.2) was the fix.

## §27.2 — Our firmware's stack data model (verified in-image)

**bredr memory pool** — init sequence `0x01E18B92`–`0x01E18BDA`: `malloc(0x76C)`
(1900 B, wrapper `0x01E30F36`, `memset` `0x021127B4`), then pool-create
`0x01E18AC6(head, storage, count, block_size)`:

| pool | SDK default | **our image** | block |
|---|---:|---:|---:|
| `l2cap_service_t` | 4 | **18** | 16 B |
| `l2cap_channel_t` | 5 | **20** | 56 B |
| `rfcomm_multiplexer_t` | 1 | **2** | 20 B |
| `rfcomm_service_t` | 3 | **6** | 20 B |
| `rfcomm_channel_t` | 3 | **6** | 52 B |

Storage offsets inside the 1900 B block: `+0x14 / +0x134 / +0x594 / +0x5BC / +0x634`.
The SDK reference pool is 600 B (`ret i16 600` in the IR size function); our image
has no such function — the `0x01E34B50: r0=0x258; rts` hit is unrelated.

**`conn_info` array** — RAM base **`0x1A5B8`**, stride **`0x1C` (28 B)**, end
sentinel **`0x1A5F0`** ⇒ **2 slots**. Fields: `addr[6] @ +0`, HCI handle `i16 @ +6`,
`inused` = bit 29 (`0x20000000`) of the word at `+0xE`. Five iteration sites use
exactly these bounds (get-conn-for-addr `0x01E1682A` with a 6-byte compare,
`get_bt_current_conn` `0x01E16878`, `0x01E17CEE`, `0x01E20F58`, `0x01E2136E`), plus
the same loop shape throughout the decompilation tree (`decompiled_all.c` lines
25265, 25295, 27110, 35940, 36150, 36283, 36502, 36980). `__user_info` base is
implied at `0x1A53C` (`0x1A5B8 − 0x7C`).

The `hfp_con` (`[1 x]`, 1120 B) and `spp_conn` (`[1 x]`) profile structs are
**sufficient for the goal** (one HFP device + one SPP device): the target topology
needs exactly one of each.

## §27.3 — Correction to §9B.11

Claim 3 of §9B.11 ("`struct user_info_t` embeds `[1 x conn_info]` … the single-device
ceiling is entirely in the precompiled host stack") is **wrong for our firmware**.
It holds for every *public SDK* library build (bd29/br23/br25/br30/bd19/br34), but
the vendor's build embeds **2** slots (§27.2). Claims 1–2 (`is_1t2_connection`
semantics, `multi_bd.c` compiled empty) and claim 4 (controller built for 4 links)
stand. A correction note was added at §9B.11.

## §27.4 — Correction to §26.11: HCI Disconnect has many senders

§26.11 stated "opcode `0x406` (Disconnect) appears exactly once in the image".
**Wrong** — the literal appears at 13 sites; the real senders are:

| sender | reason | trigger |
|---|---|---|
| `0x01E074EE` (kick executor, inside `0x01E074DE`) | 19 (0x13) | app kick — **dead** under `--no-kick` |
| `0x01E07606` (L2CAP-side, caller `0x01E02FC0`) | 0x0F (Connection Timeout) | L2CAP layer timeout |
| `0x01E07B08(handle, reason)` wrapper, site `0x01E07B26` | param | see below |

Wrapper `0x01E07B08` callers: `0x01E178CE` (reason **0x13**), `0x01E1A100` and
`0x01E1A300` (reason 5, dispatcher region). The 0x13 path `0x01E178B2` = "find conn
by handle (via `0x01E17420` modes 0 and 2); if found, disconnect(handle, 0x13),
return 0; else return 1". Its callers are **action-driven only**:

* `0x01E17B2A` — "disconnect current device" (after `get_bt_current_conn(0)`),
* `0x01E21F2C` / `0x01E21F56` — the stack command dispatcher's **cmd 8 / cmd 10**
  (disconnect-by-address), posted from the app command table.

Nothing posts cmd 8/10 automatically when a second link arrives. The app-layer
handle gates at `0x102F0+0x82` (`0x01E4E2EC`, `0x01E502DA`, `0x01E5A5F2`,
`0x01E5AECE`) are all "if connected do X" patterns — no auto-reject.

## §27.5 — The round-2 capture, fully decoded

`/tmp/spp_reject.hcd` (btsnoop, PC adapter `90:DE:80:55:E3:A6`), decoded with
`btmon -r`:

1. **t=4.345 s** — PC `Create Connection` → radio `0B:FF:59:E8:85:92`
   (role switch: allow peripheral).
2. **t=4.989 s** — `Connect Complete` **status 0x13** (Remote User Terminated),
   handle 3 — **644 ms** after the page. There is no prior successful `Connect
   Complete` and no `Disconnect Complete`: the PC's link came up at the LL level
   and the **radio's controller sent `LL_Disconnect(0x13)`** before reporting the
   connection upward. A host-originated disconnect would normally surface as
   `Connect Complete` success + `Disconnect Complete`; the observed shape says the
   radio's controller never delivered the established link to its own host, or
   tore it down during establishment.
3. **t=16.0 s** — the TID-PTT (`6F:E5:E7:FB:12:4F`, class `0x240404`) pages the
   **PC** (BlueZ auto-connect; the §26.11 gotcha). Accepted; SDP query for
   Handsfree-Audio-Gateway returns an RFCOMM protocol descriptor on **channel 13**
   — the TID-PTT also advertises an HFP AG service. Side note, not part of the
   failure.

The `ECONNRESET` outcome quoted in §26.11 came from a different run (not in this
capture). Both outcomes share the same signature: the radio's controller (or the
RFCOMM layer refusing on the new handle) kills the second link; the host stack's
own policy code never asks for it.

## §27.6 — The radio's Connection Request handler: always accepts

Stack task event switch `FUN_01e19e44` (decompiled at `decompiled_all.c` ~29620),
case 4 = HCI Connection Request:

```c
case 4:
    bVar12 = param_1[0xb];          // link type
    if ((bVar12 | 2) == 2) {
        if (FUN_01e18ffa(1) != 0)   // veto hook — DEAD (ops slot never written)
            break;                  // (would ignore the request)
    }
    if (bVar12 == 0)      role = 1;             // SCO   -> accept
    else if (bVar12 == 2) FUN_01e086fe(addr);   // eSCO  -> Accept Sync (HCI 0x429)
    else if (bVar12 != 1) FUN_01e08726(addr);   // other -> REJECT, reason 0x0A
    else role = (DAT_0000c02b & 8) ? 0xAA : 1;  // ACL: role keep vs become-master
    FUN_01e086f2(addr, role);                   // ACCEPT (HCI 0x409)
```

HCI command helpers (all via `0x01E02C56`): `0x01E086F2` = Accept Connection
Request (opcode `0x409`), `0x01E086F2`'s sibling `0x01E08726` = Reject
(`0x40A`, reason `0x0A`), `0x01E086FE` = Accept Synchronous Connection (`0x429`).

**There is no "already connected" gate.** An incoming ACL is always accepted; the
role parameter is `1` (become master) unless config flag `DAT_0000c02b & 8` selects
`0xAA` (vendor "keep role"). Case 5 (Connection Complete) with status 0 only posts
a notification to the app (`FUN_01e19a78(4,10)`); case 6 (Disconnection Complete)
only cleans up. The host never disconnects a freshly accepted link.

`DAT_0000c02b` is a RAM config byte (no literal write site; initialized with the
stack config block around `0xBFxx`–`0xC0xx` at boot). It also gates four other
accept-path decisions in the same switch (`& 0xd`, `& 0xc` variants).

## §27.7 — Verdict: the wall is the prebuilt controller library

Chain of evidence:

1. The host stack **accepts** every incoming ACL (§27.6) and **can track two**
   (`conn_info[2]`, 2 RFCOMM muxes — §27.2).
2. The host's only 0x13 senders are **action-driven** app commands (§27.4); none
   fires on link establishment.
3. The capture shows the radio's **controller** terminating the link at LL level
   644 ms after the page, before its host reports the connection (§27.5).

⇒ The teardown originates **below the host stack**: in the JieLi BR/EDR controller
library (prebuilt, linked into the app image — the `btctrler.a` equivalent, the
code that consumes HCI commands and drives the baseband). The SDK reference
controller is built for 4 links (`bredr_table[4]`, §9B.11 claim 4), but the
vendor's controller build behaves as single-link — plausibly a scheduling/role
limit when an HFP/eSCO link is active.

**Consequences for the plan:**

* **Step 3 of the proposed surgery (widen `conn_info`) is unnecessary** — already
  2 slots.
* The "widen the data model" route collapses. What remains:
  (a) **controller-level experiments** (role parameter, config bytes) — cheap,
      testable by patch;
  (b) **live experiments** to characterize exactly when the controller refuses
      (§27.8) — the results decide everything else;
  (c) if the controller is hard-limited: vendor multipoint controller library,
      SDK rebuild, or the single-device combo workaround (unchanged).
* The decompile⇒compile route (Ch. 25) stays valuable: the controller region is
  now the target for Ghidra attention.

## §27.8 — Experiment matrix (hardware; user flashes)

All tests with the Option-A2 trio (`--conn-num=2 --no-kick --force-page-scan`)
plus one variable each. Capture with `btmon -w` on the PC. **Turn the PC adapter
off for radio-side pairing** (§26.11 gotcha) and re-pair the PTT to the radio.

| # | Setup | Action | Question answered |
|---|---|---|---|
| E1 | Radio idle, no headset | PC `bt_spp_hold` → radio | Trio harmless? Second-slot SPP works at all? |
| E2 | Headset connected, idle (no SCO) | PC pages radio | Reproduce `0x13` cleanly (baseline for E4) |
| E3 | PC (or PTT) link **first**, then connect headset from the radio UI | watch both links | Does the controller refuse only *incoming-while-connected*, or any 2nd link? |
| E4 | E2 + **role patch** `--force-role-keep`: accept the case-4 ACL with role `0xAA` (keep-role) instead of stock `1` (become master) | PC pages radio | Is the refusal a role-switch conflict? |
| E5 | Headset streaming SCO (mic live) | PC pages radio | Is eSCO scheduling the trigger? |

**E4 patch SHIPPED 2026-10-07** as `--force-role-keep`. The site is fully
located: the role test is `lb.z r0,[r9 + 0x107]` + `jmnz r0,#0x8,0x01e1a4c8`
at `0x01E1A03A` (r9 = `0xBF24` = `_stack_config` base, so the flag is RAM
`0xC02B`; the config blob @`0x01EC2064` initialises it to `0x00` → stock
runtime role = 1, become master). The patch replaces the pair with an
unconditional `goto 0x01E1A4C8` (the `mov r1,#0xaa` keep-role load) plus nops:
`50 ee 97 01 61 ff 08 00 42 02` → `c0 ea 45 02 00 00 00 00 00 00`. Only the
ACL path reaches the site — SCO (role 1), eSCO and reject branch away earlier,
and the register context at the jump is identical. `--show` reports both
states; both test suites green. E4 builds as
`--conn-num=2 --no-kick --force-page-scan --force-role-keep`.

**E4 build prepared 2026-10-07** — `work/e4_twodev.bin` (full 1 MiB, from
`Dumps/dump_internal.bin` with `--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT
--conn-num=2 --no-kick --force-page-scan --force-role-keep`; run with `python3`
on the Linux host — its plain `python` is 2.7). Validation: a from-scratch rebuild
of the A2 image (`--conn-num=2 --no-kick --force-page-scan`) reproduces all 10
`../jl-uboot-tool/multi-bt-ptt2_*.bin` sectors byte-for-byte (deterministic
pipeline), and the 2026-10-05 radio readback `Dumps/rb_060000.bin` (flash
`0x060000`) is byte-identical to the E4 build's `0x060000` sector — the SFC
round-trip to NOR is exact. All four multipoint patch bytes verified in the
decrypted image: `31 25` @file `0x182DC` (conn_num), `40 23 80 00` @`0x5B22A`
(kick-NOP), `00 00 00 00` @`0x18B0E` (page-scan NOP), `c0 ea 45 02 00 00 00 00 00 00`
@`0x1A03A` (role-keep). Consequence: the E4 delta vs the radio's current A2 content
is **exactly one 4 KiB sector — flash `0x01F000`** (file offset `0x1A000`, the
role-keep site; `work/e4_01F000.bin`, staged as `../jl-uboot-tool/e4_01F000.bin`).
Every other patch sector is byte-identical to what the radio already carries, so
writing that one sector upgrades A2 → E4 with zero touch on the VM region or the
device-specific bytes @`0x0C8FE0`. Pre-write sanity: `read 0x01F000 0x1000` from
the radio must match `Dumps/dump_internal.bin` @file `0x1A000` (the sector is
untouched stock); post-write `read` back and compare against `e4_01F000.bin`.

**E4 hardware result 2026-10-07: FAILED — the wall stands.** The flashed image
`../jl-uboot-tool/multi-bt-ptt4.bin` (user-built full image) is byte-identical to
`work/e4_twodev.bin` (verified with `cmp`), so the result belongs to this exact
build. Sequence: (1) radio idle → `bt_spp_hold` → OK (E1 passes on the E4 image —
second-slot SPP fine, role patch harmless); (2) headset paired from the radio UI
while the PC SPP was still held → radio reported **"BT disconnected"** and the PC
link dropped, headset then worked (a radio-initiated 2nd link kills the incumbent
*despite `--no-kick`* — a second eviction path beyond the NOPed kick, either the
app's disconnect-current wrapper `0x01E07B08` / dispatcher cmd 8/10 path or the
controller itself); (3) PC `bt_spp_hold` again while the headset holds HFP →
`ECONNRESET`; btmon shows Create Connection → Connect Complete **status 0x13,
handle 3, ~722 ms** after the page — the same LL-level signature as the A2
round-2 capture (~644 ms). The PC's page even offered
`Role switch: Allow peripheral (0x01)`, so stock role-1 was permitted too —
**the role parameter is conclusively not the trigger**; the controller refuses a
second incoming ACL regardless of role. Next: **E3 instrumented** — btmon running
the whole time, PC `bt_spp_hold` first and kept alive, then connect the headset
from the radio UI, and watch the PC's own link: does it get HCI-Disconnected
*before* the headset page even starts (app-level choice — patchable; hunt the
disconnect-current / dispatcher cmd 8/10 posters), or only when the headset link
would complete (controller-level one-link policy)? Note the PC's btmon cannot see
the radio↔headset link — it only shows the PC's own ACL events. E5 (SCO live)
after that if needed. Note: the user wrote the FULL image, so the VM region
rolled back to the 2026-09-15 dump state and all pairings reset (re-paired in
this session); for single-sector upgrades use the `--sectors` route.

## §27.9 — What this means for the goal

Goal: headset (HFP mic) + TID-PTT (SPP PTT) simultaneously. The host stack is
**already provisioned** for exactly this (2 conn slots, 2 RFCOMM muxes, one HFP +
one SPP profile instance each). The blocker is the controller's link policy. E1–E5
decide whether a small patch (role/config) can open it, or whether the remaining
routes are vendor-library/SDK-rebuild/combo-device.

## §27.10 — E3 RUN 2026-10-08: the incumbent-kill is APP-LEVEL — `--no-disconnect-13` (E6)

E3 was run on the flashed E4 image (`--conn-num=2 --no-kick --force-page-scan
--force-role-keep`): `btmon -w /tmp/e3_instrumented.hcd` for the whole session,
PC `tools/bt_spp_hold.py` holding SPP to the radio, then the headset (Jabra
Evolve 65, `74:5C:4B:E2:73:34`) joined from the radio UI. Decode tip: the
capture is btmon's mixed HCI+MGMT framing — plain `btmon -r file.hcd` (no
root needed on a world-readable file) decodes it; a raw btsnoop parser chokes.

**Evidence (rel timestamps, base 20:17:49.03):**

- rel 436.5 (20:25:05.9): PC Create Connection → radio, Connect Complete OK,
  handle 1; SPP up; PTT ops OK until 20:27.
- rel 451/470/537: three `Connect Request (0x04)` from the radio answered with
  `Reject Synchronous Connection Request, Limited Resources (0x0d)` — the radio
  attempting SCO to the PC (duplex RX audio) with no PipeWire SCO channel.
  Normal, not the failure.
- rel 613.2: PC inquiry sees the Jabra (coincidental background discovery).
- **rel 627.5–627.67 (20:28:16.7): graceful L2CAP Disconnection Request/
  Response (ident 22, RFCOMM CIDs 64/65), then `Disconnect Complete` Status
  Success, Handle 1, Reason Remote User Terminated (0x13); MGMT Device
  Disconnected reason 0x03 (terminated by remote host).** The radio's HOST
  stack deliberately closed RFCOMM/L2CAP and then HCI-Disconnected the ACL —
  **app-level, patchable**, not the raw LL teardown of §27.5.
- rel 674.4 (20:29:03.4): PC reconnect attempt → Connect Complete **0x13,
  handle 5, ~1028 ms** — the familiar controller signature, now with the
  headset holding the link; the headset stayed connected.

**Executor located (decompilation tree + disasm):** the reason-0x13 teardown
runs through the call at **`0x01E178CE`** inside `0x01E178B2` — find connection
(`0x01E17420` modes 0/2) then `disconnect(handle, 0x13)` via the wrapper
`0x01E07B08`. Its callers are every app-level "disconnect current device"
route: the BT API dispatcher `0x01E1792E` **case 0x4A** (callers: BT mode-set
`0x01E60188` and the BT task UI state machine `0x01E61E22` — the "connect
selected device" flow, which posts `0xc, 0xe, 0x12, 5, 0x4a` after copying the
"Connecting" string from `&DAT_01E9C7E0`), and the stack command dispatcher
`0x01E21AF8` **cases 8/10** (disconnect by address). The kick (cmd 5 →
`0x01E074DE`, also reason 0x13) is a separate executor already covered by
`--no-kick`; dispatcher case 4's reason-`0x16` call is a different site and was
not implicated.

**Patch (E6):** `--no-disconnect-13` NOPs the call at `0x01E178CE`
(`bf ea 1b 81` → `00 00 00 00`). The function then falls through to
`mov r0,r4` (r4 = 0) and returns "disconnected", so every caller behaves as if
the teardown succeeded. Side effects: menu disconnect / explicit disconnect
commands no longer release links (power-cycle instead), and app device state
diverges from link state — the app believes the incumbent is gone while the
ACL stays up. Both suites green (`verify_actions.py`, `verify_cli.py`).

**E6 build:** `work/e6_twodev.bin` = E4 recipe + `--no-disconnect-13`, built
from `Dumps/dump_internal.bin`. Diff vs the flashed E4 image: **exactly 4
bytes, all inside one sector** — flash `0x01C000`. All five multipoint patch
bytes verified in the decrypted app (`0x178CE: 00000000`, plus nokick/pagescan/
rolekeep/connum unchanged from E4). Flash route:

```bash
jl-uboot-tool erase 0x01C000 0x1000
jl-uboot-tool write 0x01C000 work/e6_01C000.bin
jl-uboot-tool read  0x01C000 0x1000 verify_01C000.bin   # cmp work/e6_01C000.bin
```

**E6 test (hardware):** with the PC holding SPP, join the headset from the
radio UI while btmon records. Outcomes: **(a)** PC link SURVIVES and the
headset connects → the app teardown was the whole eviction; then verify SPP
keys still actuate PTT and headset HFP audio works (the multipoint goal).
**(b)** PC link survives but the headset page fails (or dies at LL) → the
controller also refuses a radio-initiated OUTGOING second link → hard
controller wall; remaining routes: vendor multipoint controller lib, SDK
rebuild (ch. 25), or the single-device combo workaround (profile coexistence
proven, §9B.6.1). **(c)** PC link still dies → a third path (check for
reason-0x16 / dispatcher case 4, or controller-originated) — re-instrument.
E5 (SCO scheduling) stays secondary.

## §27.11 — E6 RUN 2026-10-08: **PASSED — the radio holds TWO links; multipoint works radio-initiated**

**Flashed:** `work/e6_01C000.bin` (the single 4 KiB sector, `erase/write/read`
above; readback matched). Pairings were re-established after a power cycle
(see timeline). Capture: `/tmp/e6.hcd` (btmon -w, decoded with `btmon -r`,
rel base **22:31:33.5**), plus `tools/bt_spp_hold.py` stdout (user terminal).

**Timeline (handle 6 = first PC ACL, handle 8 = second):**

| rel | wall | event |
|---|---|---|
| 27.02 | 22:32:00 | radio **pages the PC** (`Connect Request` from `0B:FF:59:E8:85:92`), PC accepts, PC = Central, handle 6 |
| 42.2 | 22:32:15 | L2CAP CID-64 teardown/re-setup dance (profile reconnect) |
| 93.29 | 22:33:06 | **handle 6 dies: Disconnect Complete reason `0x08` (Connection Timeout)** — this is the user power-cycling the radio (trouble connecting), NOT an eviction |
| 117.83 | 22:33:31 | radio (back up on E6) **pages the PC again** → handle 8; SPP up 22:33:31.570 |
| 130–146 | 22:33:43–58 | PC PTT `p`/`r` → clean `+SPP=P`/`+SPP=R` echoes, radio transmits |
| ~174 | ~22:34:2x | user joins the Jabra (74:5C:4B:E2:73:34) from the radio UI |
| 174.3–245 | 22:34:27–35:35 | **binary blobs arrive on the PC's SPP** (details below) — the PC link is **still up** |
| 197–229 | 22:34:50–22:35:22 | PC PTT still works (`+SPP=P/R` echoes, interleaved with blobs); user also presses radio PTT, PTT2 (both BT-PTT-mapped) and the normal PTT — all act as expected |
| 265 (end) | 22:35:58 | capture ends; radio switched off ~22:36. **No `Disconnect Complete` for handle 8 in the whole capture** — exactly one disconnect event total (the power-cycle `0x08` on handle 6) |

**Verdict — outcome (a): the E3 app-level teardown WAS the whole eviction.**
With `--no-disconnect-13`, a radio-initiated headset join does **not** kill the
incumbent PC link, and the radio's controller happily holds the PC ACL **while
it pages and brings up a second link to the headset** — the "controller wall"
of §27.5/§27.7 only ever applied to **incoming** second pages (E2/E4:
`Connect Complete 0x13` ~700 ms). Outgoing second links are fine. The full
E6 recipe `--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2 --no-kick
--force-page-scan --force-role-keep --no-disconnect-13` achieves concurrent
PC-SPP + headset multipoint, with SPP PTT keys working while both are up.

Also noteworthy: the radio **re-paged the PC on its own after reboot**
(rel 117.8) and accepted the Peripheral role — reconnect + `--force-page-scan`
behave as designed.

**Side effect observed — malformed squelch/AT notifications after the headset
joins.** From rel 174.3 (first join attempt) and continuously after the
headset became current, the PC's SPP socket receives short binary frames on
the **same L2CAP channel 65 / RFCOMM dlci 4**, but with the RFCOMM **`cr` bit
flipped** (`Address: 0x11 cr 0` vs the normal `0x13 cr 1` of `+SPP=P/R`):

- `09 04 XX 08 05 0d 03 01` / `...00` pairs (XX = a sequence counter, +3..+6
  per frame) arriving ~0.4–1.3 s apart, 01-then-00 — the same rhythm as the
  stock `AT+MPTT=1/0` RX-squelch notifications;
- `09 41 2b cb fe f5 41 09 2b 4d 50` containing literal `+MP` — an
  `AT+MPTT`-family payload, corrupted/interleaved.

Interpretation (hypothesis, mechanism UNCONFIRMED): once the headset is the
app's current device (single global struct `0x102F0`), the notification path
formats/routes through the headset's HFP-oriented state but the bytes still
land on the PC's SPP DLCI. The `+SPP=P/R` echo path is unaffected (it kept
working throughout). This is cosmetic for the PTT use case but is the first
static-analysis follow-up: trace the `AT+MPTT` writer and the `cr`-bit/RFCOMM
instance selection against `gp+0xC7`-style current-device state.

**Next:** (1) user is testing the TID-PTT button (6F:E5:E7:FB:12:4F) against
the E6 firmware — a third-device join while PC+headset are up; (2) verify
headset HFP audio/SCO actually works while the PC link is up (not yet
confirmed — user reported function, not audio path); (3) root-cause the
malformed-notification path above; (4) E5 (SCO scheduling) stays secondary.

## §27.12 — E6 field observations + the pairing kick is a THIRD executor (reason 0x16) — `--no-pairing-kick` (E7)

**User report 2026-10-08 (E6 firmware, three observations):**

1. *"When I pair the headset, after a broadcast using the BT-PTT button on
   the radio the mic output of the radio is being sent to the headset
   speakers — I never heard that before!"* — **this is the SCO downlink to
   the headset being live in the two-link state**: while TX-ing via BT-PTT
   the radio now streams to the HFP headset as an audio device, i.e. the
   HFP/SCO audio path engages while the PC's ACL coexists (§27.11 outcome
   (a) + first evidence of live audio in multipoint). Whether this is
   sidetone or the RX-audio router picking the headset as the current audio
   device is not yet traced — cosmetic either way, and a positive signal.
2. *"I can (still) not pair the TID-PTT and headset at the same time. Every
   time … I select it from the list and press connect, at that moment the
   radio disconnects the connection; or if I put the radio in pairing mode …
   when I press connect the other gets kicked."* — the **pairing /
   new-device flow** still evicts, even though §27.10/§27.11 killed the
   reason-`0x13` executor. Static analysis (below): the pairing path uses a
   **different, unpatched executor — HCI Disconnect with reason `0x16`**
   (Connection Terminated By Local Host … a *disconnect-all* variant in the
   stack's BT-task dispatcher).
3. *"When I power-cycle the radio, the last paired device is automatically
   connected again upon power on."* — expected: the app's single-device
   reconnect-on-boot flow (one tracked device in struct `0x102F0`); it
   reconnects whichever device was current. Not a multipoint feature, no
   patch needed (a multipoint boot-reconnect of *both* devices would be a
   follow-up experiment).

**Locating the pairing kick (2026-10-08/09, decompilation tree).** All
disconnect executors funnel into the wrapper `0x01E07B08(handle, reason)`
(push `{rets,r9..r4}`; `mov r4_r5,r0_r1`; …). Its callers, complete list:

| Caller | Reason | Path | Status |
|---|---|---|---|
| `0x01E178CE` | `0x13` | app disconnect-current (dispatcher `0x01E1792E` case `0x4A`) + stack cmd 8/10 | NOP'd by `--no-disconnect-13` (E6) |
| `0x01E1A100` | 5 | ACL-layer teardown (explicit) | untouched |
| `0x01E1A300` | 5 | ACL-layer teardown (explicit) | untouched |
| `0x01E21DE4` | **`0x16`** | **disconnect-ALL loop** in stack BT-task dispatcher `FUN_01e21af8` (`0x01E21AF8`) | **the pairing kick — now `--no-pairing-kick`** |
| `0x01E21EC4` | **`0x16`** | single `disconnect(handle-from-message+6, 0x16)` in the same dispatcher | **companion — same option** |

Both `0x16` sites call through thunk `0x01E19492` — a bare
`ff ea 39 73 goto 0x01e07b08` (the wrapper again). Three other thunk callers
(`0x01E19AD0`, `0x01E19B14` in the HCI-event handler `FUN_01e19a78`;
`0x01E20AB2` in the profile state machine `FUN_01e20962`) are
connection-cleanup paths with reasons 0x13/variable and are deliberately
NOT touched — they free slots for links that already died.

The disconnect-ALL loop at `0x01E21DE4` iterates the 2-slot conn array
(`0x1A5B8`–`0x1A5F0`, stride `0x1C`): test in-used bit 29 (`and r0,r8,
#0x20000000`), load handle (`lh.z r0,[r6]`), skip if zero, `mov r1,#0x16`,
`call 0x01e19492`, set was-connected flag, loop. The dispatcher's message
that lands here is the stack-level "prepare for new pairing/connection"
command (the poster is a callback-registered path — pointer at file
`0x018CBE`; not fully traced, patch is empirical). **This is why
already-paired joins work (§27.11) but entering pairing mode / connecting a
never-paired device still clears the field**: different command, different
reason byte. (Note: `disassembled/full.lst` has linear-sweep drift in the
`0x01E19`/`0x01E21` regions — trust `disassembled/disasm/*.asm`.)

**`--no-pairing-kick` shipped (E7).** NOPs both `0x16` calls (`bfea55bb` /
`bfeae5ba` → `00 00 00 00`, 8 bytes total): the disconnect-all loop keeps
walking and the scan reset still runs, but no link is torn down; the single
site falls through to its return. Both suites green (`verify_actions.py`,
`verify_cli.py`, 0 failures each, incl. an E7 combo check that all **seven**
multipoint patches land).

**E7 build 2026-10-09:** `work/e7_twodev.bin` =
`--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2 --no-kick
--force-page-scan --force-role-keep --no-disconnect-13 --no-pairing-kick`.
Diff vs the flashed E6 image: **exactly 8 bytes, all in sector
`0x026000`** (file `0x26DE4`–`0x26DE7`, `0x26EC4`–`0x26EC7`); the other 12
sectors are byte-identical. All seven patch sites re-verified in the
decrypted image. Flash (one sector, pairings survive):

```bash
jl-uboot-tool erase 0x026000 0x1000
jl-uboot-tool write 0x026000 work/e7_026000.bin
jl-uboot-tool read 0x026000 0x1000 verify_026000.bin   # cmp with work/e7_026000.bin
```

**E7 hardware test → RUN 2026-10-09, FAILED for the accessory-incumbent case (§27.13):** the
Paired→Connect kick still fires when the incumbent is the TID-PTT accessory — that flow uses
an as-yet-unlocated, class-dependent executor, not these `0x16` sites. The pairing-mode flow
these NOPs target could not even be reached while connected (Pairable is gated while a device
is connected — §27.13 obs. 1). `--no-pairing-kick` therefore remains **UNTESTED for its own
target flow**; multipoint stays confirmed only with a PC-class incumbent.
Realistic pass condition: **pairing a second device while the incumbent is
connected no longer drops the incumbent**, then connect the two paired
devices as in §27.11. Side effects: any UI action that "prepares pairing"
no longer releases links — power-cycle to clear stale links; explicit
menu-disconnect on those two paths is dead (same class of side effect as
`--no-disconnect-13`).

## §27.13 — E7 FIELD TEST 2026-10-09: **FAILED — the kick survives, but ONLY with an accessory incumbent** (+ Pairable gating, Delete weirdness, SCO-stays-open)

The user flashed sector `0x026000` (`work/e7_026000.bin`) and retested. Result, verbatim:
*"E7 did not work. As soon as I press Ok when the menu selects the Connect line I hear bluetooth
disconnected, than I see Connecting... on the screen and a few seconds later I hear bluetooth
connected."* Scenario: TID-PTT button (accessory) was the connected incumbent; menu
**Bluetooth → BT Pairing → Paired → Jabra → MORE → [2]Connect → OK**. At the OK press the
TID-PTT's LED started blinking (it lost the link and re-entered pairing/search), the radio
announced *Bluetooth Disconnected*, displayed `Connecting…`, the Jabra **never came up**, and
seconds later the TID-PTT auto-reconnected (radio announced *Bluetooth Connected*).

**The critical contrast with §27.11:** the *same* Paired→Connect flow with the **PC** as
incumbent did **not** evict it (E6 PASSED, both links up, SPP keyed with both devices).
Every executor we have located and NOP'd (kick `0x01E5B22A`, `disconnect(...,0x13)`
`0x01E178CE`, reason-`0x16` pair-kick `0x01E21DE4`/`0x01E21EC4`) is bypassed for the PC
incumbent — yet an **accessory incumbent still dies**. The surviving kick is therefore
**device-class-dependent** (classifier modes, ch. 12: TID-PTT = accessory vs PC ≈ phone vs
Jabra = headset) and runs through an executor we have **not yet located**. The Jabra join
then failing (and falling back to the TID-PTT) may be a knock-on (pairing-prep state) or
environmental — undetermined.

Static follow-ups this round (all negative — narrows the search):
`0x01E20AB2` (in `FUN_01e20962`, profile state machine, reason `0x13` via thunk `0x01E19492`)
is a **conditional profile-record teardown**, not the menu path; the explicit if-chain codes
`0x58`/`0x6d`/`0x20` in app dispatcher `0x01E1792E` are getters/config writes; the jumptable
codes remain undecoded (Ghidra reconstruction unreliable there). Candidates left: a
class-specific branch in the BT-task UI (`FUN_01e60e44` family) posting a different teardown
for accessories, or a direct `user_send_cmd_prepare` HCI-Disconnect we have not enumerated.
**Readback of `0x026000` is still pending** — rule out the flash before deeper RE
(`jl-uboot-tool read 0x026000 0x1000 rb_026000.bin` + `cmp` with `work/e7_026000.bin`).

**Next tests (discriminate the hypotheses; btmon on the PC):**
- **V2a (regression):** PC incumbent (`bt_spp_hold`), Paired→**Jabra**→Connect. Expect NO kick
  (E6 behavior). If the PC now dies, the E7 write broke something or wasn't applied → readback.
- **V2b (accessory TARGET):** PC incumbent, Paired→**TID-PTT**→Connect. If the PC is kicked,
  the reason code pins the executor: `0x16` → pairkick sites ineffective; `0x13` → an
  un-NOP'd 0x13 site (e.g. `0x01E19B14`); `0x05` → ACL-reject path; **no HCI event at all** →
  the radio never dropped the PC and only the accessory link died (incumbent-class-dependent).
- Accessory-incumbent + btmon is not directly observable from the PC (the radio↔TID-PTT link
  is off-air from the PC's perspective) — V2b is the proxy.

**Side observations (same report, all real and reproducible):**
1. **Pairable is gated while connected.** *Bluetooth → BT Pairing → Pairable* goes
   `Searching…` and lists devices **only when nothing is connected**; with the headset up, a
   TID-PTT in pairing mode never appears and the screen jumps back. App-level gate —
   consistent with the scan policy of §26.9 (our `--force-page-scan` keeps the radio
   *connectable*, but inquiry-window/pairing UX still assumes the single-device model).
2. **Delete leaves the link up and wedges pairing.** Deleting the Jabra from the Paired list
   (MORE → Delete) produced *no* disconnect announcement — the link stayed up (our NOPs kill
   the disconnect side, an **expected side effect** of `--no-disconnect-13`/`--no-pairing-kick`)
   — and Pairing then wedged (`Searching…` → back to menu) until the headset was powered off
   (radio then announced *Bluetooth Disconnected*). After a power-cycle, the TID-PTT was
   temporarily invisible in Pairable searches (still in the Paired list; connectable from it)
   while the headset in pairing mode showed up fine; after cycling pairing mode a few times
   the TID-PTT appeared again. Diagnosis: app pairing state machine confused by
   record-deleted-but-link-alive (expected class of side effect); the transient
   not-found-while-inquiry is likely page/inquiry scan contention under `--force-page-scan`
   (UNCONFIRMED).
3. **SCO stays open after BT-PTT release (mic sidetone to the headset).** Fresh connection =
   clean (no mic audio on the headset). After the **first** BT-PTT press-and-release, radio
   mic audio keeps coming out of the headset speakers continuously; pressing BT-PTT silences
   the radio mic and switches to the **headset mic** (BT-PTT working exactly as designed),
   releasing returns to radio-mic audio. Key clicks and menu ticks are audible in that
   downlink too. So in the 2-link state the SCO/eSCO uplink is **never torn down** after TX
   release (or the vendor keeps it open for the accessory-audio path) — the "mic audio on
   headset speakers" of §27.12 is this sidetone, now characterized. During-press headset-mic
   capture = **first end-to-end confirmation of HFP audio in multipoint**.

**E7 verdict:** `--no-pairing-kick` did **not** fix the user's flow — that flow
(Paired→Connect with an accessory incumbent) is driven by an as-yet-**unlocated,
class-dependent executor**, and the pairing-mode flow it *was* aimed at can't even be reached
while connected (observation 1). Status of the option: **UNTESTED for its own target flow /
field-FAILED for the accessory-incumbent case.** Multipoint (E6, §27.11) remains confirmed
**only with a PC-class incumbent**.

> **2026-10-19 update (V2b, §27.14; class interpretation superseded by §27.15):** the
> surviving kick is now **proven on the TARGET
> side** — with the PC as incumbent, Paired→**TID-PTT**→Connect evicted the **PC** with a
> graceful `0x13` teardown. The trigger is the accessory being *involved* in the connect,
> not the incumbent's class. The `0x026000` readback came back **clean** (not a flash issue).
> **§27.15 correction:** the E8 capture showed **no class check exists at all** — the
> eviction is the **unconditional `0x4a` L2CAP channel-close** in the Paired→Connect flow.
> The class appearance is a flow artifact (fresh-pairing posts no `0x4a`; PC bluetoothd
> keeps the ACL when only a channel closes; the SPP-only accessory drops its ACL instantly).

## §27.14 — V2b RUN 2026-10-19: kick **TARGET-side proven** (accessory as connect target) — `--no-cleanup-kick` (E8)

**Flash ruled out first.** The user read back sector `0x026000`
(`jl-uboot-tool read 0x026000 0x1000 rb_026000.bin` + `cmp` vs `work/e7_026000.bin`) →
**clean**: the E7 pairing-kick NOPs really are in the radio. The §27.13 kick is not a
flash artifact.

**V2b run** (PC as observable incumbent): `sudo btmon -w /tmp/e7v.hcd` +
`sudo python3 tools/bt_spp_hold.py 0B:FF:59:E8:85:92` (SPP up 09:00:01), then on the radio:
**Bluetooth → BT Pairing → Paired → TID-PTT → MORE → Connect**. The **PC** was evicted.
Capture (`btmon -r`, 443 lines):

| rel (s) | event |
|---|---|
| 40.673 | `> ACL RX` **L2CAP Disconnection Request** ident 11, CID 64→64 — **from the radio** (graceful RFCOMM teardown) |
| 41.024 | `> HCI Event: Disconnect Complete` handle 1, **reason 0x13** (Remote User Terminated) |
| 41.03 | MGMT Device Disconnected, reason 0x03 (terminated by remote host) |
| ~47 | second `bt_spp_hold` attempt → `ECONNRESET` (radio mid-`Connecting…`) — expected |

**Verdict.** The kick fires when the **TID-PTT accessory is the connect TARGET** (PC
incumbent dies), and §27.13 showed it also fires when the accessory is the **incumbent**.
The common factor is the **accessory being involved in the connect flow**, and the eviction
is the same **app-level graceful teardown** as E3 (§27.10): L2CAP first, then HCI
Disconnect **reason `0x13`** — through the wrapper `0x01E07B08` but **not** through the
NOP'd `0x01E178CE` (sector `0x01C000` verified when E6 was flashed; `0x026000` now).
**Corrected by §27.15:** the E8 run showed the L2CAP close fires **unconditionally** in the
connect flow (no class check anywhere on the path); the class-dependence was a flow artifact
(fresh-pairing vs Paired-list) plus SPP-only accessories dropping their ACL when their
channel closes.

**Executor funnel — the complete remaining candidate set.** All callers of wrapper
`0x01E07B08` (direct + via thunk `0x01E19492`, which is a bare `goto 0x01E07B08`):

| site | reason | context | status |
|---|---|---|---|
| `0x01E178CE` | `0x13` | app BT-API dispatcher `0x4A` / cmd 8/10 (FUN_01e178b2) | **NOP'd** (`--no-disconnect-13`) |
| `0x01E1A100`, `0x01E1A300` | `0x5` | ACL setup-fail/reject paths (FUN_01e19e44) | excluded (wrong reason) |
| `0x01E21DE4`, `0x01E21EC4` | `0x16` | stack dispatcher pairing kick | **NOP'd** (`--no-pairing-kick`) |
| `0x01E19AD0` | **variable** (from message) | stack event handler `FUN_01e19a78` (forwarded events from the HCI pump `FUN_01e19e44`), jumptable case `disconnect(handle, msg[2])` | **NOP'd (E8)** |
| `0x01E19B14` | `0x13` | same handler, subtype `0x73`: disconnect any handle not tracked state-1 (**orphan-ACL cleanup**) | **NOP'd (E8)** |
| `0x01E20AB2` | `0x13` | **profile-record cleanup** `FUN_01e20962` (BT-task callback registered at file `0x018C90`): disconnect(record.handle, 0x13) for profile types `&2`/`==0x40`, then clears the record | **NOP'd (E8)** |

A `0x13` graceful teardown can therefore only come from the last three sites — **E8 NOPs all
three** (`--no-cleanup-kick`, 12 bytes: `bfeadffc`/`bfeabdfc`/`bfeaeec4` → `00000000`; the
surrounding cleanup bookkeeping still runs, only the HCI disconnect call is removed).

**E8 build** (from `Dumps/dump_internal.bin`):

```bash
python3 tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin work/e8_twodev.bin \
    --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2 --no-kick \
    --force-page-scan --force-role-keep --no-disconnect-13 --no-pairing-kick \
    --no-cleanup-kick --sectors=work/e8
```

Diff vs the flashed E7 image = **exactly 12 bytes** (file `0x1EAD0-3`, `0x1EB14-7`,
`0x25AB2-5`) → **two sectors**: flash `0x1E000` + `0x25000`; all 13 other sector files
byte-identical to E7's. All **ten** patch sites verified in the decrypted image; both test
suites green (`verify_actions.py` / `verify_cli.py`, 0 failures — E8 combo carries all ten).
Pairings survive (no VM touch). Flash:

```bash
jl-uboot-tool erase 0x01E000 0x1000 && jl-uboot-tool write 0x01E000 work/e8_01E000.bin
jl-uboot-tool erase 0x025000 0x1000 && jl-uboot-tool write 0x025000 work/e8_025000.bin
jl-uboot-tool read 0x01E000 0x1000 verify_01E000.bin   # cmp work/e8_01E000.bin verify_01E000.bin
jl-uboot-tool read 0x025000 0x1000 verify_025000.bin   # cmp work/e8_025000.bin verify_025000.bin
```

**E8 hardware test — RUN 2026-10-19: PARTIAL SUCCESS (see §27.15).**
- T1 was run: the PC was **still evicted** — but the capture shows the radio **no longer
  sends any HCI Disconnect** (the E8 NOPs worked; the PC's own bluetoothd dropped the ACL
  locally, reason 0x16/0x02, after the radio closed only the RFCOMM channel). The surviving
  closer is the app's **L2CAP channel-close** (`user_send_cmd_prepare(0x4a)` =
  `l2cap_disconnect_all_channel`), one protocol layer above every NOP so far.
- The old **E9 = wrapper-entry early-return** plan is **moot** (no radio HCI Disconnect
  happens on this path anymore). E9 shipped instead as `--no-l2cap-teardown` — §27.15.
- T2 (TID-PTT incumbent + Jabra Connect) and T1 on the E9 image remain to run.

**Side effects:** the orphan-ACL and profile-record cleanup paths no longer release links —
stale handles may linger until power-cycle; explicit disconnect commands on those paths are
dead (same class of side effect as the existing NOPs).

## §27.15 — E8 RUN 2026-10-19: **PARTIAL SUCCESS — the HCI kick is dead; the closer is an L2CAP channel-close** (`--no-l2cap-teardown`, E9)

**E8 flashed clean** (both sectors `0x01E000`/`0x025000` read back and `cmp`-verified) and the
test **changed the behaviour exactly as designed — but the PC link still died.** Field report:
PC SPP connected (12:43:54), PTT OK, then **Paired→TID-PTT→Connect** → `SPP link is dead`
(12:44:25); reconnect attempt → `ECONNRESET` (radio mid-`Connecting…`). Capture
`/tmp/e8.hcd` (`btmon -r`, 765 lines):

| rel (s) | event |
|---|---|
| 29.483 | `> ACL RX` **L2CAP Disconnection Request** ident 17, **DCID 64 → SCID 67** on handle 4 — **from the radio** (RFCOMM well-known channel closed) |
| 31.540 | `< HCI Command: Disconnect` — issued by the **PC's own bluetoothd** (reason 0x13 param), i.e. the host gave up on the channel-less link |
| 31.625 | `> HCI Event: Disconnect Complete` reason **0x16 (local host)**; MGMT Device Disconnected reason **0x02 "terminated by local host"** |
| ~42.7 | PC reconnect attempt → Connect Complete **0x13** handle 7 ~800 ms — radio busy mid-page-to-TID-PTT |

**Verdict: the HCI-level eviction is FULLY DEAD.** In E3/V2b the radio itself sent the HCI
Disconnect (MGMT 0x03 remote host). In E8 **the radio sent no HCI Disconnect at all** — the
E8 NOPs worked. The surviving eviction is **one protocol layer up**: the radio's stack closes
the incumbent's **RFCOMM/L2CAP channel** when a new connect starts, and the PC's bluetoothd
then drops the now-useless ACL itself.

**The closer (static analysis, ~90%):** `user_send_cmd_prepare(0x4a)`. Dispatcher
`0x01E1792E` branches at `0x01E17974` (`je r11,#0x4a,0x01e17b20`) to the body at
`0x01E17B20` = **`l2cap_disconnect_all_channel()` inlined**: after a conn query
(`FUN_01e16878(0)`) and the already-NOP'd HCI disconnect call (`FUN_01e178b2`, E6) it loops
≤100× over the channel list `[[0x1A4E0]]+8`: skip states {1,9}, force each channel's state
byte to `0xd`, pump `l2cap_run` (`FUN_01e16f60`) — which for state `0xd` does
`l2cap_next_sig_id()` + `l2cap_send_signaling_packet(handle, code 6, id, remote_cid,
local_cid)` = **the L2CAP Disconnect Request in the capture, field-for-field** (ident 17,
DCID 64, SCID 67). Synchronous at button-press; pure L2CAP — which is why every E6/E7/E8 NOP
(HCI-level) left it untouched.

**Only two `0x4a` posters exist** (census of all 67 dispatcher call sites; zero
pointer-table refs):

- `0x01E61E22` — `FUN_01e60e44` "connect selected device" UI handler
  (**Paired→Connect**). **Unconditional.**
- `0x01E60188` — `FUN_01e60120` routing-mode setter; posts `0x4a` only when the routing
  mode *changes* while a link is active.

**Class-dependence reinterpreted (corrects §27.13/§27.14).** There is **no device-class
check** on this path. E6's "clean" Jabra join went through the **fresh-pairing flow**, which
posts no `0x4a`; the E7 "PC incumbent clean" claim was never btmon-verified. And when only a
channel closes, **PC bluetoothd keeps the ACL up** (the link looked healthy at UI level),
while the **TID-PTT is SPP-only** — it drops its ACL the instant its RFCOMM channel closes,
which is what made the kick look instant and class-dependent.

**E9 = `--no-l2cap-teardown`** — NOP both `0x4a` posters:

| site | stock | patch | note |
|---|---|---|---|
| `0x01E61E22` | `bdea84ad` | `00000000` | `nop;nop` — fall-through safe (next insn reloads `r0`); the connect-pending bit and the `0xc/0xe/0x12/5` posts remain, so the outgoing page still happens |
| `0x01E60188` | `bdead1bb` | `00000000` | covers the mode-change close after link-up |

8 bytes, **two new flash sectors `0x065000` + `0x066000`** (diff vs E8 = exactly 8 bytes; the
other 15 sector files byte-identical); all twelve patch sites verified in the decrypted
image; both test suites green (`E9 combo carries all twelve multipoint patches`). Build:

```bash
python3 tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin work/e9_twodev.bin \
    --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2 --no-kick \
    --force-page-scan --force-role-keep --no-disconnect-13 --no-pairing-kick \
    --no-cleanup-kick --no-l2cap-teardown --sectors=work/e9
```

Flash (pairings survive — no VM touch):

```bash
jl-uboot-tool erase 0x065000 0x1000 && jl-uboot-tool write 0x065000 work/e9_065000.bin
jl-uboot-tool erase 0x066000 0x1000 && jl-uboot-tool write 0x066000 work/e9_066000.bin
jl-uboot-tool read 0x065000 0x1000 verify_065000.bin   # cmp work/e9_065000.bin verify_065000.bin
jl-uboot-tool read 0x066000 0x1000 verify_066000.bin   # cmp work/e9_066000.bin verify_066000.bin
```

**E9 hardware test — RUN 2026-10-20: FAILED (the close persisted; root cause in §27.16):**
- **T1** — repeat V2b under `sudo btmon -w /tmp/e9.hcd`: PC incumbent
  (`sudo python3 tools/bt_spp_hold.py 0B:FF:59:E8:85:92`), then
  Paired→TID-PTT→Connect. Expect **no L2CAP Disconnection Request** and the PC link
  **alive**. Then watch whether the TID-PTT SPP actually binds: the app models **one SPP
  session** (SPP control block `0x1A740`, device struct `0x102F0`) — a second same-profile
  session is untested and is the **candidate next wall** (E6 proved a second
  *different*-profile HFP link coexists fine).
- **T2** — the original §27.13 scenario: TID-PTT incumbent + Paired→Jabra→Connect.
- If the close persists → **E10** falsification: NOP the dispatcher branch itself
  `0x01E17974` (stock `0bf8d494`, flash `0x1C974`, sector `0x1C000` — the `0x4a` body
  provably sends nothing else), and if that still misses, the scan task (`0x01E184xx`
  cluster reacting to the connect-pending bit `[0x1A520+0x142]` bit 7, set @`0x01E61DEA`)
  and the stack's single-RFCOMM-multiplexer behaviour on outgoing pages are the remaining
  suspects.

**Side effects:** the app never tears down L2CAP/RFCOMM channels on these flows — stale
channels persist until power-cycle (the E6 malformed-`AT+MPTT` side effect remains); the
100×3 ms settle loop before paging is lost (page starts marginally earlier; low risk).

## §27.16 — E9 RUN 2026-10-20: **FAILED — the 0x4a posters were co-actors; the closer is `spp_channel_disconnect()`** (`--no-spp-close`, E10)

**E9 field result — FAILED.** Both new sectors (`0x065000`, `0x066000`) flashed and
readback-`cmp` clean; all twelve prior sites verified in the decrypted image. Test
(`sudo btmon -w /tmp/e9.hcd` + `sudo python3 tools/bt_spp_hold.py 0B:FF:59:E8:85:92`):
SPP connected 00:42:49, two successful PTT cycles, then Paired→TID-PTT→Connect →
'SPP link is dead' at 00:43:39; reconnect `ECONNRESET`. User: *"still I heared bluetooth
disconnected directly after pressing the connect on the radio"*.

**Capture decode** (`/tmp/opencode/e9_btmon.txt`): rel 39.632 the radio again sends an
**L2CAP Disconnection Request (ident 20, DCID 64, SCID 69, handle 10)** — the same
signature as E8; the PC's own bluetoothd then issues the ACL teardown (rel 43.676,
Disconnect Complete 0x16, MGMT 0x02 *local host*). The radio still sends **no HCI
Disconnect** (E8's HCI-level victory holds). The closing channel is **confirmed SPP**:
the capture earlier shows RFCOMM UIH DLCI 4 carrying `+SPP=P`/`+SPP=R` on SCID 69.
NOP-ing the two `0x4a` posters changed nothing → the poster census was not the press-time
path (or not the only one).

**Root cause (high confidence; subagent re-census).** The close funnels through
**`FUN_01E173EC` = `spp_channel_disconnect()`** — read the SPP control block RAM
`0x1A740`, take the live L2CAP CID at `[cb+2]`, call `FUN_01E173D0` =
`l2cap_disconnect(cid)` (channel-by-CID via ROM `0x01e16938`; skip states {1,9}; force
state `0xd`; pump `l2cap_run` `FUN_01e16f60` → **L2CAP Disconnect Request**). Two
press-time routes reach it:

1. **The single-SPP-session chokepoint:** the connect state machine calls
   `FUN_01e1750c` (`spp_connect`); if `[cb+2]` is BUSY (the incumbent PC holds the SPP
   channel) it calls `FUN_01e173ec` at **`0x01E1751E`** — *close the incumbent, return
   −2, retry* — before paging the new device.
2. **The `0xB` (`DISCONN_SDP_MASTER`) path:** posts at `0x01E20BD2`/`0x01E20E92` →
   consumer `FUN_01e21af8` case `0xB` @`0x01E21F5C` → `FUN_01e1782c(0, mode 1, 0)` →
   call @`0x01E1786C` `FUN_01e173ec`.

Census facts: `l2cap_run` has 12 call sites (`0x01E173E6`/`0x01E17506`/`0x01E17B60`/
`0x01E194CE`/`0x01E19994`/`0x01E19C04`/`0x01E19C90`/`0x01E1A750`/`0x01E1A75A`/
`0x01E1B68A`/`0x01E1B69E`/`0x01E229E6`); `findva 0x01E17B20` (the `0x4a` body) = **0
pointer hits** — the E8 attribution to `0x4a` was a **co-actor** (its body pumps the same
`l2cap_run`), not the sole cause. **This finally explains everything as PROFILE- not
class-dependence:** an SPP target (TID-PTT) runs `spp_connect` → incumbent SPP channel
closed; an HFP target (Jabra, E6) never touches the SPP site → no close.

**E10 patch — `--no-spp-close`** (one 4-byte entry no-op kills every
`spp_channel_disconnect()` route, both press-time paths included):

| VA | stock | patch | meaning |
|---|---|---|---|
| `0x01E173EE` | `c0 ff 40 a7` | `40 20 00 04` | `mov r0,#0; pop pc` → return 0, close nothing (`push rets` @`0x01E173EC` intact; next 4 bytes `01 00 00 60` become dead) |

File `0x173EE` → flash `0x1C3EE` → sector **`0x01C000`** (already-flashed E6 sector —
the E10 upgrade is **ONE sector write**). Callers tolerate the 0 return (`spp_connect`
busy-path just retries; return ignored @`0x01E20F16`); the outgoing page and the pairing
flow are untouched. Side effects: stale SPP sessions until power-cycle. **Next wall after
E10:** the single SPP session itself (`0x1A740`) — the TID-PTT's SPP may not bind while
the PC's holds the CID (expected roadmap item, not a regression).

**Built 2026-10-20:** `work/e10_twodev.bin` + 17 sector files; diff vs E9 = **exactly 4
bytes** (`0x1C3EE`–`0x1C3F1`), only `work/e10_01C000.bin` differs; all **thirteen** patch
sites verified in the decrypted image; both suites green (`E10 combo carries all thirteen
multipoint patches`). Flash (pairings survive):

```bash
jl-uboot-tool erase 0x01C000 0x1000
jl-uboot-tool write 0x01C000 work/e10_01C000.bin
jl-uboot-tool read 0x01C000 0x1000 verify_01C000.bin   # cmp vs work/e10_01C000.bin
```

**E10 hardware test (2026-10-20): FAILED — the close persists** (see §27.17). Flashed
cmp-clean (sector `0x01C000` readback-verified). PC incumbent SPP 10:46:32 + PTT OK;
Paired→TID-PTT→Connect → PC SPP dead ~10:47:19. Capture `/tmp/e10.hcd`
(→ `/tmp/opencode/e10_btmon.txt`): rel 46.593 the radio (handle 1) sent **two** L2CAP
Disconnection Requests — ident 6 (DCID 65, SCID 65) **and** ident 7 (DCID 64, SCID 64) —
closing **every** L2CAP channel on the PC link; rel 48.596 PC bluetoothd dropped the ACL
itself (0x16 local / MGMT 0x02). HCI-level still dead (no radio HCI Disconnect). The
TID-PTT did pair and join, but its key-presses never reached the radio (the
single-SPP-session wall `0x1A740` — expected). The two-channel (64+65) signature is the
`l2cap_disconnect_all_channel` **walk**, which forces channel state `0xd` + pumps
`l2cap_run` directly — bypassing `spp_channel_disconnect` (E10) entirely — and whose
dispatcher branch survives E9's poster-only NOPs.

## §27.17 — E10 RUN 2026-10-20: **FAILED — the closer is the all-channel walk; kill it at the L2CAP door** (`--no-l2cap-disconnect`, E11)

E10 exonerated `spp_channel_disconnect()` as the press-time closer: with its entry no-op'd
(readback-verified) the radio still closed **both** L2CAP channels (64 RFCOMM + 65) on the
PC link. Reconciliation of E8→E10:

- **E8** closed one channel (SCID 67) — the SPP path (`spp_connect` busy-close) and/or the
  walk; **E9** (posters NOP'd) still closed one (SCID 69) — SPP path; **E10**
  (`spp_channel_disconnect` NOP'd) closed **two** (64+65) — the walk, previously masked by
  the SPP close racing first, or reached via a third caller of the walk. The walk
  (`user_send_cmd_prepare(0x4a)` body `0x01E17B20`) was never fully dead: E9 NOP'd its two
  known **posters**, but the dispatcher **branch** (`je r11,#0x4a` @`0x01E17974`) and the
  four direct `l2cap_disconnect()` calls in the SPP state machine
  (`0x01E235B8`/`0x01E2376A`/`0x01E23A50`/`0x01E23BF4`) remained live.

**E11 patch — `--no-l2cap-disconnect`** (the L2CAP-level kill; two sites, both in sector
`0x01C000`):

| VA | stock | patch | meaning |
|---|---|---|---|
| `0x01E17974` | `0b f8 d4 94` | `00 00 00 00` | NOP the `je r11,#0x4a` dispatch branch — code `0x4a` falls through the je-chain to the default no-op (returns 0, debug-ring log only) for **every** caller, incl. any poster the E9 census missed; next insn is the chain's next `je` (fall-through safe) |
| `0x01E173D0` | `10 04 bf ea` | `00 23 80 00` | `l2cap_disconnect()` entry no-op `mov r0,#0; rts` — kills every direct caller at once (the four SPP-SM sites + `spp_channel_disconnect` + any other); return 0 = success, callers advance while channels stay open |

Pointer scans: zero 32-bit LE refs to either `0x01E17B20` (walk body) or `0x01E173D0`
(`l2cap_disconnect`) — direct calls only, no table routes. Side effects: the app can never
tear down **any** L2CAP channel (RFCOMM/AVDTP included) through these paths; stale channels
persist until power-cycle (the E6 malformed-AT+MPTT side effect remains). The outgoing page
and pairing flows are untouched.

**Built 2026-10-20:** `work/e11_twodev.bin` + 17 sector files; diff vs E10 = **exactly 8
bytes** (`0x1C3D0`–`0x1C3D3` + `0x1C974`–`0x1C977`), only `work/e11_01C000.bin` differs —
the E11 upgrade is **ONE sector write**. All **fifteen** patch sites verified in the
decrypted image; both suites green (`E11 combo carries all fifteen multipoint patches`).
Flash (pairings survive):

```bash
jl-uboot-tool erase 0x01C000 0x1000
jl-uboot-tool write 0x01C000 work/e11_01C000.bin
jl-uboot-tool read 0x01C000 0x1000 verify_01C000.bin   # cmp vs work/e11_01C000.bin
```

**E11 hardware test: RUN 2026-10-20 — see §27.18.**

---

## §27.18 — E11 RUN 2026-10-20: **THE EVICTOR IS DEAD** — zero teardowns all capture; two new walls: pairing-flow lockup + single-SPP-session routing

**Field result (user, capture `/tmp/e11.hcd`, 201 KB / 24,743 decoded lines →
`/tmp/opencode/e11_btmon.txt`):** flashed `work/e11_01C000.bin`, readback `cmp` clean.
Reported: *"Moderate success; I did not hear / see a direct disconnect but when trying to
pair the TID-PTT button the Radio locks up. Restarting the radio while leaving the
bt_spp_hold.py open saved the connection ... after some trials I was able to pair both so
it seems (no sure) but neither of them have the PTT operation to receive over the
spp_channel (pressing enter on PC seems to work (from the PC side) but no action on the
radio) also pressing the button on the TID-PTT blinked the transmit led but nothing on the
radio."*

**Capture decode — the headline: the radio sent ZERO L2CAP Disconnection Requests and
ZERO HCI Disconnects the entire session.** All radio-originated L2CAP signaling in the
file is Connection Request/Response, Configure Request/Response, Information Response,
and two Disconnection **Responses** (idents 5/8 — replies to the PC's own closes). The
only two Disconnection *Requests* are PC-side (`<` TX, bluetoothd closing its dynamic
channels when `bt_spp_hold` quit). The only link teardown is rel 98.767 Disconnect
Complete **reason 0x08 Connection Timeout** = the radio vanishing when the user
power-cycled it after the lockup. **E6→E11 eviction chain: fully dead at every layer we
mapped** (HCI kick, reason-0x13/0x16 executors, `0x4a` walk, `spp_channel_disconnect`,
dispatcher branch + `l2cap_disconnect` entry). The PC held its SPP session through an
accessory pairing attempt for the first time in the project's history.

**Timeline (bt_spp_hold, rel 0 ≈ 14:28:40.8):** session 1 SPP up rel 4.85, PTT DOWN/UP
**works** (`AT+MPTT=0` echo, line 40 — the only normal AT in the capture); pairing
attempt window rel ~85-95 (PC Inquiry Cancel rel 94.9); **radio locks up** → user power
cycles → 0x08 timeout rel 98.77; PC reconnect retries rel 127.9-172 fail (Connect
Complete 0x13 / Connect Failed 0x04 — radio rebooting, then busy paging the TID-PTT);
link re-established rel 213-233; session 3 SPP up rel ~252 (14:32:52).

**Wall 1 — pairing-flow deadlock.** With every teardown path NOP'd, entering
pairing/connect of the SPP accessory **while the PC holds a live SPP session locks the
radio up** (screen frozen; needs power-cycle). The app's connect flow evidently waits for
the incumbent channel-close to *complete* (the `spp_connect` busy-path returns −2 and
retries expecting the close we no-op'd, or pairing waits on a channel-closed event that
never fires). A side effect of killing the eviction, as anticipated in the §27.16/§27.17
risk notes — now confirmed as a hard blocker for the *simultaneous* SPP-pairing flow.

**Wall 2 — single-SPP-session + current-device routing (the echo).** After the
power-cycle the radio auto-joined the TID-PTT (current device = button). Session 3: every
`+SPP=P/R` frame from the PC comes back **echoed verbatim** (`2b 53 50 50 3d 50 00`,
`+SPP=R` doubled) with **no AT+MPTT and no keying**; the button's own events stop keying
too (its TX LED blinks, radio deaf). The PC's RFCOMM session binds SPP control block
`0x1A740` (last-connection-wins) while PTT command processing is gated on the
*current-device* pointer (struct `0x102F0`, ch. 22) — with two SPP devices attached the
data path and the command path point at different sessions, so **neither works**. This is
app architecture, not the eviction chain: no NOP on the sites we've mapped can fix it.

**Assessment.** E11 achieved its design goal (evictor dead, proven at the wire level) and
exhausted the NOP-against-eviction strategy for the **two-SPP-device** case. What remains
for PC + TID-PTT is *rewriting* the SPP layer: (a) surgical code-cave work (ch. 23 cave
@`0x01EA76DE`, ch. 25 decompile⇒compile route) to make the walk/chokepoint
handle-selective and the SPP session table multi-instance; (b) SDK rebuild (ch. 24/25);
or (c) the single-device workaround — one combo device (e.g. ESP32) carrying SPP+HFP,
profile coexistence proven (ch. 22 §9B.6.1). **Untested on E11 and likely still fine:**
the PC + Jabra combo (HFP second device never touched the SPP path; E6 proved it).
Also untested: whether *disconnecting* the PC's SPP first (q in `bt_spp_hold`) lets the
accessory pairing flow complete without lockup — that would make E11 usable in
*sequential* mode (PC or button, switch by choice, power-cycle-free).

**NEXT:** (1) user runs PC+Jabra regression on E11 (expect unchanged-good) and the
sequential-pairing check (PC SPP closed → pair TID-PTT → does the button key?);
(2) decide strategy for the two-SPP case: code-cave SPP multi-session rewrite vs SDK
rebuild vs combo-device workaround; (3) E12 (gate `l2cap_run` state-`0xd` send) is
**deprioritized** — the evictor is provably dead, E12 would only fight the lockup's
symptoms, not the architecture.

## §27.19 — E11 follow-up checks 2026-10-20: deadlock is **generic**, sequential pairing avoids it — but E11 **corrupts normal operation**; NOP route **exhausted**, rollback to E7 prepared

Two follow-up checks were run on the E11 build the evening of 2026-10-20. Both are
decisive, and together they close the NOP era of this project.

**Check 1 — PC + Jabra regression (capture `/tmp/e11_jabra.hcd` →
`/tmp/opencode/e11_jabra_btmon.txt`, 6,139 lines).** User: *"Paired to PC successfully and
transmitted, also used the PTT button on the radio a few times all ok, but when trying to
connect the Jabra the radio froze/locked/needed to be restarted but the headset never
connected."* Decode: normal SPP + PTT + `AT+MPTT=0` until the Paired→Jabra→Connect press
(22:43:00); afterwards PTT sends got **zero responses**; there is **no Disconnect Complete
anywhere** in the capture — the ACL was never torn down (the evictor is still dead).
Decisive detail: 90 s into the freeze the PC's own RFCOMM Disconnection Request was
answered with an L2CAP Disconnection Response in **24 ms** — the radio's BT **stack task
was alive while the app task was deadlocked**. **The lockup is NOT SPP-target-specific:
even an HFP (Jabra) Connect press deadlocks whenever a live SPP session exists.** The
press-time connect flow waits on a channel-close completion that the E9+E10+E11 NOPs made
impossible (prime suspect: the `spp_connect` busy-path −2 retry loop §27.16, or an
equivalent wait-for-release spin).

**Check 2 — sequential pairing (capture `/tmp/e11_seq.hcd` →
`/tmp/opencode/e11_seq_btmon.txt`, 1,920 lines).** Flow: SPP up 22:49:36 → PTT → `q` →
`bluetoothctl disconnect` → *then* pair the TID-PTT. Results:

1. **No lockup** — sequential pairing (PC SPP closed first) completes cleanly. The
   deadlock theory is confirmed: the freeze requires a *live* SPP session at Connect press.
2. But the **echo state was present from the very first PTT** — fresh boot, first
   connection, nothing else paired: `+SPP=P/R` came back doubled with **no `AT+MPTT`**
   (grep count in the capture: 0). The radio received and processed the frames (echo
   proves it) but treated the channel as a data pipe, not the control channel.
3. **TID-PTT button regression:** after pairing, the button's own presses key nothing
   (radio deaf; button's TX LED doesn't even light = the button believes the link can't
   send), while the radio→button direction works (button red LED mirrors radio TX; its mic
   is used as BT-PTT TX source). The button keys the radio via **`AT+MPTT=1/0` over its
   link** (ch. 08/09) — inbound command processing is what is dead. Reboot + re-pair
   button "alone" did not restore it.

**Verdict.** E11 killed the evictor at the wire level (zero radio teardowns across all
three E11 captures) but its blunt teardown NOPs leave the app's single-session /
single-current-device bookkeeping **half-completed on every legitimate flow**
(connect/reconnect/cleanup), corrupting session state app-wide — hence echo + deaf
inbound command processing even on a fresh boot with one device. Blocking closes →
deadlock; allowing closes → eviction. The app's SPP layer admits no middle ground by
NOP. **The NOP route is exhausted; E12 stays deprioritized** (a fake-complete of the
close would be eviction in disguise).

**Rollback.** The last known-good baseline is **E7** (E6-style PC+Jabra multipoint
intact, button keys normally; flaw: paired-join kicks the incumbent). E11→E7 is exactly
32 bytes across five sectors — `0x01C000` (E10/E11 entries + branch), `0x01E000` +
`0x025000` (E8), `0x065000` + `0x066000` (E9). Sector files extracted from
`work/e7_twodev.bin` as `work/e7rb_*.bin` (cross-checked against the original E7 build).
Pairings/VM untouched; power-cycle after.

**Where this leaves the goal.** Genuine two-device operation (headset for mic/speaker +
button for PTT, or PC + button) requires **rewriting** the SPP session layer, not
disabling it. The SDK-fork survey for the rebuild route is [ch. 28](28-sdk-forks-survey.md)
(Linux br23 build **externally proven green**; no fork solves multipoint; §28.6 scopes the
sub-routes). The static-analysis reference map is now **written** —
[ch. 29](29-static-analysis-reference-map.md) (every SDK function, RAM structure and patch
site in one table); the consolidated Two-Device Bluetooth Plan (ch. 30) is still to be written.

> **Goal clarification 2026-10-21 (user).** The goal was **always** "multiple BT devices
> connected — SPP commands from one, audio from the other" (Jabra HFP mic/earphones +
> TID-PTT SPP button, either pairing order); **two concurrent SPP sessions was never a
> goal** — it only surfaced as the final wall because the PC test client is itself an SPP
> device. The SPP-session *rewrite* conclusion above therefore applies to the generic
> any-two-SPP case only: the goal topology (one SPP + one HFP) is exactly what **E6
> already ran hardware-confirmed** (§27.11) with the PC in the SPP role, and needs only a
> minimal close-suppression, not a rewrite. Plan of record:
> **[ch. 30 — the Two-Device Plan](30-two-device-plan.md)** (§30.0 goal statement, §30.1
> which ch. 27 results transfer).

---

*[<< Index](Findings.md)* · [Ch. 22 §9B.11 (corrected)](22-bluetooth-7-multipoint-architecture.md#9b11--the-real-cap-the-stacks-connection-data-model-is-1-x-conn_info) · [Ch. 26 (mechanism)](26-bluetooth-9-eviction-decision.md) · [Ch. 18 (priorities)](18-open-questions-next-steps.md)
