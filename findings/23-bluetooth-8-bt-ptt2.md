[<< Index](Findings.md)

# Bluetooth HFP — 8. BT-PTT2: the Bluetooth mic on the second channel (§9C)

> [!TIP]
> **Hardware-confirmed 2026-09-30.** Flashed build:
> `--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT`. The `BT-PTT2` option transmits as
> expected, **both with and without a Bluetooth headset connected**, and the normal
> `PTT` option keeps working in all cases (BT connected or not) — the one-shot
> force-B flag leaks into nothing. Label rendering is verified across all nine menu
> languages — statically (§9C.9) and on the display (2026-10-01: the
> `--PTT2=BT-PTT2 --OD-PTT=BT-PTT` combo shows `"BT2"` / `"BT PTT"` correctly).
> `BT-PTT2` is fully validated.

### 9C.1 Goal

`BT-PTT` ([§9A.44](13-bluetooth-6-key-remap-milestones.md)) makes a radio key transmit
through a linked BT headset's mic, on whatever VFO is current. The ask: a **second
channel** — the same BT-mic transmit, but forced onto **VFO B**, selectable as a PF-menu
action (`--PTT2=BT-PTT2` / `--OD-PTT=BT-PTT2`), so one key can be "BT mic, VFO A" and
another "BT mic, VFO B".

Stock `PTT2` already forces VFO B (via the `b[gp+0x46]` select byte —
[§9A.42](13-bluetooth-6-key-remap-milestones.md)), and `BT-PTT` already produces BT-mic
TX (by pushing virtual key `0x2A` — [§9A.44](13-bluetooth-6-key-remap-milestones.md)).
`BT-PTT2` = push `0x2A` **and** pin the select byte to 1. Neither existing mechanism
does both, and the `0x2A` standby handler recomputes the select byte from the *current*
VFO every time — so the handler itself must be intercepted.

### 9C.2 The interception point: key-0x2A standby handler tail (v1.0.50)

The key-`0x2A` (`+SPP=P`) standby handler runs UI notifications and then, at its tail,
computes the VFO select and calls the TX start (all register contexts below are
disassembly-verified; `r7 = gp = 0x102F0` in this handler):

```
01E794DA  50 ee 77 07         r0 = b[r7 + 0x77]      ; current-VFO state byte
01E794DE  80 a7               r0 = r0 >> 0x7         ; bit 7 = VFO B?
01E794E0  52 ee 76 04         b[r7 + 0x46] = r0      ; TX VFO select: 0=A, !=0=B
01E794E4  bf ea 2a 02         call 0x01E5993C        ; TX start (reads b[r5+0x46])
01E794E8  52 ee 4e 6e         b[r4 + 0xEE] = r6      ; <- resume point
```

The TX start at `0x01E5993C` treats **any nonzero** `b[+0x46]` as VFO B. So overriding
those 14 bytes is exactly the hook needed: same call, different select value.

### 9C.3 Trampoline + code cave

There is no free space inside the app ([§9B.7](22-bluetooth-7-multipoint-architecture.md)),
but the tail above is replaced by a 4-byte absolute goto into a verified-zero cave:

- **Trampoline** (`pfhandler`): 14 B @`0x01E794DA` → `goto32 0x01EA76DE` + 10 B zeros.
  The native 14 bytes are kept as the `native` known-state so stock and patched images
  are both recognised.
- **Code cave** (`pfcave`): 68 B used of a 364 B run @`0x01EA76DE` that is ALLZERO in
  v1.0.44, v1.0.45 **and** v1.0.50 (`tools/freespace.py --other`). [§9B.7](22-bluetooth-7-multipoint-architecture.md)
  rejected this run because of the immediate `r5 = 0x1EA77A0` @`0x01E52F24` feeding a
  draw call @`0x01E507CC` — that buffer sits at cave **+194**, 126 B clear of the 68 B
  used here, so the two do not collide — consistent with the hardware validation passing
  (2026-09-30). Keep any future code in this run under 194 B, or beyond the draw
  buffer's full extent (not mapped) — never straddling cave+194.

Cave layout (`CAVE_VA = 0x01EA76DE`):

| Offset | Size | Role |
|---|---|---|
| `+0` | 36 B | **TX handler** — runs in place of the native tail, `r7 = gp` |
| `+36` | 12 B | **press helper** — set flag, push key `0x2A` |
| `+48` | 20 B | **release helper** — clear flag, push key `0x2B` |

The TX handler (semantics verified by disassembling the built image):

```
+0   50 ee 77 0c   r0 = b[r7 + 0xC7]        ; one-shot force-B flag
+4   41 20         r1 = 0
+6   52 ee 77 1c   b[r7 + 0xC7] = r1        ; CLEAR immediately (one-shot)
+10  (branch2)     if (r0 == 0) goto +18    ; flag was clear -> stock path
+12  40 21         r0 = 1                   ; flag was set  -> VFO B
+14  (goto32)      goto +24
+18  50 ee 77 07   r0 = b[r7 + 0x77]        ; stock: current-VFO bit
+20  80 a7         r0 = r0 >> 0x7
+22  52 ee 76 04   b[r7 + 0x46] = r0
+24  (call)        call 0x01E5993C          ; TX start — unchanged
+28  (goto32)      goto 0x01E794E8          ; resume after the native call
```

The one-shot semantics matter: the flag is consumed the moment the handler runs, so a
later plain `0x2A` — main PTT with `BT-PTT`, or a real `+SPP=P` from the headset — is
never affected, **even if a key release was lost**.

### 9C.4 The flag byte: `gp + 0xC7`

`gp` (`0x102F0`) is the global BT/state struct
([§9A.30](11-bluetooth-4-routing-modes-decoded.md)). Byte `+0xC7` was verified unused:
zero hits for any `0xC7`-displacement access on any base or width in the whole v1.0.50
disassembly (`work/full.lst`), and no code writes the surrounding struct beyond what the
scan covers. The press helper sets it (`b[r4+0xC7] = 1`), the TX handler consumes it, and
the release helper clears it defensively.

### 9C.5 Press bodies and release dispatch

The PF-menu press bodies (menus 27/29, [§9A.42](13-bluetooth-6-key-remap-milestones.md))
run with `r4 = gp`, so the BT-PTT2 press body is tiny — set `r0 = 1` and jump to the cave
press helper, which stores the flag and pushes virtual key `0x2A` through the same queue
helper (`0x01E52362`) that `BT-PTT` uses:

```
pfbody7 (10 B):  40 21 | goto32 0x01EA7702 | 00 00 00 00
pfbody8 (8 B):   40 21 | goto32 0x01EA7702 | 00 00
press helper:    52 ee 47 0c  b[r4 + 0xC7] = r0
                 48 2a        r0 = 0x2A
                 call 0x01E52362   ; push virtual key
                 55 04        {pc, r5, r4} = [sp++]   ; stock epilogue
```

Release: the release executor runs with `r0` = the released PF number and `r4` **not**
`gp`, so the 4-byte release body jumps to the cave release helper, which loads `gp`
itself, clears the flag, and pushes `0x2B`:

```
release body (4 B):  goto32 0x01EA770E
release helper:      c0 ff f0 02 01 00  r0 = 0x102F0 (gp)
                     41 20              r1 = 0
                     52 ee 07 1c        b[r0 + 0xC7] = r1
                     48 2b              r0 = 0x2B
                     call 0x01E52362    ; push virtual key
                     00 04              pc = [sp++]
```

The 32-byte release dispatch window @`0x01E75E78`
([§9A.50](13-bluetooth-6-key-remap-milestones.md)) gains BT-PTT2 as a third tenant class.
Slot budget: `0x01E75E82` (16 B) / `0x01E75E8C` (6 B) / `0x01E75E92` (TX-stop). The
4-byte `goto32` release body fits the tight 6-byte slot, so `BT-PTT2` pairs with every
other action: with `OD-PTT` the tight OD body sits at `+0x0A` and BT-PTT2 at `+0x0C`;
with `BT-PTT` the 8-byte BT release takes `+0x0A` and BT-PTT2 again `+0x0C`; in the
generic case BT-PTT2 takes the `+0x0A` body slot. **All 20 ordered pairs of the five
actions build.**

### 9C.6 Menu labels

Whatever an option is set to, its label follows in all nine language lists
([§9A.50](13-bluetooth-6-key-remap-milestones.md)). `BT-PTT2` has three placements
depending on which strings are still free:

| combo | label | where |
|---|---|---|
| `BT-PTT2` alone (no `BT-PTT`) | `BT PTT2` | over `"PTT2"` + 3 B of `"NET"` @`0x01E8E313` |
| `BT-PTT2` + `PTT2` kept | `BT2` | over `"NET"[0:4]` @`0x01E8E313` |
| `BT-PTT2` + `BT-PTT` | `BT2` | over `"PTT2"`; `BT-PTT` keeps `"BT PTT"` over `"NET"` |

(The short `BT2` form is needed because both BT labels must coexist in the 8 bytes
spanning `"PTT2\0NET\0"`.) The Russian lists re-point their `None` entries to
`"Нет"`/`"НЕТ"` whenever either BT label overwrites the shared string area.

### 9C.7 Encodings used (verified against stock vectors)

- **`goto32`** (32-bit absolute goto): `target = addr + 4 + sign_extend_23(A:B<<1)` —
  the `call` encoding with bit 6 of word 0 set ([§9A.26](10-bluetooth-3-disassembly.md),
  [`tools/isa/pi32v2.md`](../tools/isa/pi32v2.md)). Encoder: `encode_call` then
  `b[0] |= 0x40`; round-trip-checked against stock `call`/`goto32` sites.
- **2-byte conditional branch** (`if (r0 == N) goto`): 9-bit signed word offset, even,
  −256…+254 — `encode_branch2`, verified 8/8 against stock vectors in the release window.

### 9C.8 Tooling, coverage, status

- Tool: `--PTT2=BT-PTT2` / `--OD-PTT=BT-PTT2` (aliases `BTPTT2`, `BT_PTT2`, `BT PTT2`)
  in `tools/patch_h3plus_firmware_bluetooth.py`; new internal patch sites `pfhandler`
  (trampoline) and `pfcave`, installed unconditionally so `--show` recognises both states.
  Refused for `--PTT=` (same restriction as `PTT2`/`OD-PTT` — the main PTT key cannot
  reach the PF-menu executor).
- `tools/verify_actions.py` now builds all **20 ordered pairs** (784 checks): cave bytes
  byte-for-byte, handler reproduces the stock tail semantics (load/shift/store + TX-start
  call + resume), trampoline untouched in non-BT-PTT2 builds, label placements, changed-
  byte-set equality, idempotency, refusal cases.
- Byte cost (with default `--PTT=BT-PTT`, on a full dump): `--PTT2=BT-PTT2` alone 117 B,
  `--OD-PTT=BT-PTT2` alone 123 B, `--PTT2=BT-PTT --OD-PTT=BT-PTT2` 156 B.

**Hardware validation — PASSED 2026-09-30** (user, on radio): flashed
`--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT`. The "BT PTT2" PF option transmits on VFO B
with the BT mic **both with and without a headset connected** (no headset ⇒ the normal
graceful fallback to the internal mic), and the `PTT` option on the other PF key keeps
working in every case — BT connected or not — confirming the one-shot force-B flag at
`gp+0xC7` never leaks into a plain main-PTT / `+SPP=P` transmit.

Cosmetic follow-up also closed (2026-10-01): the reverse-assignment combo
`--PTT2=BT-PTT2 --OD-PTT=BT-PTT` was flashed and its labels (`"BT2"` / `"BT PTT"`)
confirmed correct on the display, matching the §9C.9 static prediction exactly.

### 9C.9 Label rendering — static verification across all languages (2026-10-01)

The "other menu languages" concern is **resolved statically**: the stock firmware never
localises these labels.

- The nine PF S Press lists were located and dumped — languages **en, zh (GBK), tr,
  ru (UTF-8), de, es, it, fr, th** (two lists @`0x01EBD728`/`0x01EBD748`, seven
  contiguous @`0x01EBF08C`…`0x01EBF184`). All nine show English `PTT2` / `OD PTT` in
  stock — no language has localised PTT labels, so the patched English labels
  (`BT PTT` / `BT PTT2` / `BT2` / `PTT`) match the stock convention in every language.
- **Reference model verified** on the stock image (full-image 2-byte-aligned LE scan):
  `"PTT2"` @`0x01E8E30E` has exactly **9** refs (the nine PF lists only); RU `"НЕТ"`
  @`0x01E8E313` exactly **3** refs (identical to `RU_NONE_PTRS`); `"OD PTT"`
  @`0x01E8CE54` **17** refs (9 PF lists + 8 other menus — never modified by the patch);
  `"PTT"` tail @`0x01E8CE57` **0** stock refs. The RU fallback `"Нет"` @`0x01E92010`
  exists in a multilingual "None" string block and is already referenced elsewhere
  (`0x01EC1304`), so its glyphs render.
- **All 20 action pairs** were rebuilt from `_label_sites()` and independently
  re-verified: native bytes and guards match at every site; string placements never
  overlap; every pointer in the whole patched image landing inside the
  `"PTT2\0НЕТ\0"` block reads a complete intended string (no mangled fragments); all
  nine lists' entries 6/7 read the expected labels; the RU `None` entries re-point to
  `"Нет"` exactly when the `"НЕТ"` bytes are destroyed; `"OD PTT"` and its 8 non-PF
  refs stay intact. 0 failures / 20 combos (on top of the tool's own 784-check suite,
  also green).
- The lists are reached by computed addressing (no literal pointer to any list start
  exists in the image) — irrelevant to patching, which rewrites fixed VAs in all nine.
- Label table per combo (the tool's placement rules, now verified): `BT-PTT2` renders
  **"BT PTT2"** unless the other slot keeps `PTT2` or is `BT-PTT`, in which case it
  renders **"BT2"**; `BT-PTT` always renders **"BT PTT"**.

Hardware check closed (2026-10-01): flashed `--PTT2=BT-PTT2 --OD-PTT=BT-PTT` — the
display shows **"BT2"** and **"BT PTT"** as predicted. Every BT-PTT2 placement is now
confirmed on real hardware or statically verified; nothing in this chapter remains
untested.
