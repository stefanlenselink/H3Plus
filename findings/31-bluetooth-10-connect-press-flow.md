# Chapter 31 — Bluetooth 10: The Connect-Press Flow — R2 Static Analysis (app v1.0.50)

> **Status: static analysis complete; no hardware test run (nothing flashed from this
> chapter).** R2 is the read-only investigation commissioned by
> [Ch. 30 §30.14.10](30-two-device-plan.md#301410--r1-c-field-failed-the-freeze-root-caused-the-press-flow-waits-for-the-kill-2026-10-2728)
> after the R1-c field failure ("patch the WAIT, not the kill" — designs D1/D2 to be
> settled by byte-level static GO/NO-GO before any build).
> **Headlines:** D1 = **GO** (recipe in Q6), D2 = **NO-GO** (Q6); the R1-c freeze model is
> **corrected** — `FUN_01e17f26`/`FUN_01e07bd4` report *transitional* controller links, not
> "any link up", so the press-flow wait loops do **not** wait for all links to drop (Q1);
> the real freeze is the same-address guard `0x01E16824` refusing the page → silent
> "Connecting" hang (Q1, corrections register Appendix C). The resulting **R1-e design**
> (press-store + targeted cmd-5 kill) is specified in
> [§30.14.11](30-two-device-plan.md#301411--r2-press-flow-analysis-and-the-r1-e-design-2026-10-28).
>
> **Provenance:** produced 2026-10-28 against the official JieLi objdump
> (`jieli-linux-toolchains-20250324.1/pi32v2/bin/objdump`) on `/tmp/opencode/app.o`,
> cross-checked against `work/app_dec.bin` (stock v1.0.50). Recovered 2026-10-29 from the
> DCP compression store (`ses_e825179aaffe7EJIlHD70vrmhc.json`) plus its scratch copy; every
> patch-site byte was independently re-verified against `work/app_dec.bin` on 2026-10-29
> (all pass), including the settings-press call site `0x01E6ECDA`
> (`bd ea 28 46` = `call 0x01E1792E`).
>
> **Address convention (this chapter only):** all addresses in the R2 body below are
> **objdump addresses = file offsets in `app.o`**; VA = offset + `0x01E00000`
> (in the ELF, `.text` sits at file offset `0x34`, vaddr 0). The one-line patch table and
> findings elsewhere in this repo use VAs — convert before patching.

Date: 2026-10-28. READ-ONLY analysis; no repo file modified; scratch in `/tmp/opencode/`.
Authority: official JieLi objdump (`jieli-linux-toolchains-20250324.1/pi32v2/bin/objdump`)
on `/tmp/opencode/app.o`. **All addresses below are objdump addresses = file offsets;
VA = offset + 0x01E00000.** (Note for patchers: in the ELF `app.o`, `.text` sits at file
offset **0x34**, vaddr 0 — a byte patch at vaddr V goes at file offset V+0x34.)
Cross-checked against `work/app_dec.bin` (stock v50) and `full.objdump`.

Two corrections to the incoming brief (the D1/D2 design questions of
[Ch. 30 §30.14.10](30-two-device-plan.md#301410--r1-c-field-failed-the-freeze-root-caused-the-press-flow-waits-for-the-kill-2026-10-2728))
are flagged inline and summarized in Appendix C:
the `DAT_0001a5f1` write is in the **cmd-0** handler (not "ring case 0x11"), and the
walker-arm handlers live in the **HCI-'m'** switch (not the CON switch).

---

## Q1 — `FUN_01e600b4` (0x01E600B4–0x01E6011E): the wait loops, fully decoded

Entry: `r0` = pointer to a 6-byte BD_ADDR → spilled to **r4** @0x600C8.

```
01e600b4:  75 04            [--sp] = {rets, r5, r4}
01e600b6:  41 e0 10 0b      r1 = 0xB10
01e600ba:  c2 ff f0 02 01   r2 = gp (0x102F0)
01e600c0:  d8 ee 20 11      r1 = b[gp+0xB10]            ; routing-mode byte
01e600c4:  71 e1 3f 10      r1 = r1 & ~0x3F
01e600c8:  04 16            r4 = r0                      ; BD_ADDR ptr
01e600ca:  01 f8 07 80      if (r1 == 64) goto 0x600DC   ; GATE: mode field == 1
01e600ce:  55 04            return                       ; (else no-op)
01e600d0:  bd ea 9d b6      call 0x16E0E                 ; mask of active device slot
01e600d4:  80 48            if (r0 != 0) goto 0x600E6    ; a device is up -> teardown decision
01e600d6:  40 2a            r0 = 10
01e600d8:  8d ea 53 0f      call 0x201F82                ; dly(10)  (OS sleep, outside app)
01e600dc:  bd ea 23 bf      call 0x17F26                 ; GLOBAL link-state check
01e600e0:  05 16            r5 = r0
01e600e2:  15 f8 f5 01      if (r5 == 128) goto 0x600D0  ; <<< LOOP A
01e600e6:  bd ea 92 b6      call 0x16E0E
01e600ea:  00 42            if (r0 == 0) goto 0x600F0
01e600ec:  50 2a            r0 = 0x4A                    ; device up -> disconnect current
01e600ee:  04 87            goto 0x600FE
01e600f0:  05 4e            if (r5 == 0) goto 0x6010E    ; loop-A exit state
01e600f2:  40 32            r0 = 0x12                    ; transitional state -> post 0x12 ...
01e600f4:  41 20  42 20     r1 = 0, r2 = 0
01e600f8:  bd ea 19 bc      call 0x1792E                 ; user_send_cmd_prepare
01e600fc:  40 25            r0 = 5                       ; ... then 5 (kill loop, §Q3)
01e600fe:  41 20  42 20     r1 = 0, r2 = 0
01e60102:  bd ea 14 bc      call 0x1792E
01e60106:  04 83            goto 0x6010E
01e60108:  40 2a            r0 = 10
01e6010a:  8d ea 3a 0f      call 0x201F82                ; dly(10)
01e6010e:  bd ea 0a bf      call 0x17F26                 ; GLOBAL link-state check
01e60112:  f0 5a            if (r0 != 0) goto 0x60108    ; <<< LOOP B: wait state == 0
01e60114:  40 21            r0 = 1                       ; cmd 1 = CREATE_CONNECTION
01e60116:  41 26            r1 = 6
01e60118:  42 16            r2 = r4                      ; BD_ADDR
01e6011a:  bd ea 08 bc      call 0x1792E                 ; <<< THE PAGE POST
01e6011e:  55 04            return
```

Gate: proceeds only when `(b[gp+0xB10] & ~0x3F) == 0x40`, i.e. the 2-bit routing-mode
field (bits 6–7) equals 1. `FUN_01e60120` (0x01E60120) is the setter of that field
(@0x601B0–0x601BC) and contains a structurally identical wait/teardown/wait sequence —
the same two global waits exist there too (out of scope for D1 below, noted for symmetry).

### Helper semantics (all re-verified this round)

* **0x16E0E** (`FUN_01e16e0e`): `r0=1; r5=FUN_01e16878(1); return r5 ? h[r5+8] : 0`.
  Returns the **mask halfword @slot+8** of the active device slot, else 0.
* **0x16878** (`FUN_01e16878(mode)`): scans the 2-slot conn table **0x1A5B8 / 0x1A5D4,
  stride 0x1C** (addr @+0, handle @+6, mask @+8, inuse word @+0xF bit29).
  mode 1 → last slot with `inuse && handle!=0 && !(h[slot+8] & 0x2080)`;
  mode 0 → counts such slots: 1 → that slot, ≥2 → tail-calls `0x16824(0x1A618)`
  (is the *ring* address connected?), 0 → 0; other modes → `0x16824(0x1A618)`.
* **0x17F26** (`FUN_01e17f26`) is a 2-instruction thunk → **`FUN_01e07bd4` @0x01E07BD4**:
  ```
  01e07bd4:  push {rets,r4}; r1 = 0x1A0A8; r0 = 0; r2 = r1
  01e07be2:  r3 = [r2+196]                  ; 16 pointer words @0x1A16C+28*i
  01e07be6:  if (r3 == 0) goto next
  01e07be8:  r4 = b[r3+40];  r3 = -128
  01e07bf0:  if ((r4 & 4) != 0) r3 = r0     ; bit2 SET -> keep r0
  01e07bf6:  r0 = r3                        ; bit2 CLEAR -> r0 = 0x80 (sticky)
  01e07bf8:  r2 += 28; if (r2 < r1+448) loop
  01e07c02:  if ((r0 & 0xFF) != 0) goto ret ; any busy entry -> return 0x80
  01e07c08:  call 0xFF2C                    ; = b[0x1A053] (controller state+99)
  01e07c10:  r0 = r0.b0; pop; rts           ; else return b[0x1A053] & 1
  ```
  Verified `c2 3c` = `r2 += 28` against the ISA (pattern `001Aaaaa11BbbXxx`,
  s = `BbbAaaaa` = 0b011100 = 28). **Ghidra's decompile of this function is wrong**
  (stride 0xE0, flag +0x208, `DAT_0001a5f3`) — objdump is authoritative.
  Semantics: **0x80 ⇔ some controller link-table entry is non-null with bit2 of its
  byte+40 CLEAR** (a link in a transitional/not-ready state); otherwise the function
  returns `b[0x1A053] & 1`. Field calibration (E6, 2026-10-08): a *stable* PC SPP ACL
  reads as **0** — so "128" is not "any ACL up" but "a link is mid-establishment /
  mid-teardown". The exact meaning of bit2 is controller-library internal —
  **UNRESOLVED** (precompiled), but behaviorally pinned by E6.
* **0x201F82** = OS delay (outside the app image; offset > app size).

**Loop A** (0x600D0–E2): while *no active device mask* AND *a link is transitional*,
sleep 10 ms. **Loop B** (0x60108–112): sleep 10 ms; while *any link is transitional
(or state byte ≠ 0)*, repeat. Only then is cmd 1 (page, 6-byte addr) posted.
Both waits are **global** — they do not consult the requested address (r4) at all.
That is the structural defect D1 targets (§Q6).

---

## Q2 — UI path mapping: which handler is "Menu→Bluetooth→BT Pairing→Paired→device→Connect"

**Callers of `FUN_01e600b4`** (all pass a BD_ADDR ptr in r0 — verified per site):
| site | context | r0 source |
|---|---|---|
| 0x01E6022C | inside `FUN_01e601c0` (retry helper) | stack buffer `sp+6` filled by `0x181C0` query |
| 0x01E670C6 | UI list handler | `[[0x102D0]*0xC + [r5+216] + 8]` — heap list, selected index |
| 0x01E6ECEA | **settings press** `FUN_01e6ec9e` | `[[0xB468] + idx*12 + 8]` |

**Settings press `FUN_01e6ec9e` (0x01E6EC9E)** — the real "Connect" press:
```
01e6eca2:  r9 = 0xB390 (UI gp);  r1 = [r5+216] = [0xB468]  ; device-list base
01e6ecae:  r4 = idx * 0xC                                   ; idx = r0 (menu selection)
01e6ecba:  call 0x60120(1)                                  ; set routing mode 1
01e6ecbe:  r0=0x11; call 0x1792E(0x11,0,0)                  ; controller query
01e6ecca:  r0=0x12; call 0x1792E(0x12,0,0)                  ; ctrl post 0xCFD type2
01e6ecd4:  r0=5;   call 0x1792E(5,0,0)                      ; KILL loop (cmd 5)
01e6ecde:  r0=5;   call 0x201F82                            ; dly(5)
01e6ece4:  r0 = [[r5+0] + r4 + 8]                           ; selected device BD_ADDR*
01e6ecea:  call 0x600B4                                     ; connect flow (Q1)
```
`FUN_01e6ec9e` has exactly two callers — 0x01E6F9C0 (inside `FUN_01e6f8b2` case 5,
`FUN_01e6ec9e(DAT_000102d0)`) and 0x01E701D6 (inside `FUN_01e7013e`,
`DAT_000102d0 == 1`) — both UI-framework key handlers; `findva` finds **no** pointer-
table entries (registered by framework dispatch, not by address). The selection lives
in the heap list `[0xB468] + DAT_000102D0*12 + 8`.

**Modal press** = tail of BT-task state-3 `FUN_01e60e44` (block 0x01E61D92–0x01E61E4A,
§Q5) — it never touches `FUN_01e600b4` and carries no address.

**Verdict:** "Menu→Bluetooth→BT Pairing→Paired→device→Connect" runs the **settings
path `FUN_01e6ec9e`** (posts 0x11/0x12/5, then `FUN_01e600b4(selected addr)`).
The modal press is an address-less retry. The settings chain never touches
`gp+0xB44` (0x10E34) — verified by exhaustive scan of 0x6EC9E–0x6EDD0.

---

## Q3 — Ring dispatcher `FUN_01e21af8`: case map and the `DAT_0001a5f1` correction

Dispatcher head @0x01E21AF8. Command byte `r6`; range checks:
`r6-22 > 26` → 0x21C68 (default); `22 ≤ r6 ≤ 48` → 0x21CCA (secondary, incl. **0x4A**
at ~0x21D06 region); `0 ≤ r6 ≤ 21` → **tbh @0x01E21B96**, table @**0x01E21B98**,
16-bit entries, **target = 0x21B98 + 2×entry**.

| cmd | body | what it does |
|---|---|---|
| 0 | 0x21BC4 | **connect-request pop**: gate `is_1t2` (0x1787C); ring idx = bits 3–5 of `h[0x1A662]`; pop 6 B from ring **0x1A618**; advance idx; guard `0x16824(entry)`; alloc `0x2181C(entry,0)`; **copy 6 B rec → 0x1A5F1 @0x21C44 (`rep 4 6`)**; `0x2193A`, `0x21988`, `0x187AC(r5,0x11,0x2C)` |
| 1 | 0x21E58 | **page**: gate `is_1t2()==0`; ring idx ≥ 0; guard `0x16824(0x1A5FD)==0`; alloc `0x2181C(0x1A5FD,0)`; `0x21A44(0)`, `0x18AFC(0)`; `0x2193A`; `0x21988` |
| 2 | 0x21E38 | **re-page saved target**: `user_send_cmd_prepare(1, 6, 0x1A5F1)` @0x21E4E |
| 3 | 0x21E54 | same body as cmd 1 entered one insn earlier (`r7 = 0x1100` variant) |
| 4 | 0x21EB4 | `if (r5==0) bail; if (h[r5+6]==0) bail; 0x19492(r5, 22)` |
| 5 | 0x21ECA | **KILL loop**: slots 0x1A5B8→0x1A5F0 stride 0x1C; kill iff `inuse(word+0xF bit29) && h[slot+8]==0` → `call 0x01E08A94` @0x21EF4 (stock bytes `bf ea ce 35`) |
| 6 | 0x21F04 | `0x8A78(0x1A5D7, 0)` |
| 8 | 0x21F10 | `if (r5) ...` (disconnect-variant) |
| 0xC | 0x21F76 | `FUN_01e21a44(0)` — clear bit0 of 0xBEC8 + HCI update |
| 0xD | 0x21F7E | gates; `FUN_01e21a44(1)` |
| 0xE | 0x21F9E | `FUN_01e18afc(0)` — clear bit1 of 0xBEC8 (`--force-page-scan` NOPs the *set* path @0x18B0E) |
| 0xF | 0x21FA6 | gates; `FUN_01e18afc(1)` |
| 0x10 | 0x21FC6 | `0x8AE8(b[0x1A5EC])` |
| 0x11 | 0x21FD0 | **thunk `0x01E181DA` → `goto 0x01E07FC8`** — controller query only |
| 0x12 | 0x21FD6 | `FUN_01e21a6a` → `0x01E08990` (ctrl post 0xCFD type2) |
| 0x13 | 0x21FDC | bookkeeping: scan `[r6+61..63]` for ≠255; `0x16824([r6+72+r0])`; write 255; notify `0x20F1C` |

**Correction to the brief:** *"ring case 0x11 writes DAT_0001a5f1"* is wrong twice over.
`DAT_0001a5f1` (SAVED TARGET, = `r14+209` with `r14 = 0x1A520`) is written at
**0x01E21C44 inside the cmd-0 handler** (`rep 4 6` copy of the popped ring record), and
by bookkeeping `FUN_01e21988`. **Case 0x11 writes nothing of the sort** — it is a
thunk into the controller (0x01E07FC8). The "0x11" in play is the **CON event 0x11**
posted by `FUN_01e187ac` from the cmd-0 handler (`call 0x187AC(r5, 0x11, 0x2C)`), and
the bookkeeping body at 0x21FDC is **case 0x13**, not 0x11. None of 0xC/0xE/0x10/0x11/
0x12/0x13 writes 0x1A5F1, 0x10E34, or 0xB4F0.

---

## Q4 — CON pump events and the walker arming (correction: HCI-'m', not CON)

`FUN_01e187ac(r0 = addr, r1 = event, r2 = flag)` (0x01E187AC):
bails if `addr == 0` or `0x16824(addr) == 0`; events **0xb/0xe** copy addr → ring
head 0x1A618; other events write the ring only when no live-handle match; then posts
`FUN_01e18784(addr, "CON"(0x434F4E00), event, bit6 of h[slot+13])`; `b[0x1A660] = event`.

* **CON event 3** handler @0x01E6116A: `b4f0 |= 1`; timers `0xB50C/0xB510 = 25000`;
  `strncpy` remote name → 0xB420 (≤24 B + 5 B flash tail); `FUN_01e4e2c4(1)`;
  `FUN_01e6076c(1)`; `FUN_01e60120(b[0xB461] ? 1 : 2)`.
  **Event 3 writes NO address** to 0x10E34/0x1A5F1.
* The **walker-arm handlers** 0x01E61828 (sub 8) and 0x01E6194E (sub 0xb) are cases of
  the **HCI-'m' (0x48434900) switch** (tbh @0x01E6104C, sub-event = word at msg+0x28) —
  *not* the CON switch. Both gate on `FUN_01e18552()==0 && FUN_01e18572()==0`, set
  `gp+0xB38 = 30000/8000`, copy **6 B from the event object `*(puVar19+0x10)` →
  DAT_00010E34 (= gp+0xB44, the armed page target)**, then run the walker
  `FUN_01e60d34(0)` (the sub-8 handler posts 0x12 first @0x61968).
* The HCI-'m' poster is in `FUN_01e21af8`'s btstack-callback tail:
  ```
  01e226ac:  c1 ff 00 49 43 48   r1 = 0x48434900   ; "HCI"
  01e226b2:  5a 2d               r2 = 109          ; 'm'
  01e226b4:  bf ea 66 b0         call 0x18784
  ```
  (verified this round; `FUN_01e18552` re-checked @0x226BA immediately after).

**Net:** the armed target 0x10E34 is populated **only** by HCI-'m' sub 8/0xb copies
from controller event objects. No CON event, no press, and no ring dispatcher case
writes it. The walker (page post @0x01E60DE4) is therefore armed exclusively by
controller-level connection-state-change events, with its timer in `gp+0xB38`, and
gated off while `b4f0` bit3 is set (`0x60DAA: if ((b4f0 & 8) == 0) goto body`).

---

## Q5 — Modal press: no target propagation exists

Modal press block 0x01E61D92–0x01E61E4A (tail of BT-task state-3 `FUN_01e60e44`):
* posts `(cmd, 0, 0)` five times — 0xC, 0xE, 0x12, 5, 0x4A — **all argument-less**;
* `bset b4f0 bit3` @0x61DE4 (press-pending); `bset bit4` @0x61E46 (exit-requested);
* sets page-pending `DAT_0001a662` bit7 via `0x185F0(1)`;
* arms one-shot watchdog `0x249DE(0, 0x01E7EFD2, 10)` @0x61E38;
* the 24-byte `rep` @0x61DB8 copies a **flash template** (`r8(0x01E9B5CA)+0x1215`),
  not a device record;
* modal exit gate 0x61E52–5C needs `(b4f0 & 0x18) == 0x10` (bit3 clear — only the
  watchdog clears it, and it early-returns while bit0 is clear or the audio object is
  live, `0x7EFFE`).

Exhaustive ref scan of the modal block: **zero references** to 0xB468, 0x102D0,
0x1A5F1, 0x10E34, or any address-bearing structure. The modal press **cannot** convey
a newly selected device address; device selection exists only in the settings heap
list (`[0xB468] + idx*12 + 8`, idx = `DAT_000102D0`). Any page of a *new* device must
flow through `FUN_01e600b4(r4)` (settings path) — the modal retry can only ever
re-engage whatever the controller/arm state already holds.

---

## Q6 — Verdicts on D1 / D2

### D1 — target-specific wait loops in `FUN_01e600b4`: **GO**

Replace the two global `FUN_01e17f26` checks with the target-specific
`FUN_01e16824(r4)` ("does the requested address hold an inuse conn record, regardless
of handle?"). `FUN_01e16824` takes **only r0** and returns slot-ptr-or-0 — the exact
predicate needed; it ignores the handle, so a same-address phantom still blocks until
cmd-5 kills it (stock cmd-5 predicate `inuse && h[slot+8]==0` kills precisely that
phantom, and the press posts cmd 5 *before* calling `FUN_01e600b4`).

**Byte recipe (all three sites round-trip through the official objdump — verified):**

| site | old bytes | new bytes | disassembly |
|---|---|---|---|
| 0x01E600DC (10 B) | `bd ea 23 bf 05 16 15 f8 f5 01` | `40 16 bd ea a1 b3 05 16 f5 55` | `r0=r4; call 0x16824; r5=r0; if (r5 != 0) goto 0x600D0` |
| 0x01E6010E (4 B) | `bd ea 0a bf` | `82 ea 23 3b` | `call 0xA7758` (cave thunk) |
| 0x01EA7758 (6 B, ALLZERO-verified free, run continues 0xF2 B) | `00…` | `40 16 fb ea 63 78` | `r0=r4; goto 0x16824` (tail-call thunk) |

Round-trip excerpt (patched `d1test.o`, official objdump):
```
600dc:  40 16            r0 = r4
600de:  bd ea a1 b3      call -301246 <.text+0x16824 : 16824 >
600e2:  05 16            r5 = r0
600e4:  f5 55            if (r5 != 0) goto -22 <.text+0x600D0 : 600d0 >
6010e:  82 ea 23 3b      call 292422 <.text+0xA7758 : a7758 >
60112:  f0 5a            if (r0 != 0) goto -12 <.text+0x60108 : 60108 >
a7758:  40 16            r0 = r4
a775a:  fb ea 63 78      goto -593722 <.text+0x16824 : 16824 >
```
Loop B needs the cave because `mov+call` (6 B) doesn't fit the 6 B between the dly and
the existing 2-byte `f0 5a` branch; the tail-call thunk returns into `f0 5a` unchanged.
Flash sectors touched: **0x65000** (both 0x600DC and 0x6010E sites) + **0xAC000**
(cave). No overlap with any existing patcher site (nearest is E9's 0x01E60188).

**Semantics after D1:**
* Loop A: wait while (no active mask) && (target record inuse) — an unrelated live
  link no longer matters; the same-address phantom still waits for the cmd-5 kill.
* 0x600F0 `if (r5 == 0)`: r5 is now slot-or-0 instead of state-or-128 — branch
  polarity preserved (0 = "target not connected" ⇔ old "idle").
* Loop B: wait until the target's record clears (disconnect completion) → page posts.
  With a PC incumbent and a Jabra target, Loop B exits immediately → **cmd 1 posted
  while the PC link stays up** — the multipoint unlock D1 exists for.
* Stock single-device behavior is preserved: same-address presses still serialize on
  the kill; the 0x4A-on-connected-device path (0x600E6) is untouched.

**Residual risks (must be HW-tested):**
1. Page may now be posted while *another* link is transitional (stock waited for
   global idle) — controller-level page-collision behavior on BR/EDR is expected-OK
   (E6 proved outgoing joins work with a live link) but unproven for the
   mid-teardown case.
2. If cmd-5's kill is NOP'd (E7+ base) **and** the press targets an already-connected
   device, Loop B waits on a record that never clears — same-address re-page on a
   fully-NOP base needs the conditional-kill cave (R1 design notes) alongside D1.
   D1 is therefore specified for a base where cmd-5 still kills (stock predicate or
   the R1 cave), not for the E11 all-NOP state.
3. `FUN_01e60120` (routing-mode setter, called first by the settings press at
   0x6ECBA) keeps its *own* global waits; when the mode is already 1 it returns
   immediately (`0x60136`), so the press flow is unaffected — but any flow that
   changes routing mode while a second link is transitional can still stall there.

### D2 — copy `0x1A5F1 → 0x10E34` (+ set `b4f0` bit0/bit3) at press/cmd-5 time: **NO-GO as specified**

* **Stale target.** `DAT_0001a5f1` (saved target) is written only by the cmd-0
  ring-pop (@0x21C44) and by bookkeeping `FUN_01e21988`. Neither the modal press
  (Q5: no refs at all) nor the settings press (posts 0x11/0x12/5 — no cmd 0, no ring
  push) updates it with the newly selected device. At press time 0x1A5F1 holds the
  *previous* connect/disconnect target → the walker would arm and page the **wrong
  (old) device**.
* **A data copy does not arm the walker.** Arming is `gp+0xB38 = 30000/8000` + the
  walker body gated on `b4f0 bit3 == 0` (0x60DAA); the timer is set only inside the
  HCI-'m' sub-8/0xb handlers (Q4). Copying an address to 0x10E34 while the press has
  just set bit3 leaves the walker dead. (The bit0/bit3 manipulation itself is
  trivially encodable — bit0 set makes the watchdog proceed, `0x7EFFE` — that part
  is feasible but pointless without a target.)
* **Redundant.** The settings path already propagates the selection natively
  (r4 → cmd 1 @0x60114); D1 removes the only blockers in that path. D2 adds no
  capability D1 doesn't already deliver, and its target source is wrong.

If a modal-driven page is ever wanted, the prerequisite is a **selection store** for
the modal (none exists — Q5), i.e. code-cave work, not a copy patch.

---

## Appendix A — `FUN_01e16824` calling-convention evidence (required)

```
01e16824:  d9 e8 70 03   [--sp] = {rets, r9, r8, r6-r4}
01e16828:  04 16         r4 = r0            ; single arg: BD_ADDR ptr
01e1682a:  c6 ff b8 a5 01 00  r6 = 0x1A5B8
01e16836:  42 26         r2 = 6
01e16838:  40 15         r1_r0 = r5_r4      ; (slot, arg)
01e1683a:  97 ea b9 df   call 0x3127B0      ; memcmp 6
01e16840:  80 52         if (r0 != 0) goto next
01e16858:  62 e1 00 85   r2 = word[slot+0xF] & 0x20000000   ; inuse bit29
01e16862:  52 e8 06 02   if ((r2 & 1) != 0) goto found      ; -> r0 = r5 (slot)
01e16866:  1d 8d         r5 = r1 + 13       ; next slot (+0x1C)
01e1686c:  80 e9 e3 51   if (r5 < 0x1A5F0) loop
01e16870:  95 16         r5 = r9            ; r9 = 0 -> not found
01e16872:  50 16         r0 = r5
01e16874:  d5 e8 70 03   {pc, r9, r8, r6-r4} = [sp++]
```
* **One argument (r0), return r0 = slot pointer or 0.** Ignores the handle field.
* Preserves r4, r6, r8, r9 + rets (prologue/epilogue above); clobbers r0–r3, r5.
  Safe to call with the target pointer parked in r4 (D1 relies on this).
* All four call sites pass r0 only: 0x168E2 (`r0 = 0x1A618`, tail), 0x21C24
  (`r0 = sp+12`), 0x2200C (`r0 = struct+72`), 0x21E76 (`r0 = 0x1A5FD`).

## Appendix B — verified encodings used (corrected formulas)

* 32-bit **call far**: halfword0 = `0xEA80 | A`, halfword1 = B; X = A:B (22-bit,
  sign-extended), `target = addr + 4 + (X<<1)`. (0xEA40 base is wrong — opcode field
  is bits 15..6 = `1110101010`.)
* 32-bit **goto far**: halfword0 = `0xEAC0 | A`.
* 16-bit **`if (rXxx != 0) goto`**: word = `010 Aaaaa 1 Bbb 0 Xxx` — Xxx = **bits 2..0**
  (not 3..1), Bbb = bits 6..4, Aaaaa = bits 12..8, s = Bbb:Aaaaa (8-bit signed),
  disp = s<<1, `target = addr + 2 + disp`. (`if (r5 != 0) goto -22` = `f5 55`.)
* `00 00` = nop (used in E-patches; not needed in the final D1 recipe).

## Appendix C — corrections register vs incoming brief

1. **"ring case 0x11 writes DAT_0001a5f1"** → the write is in the **cmd-0 handler**
   @0x01E21C44; case 0x11 is a controller-query thunk (0x01E181DA→0x01E07FC8); the
   bookkeeping body at 0x21FDC is **case 0x13**; "0x11" is also the CON *event* posted
   by `FUN_01e187ac` from cmd 0.
2. **Walker-arm handlers 0x61828/0x6194E are in the HCI-'m' (0x48434900) switch**
   (tbh @0x6104C), not the CON switch.
3. `FUN_01e17f26` fallback byte is `b[0x1A053]` (via `FUN_01e0ff2c` = `b[0x19FF0+99]`),
   not `b[0x1A093]`; its "128" means "a controller link entry is in a
   bit2-clear/transitional state" — a *stable* second link reads 0 (E6-calibrated),
   which is why E6's page succeeded through the stock Loop B.
4. `FUN_01e16878` mode-1 exclusion test is `h[slot+8] & 0x2080` (mask halfword), not
   `h[slot+0xA]`.

*End of report.*


---

## Where this goes next

R2's product is the **R1-e design** — press-store hook at the settings-press cmd-5 post
(`0x01E6ECDA`) + a target-aware cmd-5 kill predicate replacing the mask test at
`0x01E21EF0`, built on the F3-v3 known-good base. Full spec, kill-matrix and corrected
sector list (`0x026000` + `0x073000` + `0x0AC000`):
[Ch. 30 §30.14.11](30-two-device-plan.md#301411--r2-press-flow-analysis-and-the-r1-e-design-2026-10-28).
D1 is **GO** as optional R1-f hardening (recipe in Q6 above). Nothing here is flashed;
the radio currently runs R1-c (rollback: `work/ch30_r1crb.sh`).

---

*[<< Index](Findings.md)* · [Ch. 30 (two-device plan — §30.14.11 R1-e design)](30-two-device-plan.md) · [Ch. 29 (address map)](29-static-analysis-reference-map.md) · [Ch. 27 (E1–E11 log)](27-firmware-2slot-stack-controller-wall.md) · [Ch. 26 (eviction decision)](26-bluetooth-9-eviction-decision.md) · [Ch. 18 (priorities)](18-open-questions-next-steps.md)
