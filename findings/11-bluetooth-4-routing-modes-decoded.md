[<< Index](Findings.md)

# Bluetooth HFP — 4. Routing-mode classifier fully decoded (9A.28–9A.32)

### 9A.28 ⭐⭐⭐ The routing-mode classifier found and fully decoded

With the disassembler corrected, the name-matching code is legible in full. This is the single most directly actionable result so far for the original quest.

#### The accessory-name strings

Only four relevant literals exist in the image, and **only one** of them is referenced by code:

| VA | String |
|---|---|
| `0x01E9B968` | `TID-PTT` ← the only xref'd one |
| `0x01E9B970` | `TID-MIC` |
| `0x01E9BF5C` | `TID-MIC-EAR` |

The single reference is at `0x01E7EC5A`, which loads `r6 = 0x01E9B968` and then reaches the other two as **offsets from that base** — the same one-base-pointer idiom used by the SPP command dispatcher:

```
r6 + 0x000  ->  0x01E9B968  'TID-PTT'
r6 + 0x008  ->  0x01E9B970  'TID-MIC'
r6 + 0x5F4  ->  0x01E9BF5C  'TID-MIC-EAR'
```

#### The classifier

```
01E7EC5E  r2 = 0x7              ; compare 7 bytes
01E7EC60  r0 = r9               ; r9 = the peer's advertised name
01E7EC62  r1 = r6               ;      "TID-PTT"
01E7EC64  call 0x021127C4       ; memcmp (ROM)
01E7EC68  if (r0 == 0) goto 0x01E7EC8A     ; match -> mode 1

01E7EC6A  r1 = r6 + 0x5F4       ;      "TID-MIC-EAR"
01E7EC6E  r2 = 0xB              ; compare 11 bytes
01E7EC72  call 0x021127C4
01E7EC76  if (r0 == 0) goto 0x01E7EC8E     ; match -> mode 4

01E7EC78  r1 = r6 + 0x8         ;      "TID-MIC"
01E7EC7A  r2 = 0x7              ; compare 7 bytes
01E7EC7E  call 0x021127C4
01E7EC82  r1 = 0x2
01E7EC84  if (r0 == 0) goto 0x01E7EC90     ; match -> mode 2
01E7EC86  r1 = 0x3                          ; no match -> mode 3
01E7EC88  goto 0x01E7EC90

01E7EC8A  r1 = 0x1
01E7EC8E  r1 = 0x4

01E7EC90  r0 = 0x278            ; store mode to global gp+0x278
```

#### The routing-mode table, as implemented

| Mode | Matched by | Compare length |
|---|---|---|
| **1** | `TID-PTT` | 7 |
| **4** | `TID-MIC-EAR` | 11 |
| **2** | `TID-MIC` | 7 |
| **3** | *anything else* — the default | — |

Four facts fall out of this immediately:

1. **Matching is by prefix, not equality.** The compare length is an explicit `memcmp` argument equal to the literal's own length, and the peer name is not length-checked. `TID-PTT-anything` matches mode 1. This confirms the prefix hypothesis from §9A.22 and explains precisely why `TID-TEST456` did **not** match: the shortest prefix in the table is 7 characters (`TID-PTT` / `TID-MIC`), and `TID-TEST456` shares only 4.

2. **Order matters, and it is correct.** `TID-MIC-EAR` is tested *before* `TID-MIC`, which it would otherwise shadow as a prefix.

3. ⚠️ **This corrects §9A.22.** That section recorded `TID-MIC` and `TID-MIC-EAR` as behaving "identically". They are **not** the same to the firmware — they produce **different mode values (2 vs 4)**. The hardware test that found them indistinguishable was measuring TX/RX audio routing only; whatever else mode 4 changes (earpiece handling, most likely, given the name) was not exercised by that test. The two modes may well converge in the audio path while differing elsewhere.

4. **There is no "unlisted name" rejection.** An unrecognised name is not refused — it is assigned mode 3. Mode 3 is a *supported* configuration, not an error path. This matches §9A.22's observation that an unrecognised name still keys the transmitter and still routes audio, just with the radio's own microphone.

#### Where the mode goes

> ⚠️ **The rest of this subsection is WRONG — corrected in §9A.29.** The `0x278` value below belongs to a *different* byte that is loaded and branched on; the routing mode is actually stored at `base + 0xD4` (RAM `0xB464`). The error came from reading an adjacent, still-undecoded instruction as if it were the store. Kept here because the mistake is instructive.

The mode is written to a global at **`gp + 0x278`** (`gp = 0x000102F0`). Scanning the whole image for accesses to that offset yields exactly **two** sites:

| VA | Role |
|---|---|
| `0x01E7EC90` | the write, above |
| `0x01E611D2` | the only read |

`0x01E611D2` sits inside a connection-setup routine, immediately after `call 0x01E4E2C4` and `call 0x01E6076C` (both invoked with `r0 = 1`) and shortly before `call 0x01E60120` and a tail `goto 0x01E61D7C`. This is the point at which the accessory's routing mode is turned into actual audio-path configuration.

**That single global is the whole gate.** Forcing it to a constant — or forcing the classifier to fall into mode 2/4 unconditionally — is a far smaller and safer patch than rewriting a string compare, and it is the most promising lever identified so far for Step A of the original quest.

#### The remaining obstacle

Reading `0x01E611D2` further immediately runs into the `0xEC`/`0xEE` Group 7 encodings (§9A.27): the load/store that actually consumes the mode is one of the undecoded forms. So the mode's *destination* is known to the byte, but what it is compared against and what it switches is not yet readable.

This is now the **critical path**. The Group 7 gap has stopped being a cosmetic 23% and has become the specific thing standing between us and the answer — both here and at `0x01E4BAEA` (the front-panel key path). Decoding the `0xEC`/`0xED`/`0xEE` load/store family is the highest-value next piece of work, and it would benefit the `ghidra-jieli` project too, since it is the top item on that project's own TODO list.

---

### 9A.29 ⭐⭐⭐ Group 7 load/store decoded — and the routing-mode variable found

The Group 7 wall was taken down empirically rather than from documentation, and it immediately produced the answer §9A.28 was reaching for.

#### Why nothing ever matched

The community spec documents this family only in its **all-operands-zero** form:

```
1110110011010Aaa0000000000000000   ???   r0 = [r0+s`Aaa00000000`]
111011100101001A0000000000000000   ???   b[r0+s`A00000000`] = r0
```

Those sixteen trailing zeros are a literal match requirement, so no real instance — which always has a non-zero operand iword — could ever match. The author evidently dumped these from a tool with all registers reading `r0`, and the `???` marks them unverified. The registers and the low displacement bits live in that second iword, undocumented.

#### Recovering the field layout

Three independent statistical probes against the firmware, each using a different ground truth:

**1. Base register.** The compiler frequently loads a known pointer constant then dereferences it. Taking every `rN = 0x000102F0` immediately followed by a Group 7 instruction (540 sites) and asking which nibble of the operand word equals `N`:

| Operand-word nibble | Equals the loaded register |
|---|---|
| bits 15:12 | 17.2% |
| bits 11:8 | 3.7% |
| **bits 7:4** | **98.1%** ✓ |
| bits 3:0 | 9.3% |

**2. Destination register.** A load is very often followed by a zero/equality test on the loaded value. Taking every Group 7 instruction followed by a 32-bit `if (rX …)` compare (677 sites) and asking which nibble equals `X`:

| Operand-word nibble | Equals the tested register |
|---|---|
| **bits 15:12** | **82.0%** ✓ |
| bits 11:8 | 31.8% |
| bits 7:4 | 13.0% |
| bits 3:0 | 27.2% |

**3. Displacement.** Restricting to **word** loads (which should be 4-byte aligned) and testing candidate placements of the low displacement bits:

| Candidate | % displacement ≡ 0 (mod 4) |
|---|---|
| `Aaa` only, low bits literal zero | 100% but only **4 distinct** values — absurd |
| `Aaa : w1[11:8]` | 29% |
| **`Aaa : w1[11:8] : w1[3:0]`** | **90%** ✓, 73 distinct |

Confirmed by the value distribution: `w1[3:0]` is overwhelmingly `{0, 4, 8, 12}` (187/208) — exactly the low nibble of a word-aligned offset.

#### The layout

```
iword0 = <opcode> <displacement high bits>
iword1 = Dddd(15:12)  Iiii(11:8)  Bbbb(7:4)  Llll(3:0)

   destination / source register = iword1[15:12]
   base register                 = iword1[7:4]
   displacement                  = <iword0 low bits> : iword1[11:8] : iword1[3:0]
```

The number of displacement bits contributed by `iword0` scales with access width — 3 for word, 2 for halfword, 1 for byte — giving 11/10/9-bit displacements respectively. That is why the spec's three templates show `s\`Aaa00000000\``, `s\`Aa00000000\`` and `s\`A00000000\``.

Implemented in `tools/pi32dis.py` as a pre-decode hook. **Unknown-encoding rate fell from 23.2% to 15.6%**, with 1,333 Group 7 loads/stores now decoded in a 20,000-instruction window.

> Scope: only the plain displacement load/store forms are implemented. The post-increment variants (`0xECD8`–`0xECDF`, `0xEED8`) still do not decode — their `iword1[3:0]` is a near-constant `0xA` across 37/38 samples, which looks like a register rather than an immediate, and that has not been pinned down. The multiply-accumulate and predicated-block forms in the same opcode range are untouched.

#### ⚠️ This corrects §9A.28: the routing mode is **not** at `gp + 0x278`

§9A.28 concluded that the classifier stored its result to a global at `gp + 0x278`, reasoning from the `r0 = 0x278` sitting at the end of the function. With the family decoded, that is simply wrong. The actual tail is three instructions, not one:

```
01E7EC90  r0 = 0x278
01E7EC94  r0 = b[r7 + r0]        ; reads an unrelated flag at +0x278
01E7EC98  b[r5 + 0xD4] = r1      ; <-- the routing mode is stored HERE
01E7EC9C  if (r0 == 0) goto 0x01E7ED48   ; branches on the +0x278 flag
```

`0x278` belongs to a *different* byte that is loaded and then branched on. The mode — the `1`/`2`/`3`/`4` computed by the name compares — is stored at **`base + 0xD4`**. This is exactly the failure mode §9A.26 warned about: an inference drawn from an adjacent, partially-decoded instruction, which looked entirely reasonable until the instruction in between became readable.

#### The routing-mode variable

The base register is a RAM pointer constant that appears **135 times** across the image:

```
routing mode byte  =  0xB390 + 0xD4  =  RAM 0xB464
```

Scanning for every byte access with displacement `0xD4` yields a coherent set of **16 sites** — two stores and fourteen reads:

| VA | Access |
|---|---|
| `0x01E7EC50` | `b[r5 + 0xD4] = r0` — initialise |
| `0x01E7EC98` | `b[r5 + 0xD4] = r1` — **the classifier's store** |
| `0x01E61C88` | `b[r6 + 0xD4] = r12` |
| `0x01E51FEE`, `0x01E5DFE0`, `0x01E7EEB4` | reads |
| `0x01E5B368` | read — in the SPP command dispatcher, but see correction below |
| `0x01E61270`, `0x01E61790` | reads — connection setup |
| `0x01E72C4A`, `0x01E72DD2` | reads — near the `+SPP=P` **sender** (§9A.23) |
| `0x01E733FC`, `0x01E73482`, `0x01E7358C` | reads |
| `0x01E794EC`, `0x01E7953C` | reads |

> ⚠️ **Corrected while writing §9A.30.** It is tempting to read the `0x01E5B368` entry as "the `+SPP=P` handler consults the routing mode, and the front-panel key path does not — there is the §9A.22 asymmetry in code". That is **not** what the listing says. The mode read sits in the branch belonging to one of the *8-byte* commands (the one compared at `0x01E5B35C`), which ends at `goto 0x01E5B388`. The `+SPP=P` and `+SPP=R` handlers begin two instructions later at `0x01E5B37A` / `0x01E5B380` and **do not read the mode at all** — they simply raise event `0x2A` / `0x2B`. Same function, different branch. The asymmetry is real on hardware but it is *not* located here.

#### The mode switch

The consumer at `0x01E61270` is a jump table:

```
01E61270  r0 = b[r6 + 0xD4] (u)     ; load routing mode
01E61274  r1 = r0 + -0x1            ; mode - 1   (modes are 1..4)
01E61278  <bounds check>
01E6127E  r0 = r1 << 0x1            ; halfword index
01E61280  tbh r0                    ; switch (mode)
01E61282  <table>
```

`mode - 1` followed by a bounds check and a table branch is a compiler-generated `switch` over exactly the four modes the classifier produces. **This is the routing decision.**

#### Where this leaves the original quest

The chain is now complete and every link is a concrete address:

```
advertised name -> memcmp chain @0x01E7EC5A -> mode 1..4
                -> stored to byte 0xB464
                -> read by SPP dispatcher @0x01E5B368
                -> switch via tbh @0x01E61280
```

Two candidate interventions, both small:

1. **Patch the classifier** so the default branch yields mode 2 or 4 instead of 3 — a two-byte change to the `r1 = 0x3` at `0x01E7EC86`. Any headset name would then be treated as `TID-MIC`.
2. **Patch the store** so `0xB464` is unconditionally set to the desired mode.

Option 1 is the cleaner of the two and is the smallest patch identified in this project so far. It addresses **Step A** of the original quest.

It does **not** address Step B — the front-panel key path still never consults `0xB464`. Resolving the jump-table targets at `0x01E61282` is the next step for that, and needs the `tbh` table decoded.

---

### 9A.30 ⭐⭐⭐ The mode switch resolved — and the two routing switches identified

#### Deriving `tbh`

The spec gives `tbb`/`tbh` a mnemonic and nothing else (lines 81–82), and the bounds-check instruction in front of it is one of the 48-bit `???` forms with the same all-zero-operand problem as Group 7. So the table format had to be derived.

Assuming ARM-like semantics — halfword entries, each a **halfword count** from the address following the instruction — and noting the preceding `r0 = r1 << 0x1` (so `r0` is already a byte index):

```
table base = 0x01E61282        (the byte after `tbh r0`)
target     = base + 2 * entry
```

The result is self-validating in a way that leaves little doubt:

| idx | mode | entry | target |
|---|---|---|---|
| 0 | 1 `TID-PTT` | `0x027C` | `0x01E6177A` |
| 1 | 2 `TID-MIC` | `0x0006` | **`0x01E6128E`** |
| 2 | 3 *unrecognised* | `0x0281` | `0x01E61784` |
| 3 | 4 `TID-MIC-EAR` | `0x0006` | **`0x01E6128E`** |
| 4 | 5 | `0x021E` | `0x01E616BE` |
| 5 | 6 | `0x021E` | `0x01E616BE` |

Entry 1 resolves to `0x01E6128E`, which is **exactly the first byte after a six-entry table**. The table's own contents therefore fix its length, and the length is consistent with the bounds check (`index > 5 → default`). All six targets decode as valid instruction starts.

#### ⭐ Modes 2 and 4 are the same — §9A.28 was wrong, the hardware was right

`TID-MIC` (mode 2) and `TID-MIC-EAR` (mode 4) **branch to the same address**.

§9A.28 made a point of "correcting" §9A.22's note that the two names behaved identically, on the grounds that they produce different mode values. They do produce different values — and then the switch immediately funnels them to identical code. The distinction is real in the classifier and **discarded at the point of use**.

The original hardware observation was correct, and the static "correction" of it was not. This is the same pattern recorded in §9A.25 and §9A.29, now with a tighter moral: *a difference that exists in an intermediate value is not a difference in behaviour until you have followed it to its use.*

#### ⭐⭐ What the branches do: two boolean audio switches

All six targets converge on a six-instruction region that calls just two functions, each with a boolean:

```
mode 1   (TID-PTT)      f_50398(0)   f_503CA(1)
mode 2/4 (TID-MIC*)     f_50398(0)   f_503CA(0)
mode 3   (unrecognised) f_50398(1)   f_503CA(0)
```

`0x01E50398` and `0x01E503CA` are byte-for-byte the same routine except for one constant — a stream/endpoint id of `0x20` and `0x00` respectively — so they are one "enable endpoint N" function instantiated twice.

Cross-referencing those three rows against the routing table established **from hardware** in §9A.22 determines both uniquely:

| Mode | TX mic source (§9A.22) | RX destination (§9A.22) | `f_50398` | `f_503CA` |
|---|---|---|---|---|
| 1 `TID-PTT` | Bluetooth peer | **radio's own speaker** | 0 | **1** |
| 2/4 `TID-MIC*` | Bluetooth peer | Bluetooth peer | 0 | 0 |
| 3 unrecognised | **radio's own mic** | Bluetooth peer | **1** | 0 |

```
0x01E50398(en)  =  enable/disable the radio's LOCAL MICROPHONE   (endpoint 0x20)
0x01E503CA(en)  =  enable/disable the radio's LOCAL SPEAKER      (endpoint 0x00)
```

Three rows, two unknowns, and the assignment is consistent in all three — including the doubly-zero row for duplex mode, where the radio uses neither of its own transducers. A hardware-derived table has now been used to *label functions in the disassembly*, which is a much stronger position than either source alone.

A helper at `0x01E56D3C` is simply both at once:

```
01E56D3C  [--sp] = rets
01E56D3E  r0 = 0x1 ; call 0x01E50398     ; local mic  ON
01E56D44  r0 = 0x1 ; goto 0x01E503CA     ; local spk  ON   (tail call)
```

i.e. **restore fully-local audio**. It has 8 callers, one of which (`0x01E61C84`) is immediately followed by a store to the routing-mode byte — almost certainly the disconnect/reset path.

#### Modes 5 and 6 exist, and the radio can act as an accessory

The classifier only ever produces 1–4, but the table has six entries and two other sites store to `0xB464`. Modes 5/6 gate this, at `0x01E72C42`:

```
01E72C4A  r1 = b[r0 + 0xD4] (u)      ; routing mode
01E72C4E  r1 += -0x5
01E72C52  if (r1 > 0x1) goto exit     ; require mode 5 or 6
...
01E72C86  r4 = 0x1E9B74D              ; "+SPP=P"
01E72C96  rep ...                     ; copy into a buffer and send
```

So in modes 5/6 the radio **sends** `+SPP=P` — it behaves as the accessory rather than the host. This confirms the §9A.24 suspicion that one shared codebase serves both ends of the product family, and it is a plausible route to the multipoint/relay behaviour deferred in §9A.7.

#### New tool: `tools/xref.py`

Call-graph work now needs doing repeatedly, so the scan is factored out:

```
python tools/xref.py work/app_dec.bin 0x01E50398 --both
```

It reports every 32-bit `call`/`goto` targeting a VA, using the corrected sign-extended, next-instruction-relative displacement from §9A.26.

#### Step B status

Step B is **not yet solved**, but the search space is much smaller and two leads are now concrete.

What is established: under `TID-MIC` the local microphone is switched **off** at connection setup (`f_50398(0)`). Yet the front-panel key still transmits the radio's own microphone (§9A.22). Therefore **something in the key/TX path must re-enable it**, and that call is the thing to neutralise.

There are 15 callers of `0x01E50398`, of which 8 pass `1`. Eliminated so far:

| Site | Verdict |
|---|---|
| `0x01E61786` | the mode-3 branch itself — not it |
| `0x01E72C66` | gated to modes 5/6 — not it |
| `0x01E56D40` | inside the restore-local-audio helper |
| `0x01E521BE` | sets mic ON + speaker OFF, i.e. re-applies the mode-3 pattern |

Remaining candidates: `0x01E6B80E`, `0x01E7342A`, `0x01E7924A`, `0x01E7DF2A`, `0x01E7DFFC`, plus the 8 callers of the `0x01E56D3C` helper.

Two dead ends worth recording so they are not retried: the `0x2A` comparison at `0x01E64D1A` is a buffer-scan loop, not an event test; and the `0x2A`/`0x2B` values in the `0x01E7Dxxx` region are arguments to a long configuration sequence (`call 0x01E507C8` repeated with many different constants), not PTT events.

The front-panel key does not act directly — it posts event `0x2A` into a ten-slot queue via `0x01E4BAEA` → `0x01E4BAC4`. Finding that queue's consumer remains the cleanest way in.

> ⚠️ **Corrected in §9A.31.** `0x01E4BAC4` does not *post* to that table — it **removes** an entry from it. The "post" function is a different one, and the SPP path uses a different mechanism again. See §9A.31.

---

### 9A.31 ⭐⭐ Register-indexed loads and conditional branches decoded — and the event mechanisms are not what they looked like

§9A.29 left the `0xEED8` / `0xECD8` / `0xEDD8` forms undecoded and called them "post-increment". That label was a guess, carried forward from the spec's surrounding entries, and it was wrong.

#### They are register-indexed, not post-increment

The frequency alone should have raised suspicion: `0xEED8` alone occurs **2,852** times, `0xECD8` 1,303, `0xEDD8` 792 — 4,947 sites for what was supposedly a niche addressing mode. The spec does cover two of them, in the same `???` all-zero-operand form that makes them unmatchable:

```
line 632  0xEDD8   r0 = h[r0+r0] (u)
line 665  0xEED8   r0 = b[r0+r0] (u)
```

These are **register-indexed** accesses: `rD = b[rB + rI]`. They are common because the compiler uses them whenever a displacement exceeds the immediate forms' range — load the offset into a register, then index by it. That is also why they cluster immediately after constant loads, which is what made them look like part of a pointer-walking idiom.

#### Field layout

Same probes as §9A.29, per opcode:

| Probe | `0xEED8` | `0xEDD8` | `0xECD8` |
|---|---|---|---|
| after a **pointer** constant load, `iword1[7:4]` == that register | 90% | 90% | 84% |
| after a **small** constant load, `iword1[11:8]` == that register | 100% | 93% | 99% |
| followed by a compare, `iword1[15:12]` == tested register | 96% | 94% | 79% |

```
iword1 = Dddd(15:12)  Iiii(11:8)  Bbbb(7:4)  Ssss(3:0)

   destination / source   = iword1[15:12]
   index register         = iword1[11:8]
   base register          = iword1[7:4]
   direction / signedness = iword1[3:0]
```

The two constant-load probes separate cleanly because the compiler uses the two shapes for different roles: a *pointer* constant becomes the base, a *small* constant becomes the index.

`Ssss` is tightly clustered and its meaning was read off behaviour — conditioning on "is the `[15:12]` register tested immediately afterwards", which a load satisfies and a store does not:

| Opcode | `Ssss` | dest tested after | Reading |
|---|---|---|---|
| `0xEED8` | 0 | **96%** | `rD = b[rB+rI] (u)` |
| `0xEED8` | 1 | 17% | `b[rB+rI] = rD` (store) |
| `0xEED8` | 2 | 89% | `rD = b[rB+rI] (s)` |
| `0xEDD8` | 8 / 9 | 79% / 0% | load / store |
| `0xECD8` | 10 / 11 | 94% / 67% | load / store |

> The `Ssss` base value differs per width (0 for byte, 8 for halfword, 10 for word) for no evident reason, and the rarer `0xECD8` values 2, 4 and 5 are unexplained. Whether the index is scaled by the access width is **not established** — no test here distinguishes it. The decoder emits `?N` for unrecognised selectors rather than guessing.

While implementing this, one earlier entry was also corrected: `0xEC50` is a **64-bit pair** load (`r1_r0 = d[...]`, spec line 598), not the 32-bit word load §9A.29 registered it as.

#### Two-register conditional branches

The same all-zero-operand problem hides the conditional branch family (`0xE8xx`–`0xEExx`, spec lines 509–667). Layout:

```
iword1 = Aaaa(15:12)  ...(11:9)  Dddddddddd(8:0)

   first compared register = iword1[15:12]
   second                  = iword0[3:0]   (already in the spec)
   displacement            = signed(iword1[8:0]) * 2, from the next instruction
```

Across 8,000 candidate sites: **100%** of targets land inside the image and **100%** within ±1 KB — the signature of a local branch, and far too strong to be coincidence. The PC base is `addr + 4`, consistent with the universal rule established in §9A.26.

Cumulative effect on `tools/pi32dis.py`: unknown encodings **23.2% → 13.7%**.

#### ⚠️ The correction: `0x01E4BAC4` removes, it does not post

With indexed loads and conditional branches both decoding, the function §9A.30 described as posting events reads in full:

```
01E4BAC4  [--sp] = {r4}
01E4BAC6  r1 = r0                        ; event code
01E4BAC8  r0 = 0x0                       ; result = not found
01E4BACA  r2 = 0xFF59                    ; table base (RAM)
01E4BAD0  r3 = 0x0
01E4BAD2  if (r3 > 0x9) goto 0x01E4BAE8  ; 10 slots
01E4BAD6  r4 = b[r3 + r2] (u)
01E4BADA  r3 += 0x1
01E4BADC  if (r4 != r1) goto 0x01E4BAD2  ; keep scanning
01E4BAE0  r0 = r3 + r2
01E4BAE2  r1 = 0x0
01E4BAE4  b[r0 + -0x1] = r1              ; clear the matching slot
01E4BAE6  r0 = 0x1                       ; result = found
01E4BAE8  {pc, r4} = [sp++]
```

It **finds and clears** an entry, returning whether it was present. §9A.30's "posts event `0x2A` into a ten-slot queue" was wrong in the most consequential way possible — the direction.

The actual writer is the *only other* function referencing `0xFF59`, at `0x01E4A9DA`:

```
01E4A9E4  if (r1 >= 0xA) goto 0x01E4A9F6   ; pass 1: already present?
01E4A9E8  r3 = b[r1 + r2] (u)
01E4A9EE  if (r3 != r0) goto 0x01E4A9E4
01E4A9F2  r1 = 0x0 ; goto exit             ; yes -> do nothing
01E4A9FA  if (r3 > 0x9) goto 0x01E4AA0C    ; pass 2: find a free slot
01E4A9FE  r4 = b[r3 + r2] (u)
01E4AA04  if (r4 != 0) goto 0x01E4A9FA
01E4AA08  b[r1 + -0x1] = r0                ; store the event
```

So `0xFF59` is a **10-entry set** with add-if-absent and remove-if-present primitives. It is a *set*, not a queue: no ordering, no head or tail.

#### The SPP path uses a different mechanism entirely

`0x01E52362`, which the `+SPP=P` handler calls, is a genuine FIFO enqueue:

```
01E52362  r1 = 0x102F0
01E52368  r2 = b[r1 + 0x76] (u)    ; tail index
01E5236C  r3 = r2 + 0x1
01E5236E  b[r1 + 0x76] = r3        ; tail++
01E52372  r1 += r2
01E52374  r2 = 0x566
01E52378  b[r1 + r2] = r0          ; ring[gp + 0x566 + tail] = event
01E5237C  rts
```

So the two PTT paths are more different than §9A.30 recorded. One appends to a message ring buffer at `gp + 0x566`; the other manipulates a 10-entry flag set at `0xFF59`. They are not two consumers of one event system.

This also weakens the assumption that the `0x2A` / `0x2B` in the two paths are the *same* identifiers. Supporting that doubt: at `0x01E597C6` the value `0x2A` indexes a key-name lookup, i.e. it sits in the **key-code** namespace, while the SPP dispatcher's `0x2A` is a **message id**. They may be numerically equal by coincidence — and §9A.23's "both paths raise event `0x2A`", repeated in §9A.26, has never actually been verified.

#### Step B status

Still unsolved, and this round moved the goalposts rather than the ball: the front-panel key path does not feed the same event system as the SPP path, so "find the shared consumer and divert it" was never going to work.

What stands unchanged, and is still the most solid lead: under `TID-MIC` the local microphone is switched **off** at connection setup by `f_50398(0)`, yet the front-panel key still transmits it (§9A.22). Some call must re-enable it. Five candidate sites remain — `0x01E6B80E`, `0x01E7342A`, `0x01E7924A`, `0x01E7DF2A`, `0x01E7DFFC` — plus the 8 callers of the restore-local-audio helper `0x01E56D3C`.

That list is short enough to walk exhaustively, and doing so needs no further ISA work, which makes it the right next step.

---

### 9A.32 ⭐⭐ Full re-confirmation with mature tooling — the two PTT paths, the one audio mux, and a reframe of Step B

> **⚠️ PARTIALLY SUPERSEDED by [§9A.34](12-bluetooth-5-patching-tool.md#9a34--hardware-results-duplex-works-ptt-does-not--and-the-reason-overturns-9a32).** The front-panel path described below is a *teardown* routine, not a key handler, and the pressed-key set at `0xFF59` has no reader and does not key the transmitter. The rest of the section still holds.

Prompted by a request to re-examine everything from the beginning against the goal — *connect any (named) headset and use the radio's PTT button to transmit the mic received over Bluetooth* — the whole routing architecture was re-walked with the now-complete disassembler (`work/full.lst`, 333,270 lines, 16.7% unknown) and `tools/xref.py`. Most findings re-confirm cleanly. Three things changed.

#### Confirmed, unchanged

- The classifier (`0x01E7EC5A`) maps advertised-name prefixes to modes 1–4 stored at `base + 0xD4`; modes 2 and 4 are discarded as identical at the point of use (§9A.30).
- The mode switch applies exactly two boolean switches: `f_50398` = local-microphone enable (stores `base + 0xE6`), `f_503CA` = local-speaker enable (stores `base + 0xE7`).
- PTT keying itself is not gated by the name; only the audio routing is (§9A.22).

#### ⭐ The two PTT entry points share *nothing* — not even the code `0x2A`

With both paths now fully decoded side by side:

```
front-panel key  0x01E60A66:  r0 = [r5+0x14]        ; key event type
                               0x20 -> r0 = 0x2A    ; press
                               0x80 -> r0 = 0x2B    ; release
                               call 0x01E4BAEA -> 0x01E4BAC4   ; REMOVE from 0xFF59 set

+SPP=P / +SPP=R  0x01E5B37A:  call 0x01E5B2B4
                               r0 = 0x2A / 0x2B
                               call 0x01E52362                   ; ENQUEUE to ring gp+0x566
```

The front-panel handler calls the **remove** primitive (`0x01E4BAEA` is a one-instruction wrapper: `r0 = r0.b0; goto 0x01E4BAC4`) — it *withdraws* the key code from the pressed-keys set at `0xFF59`. It never adds. The `0xFF59` set is maintained elsewhere (the generic key scanner), and `0x01E4BAEA` has seven callers — it is the common "key released" path for all keys, not a PTT event post.

So §9A.30's framing — "the key posts event `0x2A`, find the consumer" — was doubly wrong: wrong direction, and wrong namespace. The `0x2A` in the key path is a **key code** (it sits in the key-name table at `0x01E597C6`); the `0x2A` in the SPP path is a **message id** in the ring buffer. The two paths share no data structure, no function, and probably no identifier space.

#### ⭐ The mic/speaker-enable flags have exactly one consumer each — and it is not the TX path

`base + 0xE6` and `base + 0xE7` are read at exactly one place in the entire image: a large computed-branch state machine spanning roughly `0x01E6A2C0`–`0x01E6AF50`. Its shape is uniform — each arm loads an endpoint descriptor from `[r4 + const]` (0x102, 0x106, 0x112, 0x125, 0x126, 0x12A, 0x132, 0x134, 0x135, 0x136, 0x137 …), copies it into a parameter block, and calls `0x01E671E4`, the "activate endpoint" primitive. The flag arms look like:

```
01E6A6C0:  ...activate endpoint[0x106]...
01E6A6DC:  r0 = b[r7 + 0xE6] (u)      ; local-mic enable
01E6A6E0:  goto 0x01E6A796            ; -> record state, tail-exit

01E6A6E2:  ...activate endpoint[0x106]...
01E6A6FE:  r0 = b[r7 + 0xE7] (u)      ; local-spk enable
01E6A702:  goto 0x01E6A796
```

and the neighbouring arms read `0xE8`, `0xE9`, `0xEA`, `0xD0`, `0xD1` in the same pattern — a family of per-stream enable flags, of which the mic and speaker flags are two members. The state machine has **no direct callers**: it is reached through a function pointer / table dispatch (the region around `0x01E6A35A`–`0x01E6A3D6` merges into a common tail at `0x01E6A404`). This is an **audio-graph reconciler** — it (re)builds the active stream graph when the routing configuration changes. It is not consulted at key-up time.

Consequence: the `f_50398(0)` "local mic OFF" that the mode switch performs under `TID-MIC`/`TID-PTT` controls whether the **BT-mic streaming graph** includes the radio's own microphone. It was never the mechanism that feeds the DMR transmitter when the front-panel key is pressed — which is exactly why §9A.22 observed the local mic transmitting "immediately, with no Bluetooth involvement" even with the flag set to 0. **The re-enable hunt in §9A.30 was chasing the wrong wire**: nothing needs to re-enable the local mic, because the local-mic→TX path never went through `base + 0xE6` in the first place.

#### ⭐ Reframe: the SPP ring consumer *is* the mode-respecting PTT path

The ring consumer at `0x01E73E82` dequeues the message id and services it (calls `0x01E5237E` to pop, dispatches, and calls `0x01E5B2B4` to ack). This is the path by which `+SPP=P` keys the transmitter *with the routing mode honoured* — proven from hardware in §9A.22 (`TID-TEST456` + `+SPP=P` → TX with radio mic = mode 3; `TID-MIC*` + `+SPP=P` → TX with BT mic).

The front-panel key, by contrast, goes through the radio's native local-key machinery, which keys the transmitter with the radio's own mic, hardwired. The two paths converge only at the transmitter itself.

**Therefore Step B is not "find where the key path re-enables the local mic and stop it" — it is "make the front-panel key inject `0x2A` into the SPP ring (`0x01E52362`) instead of (or in addition to) the native key handling".** That is a small, surgical patch: at the front-panel handler `0x01E60A78`/`0x01E60A7C`, the press/release codes are already in `r0`; redirecting the `call 0x01E4BAEA` at `0x01E60A7E` to `call 0x01E52362` (or adding it) turns the physical button into a virtual `+SPP=P`/`+SPP=R`. Under a `TID-MIC`-named headset connection, the ring consumer would then key TX with the BT-received mic — the desired end state.

Caveats before patching:
1. The native key handling after `0x01E60A82` (list manipulation on `base+0x2BC`, a `call 0x01E6096E` gate) is what actually drives the local TX for *normal* use; suppressing vs. duplicating it needs a hardware A/B.
2. §9A.22's duplex-mode bug (repeated PTT fails after the first TX under `TID-MIC*`) applies to the ring path and would then also apply to the physical button.
3. The exact semantics of `0x01E5B2B4` (called before each SPP enqueue — probably "wake/notify the ring consumer") should be checked so the injected event is serviced promptly.

#### New enable-flag family map (base-relative)

| Offset | Read at | Written by | Meaning |
|---|---|---|---|
| `0xE6` | `0x01E6A6DC` | `f_50398` (`0x01E50398`) | local microphone enable |
| `0xE7` | `0x01E6A6FE` | `f_503CA` (`0x01E503CA`) | local speaker enable |
| `0xE8`, `0xE9`, `0xEA` | `0x01E6A720`, `0x01E6A742`, `0x01E6A698` | TBD | other stream enables |
| `0xD0`, `0xD1` | `0x01E6A748`, `0x01E6A652`, `0x01E6A648` | TBD | other stream enables |

---

*[<< Index](Findings.md)*
