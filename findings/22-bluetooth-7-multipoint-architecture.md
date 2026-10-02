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
2. **Reverse 2-ACL test** (quick, hardware): headset connected first, then
   `tools/bt_spp_hold.py` from the host — does the SPP connect get *refused*, or does it
   *evict the headset*? Distinguishes "evict-old" from "refuse-new" admission, which
   decides what the patch must change.
3. **Static: locate the eviction path** — the new-ACL-connect handler reached via the
   ops table (§9B.1)/dispatcher (§9B.2) and the disconnect call it makes on the existing
   link; the official LLVM objdump (Ch. 24 §24.5) + `tools/xref.py`/`findva.py` are the
   tools. Ghidra (quarkslab/ghidra-jieli) makes this tractable at scale.
4. If the eviction is classifier-conditional, the 9B.5 constant-routing-byte experiment
   (2–4 byte patch) may combine with disabling the kick.
5. Route C (SDK rebuild with 1拖2) stays the fallback — the SDK is now on disk
   (`fw-AC63_BT_SDK`, `cpu/br23`); Route B (erased flash) is **deprioritised** —
   ch. 24 §24.6 showed the span is VM-reserved.
