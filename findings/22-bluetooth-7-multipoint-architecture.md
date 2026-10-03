[<< Index](Findings.md)

# Bluetooth HFP — 7. Multipoint architecture: can the radio hold two BT devices? (§9B)

> Goal under test: run a **random Bluetooth headset** (HFP audio) *together with* the
> vendor **TID-PTT button** (SPP), on one radio — with a configurable mic source.
> "First connected wins" is acceptable. This chapter maps the parts of the firmware
> that decide whether that is possible, and what a patch would have to touch.

### 9B.1 The connection-callback ops table at RAM `0xBF48`

The app registers its Bluetooth event handlers into a small ops table living at RAM
`0xBF48`. Registration happens in one init sequence (v1.0.50, `0x01E60EF2`–`0x01E60F02`),
one tiny setter per slot:

| VA (setter) | Slot | Handler | Role |
|---|---|---|---|
| `0x01E1841E` | `[0xBF48+0x10]` | *(value passed in r0)* | generic slot setter |
| `0x01E18428` | `[0xBF48+0x28]` | `0x01E7EED6` | sibling event callback |
| `0x01E18438` | `[0xBF48+0x2C]` | `0x01E7EEE8` | sibling event callback |
| `0x01E18448` | `[0xBF48+0x4]` | **`0x01E7EC28`** | **the routing-mode classifier** ([§9A.28](11-bluetooth-4-routing-modes-decoded.md#9a28--the-routing-mode-classifier-found-and-fully-decoded)) |

```
01E18448  c0 ff 48 bf 00 00     r0 = 0xBF48
01E1844E  c1 ff 28 ec e7 01     r1 = 0x1E7EC28      ; classifier
01E18454  81 61                 [r0+0x4] = r1
01E18456  80 00                 rts
```

This explains why the classifier has **zero direct call/goto xrefs** — it is only ever
reached through `[0xBF48+0x4]`.

### 9B.2 The dispatcher that invokes it

`0x01E18FC0` is the indirect-call wrapper. It loads the slot and calls through it with a
stack-frame argument block (`sp+0` = buffer, `sp+4` = pointer, `sp+8` = a length/flags word):

```
01E18FC0  76 04                 [--sp] = {r6-r4}
01E18FE4  06 61                 r6 = [r0+0x4]        ; ops-table slot
01E18FEC  c6 00                 call r6
```

Five call sites feed it, all inside a larger event switch keyed off bytes of an event
buffer (`b[r15+0x1]`, `b[r15+0x2]`, …):

| Call site | Context |
|---|---|
| `0x01E19D18` | after copying name-ish bytes into a stack struct (`b[r4+0xA] = …`) |
| `0x01E1A342` | event byte `b[r15+0x1]` case |
| `0x01E1A370`, `0x01E1A410`, `0x01E1A48E` | sibling cases of the same switch |

So the flow is: **BT stack event → switch → dispatcher → classifier → routing byte**
`b[0xB390+0xD4]` (RAM `0xB464`), exactly the byte whose readers were mapped in
[§9A.35](12-bluetooth-5-patching-tool.md#9a35--the-routing-mode-byte-has-exactly-six-readers--and-only-modes-56-touch-audio). Nothing here counts links or refuses a second
device — the classifier *overwrites* the routing byte whenever a new named device
attaches. **A second connection would silently re-route the first one's behavior**,
which matches the observed "second device takes over" feel.

### 9B.3 The paired/connected device list is a real linked list

The name-match helper `0x01E1900C` (7 callers) walks a **singly-linked list at RAM
`0x1A670`**:

```
01E1900E  c3 ff 70 a6 01 00     r3 = 0x1A670
01E19016  33 60                 r3 = [r3+0x0]        ; head
01E1901A  33 60                 r3 = [r3+0x0]        ; next
01E1901E  c3 00                 call r3              ; iterator
...
01E1902C  call 0x01E1805E        ; fill: compare 0x20-byte entry
01E1903A  call 0x021127B0        ; ROM strncmp
```

Entries are `0x20` bytes (name + link fields). The list machinery itself is
multi-entry — the *stack* below can hand the app more than one device record. The
cap, if any, is not in this list.

### 9B.4 ⭐ The decisive constraint: one global device-info struct

The app layer keeps **all live state for the remote device in a single global struct at
RAM `0x102F0`** — 809 references across the image, with field offsets reaching into the
kilobyte range (name, link class `+0xB10`, gate `+0x278`, and much more). There is **no
second base address** anywhere: no `0x102F0 + n*size` indexing pattern, no array-of-2.

**Consequence:** whatever the JieLi stack *below* the app can hold, the application
models exactly **one** remote Bluetooth device at a time. Every feature — mic routing,
PTT/SPP events, battery reporting, the `AT+MPTT` squelch sender — reads through that one
struct. True simultaneous headset + button operation would require either:

1. the stack layer multiplexing both links onto the one app-visible device (unlikely —
   the routing byte is written per-connection by name), or
2. patching the app layer to be device-aware (large — 809 sites), or
3. **rebuilding the app from the JieLi SDK**, where multi-link (A2DP+HFP+SPP
   coexistence) is a supported configuration, and porting the TID-specific glue
   (whitelist, `+SPP=P/R`, `AT+MPTT`, routing modes) on top.

This is the strongest static evidence yet for the plan's **Route C** being the honest
path to full dual-device operation — with one important caveat, next section.

### 9B.5 What *is* cheap: the routing byte and the name gate

While full multipoint is architecturally expensive, everything *below* the multipoint
question is a 3–7 byte patch and already works (mode 4 duplex, key remaps —
[Ch. 12](12-bluetooth-5-patching-tool.md), [Ch. 13](13-bluetooth-6-key-remap-milestones.md)).
If the stack turns out to accept two ACL links (9B.6 decides), the *first* experiment
needs no app-layer rewrite at all: force the routing byte to a constant
(`0xB464 = 4`) and see whether a button-then-headset sequence keeps SPP alive while SCO
carries audio. The classifier overwrite (9B.2) is the thing to defeat for that test —
a two-byte NOP of the store at `0x01E7EC98` (`b[r5+0xD4] = r1`) plus a forced constant
is sufficient to try.

### 9B.6 Phase-0 live probe (decides everything, no flashing)

`tools/bt_multipoint_probe.py` automates the decisive experiment against a paired radio
(Linux/BlueZ, run as the *button* role first):

```
sudo python3 tools/bt_multipoint_probe.py <radio-mac> [--hold 2] [--ptt-hold 3] [--no-hfp]
```

It connects SPP (ch 2), holds it, then attempts HFP (ch 6) while held, then the reverse
order, and prints one of:

- `MULTIPOINT OK` — both links up simultaneously → Route A/B worth pursuing;
- `KICK-ON-CONNECT` — second connect succeeds but first drops → stack-level single-link;
- `SECOND LINK REFUSED` — page/conn refused (EBUSY caveat noted in output).

Until this runs on hardware, 9B.4 bounds the *app* layer but not the stack layer.

> [!NOTE]
> **UPDATE 2026-09-30 — stack layer answered (statically).** The public SDK's `btstack.a`
> API is explicitly multi-device: `__set_user_ctrl_conn_num()`, `is_1t2_connection()`,
> `get_total_connect_dev()`, per-address HFP/eSCO queries, and 1拖2 call
> pre-empt/restore (`__set_hfp_switch`/`__set_hfp_restore`). Two concurrent BR/EDR links
> are a supported stack feature; the single-device model is purely the H3 *app* layer.
> The probe still decides what TIDRADIO's build enables — see
> [Ch. 24 §24.4](24-jieli-ecosystem-sdk-toolchain.md#244-bt-stack--the-multipoint-answer-ch-22-open-question-b).

#### 9B.6.1 Probe results — RUN on hardware 2026-10-01 (radio `0B:FF:59:E8:85:92`)

Pairing note: the classic endpoint paired only after the KDE/BlueZ PIN popup was
approved (silent `bluetoothctl pair` did not complete it).

1. **Profile-level multipoint: OK.** `--ptt-hold 3` run: SPP ch2 + HFP ch6 connected
   concurrently from the host (each in ~0.03 s), SPP survived the HFP join, `+SPP=P`
   while both were up keyed the radio — which emitted `AT+MPTT=0` and
   `\r\n+CIEV: 2,1\r\n` on the HFP leg — and both links stayed alive; reverse order
   (HFP first, then SPP) also worked. Verdict line: `MULTIPOINT OK`.
2. **Two-ACL multipoint: KICK-ON-CONNECT.** With `tools/bt_spp_hold.py` holding SPP
   (host = button role), connecting a **real headset** to the radio killed the host's
   SPP link (radio voice-announced connect/disconnect throughout). A second *physical*
   device evicts the first.
3. **Reverse 2-ACL test: REFUSED — the radio is not even connectable.** Headset
   connected first, then `tools/bt_spp_hold.py` → `SPP connect … failed: [Errno 112]
   Host is down` in ~0 s. `EHOSTDOWN` = the page itself failed (no page-scan response),
   i.e. while a device is connected the radio stops accepting incoming connections at
   the baseband level — not an RFCOMM-level refusal (that would be `ECONNREFUSED`).

**Admission policy, fully characterised:** exactly **one active remote device**; a new
radio-initiated connection **evicts** the incumbent; incoming connections while
connected are **not possible** (radio not connectable). "Single-slot, evict-on-join."
For the stretch goal a patch therefore needs *both* (a) keep page scan on while
connected and (b) suppress the eviction — or the second device must be brought in the
way the headset was (radio-initiated), which for an SPP button means the radio must
dial out, see §9B.9.

**Reading.** The two probe legs come from one host, so BlueZ multiplexes ch2+ch6 over a
**single ACL** — i.e. one remote device with two profile connections, exactly what the
single device struct (§9B.4) tolerates. The headset test adds the second ACL, and that
is what the app evicts. So the ceiling is neither the link layer nor the profile layer:
it is the **app's single-active-device policy**. Route A therefore has a concrete,
narrow target — the eviction path taken when a new ACL connects (find it via the
connection-callback ops table §9B.1 / dispatcher §9B.2 and the disconnect call it makes).
The stretch goal (SPP button + HFP headset) needs no second audio device in the app
model — only that the SPP link is not evicted.

### 9B.7 Code space: none inside the app — but ~208 KiB of erased flash beyond it

> [!WARNING]
> **UPDATE 2026-09-30 — Route B caution.** The JLFS entry list extracted from our own
> firmware shows the erased span `0xCA000–0xFC000` lies **inside the `VM` entry**
> (`0xC9000`, size `0x34000`) — reserved for the append-only VM wear-leveling area.
> Route B (trampolines there) should be reconsidered before any hardware experiment.
> See [Ch. 24 §24.6](24-jieli-ecosystem-sdk-toolchain.md#%E2%9A%A0%EF%B8%8F-flash-map-caution-for-ch-23--route-b).

Two space results matter for any trampoline plan:

1. **Inside the app region there is no usable padding.** Every zero run ≥ 64 B was
   cross-checked against v1.0.44/v1.0.45 plaintext (`tools/freespace.py`) and scanned
   for pointers (every 2-byte-aligned LE word in the block range). The last surviving
   candidate, `0x01EA76DE` (364 B, all-zero in 44/45/50), died when a pointer at
   `0x01E52F26` (`r5 = 0x1EA77A0`) was found feeding it to a draw call at `0x01E507CC`
   — it is a runtime draw buffer, not padding.
   **Update 2026-09-30:** [Ch. 23](23-bluetooth-8-bt-ptt2.md) reclaimed the *head* of
   this run — the BT-PTT2 code occupies cave+0…+68, while the draw buffer starts at
   cave+194 (`0x01EA77A0`), 126 B clear — consistent with the hardware validation
   passing. The verdict stands for the whole run; only the first 194 B are usable,
   and only if code stays under that.
2. **Beyond the app there is a desert.** The hardware dump
   (`Dumps/dump_internal.bin`) shows `0x0CA000`–`0x0FC000` — **~208 KiB — completely
   erased (0xFF)**, with a 10-byte remnant at `0x0FD000`
   (`81 66 60 00 92 85 e8 59 ff 0b` — purpose unknown). The app ends at `0xC8FE0`
   because the *linker* says so, not because the flash is full. A scan of the full
   v1.0.50 disassembly finds **zero** references to any VA ≥ `0x01ECA000`, confirming
   the boundary is a build-time choice.

   If the SFC can map/read beyond the app end (very likely — uboot already read it in
   the dump; the open question is whether the *app's* SFC region table permits execute
   there), a trampoline at a hot site can jump into erased flash and run new code
   without touching the app's own layout. **Route B is alive.**

### 9B.8 Supporting results this session

- v1.0.44 / v1.0.45 app regions decrypted (`work/decrypted/v44_app_dec.bin`,
  `v45_app_dec.bin`) with the *raw* `.bin` fed to `tools/jl_sfcenc.py` (defaults
  `start=0x5000`, `base=0`). Feeding it the LFSR-only `.dec` files yields garbage —
  the two ciphers are independent layers.
- `tools/freespace.py` — zero-run verifier with a cross-version ALLZERO column;
  `code=` flags from `full.lst` are misleading (`0x0000` decodes as `nop`), trust the
  ALLZERO column.
- The classifier's only reference is the pointer stored by the setter in 9B.1 —
  `tools/findva.py 0x01E7EC28` → file `0x018450`. `tools/xref.py` alone finds nothing;
  always follow up pointer-table hits.

### 9B.9 Next steps

1. ~~Run 9B.6 on hardware~~ ✅ **done 2026-10-01** (§9B.6.1): profile-level multipoint
   OK; second physical device evicts the first.
2. ~~Reverse 2-ACL test~~ ✅ **done 2026-10-02** (§9B.6.1 item 3): `EHOSTDOWN` — the
   radio is not connectable while a device is connected. Refuse-new (page level) +
   evict-old (radio-initiated joins). Optional sanity checks: while the headset is up,
   does the radio still appear in `bluetoothctl scan on` (inquiry scan), and does
   `bt_spp_hold.py` work again immediately after the headset disconnects?
3. ~~**Static: locate the eviction path**~~ ✅ **done 2026-10-02** — the cap is the
   `user_ctrl_conn_num` 2-bit gate; the init setter, its caller, and the enforcement
   reader are all located in §9B.10.2, and `--conn-num=2` builds a one-byte test
   patch. Hardware test pending.
4. If the eviction is classifier-conditional, the 9B.5 constant-routing-byte experiment
   (2–4 byte patch) may combine with disabling the kick.
5. Route C (SDK rebuild with 1拖2) stays the fallback — the SDK is now on disk
   (`fw-AC63_BT_SDK`, `cpu/br23`); Route B (erased flash) is **deprioritised** —
   ch. 24 §24.6 showed the span is VM-reserved.

### 9B.10 The admission gate, found in the SDK (2026-10-02)

The 2025 `data_trans_sdk` bitcode (`cpu/br23/liba/btstack.a` is **LLVM IR bitcode**,
readable with the official toolchain's `clang -S -emit-llvm`) exposes the exact
mechanism:

- `__set_user_ctrl_conn_num(num)` (`user_interface.c`) writes a **2-bit field
  `user_ctrl_conn_num`** at bit 140 (byte 17, bits 4-5) of the global
  `_stack_config` struct — same byte as `auto_conn_device_num` (bits 0-3) and
  `hid_independent_flag` (bit 6). The SDK apps call `__set_user_ctrl_conn_num(1)`
  once at init (`apps/*/modules/bt/app_comm_edr.c:242`) — that single `1` is the
  one-device cap; the stack then enforces it (evict-on-join).
- The connectable toggle is app-side: `bt_hci_event_connection()` calls
  `bt_wait_connect_active_enable(0)` → `USER_CTRL_WRITE_CONN_DISABLE` (page scan off)
  on connect, re-enabled on disconnect — exactly the `EHOSTDOWN` we measured in
  §9B.6.1 item 3.

**Our firmware's copy (candidate):** a `_stack_config`-shaped initialiser sits at
VA **`0x01EC2064`**. It is the image's only copy of CoD `0x240404`
(`BD_CLASS_WEARABLE_HEADSET`), followed by the 8000/8000 timeouts that also appear
in the SDK default:

```
01EC2064  04 04 24 00 40 1f 40 1f 00 00 00 00 00 00 00 00
01EC2074  00 00 3c 35 00 11 08 04 23 01 46 1e 0a 00 00 00
```

Its layout matches **neither** SDK generation exactly (§9B.10.1). In the old-gen
layout the flag byte (+14) is `0x00`. In the 2025 layout +17 is also `0x00`. Under
the earlier guess of two extra i16 fields, the byte at +21 is `0x11` (auto-conn 1,
conn_num 1), but that alignment is **unproven**. No literal pointer to the blob, or
to anything in `0x01EC2000–0x01EC20FF`, exists in the image. Presumably it is copied
in bulk to RAM as part of `.bt_stack_data`.

#### 9B.10.1 Static matching against the older-generation SDK (2026-10-02)

**Older-gen reference recovered.** `fw-AC630N_BT_SDK/include_lib/liba/bd29/btstack.a`
is also LLVM IR bitcode. Copy each member to `*.bc` before running
`clang -S -emit-llvm`, because clang treats a `.o` input as linker input and emits
nothing. In that build, `__set_user_ctrl_conn_num` is a plain 32-bit RMW on struct
field 8 at byte offset 14 of a **packed** `_stack_config`:

```
w = *(u32*)(cfg + 14);  w = (w & ~0x30) | ((num << 4) & 0x30);  *(u32*)(cfg + 14) = w;
```

The AC630N apps call it as `__set_user_ctrl_conn_num(TCFG_BD_NUM)`
(`apps/spp_and_le/app_spp_and_le.c:60`, `apps/hid/app_keyboard.c:249`, …). In older
SDKs the cap is therefore a board-config macro, not a literal `1`.

Old-gen `_stack_config` layout, decoded from the bitcode's debug info:

| Byte.bit | Size (bits) | Field |
|---|---|---|
| 0 | 32 | `hci_dev_class` (CoD) |
| 4 / 6 / 8 | 16 each | `page_timeout` / `super_timeout` / `pending_sdp_handler` |
| 10 / 11 / 12 / 13 | 8 each | `update_battery_timeout` / `sbc_cap_bitpoola` / `support_profile` / `background_goback` |
| **14.0** | 4 | `auto_conn_device_num` |
| **14.4** | **2** | **`user_ctrl_conn_num`** ← the gate |
| 14.6 / 14.7 | 1 / 1 | `hid_independent_flag` / `support_aac` |
| 15.0–15.7 | 1 each | `support_aptx`, `support_ldac`, `support_msbc`, `simple_pair_en`, `display_battery`, `disable_sco`, `esco_coder_busy_flag`, **`hfp_switch`** |
| 16.0–16.3 | 1 each | **`hfp_restore`**, `own_remote_test_flag`, `music_break_in_flag`, `emitter_enable` |
| 17 | 2/2/4 | `io_capabilities` / `oob_authentication_data` / `authentication_requirements` |
| 18 / 19 / 20 / 21 | 8 each | `auto_pause_when_interrupt` / `sound_come_cnt` / `sound_go_cnt` / `phone_history_call_num` |
| 22 | 48 | `esco_addr` |

Field 8 is the stack's central feature-flag word. Its other setters are
`__set_auto_conn_device_num`, `__bt_set_hid_independent_flag`,
`__set_support_msbc/aac/aptx/ldac_flag` and `__set_simple_pair_flag`, all in
`user_interface.c`.

**Matching our image.** A full listing was regenerated with the official objdump into
`work/official/official.lst` (316,896 lines). The recipe is in ch. 24 §24.5.

- **No byte match** for either SDK generation's compiled setter. Neither the 2025
  40-bit RMW nor `& 0xFFFFFFCF` followed by `<< 4` / `& 0x30` appears as a
  contiguous sequence.
- Clear-bits-4–5 memory RMWs (`& 0xFFFFFFCF`) at `0x01E44D20`, `0x01E69ECA` and
  `0x01E71B7E` were inspected. All are peripheral or SFR bit twiddles (hardware base
  addresses). **None is the setter.**
- Two RMWs that set bits 4–5 to **1** remain **uninvestigated**:
  - `0x01E182CC`: byte at RAM `0xBF39`, `&~0x30 | 0x10`.
  - `0x01E038E4`: halfword `h[r0+2] & 0xFFFFFFCF | 0x10`, on a struct at `r4+96`.
- **One near-miss, probably a false lead:** `0x01E22A56–0x01E22A82` is a
  bitfield-store tail inside a 27-way `tbh` command dispatcher (prologue
  `0x01E22890`). It writes 2-bit fields of RAM byte **`0xC54C`** at shifts 2, 4 and 6
  (`<<2 &0xC`, `<<4 &0x30`, `<<6 &0xC0`), and the `<<4 &0x30` case has the exact
  conn_num shape. However:
  - The neighbouring fields do not follow the old-gen layout (4-bit/2-bit/1-bit/1-bit).
    The byte is laid out as four 2-bit fields.
  - The other readers of `0xC54C` (`0x01E0731E`, `0x01E073A2`, `0x01E07520`) sit in
    the LE HCI command builders. `0x01E073A2` extracts 2-bit fields of the byte and
    sends opcode **`0x2006`** (`LE_Set_Advertising_Parameters`) through the HCI-send
    helper `0x01E029DE`. Its neighbours send `0x200A`, `0x200C`, `0x200D` and
    `0x2013`.
  - **Reading:** `0xC54C` is most likely a **BLE advertising-config byte**
    (adv type, own/peer addr type, filter policy), not the BR/EDR conn gate.
    Recorded so it is not chased again.
- `0xC54C` is only ever referenced as an absolute immediate (4 sites). No pointer to
  a plausible struct base exists in the image: neither `0xC53E` (old-gen +14 base)
  nor `0xC53B` (2025 +17 base). `0xC538` is a linked-list head (`0x01E06A6E`).
- **Unfinished:** a scan of the old-gen objects for *readers* of field 8 bits 4–5,
  i.e. the enforcement site whose compiled form we would then match. It converted
  only `user_interface` because of the `.o`/`.bc` pitfall above, so it is
  inconclusive. Rerun it with `.bc` copies.

**Status.** The gate's mechanism and the old-gen layout are known. The H3's own
setter, its init call, and the RAM copy of `_stack_config` are **not yet located**.
Byte and shape matching has run out. Next options:

> **Resolved 2026-10-02 in §9B.10.2** — options 1 and 4 below are exactly where it
> was found; the text above is kept as the working record.

1. Check the two uninvestigated bits-4–5 := 1 RMWs (`0x01E182CC`, `0x01E038E4`).
   A conn_num init writes exactly that value.
2. Rerun the old-gen object scan correctly, so the *enforcement* reader
   (likely in the connection/page-scan path, `hci_vendor`/`gap`/`btstack_main`) can
   be fingerprinted.
3. Ghidra decompilation of the stack code region, followed by data-flow from the
   `0x01EC2064` blob's RAM copy.
4. Find the `.bt_stack_data` copy loop: a memcpy whose source range covers
   `0x01EC2064`. That gives the RAM base, and then field 8's absolute address.

Experiment once located: set the gate to 2 (init-call argument or the
flash-initialised byte) and rerun §9B.6.1. The stack may then hold two ACLs natively
(1拖2). This is **untested**, and the page-scan-off in the app's connect handler
would still have to be addressed for incoming joins.

#### 9B.10.2 Gate fully located — the `--conn-num` one-byte patch (2026-10-02, UNTESTED)

Resuming with the **official objdump as ground truth** (rebuild `/tmp/full.elf` per
ch. 24 §24.5). Our linear sweep `work/full.lst` **drifts around
`0x01E17xxx`–`0x01E18xxx`** — it mis-decoded the key instruction below as `|= 0x24`
and emits garbage `.word` lines there. Do not trust it in this cluster.

**Option 1 of §9B.10.1 was the hit: `0x01E182B0` is the setter.** The RMW at
`0x01E182CC` sits inside a small leaf function — the compiled form of
`__set_user_ctrl_conn_num(1)` with the argument **inlined** (the function takes no
parameters):

```
1e182b0:  [--sp] = {rets, r4}
1e182b2:   r0 = 0xBF39
1e182b8:   r1 = b[r0+3] (u) … r4 = b[r0+0] (u)      ; word @ RAM 0xBF39
1e182cc:   r1 = r4 & 0xFFFFFFCF                     ; clear conn_num bits 4-5
1e182d0:   b[r0+3] = r1>>24; b[r0+2] = r1>>16; b[r0+1] = r1>>8
1e182dc:   r1 |= 16                                 ; conn_num = 1   <-- PATCH SITE
1e182de:   b[r0+0] = r1
1e182e0:   rts
```

Consequences:

- **RAM base of `_stack_config` = `0xBF24`**; the flag byte is `0xBF39` = base + 21.
  This **proves the +21 alignment** that §9B.10 left unproven: the blob at
  `0x01EC2064` carries `0x11` at +21 (`auto_conn_device_num = 1`,
  `user_ctrl_conn_num = 1`), and the init code above re-asserts `1` regardless.
- **Single caller: `0x01E60EB0`**, inside the app BT-init sequence that calls the
  whole `__set_*` setter family (`0x01E182E2`, `0x01E18310`, `0x01E18340`,
  `0x01E18376` — the last stores `h[0xBF24+4] = 8000` etc., matching the 2025 IR's
  `page_timeout`/`super_timeout` setters). The H3 hard-codes `1` exactly like the
  2025 SDK demos, not `TCFG_BD_NUM` like the old gen.
- **pi32v2 `rN |= imm` encoding**: bytes `3N (0x20 | log2(imm))` —
  `0x22`=|4, `0x23`=|8, `0x24`=|16, `0x25`=|32, `0x26`=|64. So conn_num 1→2 is a
  **single byte, `0x24 → 0x25`, at VA `0x01E182DC`** (file `0x182DD`,
  flash `0x1D2DD`). Verified against the official objdump listing.

**Enforcement reader found too.** `0x01E1787C`:

```
r2 = uextra(word @ 0xBF39, p:4, l:2)   ; user_ctrl_conn_num
r1 = h[0x1A662] & 7
return r1 == r2                        ; "all configured devices connected?"
```

Six call sites — `0x01E17A26`, `0x01E21BC4`, `0x01E21E58`, `0x01E21F7E`,
`0x01E21FA6`, `0x01E60CB0` — app state-machine gates. The eviction itself lives in
the precompiled stack; whether it honours `conn_num = 2` is exactly what the
hardware test below decides.

**Tool support.** `tools/patch_h3plus_firmware_bluetooth.py` gained
`--conn-num=1|2` (EXPERIMENTAL): site `connum`, context-guarded, one byte.
`--show` recognises both states, `--conn-num=1` reverts. `tools/verify_actions.py`
grew seven connum cases (build, exactly-one-byte diff, `--show` clean, idempotent,
revert, refuse `--conn-num=3`). Both suites: **0 failures**.

**Hardware test — UNTESTED.** Build and flash (see `ARTIFACTS.md` §4 for the
`--sectors` route and read-back discipline):

```bash
python tools/patch_h3plus_firmware_bluetooth.py BIN/<stock>.bin work/cn2.bin \
    --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2
```

Plan: connect the TID-PTT button (SPP), then the headset (HFP); check both stay up
(no eviction), PTT still works, and which mic is live (last-connected-wins is an
acceptable outcome). If eviction persists, the cap is app-level, not the stack
gate: next targets are the connection-completion path in the app and the
`multi_bd_deal_handle` registration (§9B.1/§9B.2).

**Hardware test — RUN 2026-10-03: conn_num=2 does NOT lift the cap.** Flashed
`Dumps/dump_internal.bin --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2`
(site byte `31 25` verified in the written image). Behaviour unchanged, both
directions: headset paired+connected first, then the TID-PTT joins → *"Bluetooth
disconnected"* over radio **and** headset speaker (incumbent evicted); reverse
order (PTT up, then connect headset from the menu) → the PTT loses its link the
moment the headset connect starts. So `user_ctrl_conn_num` is **not** the (only)
enforcement point — the real cap lives elsewhere: the app's single-device model
(§9B.4, struct `0x102F0`) and/or a stack build compiled for one ACL link. The
gate patch stays available (`--conn-num`) as one necessary-but-insufficient piece.

## §9B.11 — The real cap: the stack's connection data model is `[1 x conn_info]`

*2026-10-03, static analysis of the SDK precompiled libraries (bitcode version 53,
disassembled with `llvm-dis-8` — the bundled JieLi clang 4.0.1 refuses the newer
bitcode; `llvm-dis-8` reads it fine).*

After the conn_num=2 hardware test failed (§9B.10.2), the enforcement was chased
through the precompiled `btstack.a` libraries shipped in both SDKs:

1. **`is_1t2_connection()` identified.** Old-gen `avctp_user.c` IR:
   `is_1t2_connection() = ((__user_info.field9 & 7) == (stack_configs_app.field8 >> 4 & 3))`
   — i.e. *connected count == conn_num*. This is byte-for-byte our reader
   `0x01E1787C` (`h[0x1A662] & 7`, `uextra(p:4,l:2)` of the flag word). So
   `user_ctrl_conn_num` is the **"max reached" threshold used for scan/connectability
   management** — exactly the `app_keyboard.c` pattern:
   `if (is_1t2_connection()) {scan off, conn off} else if (count==1) {conn on}`.
   Our image has exactly **6** call sites: 4 in `user_operation_control` (the
   `USER_CTRL` command switch at `0x01E21AF8`, `r14 = __user_info = 0x1A520`;
   field9 = `h[r14+322]` ✓), 1 in `user_send_cmd_prepare` (`0x01E17A26`), 1 in the
   app (`0x01E60CB0`). None of them rejects or evicts a link.

2. **The 1拖2 core (`multi_bd.c`) is absent from our build.** Old-gen bd29
   `multi_bd.o` carries real code (`multi_bd_init` registers `multi_bd_deal` into
   `user_interface_handler.multi_bd_deal_handle` = ops-table field 9 = RAM
   `0xBF48+0x24`; `multi_bd_deal` handles SCO steal/reject per the `hfp_switch`
   bit). In the **br23** library `multi_bd.c.o` is 1532 B with **zero functions** —
   compiled out. Consistent with our image: no extra `is_1t2_connection` callers,
   and the ops-table slot `+0x24` is never written. The HCI Connection-Request path
   (`hci_event_handler` case 4) calls `update_multi_bd_status(mac,1,type)` → NULL
   handler → falls through to plain accept/reject.

3. **The hard cap: `struct user_info_t` embeds `[1 x conn_info]`.** In *every*
   public SDK library build — bd29, br23, br25, br30, bd19, br34 — the host stack's
   global `__user_info` tracks exactly **one** BR/EDR connection
   (`{user_cmd_ctrl, run_loop, [1 x conn_info], ...}`). The stack's command path,
   `get_conn_for_addr()`, channel-state bits (`field9`: count=bits 0–2, slot=3–5)
   and every profile glue assume one ACL. A second physical device overwrites/evicts
   the incumbent — exactly what the hardware test showed, in both directions.

4. **The controller is NOT the limit.** br23 `btctrler.a` `bredr_link.c`
   `struct.bredr_table` contains `[4 x [80 x i8]]` / `[4 x ctrl_frame]` arrays —
   the baseband is built for up to 4 BR/EDR links. The single-device ceiling is
   entirely in the precompiled **host stack** (and mirrored in the app's own
   single-device struct `0x102F0`, §9B.4).

**Verdict: multipoint is not reachable by binary patching.** Flipping conn_num only
moves the scan-management threshold; the connection table itself is one entry deep
inside vendor-compiled code, with hundreds of call sites (`get_conn_for_addr`,
`updata_profile_channels_status`, the whole `USER_CTRL` machine) assuming it.
JieLi's 1拖2 products ship a *different, specially-built stack library* (the public
SDKs bundle only single-device builds; the `multi_bd.c` source exists but compiles
to nothing in the shipped configs). Realistic routes: (a) ask JieLi / TIDRADIO for a
multipoint br23 stack build, (b) port the bd29-gen `multi_bd` core + widen
`conn_info` in machine code (research-grade, fragile), or (c) single-device
workarounds — one device that carries both profiles (the probe already proved SPP +
HFP coexist on ONE link, e.g. a custom ESP32 "headset+PTT" combo, or a headset
whose button triggers PTT via HFP hook events).
