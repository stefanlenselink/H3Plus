# Chapter 26 — Bluetooth 9: The Eviction Decision, Located

> **Status: the eviction decision site is found and fully traced (static, v1.0.50).**
> The kick is an **app-level routine** `0x01E5B22A` that posts a disconnect command for
> the currently-tracked handle to a controller command queue; the queue relay
> `0x01E22890` case 5 is the **sole executor** of HCI Disconnect in the entire app.
> The host stack itself **never** evicts — it simply cannot track a second link
> (`[1 x conn_info]`, [§9B.11](22-bluetooth-7-multipoint-architecture.md)).
> This chapter also consolidates the **options analysis** for getting multipoint working.
>
> Hardware-confirmed facts are marked **HW-confirmed**; static-only claims **statically
> inferred**; anything unproven is marked **UNTESTED**.
> Addresses are VA of `work/app_dec.bin` (v1.0.50); file offset = `VA − 0x01E00000`;
> flash = file + `0x5000`.

---

## §26.0 — Why this chapter exists

[§9B.11](22-bluetooth-7-multipoint-architecture.md#9b11--the-real-cap-the-stacks-connection-data-model-is-1-x-conn_info)
proved the stack's connection table is one entry deep and that `--conn-num=2` only moves
a scan-management threshold — but it left the *active* eviction mechanism ("who
disconnects the incumbent?") open, and [ch. 18](18-open-questions-next-steps.md) listed
it as the next static target. This session traced it end-to-end using the
Ghidra decompilation tree ([ch. 25 §25.8](25-ghidra-decompile-compile-route.md)),
the linear disassembly `work/full.lst`, and LLVM IR from the SDK's precompiled
libraries (`fw-AC63_BT_SDK` `cpu/br23` `btstack.a`/`btctrler.a`).

## §26.1 — Method notes (reproducibility)

- The decompilation tree (`disassembled/decompiled/`, 6491 functions) plus
  `disassembled_all.c` gave the call graph; `tools/findva.py` found pointer-table
  entries for table-registered callbacks (the classic zero-direct-xref case).
- SDK IR: extract `.c.o` members from `btstack.a`/`btctrler.a`, disassemble with
  `llvm-dis-8` (bitcode version 53; the bundled JieLi clang 4.0.1 refuses some of them).
  The 2025-SDK IR differs from v50's older build (e.g. disconnect reason 22 in IR vs
  reason 19 baked into our image) — use constants + structural fingerprints, not
  byte equality.
- Compiling SDK IR with the official toolchain to byte-match our image is **blocked**:
  `pi32v2/bin/cc` (not bare `clang` — it adds `-target pi32v2`) plus stripping
  `speculatable`/`spFlags`/`llvm.dbg.*` gets IR into LLVM-3.x form, but ISel then
  segfaults on `hci_emit_remote_name_cached`. Fingerprint matching works; compilation
  does not.
- Ghidra loses the `r14`-relative base of the stack globals (`BADSPACEBASE`); switch
  tables in the big UI/stack functions must be decoded manually:
  `target = table_base + 2 × entry` for `tbh`.

## §26.2 — The sole disconnect executor: `0x01E074DE`

```
FUN_01e074de(handle):
    FUN_01e029de(0x400006, 3, 0x406, handle, 0x13)
```

`0x406` = 1030 = the controller-internal code of **HCI Disconnect** (confirmed against
`btctrler.a` IR: `lmp_hci_disconnect` posts `lmp_hci_cmd_to_conn_for_handle(handle, 2,
1030, reason)`). The **reason is baked in as `0x13` = 19** ("Remote User Terminated
Connection") — our build does not pass the caller's reason through (the 2025 IR passes
22; version drift). `FUN_01e029de` is the generic "send command to controller" writer
(0x400006 = module descriptor).

**Xref fact (the key structural result):** in the entire linear disassembly,
`0x01E074DE` is called from exactly **one** site — `0x01E22996`. There is no other
disconnect path in the app image.

## §26.3 — The controller command relay: `0x01E22890`

`FUN_01e22890` is a registered queue consumer (no direct callers; its pointer sits at
`0x01E18F68` in the BT-stack init function). The queue is created at `0x01E18F4A`:

```
0x01E18F4A  r4 = 0x1A688                     ; queue object (inside __user_info, 0x1A520+0x168)
0x01E18F56  call 0x021127B4                  ; queue init
0x01E18F62  call 0x02003BBC                  ; register handler: 0x1A688, 0xB8 entries, FUN_01e22890
0x01E18F66  r1 = 0x1E22890                   ;   (queue handle stored at 0x1A6AC)
```

The relay pops messages `{type, args…}` from mailbox `0x1A694` and dispatches:

| type | action |
|---|---|
| 1, 3, 4 | controller param writes (`0x01E07386/0x01E073F4/0x01E07440`) |
| **5** | **disconnect**: `if (handle) FUN_01e074de(handle)` @ `0x01E22996` |
| 8 | `FUN_01e1651a` + `FUN_01e22772` (profile state) |
| 0xb | remote-name cache write (into `0x1A5B8` profile-channel table) |
| 0x15 | write 2-bit fields of `0xC54C` (LE adv/connectability config — the byte ruled out in §9B.10) |
| 0x16 | accept/reject incoming (`0x200C` = 1033/1034 window) |
| 0x82 | create-connection (address + packet types) |
| 6,7,9,0xc–0xe,0xf,0x10,0x12,0x13,0x17,0x18–0x1a,0x1b | misc controller commands |

The **producer** side is `FUN_01e1664e(cmd, nargs, …)` @ `0x01E1664E` — it builds
`{cmd, args}` and posts to the `0x1A688` queue. It has exactly 12 call sites in the
app; **only one of them posts cmd 5** — inside the kick routine below.

## §26.4 — The kick routine: `0x01E5B22A` — *the eviction decision*

```c
uint FUN_01e5b22a(void)
{
    if (_DAT_00010372 == 0)          // _DAT_00010372 == app device struct 0x102F0 + 0x82
        return 3;                    //   = current connection handle (0 = not connected)
    if (FUN_01e4e2ba() != 4) {       // app BT state getter
        FUN_01e4e2c4(4);             //   set state 4 ("disconnecting")
        FUN_01e1664e(5, 1, _DAT_00010372);   // post cmd 5 (disconnect) with the handle
    }
    return 0;
}
```

This is the whole decision: **"if we have a connection, disconnect it."** No policy, no
device comparison — the caller decides. The handle lives at `0x102F0 + 0x82`
(= `0x10372`, the same word the decompiler names `_DAT_00010372`), i.e. the app's
**single** device struct ([§9B.4](22-bluetooth-7-multipoint-architecture.md)).

## §26.5 — Who invokes the kick

| caller | context | behaviour |
|---|---|---|
| `FUN_01e6076c(0)` @ `0x01E6076C` | app **BT on/off toggle**: `on → set flag + FUN_01e4e3d6(1)`; `off → if (handle) kick` | called with `r0=1` (on) at `0x01E611CE`, with `r0=0` (off → kick) at `0x01E61D42`; further call/tail sites `0x01E7EF1A`, `0x01E7F00A`, `0x01E83D9E` (UI/task callbacks) |
| `FUN_01e83d84(1)` @ `0x01E83D84` | **BT power API**: `param 2 → on (FUN_01e6076c(1))`; `param 1 → kick + FUN_01e4e3d6(0)` | called from `0x01E83DE2`, `0x01E83E12` |
| command table @ `0x01E9C9DC` | 7-entry function table right after the `"tsk_read:"` string: `[0x01E4E2E4, `**`0x01E5B22A`**`, 0x01E50248, 0x01E5B25C, 0x01E5B262, 0x01E5B26E, 0x01E5B27C]` | entry[1] = kick. The table's dispatcher is **not traced** — no 32-bit LE pointer to the table exists in the image (computed addressing or ROM-side registry). Entry[3] returns `0x84` via `0x01E5A5EE`; entry[0] is a connect-state machine using `FUN_01e4e2ba/c4` and the poster `FUN_01e1664e(2,3,0)` |

**Interpretation of the hardware tests** (§9B.11, conn_num=2 build, **HW-confirmed**
behaviour, mechanism statically inferred):

- *Test 2* — PTT connected, user presses menu → connect headset: the PTT dropped **at
  the moment of the keypress**. That is the kick firing before the new page starts —
  exactly what a single-`conn_info` stack requires (the kick frees the one slot so
  `create_bt_new_conn()` can succeed for the new device).
- *Test 1* — headset connected, pairing mode, PTT joins: entering pairing/connecting
  likewise runs the app's disconnect-then-connect flow; the "Bluetooth disconnected"
  announcement is the incumbent being kicked.
- Note the conn_num=2 build **did** let the incoming PTT page in (page scan stayed
  enabled) — consistent with `is_1t2_connection()` gating only scan/connectability.

## §26.6 — The stack never evicts (IR evidence)

From `avctp_user.c.o` (br23) LLVM IR:

- `user_operation_control` case `USER_CTRL_START_CONNEC_VIA_ADDR`:
  `is_1t2_connection()` true → **no-op**; else `get_conn_for_addr(mac)` → if absent
  `create_bt_new_conn(mac)` → **returns NULL when the single `conn_info` slot is
  inuse** ("create_bt_new_conn null"). No disconnect anywhere in the path.
- `USER_CTRL_DISCONNECTION_HCI` (op 4): the handler exists in the IR
  (`emitter_hci_disconn_deal()==0 && conn_info.handle → hci_disconnect_cmd(handle, 22)`)
  but **our app never posts op 4** — all 40+ `user_send_cmd_prepare` (`FUN_01e1792e`)
  call sites were enumerated; no literal or variable opcode resolves to 4.
- Incoming `CONNECTION_REQUEST` (HCI event 4): `update_multi_bd_status(mac,1,type)` is
  a **weak stub returning 0** in our build → plain
  `lmp_hci_accept_connection_request()`. `CONNECTION_COMPLETE` (event 3): link-key
  bookkeeping only.
- The controller is innocent: `bredr_table` is `[4 x …]` (4 BR/EDR links).

So the full multipoint constraint is **three stacked layers**, only one of which is an
active decision:

| layer | structure | limit | active eviction? |
|---|---|---|---|
| controller (`btctrler.a`) | `bredr_table[4]` | 4 ACLs | no |
| host stack (`btstack.a`) | `__user_info.conn[1]` @ ~`0x1A5F1` | **1 tracked ACL**; `create_bt_new_conn` NULL when full | no (passive) |
| app | device struct `0x102F0` (809 refs; handle @ `+0x82`) + kick `0x01E5B22A` | 1 device in UI/audio/state | **YES — the kick** |

One encouraging detail: the stack's **profile-channel table has 2 entries**
(`0x1A5B8…0x1A5F0`, stride `0x1C`) even in the single-device build — the profile layer
was sized for two links; only the `conn_info` layer is one deep.

## §26.7 — Options for getting multipoint working

Goal (restated): headset (HFP audio) + TID-PTT button (SPP `+SPP=P/R`) on one radio
simultaneously; "first or last connected wins" acceptable for the *controlling* device.

### Option A — kick-NOP experiment (cheap, one flash) — **UNTESTED**

Make the app's kick a no-op and keep `--conn-num=2` (so page scan stays enabled).
**Implemented 2026-10-04** as `--no-kick` in the patch tool (kick early-return
variant; `--no-kick --conn-num=2` builds the full Option A, verified by both
test suites). Two equivalent 4-byte candidates (the kick is the *only* producer
of cmd 5, and the relay case 5 its *only* executor):

| patch | VA / file / flash | stock bytes | patched |
|---|---|---|---|
| kick early-return (`r0 = 3; rts`) | `0x01E5B22A` / `0x5B22A` / `0x6022A` | `75 04 c5 ff` | `40 23 80 00` |
| relay case-5 call NOP | `0x01E22996` / `0x22996` / `0x27996` | `bf ea a2 25` | `00 00 00 00` |

The kick early-return is preferred (leaves the relay intact for any other future user
of cmd 5). Expected behaviour, **UNTESTED**:

- *Incoming* second device: accepted (HCI accept path is policy-free), second ACL comes
  up at controller level; the stack never creates a `conn_info` for it — it is a
  **ghost link**. Whether its RFCOMM/SPP traffic is still delivered to the app's SPP
  handler is the open empirical question (l2cap/RFCOMM are cid/handle-driven below
  `conn_info`; the 2-entry profile-channel table helps).
- *Outgoing* second device: still fails silently — `create_bt_new_conn` returns NULL
  while the slot is held, so the page never starts. (The kick existed precisely to free
  that slot.)
- Side effects: BT-off / menu-disconnect also stop working (same code path); the link
  would drop only on controller re-init or remote disconnect.

Knowledge gained: whether the vendor stack tolerates a second untracked ACL at all,
and whether SPP keys from the ghost link reach the app. If **yes** → a *gated* kick
(skip only when the incumbent is the audio device and the newcomer is a PTT-class
device) becomes a plausible follow-up patch. If **no** → multipoint by patching is
definitively dead and effort moves to C/D.

### Option B — widen `conn_info` in machine code (research-grade, fragile)

Change `[1 x conn_info]` → `[2 x …]`: every subsequent field of `__user_info`
(base `0x1A520`) is baked into vendor-compiled offsets, so the second entry must be
**stolen from adjacent spare RAM** without moving anything, and
`create_bt_new_conn`/`get_conn_for_addr`/the count bits (`field9` @ `0x1A662`,
count = bits 0–2, slot = 3–5) re-pointed by patching their walkers. Even if it works,
the **app struct `0x102F0` is still single-device** — UI, audio routing and the
name→mode classifier follow one device. B alone does not deliver the goal.

### Option C — vendor multipoint stack library (heavyweight, "real" fix)

JieLi's 1拖2 products ship a *different, specially-built* `btstack.a` (the public SDKs
bundle only `[1 x conn_info]` builds; `multi_bd.c` compiles to zero functions for
br23). Routes: ask JieLi/TIDRADIO for the multipoint br23 build, or extract it from a
br23 1拖2 product firmware. Then the app must be rebuilt from `fw-AC63_BT_SDK`
(`apps/spp_and_le` for br23) with dual-device logic — the stack library alone changes
nothing for the H3's app.

### Option D — single-link combo device (pragmatic, no multipoint needed) — **proven capability**

The probe already proved **SPP + HFP coexist on ONE ACL** (§9B.6.1, HW-confirmed).
So make the *accessory* the multiplexer:

- **D1**: a custom ESP32 (or JieLi) device presenting HFP + SPP simultaneously —
  headset audio + PTT button in one enclosure; radio side needs only the existing
  BT-PTT/BT-PTT2 patches. Zero further RE.
- **D2**: an off-the-shelf headset whose button already triggers something the radio
  maps to PTT (HFP hook/`ATD`-style events). The radio rejects inbound `AT+MPTT`
  (ch. 09), so this depends on which inbound HFP events the firmware acts on —
  **UNTESTED**.

### Option E — full SDK rebuild — blocked

The stack ships precompiled in every public SDK; rebuilding the app cannot widen the
stack's connection table. Only meaningful combined with C.

### Recommendation

1. **Flash Option A** (kick early-return + `--conn-num=2`) — one experiment, decisive
   knowledge, trivially reversible. **Build it with
   `--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2 --no-kick`** (the
   `--no-kick` flag shipped 2026-10-04; `--show` reports the kick site state).
2. In parallel, treat **D1** as the pragmatic delivery path (works with today's
   patches).
3. Keep **C** as the only route to *true* two-device multipoint; B/E only as
   research vehicles toward it.

## §26.8 — Open questions

- ~~Does the app's SPP RX path accept data from a link with no `conn_info`?~~
  Superseded by §26.9: the stack's conn pool has 20 entries — a second link gets
  a real conn entry; the open question is now the **app's SPP/profile binding**
  to its single device struct (test with Option A2).
- What exactly does the untraced command-table dispatcher at `0x01E9C9DC` consume from
  (menu key events? a ROM-side task-command interpreter — note the `"tsk_read:"`
  string immediately before the table)?
- Does entering pairing mode call the kick directly, or does the incumbent drop only
  because the app struct is overwritten? (Both consistent with test 1; not traced.)
- `FUN_01e4e2ba/c4` state machine semantics (state 4 = "disconnecting"?) — mapped only
  shallowly.

## §26.9 — Option A hardware round 1: kick-NOP **works**, page scan is the next gate (2026-10-05/06)

Option A (`--no-kick --conn-num=2`, kick NOP readback-confirmed via
`cmp Dumps/rb_060000.bin work/opta_060000.bin` → `NOP-ON-CHIP`) was flashed and
tested. Results, in order:

1. **Radio-initiated second device still evicted** the headset at the moment the
   found-device was selected in the pairing list ("Bluetooth disconnected" on radio
   *and* headset, then "Bluetooth connected" for the joiner a second later).
2. **Incoming connections no longer evict anything.** With the headset up, PC page
   attempts (`hcitool cc` / `bt_spp_hold.py`) failed with **`Page Timeout (0x04)`**
   (btmon, `Create Connection` → `Connect Complete`), and the headset stayed
   connected and fully functional throughout. The earlier `ECONNRESET`/`EHOSTDOWN`
   variants were the PC stack's own caching/timeouts; btmon is unambiguous.

**Interpretation.**

* The kick NOP is live and effective: the app can no longer tear anything down —
  the second-device join attempts leave the incumbent alone (this never happened
  on stock firmware).
* The remaining gate is **page scan**: while any link is up the radio answers no
  pages at all. Static cause (v50): the BT task's scan policy only *enables* page
  scan when `is_1t2_connection()` (`FUN_01e1787c`) is **false** (task cases `0xd`/`0xf`
  in the dispatcher around `0x01E21E46`), and the vendor's 1拖2 scan logic lived in
  `multi_bd.c` — which is **compiled EMPTY in this firmware** (the linked
  `multi_bd.bc` contains only two stray debug-flag globals; the module's code was
  `#if`-ed out at vendor build time). So in `conn_num = 2` mode nothing ever
  turns page scan on while connected.
* The eviction seen in radio-initiated pairing (result 1) is therefore **not** the
  kick (dead) and **not** the stack (its HCI event dispatcher
  `FUN_01e19a78` has no replacement logic; conn pool = 20 entries, pending list
  dynamic) — it is the outgoing-page path itself: the controller is configured
  single-ACL, and paging a second device while connected breaks the incumbent at
  the baseband/LMP level. Incoming pages avoid that path entirely.

**Structural facts established this round (all static, v50):**

* Conn-entry allocator `FUN_01e17414` draws from the pool at `[0x1A4D8]+4`:
  **20 entries × 0x38 B** (pool init `0x01E18B92`–`0x01E18BDA`). The host stack
  can track many links; the single-device cap is app-layer + controller config.
* HCI event dispatcher `FUN_01e19a78` (event 0x03 CONNECTION_COMPLETE, 0x05
  DISCONNECTION_COMPLETE, 0x13 REMOTE_NAME): pure pending-list bookkeeping,
  **no eviction**.
* Relay `FUN_01e22890` fully enumerated: case 5 is the only HCI Disconnect;
  cases 7/9/10/13/14/20/24/25/26 are no-ops.
* Scan state byte at RAM `0xBEC8` (bit 0 = inquiry scan, bit 1 = page scan).
  Page-scan setter `FUN_01e18afc` @ `0x01E18AFC`; HCI wrapper `FUN_01e08672`
  (`write_scan_enable`, opcode `0x0C1A`).

**Option A2 — `--force-page-scan` (shipped 2026-10-06).** NOP the page-scan
*disable* branch inside the setter so every call enables page scan:

```
0x01E18B0E:  80 41 24 16  ->  00 00 00 00     (nop; nop)
  stock:  if (r0 != 0) goto keep; r4 = r2(cleared)   ; r0=0 -> disable
  patched: fall through; r4 stays r3|2               ; every call -> enable
```

File offset `0x18B0E`, flash `0x1DB0E`. The stack's post-connect "disable page
scan" now turns it **on**, leaving the radio connectable while the headset holds
HFP. Side effect: the radio is always connectable (any paired device may page
it); paging behaviour slightly busier. Build:

```bash
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin \
    --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT \
    --conn-num=2 --no-kick --force-page-scan --sectors=../jl-uboot-tool/multi-bt-ptt2
```

**Option A2 hardware test (next):** with the new image flashed and the headset
connected, the PC (or the TID-PTT button, which connects *to* the radio's SPP
server) should now get an ACL + SPP while the headset survives. If the ACL comes
up but SPP is refused, the next gate is the app's single-device SPP/profile
binding (struct `0x102F0`), which is patchable with the same direct-rewrite model.

## §26.11 — Option A2 hardware round 2: page scan **works**; second link dies at the controller (2026-10-06)

> **CORRECTION 2026-10-06 (same day, later session) — two claims below are wrong.**
> (1) "opcode `0x406` appears exactly once" is false: 13 literal sites; the real HCI
> Disconnect senders are `0x01E074EE` (kick, dead under `--no-kick`), `0x01E07606`
> (reason 0x0F, L2CAP timeout) and the wrapper `0x01E07B08(handle, reason)` — whose
> 0x13 caller `0x01E178B2` is **action-driven only** (disconnect-current / dispatcher
> cmd 8/10 by address). (2) "the second ACL has no `conn_info` slot" is false for our
> build: the vendor compiled **2 slots** (+2 RFCOMM muxes, 6 svc, 6 ch). The host
> always accepts incoming ACLs (no connected-gate in the case-4 handler). The
> teardown is issued by the **prebuilt controller library** — full evidence, capture
> decode and the experiment matrix in
> [ch. 27](27-firmware-2slot-stack-controller-wall.md). "Option B (widen `conn_info`)"
> is therefore moot; the remaining binary experiments are controller-side (role
> parameter / config bytes), see ch. 27 §27.8.

Image: `--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2 --no-kick
--force-page-scan` (full `.bin` from the user's dump). Capture:
`btmon -w /tmp/spp_reject.hcd` on the PC (adapter `90:DE:80:55:E3:A6`).

**Result 1 — `--force-page-scan` hardware-confirmed.** With the headset
holding HFP, the PC's `Create Connection` to the radio (`0B:FF:59:E8:85:92`)
is now **answered**: `Connect Complete` 650 ms after the page (was
`Page Timeout 0x04` pre-patch). The radio is connectable while connected.
The kick-NOP also held: the headset survived every attempt.

**Result 2 — the second link is refused one layer deeper.** Two outcomes,
same gate: (a) `Connect Complete` status **`0x13` Remote User Terminated**
(~650 ms after link up), and (b) `bt_spp_hold` → **`ECONNRESET`** (ACL up,
RFCOMM/SPP reset). Static analysis this round proves the **app image is
innocent** of the teardown:

* Every HCI sender enumerated: opcode `0x406` (Disconnect) appears exactly
  once in the image — the kick path `FUN_01e074de` @ `0x01E074DE`, whose only
  producer is the dead kick. Relay cmd 1 → vendor `0x200A` is connectable-mode
  control (posted by `FUN_01e4e2e4` only when the tracked handle is 0), not a
  disconnect.
* Incoming-connection policy (stack task, case 4 @ `0x01E1A49E`/`0x01E1A4CC`):
  ACLs are **accepted** (role 1). Reject (reason `0x0A`) only for unknown link
  types. The veto hook `FUN_01e18ffa` reads ops-table slot `[0xBF48+0x24]` —
  the never-written `update_multi_bd_status` slot (§9B.11) — so it returns 0.
* The app's SPP RX path is **device-agnostic**: BT event dispatcher
  `FUN_01e83db4` case 7 → parser `FUN_01e5b2f4` (strncmp `+SPP=P`→key 0x2A,
  `+SPP=R`→0x2B, `AT+MPTT=1/0`, `CH_KEY=+/-`, `+POWER=0`) → key queue. No
  device check anywhere on the data path.

⇒ The refusal is the stack's **profile/conn layer**: the second ACL has no
`conn_info` slot (`user_info_t.conn[1]`, [§9B.11](22-bluetooth-7-multipoint-architecture.md#9b11--the-real-cap-the-stacks-connection-data-model-is-1-x-conn_info)),
so RFCOMM on the new handle is refused and the link is torn down. `conn_num=2`
opens the scan/policy gates; the data model remains single-device. **Option B
(widen `conn_info`) is the only remaining binary path** to true multipoint.

**Result 3 — test-setup gotcha (the "PTT invisible" scare).** The trace shows
the TID-PTT button (`6F:E5:E7:FB:12:4F`, name `TID-PTT0cd28a-B`, class
`0x240404`) paging and **connecting to the PC** (btmon event #12) — BlueZ
auto-connects paired devices. While connected to the PC the PTT is invisible
to the radio's inquiry. **Turn the PC adapter off (or
`bluetoothctl remove 6F:E5:E7:FB:12:4F`) before testing radio-side pairing.**
Not a firmware issue.

**Controlled tests to pin the boundary (next):**

1. Headset off, radio idle → PC `bt_spp_hold` → expect success (sanity that
   the patch trio didn't break the normal single-device path).
2. Headset connected → PC `bt_spp_hold` → expect `0x13`/`ECONNRESET` (the
   `conn_info` wall).
3. During test 2, `watch -n0.2 hcitool con` on the PC — does the second ACL
   persist ≥1 s (ghost link) or die at establishment?

---

*Continue from: [§9B.11](22-bluetooth-7-multipoint-architecture.md#9b11--the-real-cap-the-stacks-connection-data-model-is-1-x-conn_info)
(root cause) → this chapter (mechanism + options) →
[ch. 18](18-open-questions-next-steps.md) (priorities).*
