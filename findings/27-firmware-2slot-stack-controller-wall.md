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

---

*[<< Index](Findings.md)* · [Ch. 22 §9B.11 (corrected)](22-bluetooth-7-multipoint-architecture.md#9b11--the-real-cap-the-stacks-connection-data-model-is-1-x-conn_info) · [Ch. 26 (mechanism)](26-bluetooth-9-eviction-decision.md) · [Ch. 18 (priorities)](18-open-questions-next-steps.md)
