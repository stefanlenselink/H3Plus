# Ch. 25 — The Ghidra decompile ⇒ alter ⇒ compile route (validated)

> §25. Added 2026-10-03. Goal: prove we can decompile the shipping app with
> Ghidra + ghidra-jieli, recompile the (un)modified logic with the official
> JieLi toolchain, splice it back, and keep the result correct — the
> prerequisite for any change too big for byte patching.
> Tools: [`tools/Tools.md` §9](../tools/Tools.md#9-ghidra-pi32v2-decompile--compile-route).

---

## 25.1 Setup — zero changes to ghidra-jieli were needed

* Ghidra **12.1.4** (Java 25) + [quarkslab/ghidra-jieli](https://github.com/quarkslab/ghidra-jieli)
  (the improved kagaimiq module; languages `pi32`/`pi32v2`/`q32s`).
* Install = `cp -r ghidra-jieli <ghidra>/Ghidra/Processors/JieLi`. The shipped
  `pi32v2.sla` loads unchanged — **no gradle build, no module edits**, and
  none were required for this work.
* Language `pi32v2:LE:32:default`, compiler spec `default` (uses `pi32.cspec`).

## 25.2 Import recipe and two Ghidra-12 gotchas

1. **`BinaryLoader` ignores the base address headless.**
   `-loader-"Base Address" 0x01E00000` prints *“Skipping unsupported
   -loader-Base Address argument”* and loads at 0. Fix: `MoveBlock.java`
   pre-script relocates the block to `0x01E00000` before analysis.
2. **A raw import has no entry points** → auto-analysis finds nothing (22 s,
   zero functions). Fix: `SeedFunctions.java` — the `findva.py` pointer scan
   inside Ghidra (every 2-byte-aligned LE word pointing into
   `[0x01E00000, 0x01EC4000)` becomes a function: **6558 functions**), plus
   explicit seeds (classifier, conn readers, ops handlers).

Whole 784 KiB app: import + analysis + decompiles in **~2 minutes**.
Residual noise: ~460 `Pcode error … delay slot` warnings — SLEIGH model gaps
at a few instructions, non-fatal, worth reporting upstream.

## 25.3 The decompilation agrees with everything we hand-derived

| VA | Ghidra result | Cross-check |
|---|---|---|
| `0x01E1787C` | `return (_DAT_0001a662 & 7) == (DAT_0000bf39 & 0x30) >> 4;` | = `is_1t2_connection()` identified from old-gen IR (§9B.10/§9B.11): count word @RAM `0x1A662`, conn_num = `_stack_config` byte `0xBF39` bits 4–5 ✓ |
| `0x01E182B0` | `DAT_0000bf39 = DAT_0000bf39 & 0xcf \| 0x10;` | = `__set_user_ctrl_conn_num(1)`; the `--conn-num=2` patch site (`31 24`→`31 25` = `r1 |= 16`→`r1 |= 32`) ✓ |
| `0x01E7EC28` | name compare → `DAT_0000b464 = 1..4`; `"TID-MIC-EAR"`→4, `"TID-MIC"`→2/3, else 1; `DAT_00010e00 & 0xC0 == 0x80` → 6 | the routing-mode classifier (§9A) — first machine-readable decode of the full if-chain ✓ |

## 25.4 Round-trip: decompiled C → official toolchain → pi32v2 code

Compile flags from the SDK (`apps/spp_and_le/board/br23/Makefile`):
`clang -target pi32v2 -mcpu=r3 -Oz`. The recompiled `is_1t2_connection`
emits the **same instruction forms** as the vendor compiler:

```
vendor 0x01E1787C                     recompiled (-Oz, our C)
  r0 = 0xBF39                           r0 = 0x1A662
  r1..r0 = b[r0+3..0]  (u32 as 4 loads)  r0 = h[r0]        (u16)
  r1 = 0x1A520; r1 = h[r1+322]           r2 = r0 & 0x7
  r0 = uextra(r0, p:4, l:2)              r1 = b[0xBF39]
  r1 = r1 & 0x7                          r1 = uextra(r1, p:4, l:2)
  r0 = 1; if (r1 != r2) r0 = 0           r0 = 1; if (r2 != r1) r0 = 0
  rts                                    rts
```

54 B → 34 B (the vendor u32 field read expands to 4 byte loads; a byte read
is equivalent for bits 4–5). `set_conn_num`: 50 B → 18 B, same
`& 0xFFFFFFCF` / `|= 16` pair. **Zero relocations** in the `.o` (pure absolute
RAM addressing) — the `.text` blob drops straight into the image.

## 25.5 Fixed-point proof (static)

`splice_rt.py` replaced both functions in the user's patched image
(BT-PTT/BT-PTT2/OD-PTT intact — `--show` confirms), re-encrypted, and the
result was **re-imported into Ghidra and re-decompiled: byte-identical C** to
the decompilation of the original vendor code. vendor asm → C → vendor asm → C
is a round trip at both ends.

## 25.6 Hardware “unchanged” test — **UNTESTED**

Test image: `work/roundtrip/rt_test.bin` (built from `Dumps/dump_internal.bin`
+ `--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT` + the two recompiled functions).
Expected: identical behaviour to the current patched firmware (BT connects,
BT-PTT works, normal PTT works). Flash with the usual
`jl-uboot-tool` procedure and report.

## 25.7 What this route can and cannot fix (multipoint context)

* **Can:** replace any function or block with compiler-generated code of
  similar size — eviction policy, app-layer connection handling, new small
  features (the BT-PTT2 cave code could have been written this way).
* **Cannot (yet):** change the precompiled stack's `user_info_t` data model
  (`[1 x conn_info]`, §9B.11). That layout is baked into every function of
  the closed `btstack.a`; a second connection slot means rewriting the whole
  stack, not a function. The realistic next target found with this tooling:
  locate the exact **eviction decision** (who disconnects the incumbent when
  a second device connects) and turn it into “reject the newcomer” (first
  wins) or defer it — behaviour changes, not the data model.
* Cross-version note: Ghidra analysis is reproducible from
  `work/app_dec.bin`; keep the project in `work/` (scratch).

---

Next: use the decompiler on the HCI connection-request / connection-complete
path and the app connect menu to find the eviction call site (§9B.11 named
the suspects: `user_operation_control` @`0x01E21AF8`, ops table `0xBF48`).
