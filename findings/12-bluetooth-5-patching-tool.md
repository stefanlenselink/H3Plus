[<< Index](Findings.md)

# Bluetooth HFP — 5. The patch tool and first hardware results (9A.33–9A.41)

### 9A.33 ⭐⭐ The patch: `tools/patch_h3plus_firmware_bluetooth.py`

§9A.32's reframe is small enough to implement as **three bytes**. Both changes are in `tools/patch_h3plus_firmware_bluetooth.py`, which decrypts the app region, verifies a context signature at each site, applies the edits, re-encrypts and repacks.

| Patch | VA | flash | before | after |
|---|---|---|---|---|
| `duplex` | `0x01E7EC86` | `0x083C86` | `41 23` (`r1 = 0x3`) | `41 22` (`r1 = 0x2`) |
| `ptt` | `0x01E60A7E` | `0x065A7E` | `bf ea 34 58` (`call 0x01E4BAEA`) | `bf ea 70 8c` (`call 0x01E52362`) |

`duplex` redirects the classifier's unrecognised-name fall-through from mode 3 (TX from the radio's own mic) to mode 2 (TX from the BT mic, RX to BT), so **any** headset name is treated as a `TID-MIC` speaker-mic. The `TID-PTT` / `TID-MIC` / `TID-MIC-EAR` table entries are untouched, so a genuine TIDRADIO PTT button is unaffected.

`ptt` retargets the front-panel key handler's call from the pressed-key-set remove primitive to the SPP message-ring enqueue, turning the physical button into a virtual `+SPP=P` / `+SPP=R`. Both callees take the event in `r0` and return normally, so only the branch displacement changes. The displacement is recomputed by the tool from the §9A.26 rule (`target = site + 4 + sign_extend_23((A:B) << 1)`) rather than hardcoded.

#### Container layout — the app is not at `0x5000` in a `.fw`

A detail that cost a debugging round and is worth recording: `tools/patch_btname.py` assumes the app region begins at container offset `0x5000`, which is true for a **raw flash dump**. In a `.fw` **update file** it begins at **`0x5200`**:

```
FW/TD-H3-PlusV1.0.50.fw   0xCA1A0 bytes
  app region              0x5200 .. 0xC91E0   (0xC3FE0 bytes)
  flash address of app    0x5000              (unchanged - VA = off + 0x01E00000)
```

The SFC scrambler keys on the *app-relative* address, so using the wrong container offset yields plausible-looking garbage rather than an obvious failure. The tool therefore **detects** the offset by descrambling each patch site's context signature and accepting only the candidate where all of them match — which validates the offset, the chipkey and the firmware version in one step. `FW/TID-H3-Plus-1.0.47.fw` is correctly rejected.

Result: **3 ciphertext bytes changed**, nothing else, and the patched image re-disassembles as intended:

```
01E7EC86  41 22           r1 = 0x2            ; was r1 = 0x3
01E60A7E  bf ea 70 8c     call 0x01E52362     ; was call 0x01E4BAEA
```

#### Untested on hardware — three things to watch

1. The `ptt` patch **replaces** rather than augments the original call, so the key code is no longer withdrawn from the `0xFF59` pressed-key set. If the radio behaves oddly on key release (stuck key, repeat suppression), this is the first suspect.
2. The duplex-mode repeat bug (§9A.22 — only the first transmission works per connection) now applies to the physical button.
3. `0x01E5B2B4`, which the real SPP handler calls *before* each enqueue and which is probably a wake/notify for the ring consumer, is **not** replicated. The injected event may only be serviced on the consumer's next natural pass.

#### Applying it: two 4 KiB sectors, not a reflash

The same tool handles `BIN/TD-H3-PlusV1.0.50.bin` — the container-offset detection accepts the raw-flash layout (app at `0x5000`) as readily as the `.fw` layout (app at `0x5200`). For a raw flash image, **container offset == flash address**, so `--sectors` can export exactly the erase blocks that change:

```
python tools/patch_h3plus_firmware_bluetooth.py BIN/TD-H3-PlusV1.0.50.bin --sectors=work/sect
```

The three changed bytes fall in only two sectors:

| Sector | Bytes changed | Patch |
|---|---|---|
| `0x065000`–`0x065FFF` | 2 (`0x65A80`, `0x65A81`) | `ptt` |
| `0x083000`–`0x083FFF` | 1 (`0x83C87`) | `duplex` |

Each patch lands in its **own** sector, so the two can be flashed and evaluated independently (`--only=duplex` / `--only=ptt`).

#### Why writing these sectors is safe on this unit

Verified against `Dumps/dump_internal.bin`, the live 1 MB dump from the radio:

- Sectors `0x65000` and `0x83000` are **byte-identical** between the live flash and the distributed `.bin` — re-confirming §12A.4 at exactly the addresses being written.
- The exported sectors differ from the **live dump** in precisely the 2 and 1 intended bytes, and nothing else.
- The only bytes where live flash and the distributed `.bin` disagree at all are 31 device-specific bytes at `0x0C8FE0`–`0x0C8FFF`, entirely inside sector `0x0C8000` — untouched by either write.

That last point is the reason the sector route is preferable to a full reflash: the device-specific block and the VM area are never in the blast radius.

```
erase 0x083000 0x1000 ; write 0x083000 work/only_duplex_083000.bin   # stage 1
erase 0x065000 0x1000 ; write 0x065000 work/only_ptt_065000.bin      # stage 2
```

Rollback sectors carved from the live dump (`work/restore_065000.bin`, `work/restore_083000.bin`) restore either sector to its factory content.

### 9A.34 ⭐⭐⭐ Hardware results: duplex works, PTT does not — and the reason overturns §9A.32

Both patches were flashed and evaluated separately on the radio. The results split cleanly.

#### Patch A (duplex) — ✅ CONFIRMED WORKING, modes 2 and 4

A headset advertising as `BT TEST456` — a name matching nothing in the table — was paired and behaved as a duplex speaker-mic. Confirmed at **both** `--duplex-mode=2` and `--duplex-mode=4`, which also confirms the §9A.31 prediction that modes 2 and 4 are equivalent at the point of use.

This validates the whole approach: a **single byte** at flash `0x83C87` converts the unrecognised-name fall-through into a recognised routing class, and the rest of the accessory stack follows.

#### Patch B (PTT) — ❌ FAILED, and the reasoning behind it was wrong

Observed: the front-panel PTT starts a transmission, but **no BT audio** — the radio still uses its internal mic. Meanwhile SPP-driven PTT via `bt_spp_hold.py` on Linux still works correctly, with the radio replying `AT+MPTT=0`.

Two independent findings explain it, and both contradict §9A.32.

**1. `0x01E60A7E` is not in a key handler. It is in a teardown routine.**

The enclosing function starts at `0x01E609FE`:

```
01E609FE  [--sp] = {r8-r4}
...
01E60A3A  r0 = 0xE / 0xF / 0x10 / 0x11      ; a batch of key codes
01E60A48  call 0x01E4BAEA                   ; remove each from the pressed-key set
01E60A4C  call 0x01E4BB24
...
01E60A70  if (r0 == 0x80) goto 0x01E60A7C   ; r0 = [obj+0x14], a STORED event
01E60A74  if (r0 != 0x20) goto 0x01E60A82
01E60A78  r0 = 0x2A   /   01E60A7C  r0 = 0x2B
01E60A7E  call 0x01E4BAEA                   ; <-- the patched site
01E60A82  ...list unlink, free, timer cancel...
```

It has only two callers (`0x01E60C4C`, `0x01E7FD8C`), it begins by withdrawing a *batch* of key codes, and everything after the patch site is object teardown. The `0x2A` / `0x2B` here are being **removed during cleanup**, not generated on a press. The patch therefore injected a ring event during connection teardown — which is exactly why pressing the button changed nothing.

**2. The pressed-key set at `0xFF59` has no reader.**

Searching every 6-byte constant load of `0xFF59` (`[\xc0-\xcf]\xff\x59\xff\x00\x00`) across the whole image returns **exactly two sites**:

| VA | Register | Role |
|---|---|---|
| `0x01E4A9DA` | r2 | add |
| `0x01E4BACA` | r2 | remove |

Nothing ever reads it. It is write-only bookkeeping and cannot be what keys the transmitter. The §9A.32 claim that this path "keys the transmitter through the radio's native local-key machinery" is **withdrawn**.

#### ⚠️ Patch B is also unsafe

The genuine SPP arm always calls `0x01E5B2B4` (pop-front) **before** the enqueue at `0x01E52362`. The enqueue only pushes — it increments `b[gp+0x76]` and writes `b[gp+0x566+count]`. Patch B pushes without popping, so every press/release **leaks a ring slot** and the writes can eventually walk past the ring into adjacent RAM.

Patch B is now excluded from the tool's default patch set and must be requested explicitly.

### 9A.35 ⭐⭐⭐ The routing-mode byte has exactly six readers — and only modes 5/6 touch audio

> ⚠️ **Superseded in part by §9A.41.** The enumeration below only matched loads whose base register is `r0`. Re-scanning with any base register finds **13** candidate reads. Two of them, in the standby handler for key code `0x2A`, drive the same audio GPIOs for **modes 1, 2 and 4**. "Only modes 5/6 touch audio" is wrong. Mode 6 was tested on hardware and **failed** (§9A.40).

Rather than guess again, every read of `b[0xB390 + 0xD4]` was enumerated (pattern `[\x50-\x5f]\xee\x04.` with the low nibble of byte 3 selecting the destination register). There are **six**, and no more:

| Site | Gate | What it does |
|---|---|---|
| `0x01E51FE0` | `D2==2` and mode ∈ {2,3,4} | returns 0 — a suppression gate |
| `0x01E5B368` | — | the `+POWER=0` handler (§9A.36) |
| `0x01E5DFCA` | `D2==2` and mode ∈ {1,2} | selects a UI/timing value from `+0xE8` |
| `0x01E72C3C` | `D2==2` and **mode ∈ {5,6}** | calls `0x01E50398` / `0x01E503CA` |
| `0x01E72DCC` | `D2==2` and **mode ≥ 5** | sends `+SPP=R` via `0x01E5B28E` |
| `0x01E7EEAE` | mode ∈ {1..4}, non-zero | starts a 1000 ms timer |

`0x01E50398` and `0x01E503CA` are the **audio-path GPIO setters** — each calls `0x01E001BA` with a pin number (`0x20` and `0x00` respectively) and caches the resulting state at `+0xE6` / `+0xE7`.

The consequence is stark: **modes 1–4 never touch the audio routing at all.** The only code that drives those GPIOs, and the only code that emits `+SPP=R` autonomously, is gated on modes 5 and 6.

#### Where modes 5 and 6 come from — not the name table

The classifier's link-class branch runs *before* any name comparison:

```
01E7EC36  r3 = b[gp + 0xB10]
01E7EC40  r0 = r3 & ~0x3f               ; link / device class
01E7EC4A  if (r0 != 0x80) goto 0x01E7EC58   ; -> name matching
01E7EC4E  r0 = 0x5 ; b[r5+0xD4] = r0
01E7EC54  r1 = 0x6 ; goto 0x01E7EC90
...
01E7EC90  (common tail)
01E7EC98  b[r5+0xD4] = r1               ; overwrites with 6
```

Note the mode-5 store at `0x01E7EC50` is immediately superseded by the tail store at `0x01E7EC98`, so **mode 5 is almost certainly dead in practice** and class `0x80` really means mode 6.

This finally explains the negative results of §9A.5 / §9A.11 / §9A.12 from a different angle: the name table can only ever produce 1–4, and 1–4 are precisely the modes with no audio-routing code behind them.

#### The resulting experiment

`0x01E7EC86` — the byte patch A already changes — feeds the same `b[r5+0xD4] = r1` store. Writing `r1 = 6` there (`41 23` → `41 26`) puts an ordinary named headset into the class that does reach the audio GPIOs. `--duplex-mode` was widened to accept 5 and 6 for this test.

> **Status: TESTED — FAILED (§9A.40).** This was an inference from "modes 5/6 are the only ones touching audio routing", not a proof that it would key TX from the BT mic. What pins `0x20` / `0x00` physically switch has not been confirmed, and the path has not been traced back to a front-panel key press.

### 9A.36 The SPP command string table resolved — and `+POWER=0` identified

The SPP dispatcher at `0x01E5B300` compares against strings at offsets from `r6 = 0x01E9B74D`. Resolving that base yields the complete table:

| String | VA | Handler | Action |
|---|---|---|---|
| `+SPP=P` | `0x01E9B74D` | `0x01E5B37A` | pop `0x01E5B2B4`, `r0 = 0x2A`, push `0x01E52362` |
| `+SPP=R` | `0x01E9B754` | `0x01E5B380` | pop, `r0 = 0x2B`, push |
| `AT+MPTT=0` | `0x01E9BC3C` | `0x01E5B3A8` | `call 0x01E5A20A` |
| `AT+MPTT=1` | `0x01E9BC46` | `0x01E5B3A2` | `call 0x01E5993E` |
| `CH_KEY=+` | `0x01E9BA1F` | `0x01E5B3AE` | — |
| `CH_KEY=-` | `0x01E9BA28` | `0x01E5B3B4` | — |
| `+POWER=0` | `0x01E9BA31` | `0x01E5B362` | see below |

**Correction:** an earlier working hypothesis held that the block at `0x01E5B362` — which loads the routing mode and dispatches on it — was part of the `+SPP=P` path, implying SPP PTT was mode-aware at the point of enqueue. **It is not.** That block is the `+POWER=0` handler. The real `+SPP=P` / `+SPP=R` arms are plain pop-then-push with **no mode check at all**; the routing mode is honoured later, by the ring consumer.

#### What `+POWER=0` does

```
01E5B362  r0 = 0xB390
01E5B368  r0 = b[r0 + 0xD4]     ; routing mode
01E5B36C  30 e8 01 80           ; conditional branch, skips one instruction
01E5B370  r0 = 0x6              ; (skipped when taken)
01E5B372  r1 = 0x0
01E5B374  call 0x01E4ED02       ; post message to the 'my_ui' task
01E5B378  goto <common tail>
```

`0x01E4ED02` is a **generic message-post to the `my_ui` task** — it loads the literal `"my_ui"` (`0x01E9B607`) and walks a subscriber table at `0x10F1A8` with a bounded retry loop. Signature is `post(r0 = message_id, r1 = param)`. All 11 call sites pass a small literal id:

| id | Sites |
|---|---|
| 1 | `0x01E6148E` |
| 2 | `0x01E521CC` (immediately after `call 0x01E503CA`) |
| 4 | `0x01E5A548` |
| 5 | `0x01E4F776`, `0x01E531BE` |
| 6 | `0x01E5B374` ← `+POWER=0` |
| 7 | `0x01E71DDE` |

So `+POWER=0` posts **UI message id 6**, with the routing mode participating in selecting it. `POWER` sits in the UI string pool amongst `Freq:`, `Code:`, `RSSI:`, `TX CW`, `Input` — display-field labels — which points at a **TX power-level display/toggle** rather than a device power command.

> Two caveats: the consumer end of UI message id 6 has not been decoded, so the "TX power level" reading is inferred from the string-pool neighbourhood, not proven. And `pi32dis` cannot decode `0xE830`; the manual §9A.31 decode yields "compare r8" which is inconsistent with `r0` having just been loaded. The *structure* (it skips exactly the `r0 = 0x6`) is solid; the condition is not.

### 9A.37 Free space for a future trampoline

If a patch ever needs more than an in-place instruction rewrite — e.g. a pop-then-push sequence matching the genuine SPP arm — these runs of `0x00` in the app region are large enough to host it:

> ⚠️ **Not verified as free (§9A.45).** `0x01EB34EA` is preceded by RGB565 pixel data (`de fb 42 28 …`), so its zeros are very likely black pixels of a bitmap. The code region (`< 0x01E90000`) has no zero or `0xFF` run of 64 bytes or more. Treat every entry below as data until proven otherwise.

| VA | Flash | Bytes |
|---|---|---|
| `0x01EB34EA` | `0x0B84EA` | **1558** |
| `0x01EB276A` | `0x0B776A` | 1196 |
| `0x01EB08C8` | `0x0B58C8` | 1166 |
| `0x01EC2118` | `0x0C7118` | 1036 |
| `0x01EC1C8D` | `0x0C6C8D` | 899 |
| `0x01EC2775` | `0x0C7775` | 811 |

### 9A.38 Full-image flashing — the device-specific block must be spliced

A full reflash is riskier than the sector route because the distributed `.bin` is **not** a faithful image of a provisioned device. At flash `0xC8FE0`–`0xC8FFF` the `.bin` carries 32 bytes of `0xFF` placeholder, where the live radio holds real per-unit data:

```
.bin  : ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
live  : 0400000000000000000001000000000003011eff0d211c0067de8f434abe7800
```

Writing the stock `.bin` verbatim would erase it. The safe full image is built by splicing the live dump's block back in:

```python
raw = bytearray(open('work/mode6.bin','rb').read())
dump = open('Dumps/dump_internal.bin','rb').read()
raw[0xC8FE0:0xC9000] = dump[0xC8FE0:0xC9000]
```

| Artifact | SHA256 | Diff vs live flash |
|---|---|---|
| `work/full_write_mode4_safe.bin` | `37b77388e891e51ce31e084619d47cf653646504de825c0393015fec8d832b86` | 1 byte (`0x83C87`) |
| `work/full_write_mode6_safe.bin` | `e0dfeccd25af7ea2d9f6fbdc651281080b4570364ba0a49764db3b16b5746fe6` | 1 byte (`0x83C87`) |

Because both are derived from the **pre-patch** dump, flashing either also restores sector `0x065000` to factory — which conveniently reverts the known-bad patch B in the same operation.

> The image covers `0x0`–`0xC9000` only. The VM area at `0xC9000`+ (pairing records, BT identity) is above the end of the file and is never written.

### 9A.39 Tool changes

`tools/patch_h3plus_firmware_bluetooth.py`:

- `--duplex-mode` widened from 1–4 to **1–6**, with mode 5/6 labelled as the untested audio-routing class.
- Patch `ptt` excluded from the default set (`DEFAULT_PATCHES = ["duplex"]`); it must now be requested with `--only=ptt`.
- Docstring corrected throughout: the claims that `0x01E60A7E` sits in a key handler, and that the `0xFF59` set "keys the transmitter", are marked as disproven with the evidence above.

```console
$ python tools/patch_h3plus_firmware_bluetooth.py BIN/TD-H3-PlusV1.0.50.bin work/mode6.bin \
      --only=duplex --duplex-mode=6 --sectors=work/m6
[+] duplex
      VA 0x01E7EC86 / flash 0x00083C86
      41 23  ->  41 26
      mode 3 (factory default ...)  ->  mode 6 (link class 0x80; the ONLY class
      that reaches the audio-routing GPIOs)  [UNTESTED]
plaintext bytes changed: 1
ciphertext bytes changed: 1  (0x83C87 - 0x83C87)
```

### 9A.40 Hardware result: mode 6 does not enable the BT mic on the radio's PTT

The user did a full flash of `work/full_write_mode6_safe.bin`. The physical PTT still transmitted from the radio's own microphone. §9A.41 explains why:

- The mic-mux code that runs on PTT is gated on routing modes **{1, 2, 4}**, not {5, 6}.
- Modes 5/6 are the **Odmaster (OD) phone-link** classes. Only the `OD PTT` action uses them (§9A.42).

`DUPLEX_LABELS[6]` in the tool now reads *"TESTED: no BT mic on PTT"*.

### 9A.41 ⭐⭐⭐ One virtual key queue, one standby switch — and why only `+SPP=P` gets the BT mic

#### The virtual key queue

Physical keys and the SPP PTT commands share **one** virtual key-code queue:

- The queue lives at `0x102F0 + 0x566`. The count is at `+0x76`. The push routine `0x01E52362` does no bounds check.
- Codes are pushed by `0x01E52362` and popped via `0x01E5B2B4`.
- `+SPP=P` pushes `0x2A` and `+SPP=R` pushes `0x2B` (`0x01E5B37A` / `0x01E5B380`).
- The key scanner `0x01E5237E` pushes the physical-key codes.

The firmware therefore cannot tell *who* pressed PTT, only *which code* arrived. The mic source is decided entirely by the code.

#### The key scanner and the ADC key ladder

The debouncer `0x01E52298` works on the ADC key ladder. Windowing that reading gives three debounced key states, each `0xE` = pressed and `0xD` = released:

| State byte | Key | Setting bytes (base `0x102F0`) | Codes pushed |
|---|---|---|---|
| `0x102D6` | **A = main PTT** | — | `0x28` press / `0x29` release |
| `0x102DC` | **B = PF1** | S `+0x1058`, L `+0x1059` | `0x2C` press/short, `0x2D` release (hold modes), `0x2E` long, `0x2F` long-release |
| `0x102DE` | **C = PF2** | S `+0x105A`, L `+0x105B` | `0x30` press/short, `0x31` release (hold modes), `0x32` long, `0x33` long-release |
| (third key, `+0x105C/+0x105D`) | unidentified | `+0x105C`, `+0x105D` | `0x34`–`0x37` |

Key A is PTT. The evidence is that the press path sets the TX-VFO byte `b[+0x46]`: it forces `0` (VFO A) whenever PF1 or PF2 is set to PTT2 (value 7), and otherwise uses the current VFO (`b[+0x77] >> 7`). A separate GPIO 6 input (`0x01E52434`) can also set key A's state; it is probably an external/accessory PTT line.

PF1/PF2 behave in one of two ways depending on the S-press setting:

- **Setting 7 or 8** (`PTT2` or `OD PTT`, see below): the key acts as a **hold** key. It pushes the press code as soon as it goes down (`0x01E5253C` / `0x01E52678`) and the release code when it comes up (`0x01E52578` / `0x01E526AE`).
- **Any other setting:** the key is a tap/long-press key. A tap (< `0x50` ticks) pushes the press code *on release*. A long press (≥ `0x65` ticks) pushes the long-press code.

This matches the manual's note that "if PF1 S Press is set to PTT2 or OD PTT, PF1 L Press cannot be set".

#### The standby key switch — `tbh` at `0x01E78ED8`

The standby consumer dispatches on `code − 1`. The relevant entries are:

| Code | Handler | Action |
|---|---|---|
| `0x28` | `0x01E79464` | skipped if `b[+0x190]` is set or `b[+0x89A]==2`; else **`call 0x01E5993C` (TX start)**. Nothing else. |
| `0x29` | `0x01E79484` | same gates; `call 0x01E5A138` (TX stop) |
| `0x2A` | `0x01E794A2` | see below |
| `0x2B` | `0x01E79516` | if `b[0xB390+0xEE]==1`: `0x01E17E62(0xA)`, `0x01E17E62(0x1C)`, TX stop, clear `+0xEE`, then the same mode-gated block |
| `0x2C` | `0x01E79554` | `0x01E75DBE(b[+0x1058])` — execute PF1 S-press action |
| `0x2D` | `0x01E79588` | `0x01E75E76(b[+0x1058])` — PF1 S-release action |
| `0x2E` / `0x2F` | `0x01E7958E` / `0x01E795AC` | PF1 long press / long release (`+0x1059`) |
| `0x30`–`0x33` | `0x01E795B2`… | PF2 equivalents (`+0x105A` / `+0x105B`) |

The `0x2A` handler is the only PTT path that touches the audio routing:

```
01E794A2  if (b[+0x47] != 0) exit
01E794B8  call 0x01E17E62(0x6D, 9, tbl+0x6D0)   ; BT/audio stack messages
01E794C2  call 0x01E5F18A(1, 0)
01E794CC  call 0x01E17E62(0x09, 0, 0)
01E794D6  call 0x01E17E62(0x1B, 0, 0)
01E794E0  b[+0x46] = b[+0x77] >> 7                ; TX on current VFO
01E794E4  call 0x01E5993C                         ; TX start (same as 0x28)
01E794E8  b[0xB390+0xEE] = 1                      ; "SPP PTT active"
01E794EC  r0 = b[0xB390+0xD4]                     ; routing mode
01E794F0  if (r0 > 4) exit
01E794F4  if !((1 << r0) & 0x16) exit             ; modes 1, 2, 4 only
01E79500  call 0x01E50398(0)                      ; audio GPIO 0x20 -> 0
01E79506  call 0x01E503CA(0)                      ; audio GPIO 0x00 -> 0
01E79510  call 0x01E5DFA0(2, b[+0x3A])
```

This explains all the hardware observations:

- `+SPP=P` gets the BT mic in modes 2 and 4, where those GPIOs are switched.
- The front-panel PTT (`0x28`) only calls TX start, so it always uses the radio's own mic.
- Mode 6 fails the `0x16` mask.

The `0x16` mask decode relies on the `E194 0012` instruction, which pi32dis cannot decode. It is read from the structure and matches the hardware.

#### Correction to §9A.35 — more routing-mode readers

The §9A.35 scan only matched base register `r0`. Allowing any base register finds these reads of `b[x + 0xD4]`:

- `0x01E51FEE`, `0x01E5B368`, `0x01E5DFE0`, `0x01E72C4A`, `0x01E72DD2`, `0x01E7EEB4`: the six from §9A.35
- `0x01E794EC`, `0x01E7953C`: the `0x2A` / `0x2B` handlers, base `r4 = 0xB390`
- `0x01E61270`, `0x01E61790`, `0x01E733FC`, `0x01E73482`, `0x01E7358C`: base register value not yet confirmed

---

*[<< Index](Findings.md)*
