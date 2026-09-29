[<< Index](Findings.md)

# Bluetooth HFP — 3. PTT handler disassembly and AT+MPTT direction (9A.23–9A.27)

### 9A.23 Locating the PTT handler — the real dispatcher found

> ⚠️ **CORRECTED BY §9A.26.** Every `call` target and several branch targets in this section were produced by a disassembler with two bugs (missing sign extension on 32-bit calls, and PC-relative displacements based on the current instruction instead of the next). The *structure* described below — the string table, the unified compare chain, the fixed-length `memcmp` arguments, the `0x2A`/`0x2B` event codes — is correct and was re-verified. The **numeric call targets are not**. In particular the "event dispatcher" at `0x0265235E` does not exist; the real target is `0x01E52362`. See §9A.26 before reusing any address from this section.

Step 1 of the firmware-modification route (§9A.22's consequence: keying must arrive over Bluetooth, so the alternative is to change the firmware). **Read-only analysis; nothing written to the radio.**

#### The `AT+MPTT` handler was never the right target

Disassembling around the known `AT+MPTT=0` xref at `0x05FDE2` shows a **generic AT-command string-compare chain**, not a PTT implementation. This is consistent with §9A.20: `AT+MPTT` is not the protocol the button uses. Chasing those two xrefs further would have been wasted effort.

#### Finding the real one — via the `+SPP=` strings

The actual protocol strings live at file offset `0x9B74D`:

```
"\r\nOK\r\n\0"  "AT+ATD\0"  "+SPP=P\0"  "+SPP=R\0"  "udisk0\0"
```

Address mapping for `work/app_dec.bin` (confirmed against the known `AT+MPTT=0` anchor at `off=0x9BC3C` / `va=0x01E9BC3C` / `flash=0x0A0C3C`):

```
va    = file_offset + 0x01E00000
flash = file_offset + 0x5000
```

Three code references to `+SPP=P` (`va 0x01E9B74D`):

| Site | Role |
|---|---|
| `0x01E5B2FE` | ⭐ **the RX command dispatcher** — the one that matters |
| `0x01E72C86` | TX side: copies `+SPP=P` into a buffer and sends it |
| `0x01E7EBCE` | in the `0x083Bxx` whitelist region (§9A.11) |

#### ⭐ The dispatcher at `0x01E5B2F4` — a single unified command table

One function compares the incoming string against **every** vendor command in turn, `+SPP=` and `AT+MPTT` alike:

```
01E5B2FE  r6 = 0x1E9B74D          ; "+SPP=P"
01E5B304  r2 = 0x6                ; compare 6 bytes
01E5B30A  call memcmp             ; → match: event 0x2A
01E5B310  r1 = r6 + 0x7           ; "+SPP=R"        → event 0x2B
01E5B31C  r1 = r6 + 0x4F9         ; "AT+MPTT=1"  (= 0x1E9BC46)
01E5B32A  r1 = r6 + 0x4EF         ; "AT+MPTT=0"  (= 0x1E9BC3C)
01E5B338  r1 = r6 + 0x2D2         ; 8-byte command
01E5B346  r1 = r6 + 0x2DB         ; 8-byte command
01E5B354  r1 = r6 + 0x2E4         ; 8-byte command
```

Two facts fall straight out of this:

1. **The compare length is an explicit argument** (`r2 = 6`, `r2 = 9`, `r2 = 8`) — a fixed length per command, **not** a NUL-terminated compare. This settles the long-open "prefix or full-length?" question of §9A.11 for the *command* parser.
2. **`AT+MPTT` is parsed by the same function as `+SPP=P`.** It was never an unimplemented command — so §9A.13's `ERROR` responses were a precondition failure, not a missing feature.

#### ⭐⭐ Every command converges on one event dispatcher

The matched branches all funnel into a single tail:

```
01E5B37A  call 0x01E5B2B2   ; reply/ack helper
01E5B37C  r0 = 0x2A         ; ← "+SPP=P"  (PTT press)
01E5B382  r0 = 0x2B         ; ← "+SPP=R"  (PTT release)
01E5B384  call <event dispatcher>
...
01E5B3B0  r0 = 0x3
01E5B3B8  r0 = 0x4
```

So **`+SPP=P` does nothing more than raise internal event `0x2A`**, and `+SPP=R` raises `0x2B`. The Bluetooth PTT is a thin shim over the firmware's ordinary event queue.

This is the **favourable case** identified before starting: there is a known-good reference path in the same binary, and the job becomes redirecting an existing call site rather than inventing behaviour.

#### Candidate local-key handler

Scanning for other sites loading the same event codes gives 16 sites for `0x2A` and 15 for `0x2B`. The interesting ones are the **pairs** — a press/release decision in one place:

| Site | Shape |
|---|---|
| `0x01E60A78` / `0x01E60A7C` | ⭐ reads a state byte `[r0+0x14]`, tests it against `0x80` and `0x20`, then selects `0x2A` or `0x2B` |
| `0x01E4EDE6` / `0x01E4EDFA` | raises `0x2A` then falls through a chain of helper calls |
| `0x01E381AA` / `0x01E38198` | inside a `tbb` jump table — a key-event dispatcher |

`0x01E60A78` is the leading candidate for the physical key: a `0x80`/`0x20` bitmask test is the classic shape of a key down/up flag.

#### Where this leaves the firmware route

**Encouraging:** both PTT paths appear to converge on one event code, so the mic-source decision is almost certainly made *downstream* of the event — meaning one routing variable, not two parallel audio paths.

**Not yet established:** *where* that downstream decision reads the routing mode. Until that is found it remains possible that the local key is special-cased for latency and bypasses the Bluetooth audio mixer entirely — the pessimistic case from §9A.22, which would mean no small patch exists.

⚠️ **Disassembler caveat:** short-branch displacements are decoded **2 bytes off** in places (targets land on the `goto` immediately preceding the real instruction), and linear decode desynchronises after data-in-code. Decode each branch target explicitly with `--off` rather than trusting a long linear listing.

**Next step (step 2):** confirm `0x01E60A78` is the physical key by identifying its caller, then follow event `0x2A` into the dispatcher to find the mic-source selection and whether it reads the whitelist routing mode.

---

### 9A.24 ⭐⭐⭐ `AT+MPTT` runs in the OPPOSITE direction — the radio sends it to us

A live capture during step 2 overturns the entire `AT+MPTT` interpretation held since §9A.2. With `bt_spp_hold.py` simply holding the SPP link open, the **radio transmits `AT+MPTT=…` to the accessory, unprompted**:

```
ptt> p
>> +SPP=P   PTT DOWN
<< 41 54 2b 4d 50 54 54 3d 30   b'AT+MPTT=0'
ptt> r
>> +SPP=R   PTT UP
<< 41 54 2b 4d 50 54 54 3d 30   b'AT+MPTT=0'
<< 41 54 2b 4d 50 54 54 3d 31   b'AT+MPTT=1'
<< 41 54 2b 4d 50 54 54 3d 30   b'AT+MPTT=0'
```

**`AT+MPTT` is not a command the accessory sends to the radio. It is a STATUS NOTIFICATION the radio pushes to the accessory.** The protocol is asymmetric:

| Direction | Message | Meaning |
|---|---|---|
| accessory → radio | `+SPP=P` / `+SPP=R` | **command**: key / unkey the transmitter |
| radio → accessory | `AT+MPTT=1` / `AT+MPTT=0` | **notification**: see §9A.25 — it is **RX squelch**, not TX state |

The observed triggers confirm it is a state broadcast and not a reply: the user saw it arrive when **another radio transmitted**, when **we** sent `+SPP=`, and when the **local PTT key** was pressed.

#### This retroactively explains the single most persistent dead end in the project

Every `AT+MPTT` experiment in §9A.13 returned `ERROR`. The explanation was never a missing precondition, a wrong name, or a locked vendor parser:

> **We were sending the radio its own outbound notification.** It replied `ERROR` because an accessory-to-radio `AT+MPTT` is not a valid message in this protocol at all.

Months of the investigation treated `ERROR` as a puzzle to be unlocked. It was simply the correct response to a malformed request. This is the fourth time a hardware observation has corrected a static-analysis conclusion (§9A.22 lists the others), and it is the most expensive one.

#### Reconciling it with the shared parser in §9A.23

§9A.23 found `+SPP=P` and `AT+MPTT=0/1` compared in the **same** dispatcher at `0x01E5B2F4`, and concluded from this that `AT+MPTT` was "implemented after all". That conclusion needs correcting: the shared table is almost certainly the **accessory-side** parser, present in the radio's firmware because JieLi ships one common SPP command table to both ends of the product family (the radio and the `TID-PTT` button run closely related builds). The radio *contains* code to parse `AT+MPTT`, which is why the strings and the compare exist — but the live radio, in radio role, rejects it.

This also explains the otherwise odd fact that a single function parses both halves of an asymmetric protocol.

#### What this is good for

A genuine bidirectional channel now exists. Its exact semantics are established in §9A.25 — **not** the TX oracle first assumed here.

---

### 9A.25 ⭐⭐ `AT+MPTT` is an RX SQUELCH indicator, not a TX-state indicator

§9A.24 assumed `AT+MPTT=1` meant "the transmitter is now keyed". A controlled test disproves that. Three transmissions **from a distant radio**, of deliberately different lengths, with our SPP link idle and sending nothing:

| # | `=1` at | `=0` at | Duration | Intended |
|---|---|---|---|---|
| 1 | `+6.138s` | `+8.499s` | **2.361 s** | normal |
| 2 | `+12.801s` | `+20.577s` | **7.776 s** | long |
| 3 | `+23.912s` | `+24.317s` | **0.405 s** | short |

Three transmissions in, three `=1`/`=0` pairs out, with the measured durations in exactly the intended rank order. The correspondence is unambiguous:

| Message | Meaning |
|---|---|
| `AT+MPTT=1` | **RX squelch OPEN** — the radio is receiving a signal |
| `AT+MPTT=0` | **RX squelch CLOSED** — channel idle again |

This is a **receive** indicator. Our own transmissions — whether from `+SPP=P` or from the radio's front-panel key — produce only `AT+MPTT=0`, never `=1`.

#### Consequence: the proposed decisive test for the repeated-PTT bug is invalid

§9A.24 proposed using `AT+MPTT=1` after a second `+SPP=P` to prove whether the radio still keyed. **That test cannot work** — a local transmission never produces `=1` in the first place. The reasoning was built on a mapping that had been explicitly flagged as provisional in the same section, and the flag was then ignored one paragraph later.

The repeated-PTT bug (§9A.22) therefore remains **without** a cheap decisive instrument, and the hypotheses there stand unresolved.

#### Why `AT+MPTT=0` appears around our own PTT

The `=0` seen shortly after `+SPP=P` and after `+SPP=R` is consistent with the radio **re-asserting squelch-closed** whenever its audio state is re-evaluated: keying TX necessarily ends any RX, so the receiver reports idle. This is a side effect of the state change, not an acknowledgement of the command. Notably it means **no message confirms a PTT command** — `+SPP=P` remains entirely fire-and-forget (§9A.20).

#### What it *is* good for

1. **A genuine busy/squelch indication for the accessory** — an accessory can know when the channel is active without any audio analysis. This is almost certainly its purpose in the real product: lighting an LED on the speaker-mic.
2. **Precise RX timing**, to millisecond resolution, for correlating against audio-path debugging.
3. **A liveness check on the SPP link** that requires transmitting nothing.

#### Lesson

This is the second reversal in two sections (§9A.23's "`AT+MPTT` is implemented after all", now this). Both came from reasoning forward on an interpretation before it had been pinned down by a controlled test. The pattern is consistent enough across this project to be worth stating plainly: **with this device, a single well-chosen empirical test has repeatedly outperformed a chain of plausible static inference.**

---

### 9A.26 ⭐⭐⭐ The disassembler was wrong: every branch and call target in §9A.23 was off

While extending the disassembly it became apparent that **every `call` target printed by `tools/pi32dis.py` fell outside the image**. Examples: `call 0x021127C0`, `call 0x0264BAE6`, `call 0x0265A57A`, `call 0x02650394`. The image only covers:

```
image size   0x000C3FE0   (802,784 bytes)
VA range     0x01E00000 - 0x01EC3FE0
flash range  0x00005000 - 0x000C8FE0
```

Two independent bugs were found, and one *apparent* bug turned out to be a real hardware fact.

#### Bug 1 — no sign extension on the 32-bit call/goto form

`tools/isa/pi32v2.md` line 578/579:

```
1110101010AaaaaaBbbbbbbbbbbbbbbb    call `AaaaaaBbbbbbbbbbbbbbbb0\
  1110101011AaaaaaBbbbbbbbbbbbbbbb    goto `AaaaaaBbbbbbbbbbbbbbbb0\
  ``\
  The spec marks signed immediates with an `s` prefix (`s\`BbbAaaaa0\``). These two lines have **no** `s`, and `pi32dis.py` faithfully treated the 23-bit displacement as unsigned. But the displacement **is** signed and PC-relative. The consequence was systematic: `A = 0b111111` is simply the sign extension, and `A=0x3F` accounts for **8,607 of ~12,400** in-image calls. Every backward call therefore decoded as a bogus address near `0x0264xxxx`–`0x0265xxxx`.

The single most consequential casualty: §9A.23's "event dispatcher" at `0x0265235E` does not exist. The real target is `0x01E52362`.

#### Bug 2 — PC-relative displacements are relative to the *next* instruction

§9A.23 noted in passing that "short-branch displacements decode 2 bytes off in places" and worked around it. That was not a disassembler quirk in isolation — it is the actual architectural rule, and it applies to **every** PC-relative form:

```
target = address_of_instruction + instruction_size + displacement
```

`pi32dis.py` was using `address_of_instruction` as the base. For 16-bit branches this is the familiar 2-byte error; for 32-bit calls it is a 4-byte error, which is why it went unnoticed (call targets were already garbage from Bug 1).

Two proofs, one semantic and one statistical:

*Semantic.* In the `+SPP=P` dispatcher, the compare result must branch to the code that sets `r0 = 0x2A`:

| Base | `if (r0 == 0) goto …` target | Lands on |
|---|---|---|
| `addr` | `0x01E5B378` | `goto` — the **failure** path ✗ |
| `addr + 2` | `0x01E5B37A` | `call <ack>` then `r0 = 0x2A` ✓ |

*Statistical.* First halfword found at the destination of all 12,400 in-image 32-bit calls:

| Base | Top halfwords at call targets |
|---|---|
| `addr + 0` | `0x8102` 4.6%, `0x2040` 3.5%, `0xEAFF` 3.2% — noise |
| `addr + 4` | `0x0474` 10.7%, `0x0410` 9.2%, `0x0475` 9.1%, `0x0476` 8.9%, `0x0477` 5.9% |

Under `addr + 4`, **43.8%** of all call targets begin with a `0x04xx` halfword — the `[--sp] = {rN-rM}` push-multiple prologue family (`0x0476` is literally `[--sp] = {r6-r4}`, the first instruction of the dispatcher at `0x01E5B2F4`). That is a function-entry distribution. Under `addr + 0` it is flat noise.

Spot-confirmed afterwards: `call 0x01E5B2B4` → `[--sp] = {r4}` ✓ and `call 0x01E5B28E` → `[--sp] = {r5, r4}` ✓, both exact function starts, where the old code printed `0x01E5B2B2` and `0x01E5B28A` (both mid-instruction).

Both bugs are fixed in `tools/pi32dis.py`. **All addresses printed in §9A.23 should be re-derived.**

#### Not a bug — there is a mask ROM / SDK library outside the flash image

The first hypothesis was that *all* out-of-range call targets were decode errors, and a scoring pass was written that ranked candidate encodings by "how many targets land inside the image". That metric picked a **wrong** answer (`pc + signed16(B)<<1`, 99.1% in-range) over the correct one (80.3%), because the metric's premise was false.

Decoding correctly and then looking at *where* the out-of-image targets fall settles it — they are not scattered, they are tightly clustered:

| Target region | Calls |
|---|---|
| `0x02000000` – `0x0200FFFF` | **1,710** |
| `0x02110000` – `0x0211FFFF` | **1,019** |
| `0x01CD0000` – `0x01D3FFFF` (spread) | ~190 |
| everything else | ~70 |

2,729 of 2,988 out-of-image calls (91%) land in **two 64 KB windows**. Random garbage does not do that. These are real calls into code that is **not in the flash image** — JieLi's mask ROM / resident SDK library.

Confirmed by example: the three `memcmp` call sites in the SPP dispatcher (`0x01E5ADEC`, `0x01E5ADF8`, `0x01E5B30A`) encode three *different* displacements that all resolve to the *same* address, `0x021127C4`. That is `memcmp`, and it lives in ROM.

**This matters a great deal for the firmware-patching plan:**

- **~19% of all calls leave the image.** A large amount of the radio's behaviour — including, plausibly, much of the Bluetooth stack — is in code we do not have and cannot dump from the SPI flash.
- If the duplex-mode stack crash (§9A.22) is **in the ROM**, it is not patchable at all, and no firmware version in `FW/` will differ. Trying an older firmware is therefore not just a cheap experiment, it is a **discriminating** one: if 1.0.33 behaves identically, the bug is very likely in ROM.
- Conversely, the PTT/event logic *is* in the image and *is* patchable.

#### Lesson

This nearly became the project's seventh wrong turn, and it is a different failure mode from §9A.24/§9A.25. There the error was reasoning forward from an unverified premise. Here the error was **choosing a validation metric that encoded the assumption under test** — "correct decodings produce in-image targets" assumes a self-contained image. The metric was confident, quantitative, and wrong.

What rescued it was a *structural* check rather than a *count*: asking whether the rejected answer's outputs were **organised** (clustered in two ROM windows, converging on a single `memcmp`) rather than merely whether they fell in an expected range. Structure is much harder to produce by accident than a hit-rate is.

---

### 9A.27 Remaining disassembly coverage, and whether to move to Ghidra

#### How much of the image actually decodes

Over a 20,000-instruction linear run:

```
decoded          20,000 lines
unknown encoding  4,639  (23.2%)
```

The unknown opcodes are not evenly spread:

| High byte | Share of unknowns |
|---|---|
| `0xEE` | 15.6% |
| `0xEC` | 13.0% |
| `0xED` | 7.2% |
| `0x00` / `0x01` | 21.2% |
| rest | ~43% |

`0xEC`/`0xED`/`0xEE` alone are **36%** of the gap, and they cluster immediately after global-pointer loads such as `r0 = 0x102F0`. These are pi32v2's **Group 7 / parallel-execution** encodings — load/store with post-modify issued alongside an ALU op. The `0x00`/`0x01` share is largely *not* a real gap: it is linear-decode desync after inline data, which resyncs when a region is decoded from a known entry point with `--off`.

#### `kagaimiq/ghidra-jieli\
  The obvious next step is Ghidra via [kagaimiq/ghidra-jieli](https://github.com/kagaimiq/ghidra-jieli). Its README states plainly:

| Architecture | Status |
|---|---|
| pi32 | "not complete, but somewhat usable now" |
| **pi32v2** (what BR23 needs) | ⚠️ **"very early stage"** |
| q32s | "very early stage" |
| dv10/dv12 (Blackfin) | not implemented |
| f59, f95 | not implemented |

Its own TODO list for pi32v2 is: *"Group7 instructions of course"*, *"Some missing instructions outside group7"*, *"Flags, stacks.."*, *"Deal with its parralel execution stuff (!)"*, *"as well as rep loops & etc."*, *"Likely this is far more complicated than pi32"*.

Repository health: 19 stars, 6 forks, 1 contributor, last commit roughly two years ago, Apache-2.0, no releases.

Note the exact overlap: **the Group 7 / parallel-execution instructions are simultaneously our largest decode gap and the top item on that project's unfinished list.** Moving to Ghidra would not close the gap — it would inherit the same one.

#### Assessment

The honest comparison is not "toy script vs. professional tool". `pi32dis.py` parses the full 577-pattern community spec and, for raw instruction decoding, is plausibly *ahead* of an early-stage SLEIGH module. What Ghidra offers is not better decoding — it is everything **around** the decoding:

| Capability | `pi32dis.py` | Ghidra |
|---|---|---|
| Instruction decode fidelity | good (now correct on branches/calls) | likely worse for pi32v2 today |
| Automatic xrefs | ad-hoc scripting each time | automatic, global |
| Function/CFG recovery | none | automatic |
| Decompiler | none | yes — *if* SLEIGH semantics are right |
| Persistent naming/annotation | none | yes, and this compounds |
| Labelling the ROM region | manual | can be modelled as an external memory block |

The risk is specific and serious: **an incomplete SLEIGH module does not fail loudly, it decompiles confidently and wrongly.** Given that this project has already been derailed six or seven times by plausible-looking inference, importing a decompiler whose semantics for 36% of the instruction stream are unimplemented is exactly the wrong kind of tool to start trusting.

#### Recommendation

1. **The call-decode fix (§9A.26) had to come first regardless** — without correct call targets no tool, Ghidra included, can build a call graph. That is now done.
2. **Use Ghidra for navigation, not for conclusions.** Import `work/app_dec.bin` at base `0x01E00000`, add an uninitialised memory block at `0x02000000` and `0x02110000` for the ROM so the ~2,988 external calls resolve to nameable symbols, and use it for xrefs, function boundaries and persistent labels.
3. **Treat decompiler output as a hypothesis generator only**, and verify anything load-bearing against `pi32dis.py` output or, better, against hardware.
4. If Group 7 semantics turn out to be needed, contributing them upstream is probably less work than it looks — the spec in `tools/isa/pi32v2.md` already documents the patterns; SLEIGH just needs them written out.

#### What the corrected disassembly already shows about the actual goal

With the fix applied, the two PTT paths are visibly **different**:

```
SPP path   (+SPP=P over Bluetooth)      r0 = 0x2A  →  call 0x01E52362
local key  (front-panel PTT button)     r0 = 0x2A  →  call 0x01E4BAEA
```

Both raise the same event code `0x2A`, but they hand it to **different functions**. Under the old, broken decode these appeared as `0x0265235E` and `0x0264BAE6` — two meaningless addresses that could not be compared or followed.

This is consistent with the hardware result in §9A.22 (the front-panel key always uses the radio's own microphone, regardless of advertised name, while `+SPP=P` honours the routing mode) and it localises **where** that divergence is decided. Following `0x01E4BAEA` to the point where it selects a microphone source is now the concrete next step for the original quest.

#### A silent semantic correction: press and release were swapped

The front-panel key handler decodes cleanly now, and the branch fix inverted its meaning:

```
01E60A6E  r0 = [r0+0x14]
01E60A70  if (r0 == 0x80) goto 0x01E60A7C     ; -> r0 = 0x2B   RELEASE
01E60A74  if (r0 != 0x20) goto 0x01E60A82     ; not a PTT event -> skip
01E60A78  r0 = 0x2A                            ; PRESS
01E60A7A  goto 0x01E60A7E
01E60A7C  r0 = 0x2B
01E60A7E  call 0x01E4BAEA
```

So `0x80` = key up → event `0x2B`, `0x20` = key down → event `0x2A`. §9A.23's listing, built with the 2-byte-short branch targets, showed `0x80` falling into `r0 = 0x2A` — i.e. **press and release reversed**. Nothing downstream had been built on that yet, but it is exactly the kind of quiet error the old decoder was producing: the listing looked entirely plausible.

`0x01E4BAEA` itself turns out to be a two-instruction wrapper (`r0 = r0.b0 (u)` then `goto 0x01E4BAC4`) onto what looks like a 10-slot event-queue post routine — it scans slots, writes the event byte, returns 1. So the local key *posts* the event rather than acting on it directly, which is why the microphone decision is not visible at the call site.

---

*[<< Index](Findings.md)*
