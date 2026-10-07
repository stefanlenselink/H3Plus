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
| E4 | E2 + **role patch**: force the case-4 ACL accept role to the other value (`1` ↔ `0xAA`, one instruction at the `DAT_0000c02b & 8` branch, `0x01E1A0xx` region) | PC pages radio | Is the refusal a role-switch conflict? |
| E5 | Headset streaming SCO (mic live) | PC pages radio | Is eSCO scheduling the trigger? |

E4 candidate patch bytes: locate the branch feeding `uVar9` in `FUN_01e19e44`
(decompiled lines ~29650–29661; sites `0x01E1A044`/`0x01E1A0AC` area) — a 2-byte
immediate flip. Build as a patcher site only after E2 reproduces on the bench.

## §27.9 — What this means for the goal

Goal: headset (HFP mic) + TID-PTT (SPP PTT) simultaneously. The host stack is
**already provisioned** for exactly this (2 conn slots, 2 RFCOMM muxes, one HFP +
one SPP profile instance each). The blocker is the controller's link policy. E1–E5
decide whether a small patch (role/config) can open it, or whether the remaining
routes are vendor-library/SDK-rebuild/combo-device.

---

*[<< Index](Findings.md)* · [Ch. 22 §9B.11 (corrected)](22-bluetooth-7-multipoint-architecture.md#9b11--the-real-cap-the-stacks-connection-data-model-is-1-x-conn_info) · [Ch. 26 (mechanism)](26-bluetooth-9-eviction-decision.md) · [Ch. 18 (priorities)](18-open-questions-next-steps.md)
