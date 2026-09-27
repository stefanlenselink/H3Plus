[<< Index](Findings.md)

# Bluetooth HFP — 6. Key remap milestones — hardware-confirmed (9A.42–9A.50)

### 9A.42 Manual pages: PF1/PF2 side keys, PTT2, OD PTT and the Bluetooth menu — mapped to code

#### Side-key menus (manual 7.31, items 27–30)

| Menu | Options (manual) |
|---|---|
| 27 PF1 S Press | NONE, FM radio, Lamp, TONE, Alarm, Weather, **PTT2**, **OD PTT** |
| 28 PF1 L Press | NONE, FM radio, Lamp, Cancel Sq, TONE, Alarm, Weather |
| 29 PF2 S Press | as 27 |
| 30 PF2 L Press | as 28 |

Note in the manual: *if S Press = PTT2 or OD PTT, L Press cannot be set.*

The S-press option list in firmware (string-pointer array at `0x01EBD728`) is `None, FM Radio, Lamp, Tone, Alarm, Weather, PTT2, OD PTT`.

The S-press executor `0x01E75DBE` switches on the stored value with `tbb` over `value − 1`, covering values 1–8. Decoded:

| Value | Target | Behaviour |
|---|---|---|
| 0 | — | none |
| 1 | `0x01E75DE4` | FM radio toggle (`b[+0x29]`) |
| 2 | `0x01E75E06` | lamp (`0x01E75C02`) |
| 3 | `0x01E75E74` | nothing here; tone is handled elsewhere |
| 4 | `0x01E75E0E` | alarm; uses the Alarm Mode setting `+0x1055` |
| 5 | `0x01E75E1E` | weather (`0x01E75D00`) |
| 6 | `0x01E75E26` | toggles `b[+0x26]` (also gates PTT) |
| **7** | `0x01E75E38` | **PTT2**: `b[+0x46] = 1` (**TX on VFO B**), then TX start. No BT involvement. |
| **8** | `0x01E75E42` | **OD PTT**: `call 0x01E72C38` (the mode 5/6 audio-GPIO function from §9A.35). Requires OD connected (`b[0xB390+0xEA]`), then TX on the current VFO. |

The stored values (7 = PTT2, 8 = OD PTT) are one higher than the list positions (6, 7). The mapping in between is not yet traced. The stored values themselves are certain: the scanner's hold-mode test is "value ∈ {7, 8}", and 7 is the value that forces main PTT onto VFO A.

**So PTT2 is simply "PTT on the second VFO"** (dual-watch B). It keys TX through the same `0x01E5993C` as the main PTT and has no BT-mic logic. It is useful for a different reason: it turns a PF key into a clean **press/release hold key**, which is exactly what a PTT substitute needs.

**OD PTT is the Odmaster phone-platform PTT.** It is the only user of the mode 5/6 audio path. That is why forcing a headset into mode 6 did nothing useful: the path belongs to the phone-app link, not a headset.

#### Bluetooth menu (manual 7.35)

Firmware menu order (pointer array at `0x01EBD288`): `BT On/Off, BT Mode, BT Name, BT Pairing, OD PTT, OD Mode, BT Int Mic, BT Int Spk, BT Mic Gain, BT Spk Gain, BT PIN Code, BT Reset`.

| Menu | Manual text | Relevance |
|---|---|---|
| 2 BT Mode | Receiver / Emitter. In Emitter mode the radio pairs to accessories via menu 4; compatible accessories are "Bluetooth PTT, Bluetooth MIC, Bluetooth headset" | the mode used for headsets |
| 5 OD PTT | OD (to Odmaster only) / OD+Analog (both simultaneously) | the OD-link TX target, not a headset |
| 6 OD Mode | Local / Forward / Full | OD audio routing |
| **7 BT Int MIC** | "Bluetooth microphone gain switch", OFF/ON | ⚠️ **not yet traced**; the name suggests "use the radio's internal mic while BT is connected". Worth a zero-risk test on stock firmware. |
| 8 BT Int Spk | OFF/ON | internal speaker while BT is connected |
| 9 / 10 BT Mic / Spk Gain | 1–5 | — |

### 9A.43 The key-code patches — main PTT or a side key made identical to `+SPP=P`/`R`

Following §9A.41, the fix is to make a physical key push `0x2A`/`0x2B` instead of its own code. Each patch rewrites one `r0 = imm` literal (`48 xx`) in the scanner:

| Patch | Site VA | Flash byte | Change | Reached when |
|---|---|---|---|---|
| `pttdown` | `0x01E52400` | `0x057401` | `48 28` → `48 2a` | main PTT press (always) |
| `pttup` | `0x01E524BE` | `0x0574BF` | `48 29` → `48 2b` | main PTT release (always) |
| `pf1down` | `0x01E5253C` | `0x05753D` | `48 2c` → `48 2a` | PF1 press, **only if PF1 S Press = PTT2 or OD PTT** |
| `pf1up` | `0x01E52578` | `0x057579` | `48 2d` → `48 2b` | PF1 release, same condition |
| `pf2down` | `0x01E52678` | `0x057679` | `48 30` → `48 2a` | PF2 press, same condition |
| `pf2up` | `0x01E526AE` | `0x0576AF` | `48 31` → `48 2b` | PF2 release, same condition |

The PF literals are separate from the tap-mode literals (`0x01E525A0`, `0x01E526DA`), so tap actions such as FM, Lamp and Alarm are unaffected. The key only becomes an SPP-style PTT when set to PTT2/OD PTT.

All sites are in sector `0x057000`. Unlike patch B, each literal is used exactly as the SPP arm uses it, so there is **no queue imbalance**.

#### Recommended first test — PF variant, main PTT untouched

> ✅ **HARDWARE-CONFIRMED 2026-09-23** — see §9A.44.

```console
$ python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin work/pf_m4.bin --duplex-mode 4 \
      --only duplex --only pf1down --only pf1up --only pf2down --only pf2up --sectors work/pf
plaintext bytes changed: 5
  flash 0x057000-0x057FFF  4 byte(s) changed  -> work/pf_057000.bin
  flash 0x083000-0x083FFF  1 byte(s) changed  -> work/pf_083000.bin
```

```
erase 0x057000 0x1000
write 0x057000 pf_057000.bin
erase 0x083000 0x1000
write 0x083000 pf_083000.bin
```

Then on the radio:

1. Set **Menu 27 PF1 S Press = PTT2**. Try OD PTT only if PTT2 misbehaves.
2. Connect the headset.
3. Hold PF1: TX should come from the BT mic.

The main PTT keeps its stock behaviour, so it acts as a control in the same session.

The second variant is `work/pttkey_m4.bin` (`pttdown` + `pttup` + duplex mode 4), which moves the behaviour onto the main PTT.

| Artifact | SHA256 | Diff vs live flash |
|---|---|---|
| `work/pf_m4.bin` | `686C664C547C26726EE528C4E68F427B81237799494280489038A1F62133B754` | 5 bytes (`0x5753D`, `0x57579`, `0x57679`, `0x576AF`, `0x83C87`) |
| `work/full_write_pf_m4_safe.bin` (full image `0x0`–`0xC9000`, device block spliced) | `1DBC88FC457711C77A7865C2745F80D6D51A0E9F5FCA21F0B8495CA40B937DFF` | same 5 bytes; also the same 5 vs `full_write_mode6_safe.bin` |
| `work/pttkey_m4.bin` | `A857D9219220CDE38A3D1BB5FBE477D17FEBAA23E37C204E222A747052B77206` | 3 bytes (`0x57401`, `0x574BF`, `0x83C87`) |

Both are built from the live dump, so the `0xC8FE0` device block is already correct. Restore with `work/restore_057000.bin` and `work/restore_083000.bin`.

#### Risks and open points

- **Long hold on a PF key.** ✅ *Resolved on hardware (§9A.44): holds of several seconds release correctly on both keys.*
  - After ≥ `0x65` ticks, the scanner reaches the long-press branch. It contains `30 e9 02 40` (`0x01E525D6`), which pi32dis cannot decode, and which presumably suppresses the long-press code `0x2E` for values 7/8.
  - If it does not, `b[+0x32]` would be set and the release code `0x2B` replaced by `0x2F`, leaving TX on until the TOT timer.
  - Stock PTT2 would have the same bug, so suppression is likely, but **verify with a hold of several seconds**.
- **No headset connected.** The mask test fails for mode 0/3, so the GPIOs are left alone and the radio mic is used. That is fine *if* `+0xD4` is cleared on disconnect, which has not been verified. If a stale 4 remains, TX would be silent.
- **PTT2 side effect.** While any PF key is set to PTT2, the stock main-PTT path always transmits on VFO A. The patched `0x2A` handler uses the current VFO instead.
- **Gates differ.** `0x28` is suppressed by `b[+0x190]` and `b[+0x89A]==2`; `0x2A` is suppressed by `b[+0x47]`. Menus or special screens may therefore behave differently with the `pttdown`/`pttup` variant.
- `+0xEE` is only cleared by the `0x2B` path, so every press must be matched by a release. The scanner guarantees this through its latch.

#### Tool changes

- The literal swaps are defined in a single `KEYCODE_PATCHES` table in `tools/patch_h3plus_firmware_bluetooth.py`.
- They are not in `DEFAULT_PATCHES`; request them with `--only`. *(Superseded by `--bt-ptt`, §9A.45.)*
- The mode 5/6 labels note the `0x16` mask exclusion and the mode 6 hardware failure.

### 9A.44 ⭐⭐⭐⭐ MILESTONE: a radio key transmits the BT headset mic — HARDWARE-CONFIRMED

**Date:** 2026-09-23.
**Firmware:** `work/pf_m4.bin`, i.e. duplex mode 4 + `pf1down`/`pf1up`/`pf2down`/`pf2up`. Only 5 bytes differ from the factory flash.
**Headset:** Jabra Evolve 65. It is a generic, non-TIDRADIO headset: its name is not in the whitelist and it has no SPP/`+SPP=P` support.

This achieves the project's core goal on real hardware: **connect any named headset, press a key on the radio, and transmit the headset's microphone.** It works with no PC or phone in the loop and no accessory-side protocol.

#### Test results

| # | Step | Result |
|---|---|---|
| 1 | Flash sectors `0x057000` and `0x083000` | ✅ done |
| 2 | Menu 27 PF1 S Press = **PTT2** (also PF2 via menu 29); headset connected | ✅ done |
| 3 | Hold PF1 → TX from BT mic; release → TX stops | ✅ **works on PF1 and PF2** |
| 4 | Hold for several seconds | ✅ still releases correctly on both keys |
| 5 | Main PTT, same session | ✅ transmits the radio's own mic, as stock |
| 6 | Wired Kenwood-plug headset + main PTT | ✅ transmits via the radio's wired path, as stock |

#### Observations

1. **Repeated transmissions are stable.** Every PF1/PF2 press works, audio arrives every time, and the radio does not crash. The §9A.22 "first transmission only" failure is **not present** here. It was seen with a PC acting as the headset, so it now points at the host stack (PipeWire/BlueZ), not the radio.
2. **Tones in the headset:** one short single tone at TX start, and a short, lower two-tone "blu-bleep" at TX end. See the analysis below.
3. **The user hears their own voice in the headset** during TX, with no noticeable delay.

#### Why it works — the confirmed chain

Every link below was derived statically in §9A.41–§9A.43. This test is the first end-to-end confirmation.

```
PF key down (ADC ladder, S Press = PTT2/OD PTT -> hold mode)
  -> scanner pushes 0x2A instead of 0x2C        (patched literal, 0x01E5253C / 0x01E52678)
  -> standby switch, tbh 0x01E78ED8 -> 0x01E794A2  (the +SPP=P handler)
       send "AT+MPTT=0" to the BT peer          (0x01E17E62(0x6D, 9, 0x01E9BC3C))
       0x01E17E62(9), 0x01E17E62(0x1B)           (BT stack commands; see below)
       TX start 0x01E5993C, b[0xB390+0xEE] = 1
       routing mode 4 in mask 0x16 -> audio GPIOs 0x20 / 0x00 -> 0   <- BT mic to TX
PF key up
  -> scanner pushes 0x2B instead of 0x2D        (0x01E52578 / 0x01E526AE)
  -> 0x01E79516: 0x01E17E62(0xA), 0x01E17E62(0x1C), TX stop, +0xEE = 0, mode-gated restore
```

Small correction to §9A.41: the first `0x01E17E62` call's third argument is `0x01E9B56C + 0x6D0 = 0x01E9BC3C`, the string `"AT+MPTT=0"`. Its length is 9, which is the second argument. That is the `AT+MPTT=0` observed on every `+SPP=P` in the §9A.24 capture. `0x01E17E62(cmd, len, data)` matches the shape of the JieLi SDK's `user_send_cmd_prepare(cmd, param_len, param)`. Command `0x6D` sends raw AT/SPP data to the peer. The pairs `9`/`0xA` and `0x1B`/`0x1C` are symmetric press/release commands, most likely audio/SCO open/close. Their exact enum names are not confirmed.

#### Analysis of observation 2 — the start/end tones

It has not yet been checked whether stock main-PTT transmissions (radio mic) produce the same tones in the headset. Candidates:

- **(a) The headset's own call-audio tones.** On press, the handler issues the BT commands `9` / `0x1B`, and on release `0xA` / `0x1C`. If these open and close the SCO voice link, many headsets play a short tone on SCO connect and a lower two-tone on disconnect. This matches the "single tone up / double tone down" pattern exactly.
- **(b) A radio-generated TX-start / roger tone** mixed into the BT audio.

A quick way to tell them apart: pair a *different* headset brand. If the tones change character, they come from the headset. If they stay identical, the radio generates them. Also check whether the radio's own speaker makes the same tones when no headset is connected.

The tones are harmless and give useful feedback that TX started and stopped. They are not transmitted over the air unless the headset mixes them into its mic stream, which is unlikely.

#### Analysis of observation 3 — hearing yourself

The **absence of any noticeable delay** is the key clue. A loop through the radio would go headset mic → BT codec → radio → BT codec → headset. That round trip costs tens to hundreds of milliseconds, which is clearly audible as an echo. Zero-latency self-hearing is the signature of **headset-local sidetone**, which is mixed in the headset's own DSP.

The Jabra Evolve 65 has a configurable sidetone that is active during calls. It is adjustable (Off/Low/Medium/High) in **Jabra Direct** under the headset settings. The radio treats the BT-PTT transmission as an HFP voice (SCO) link, so the headset behaves as in a phone call.

The radio's own menu 23 *Side Tone* is the other lever to try. In handheld radios that name usually refers to DTMF/key sidetone, so it is less likely to be involved.

#### What is now known to be true

- A generic headset, **classified as mode 4 by the 1-byte duplex patch**, delivers mic audio to TX when the `0x2A` handler runs.
- The `0x2A` handler is **source-agnostic**: it behaves the same whether `0x2A` comes from SPP or from the key scanner.
- The PF hold-mode path (settings 7/8) pushes exactly one release per press, even on long holds.
- Queue balance holds over many cycles. There is no leak of the kind that made patch B unsafe.

### 9A.45 Tool: `--bt-ptt` chooses which key/setting becomes the BT-mic PTT

> **Superseded default (§9A.47):** the tool now defaults to `--duplex-mode 4 --bt-ptt ptt`, the hardware-confirmed main-PTT build. `odptt` is opt-in, and `--pf-menu` adds the relabelled "PTT" / "BT PTT" options.

`tools/patch_h3plus_firmware_bluetooth.py` now takes `--bt-ptt SOURCE`. It is repeatable. If `--only` is not given, it defaults to `ptt` (was `odptt` when this section was written).

| `--bt-ptt` | Patches | Key used | Status |
|---|---|---|---|
| `odptt` | `odpttdown`, `odpttup` | **any** PF key whose S Press = **OD PTT**; the key is chosen in the radio menu (27 / 29) | UNTESTED |
| `pf1` | `pf1down`, `pf1up` | PF1 with S Press = PTT2 **or** OD PTT | ✅ hardware |
| `pf2` | `pf2down`, `pf2up` | PF2 with S Press = PTT2 **or** OD PTT | ✅ hardware |
| `ptt` (**default** since §9A.47) | `pttdown`, `pttup` | main PTT, always | ✅ HARDWARE-CONFIRMED (§9A.46) |
| `none` | — | — | — |

#### Why OD PTT, and why in the executor

The `pf1`/`pf2` literals serve **both** PTT2 and OD PTT, because the scanner's hold-mode test is `setting − 7 ≤ 1`. That also takes away stock PTT2 ("transmit on VFO B"), which is a genuinely useful feature.

OD PTT only works with TIDRADIO's Odmaster phone app, so it is the better option to take over. The scanner offers no room for a per-value test without a code cave. The only large zero run found (`0x01EB34EA`, §9A.37) turned out to sit inside RGB565 bitmap data, so it is **not** usable.

The cleaner place is the **PF action executors**. Their case-8 bodies are OD PTT's own code and nothing else:

```
press executor 0x01E75DBE, tbb case 8 (0x01E75E42) - before:
  call 0x01E72C38            ; OD mode 5/6 audio GPIO path
  call 0x01E56D3C
  if (!b[0xB390+0xEA]) ...   ; OD connected?
  -> TX start on current VFO
after (8 bytes, flash 0x07AE42):
  48 2a         r0 = 0x2A
  be ea 8d e2   call 0x01E52362      ; push into the key queue
  55 04         {pc, r5, r4} = [sp++]

release executor 0x01E75E76, case 8 (0x01E75E82) - before:
  call 0x01E72DC4 ; if OD connected: TX stop
after (8 bytes, flash 0x07AE82):
  48 2b         r0 = 0x2B
  be ea 6d e2   call 0x01E52362
  00 04         pc = [sp++]
```

The flow becomes: key down → scanner pushes `0x2C`/`0x30` (stock) → standby handler → executor case 8 → pushes `0x2A` → the consumer picks up `0x2A` on its next pass → the `+SPP=P` handler, exactly as in §9A.44.

The release goes through `0x2D`/`0x31` and then `0x2B`. It costs one extra pass through the queue, a few ms.

Safety of the rewrite:

- The queue pop `0x01E5B2B4` decrements the count and shifts the queue left, so pushing from inside a handler just appends behind the entry being handled.
- The epilogues are byte-identical to the executors' own (`55 04` at `0x01E75E6E`/`0x01E75E74`; `00 04` at `0x01E75E80`).
- Case 7 (PTT2) enters at `0x01E75E38` → `0x01E75E56`, and on release at `0x01E75E92`. No byte it executes changes.
- The leftover bytes after each new epilogue are unreachable.
- The long-press path is safe for value 8 too: the scanner's `setting − 7` range idiom at `0x01E525D2` covers {7, 8}. The standby `0x2E` handler checks only `== 7`, so it would not help if the scanner pushed `0x2E` for 8, but it does not.

Caveat: the scanner's press path for value 8 always calls `0x01E5033A(0)` first. For value 7 it does so only when `b[+0x2A] != 0`. The function's purpose is unknown, so a small behavioural difference versus the confirmed PTT2 path is possible.

#### Artifacts

All are built from `Dumps/dump_internal.bin`, so the `0xC8FE0` device block matches the unit.

| Artifact | SHA256 | Diff vs live flash | Sectors |
|---|---|---|---|
| `work/odptt_m4.bin` (1 MiB) | `D1AF53CE9FCD2434FD94C1D3FB01956D800D3679219DA9A53F84664EFBC4C923` | 17 bytes (`0x7AE42`–`0x7AE49`, `0x7AE82`–`0x7AE89`, `0x83C87`) | `work/odptt_07A000.bin`, `work/odptt_083000.bin` |
| `work/full_write_odptt_m4_safe.bin` (`0x0`–`0xC9000`) | `6B594EBAD638B816289E29EEB81EA7691A200F05D7F0732479BA5F56F937244A` | same | — |

Restore: `work/restore_07A000.bin` (new) and `work/restore_083000.bin`.

> ⚠️ If `pf_m4` is currently flashed, writing only the two `odptt` sectors leaves the `pf1`/`pf2` literals in sector `0x057000`. Those push `0x2A` directly and would mask this test. Also write `work/restore_057000.bin`, or use the full image.

### 9A.46 Main PTT as the BT-mic PTT — HARDWARE-CONFIRMED

> ✅ **Result (flashed `mainptt_057000.bin` + `mainptt_083000.bin`).** The main PTT transmits the BT headset mic while the headset is linked, and falls back to the radio mic when it is not. No code cave or runtime condition was needed.
>
> | # | Test | Result |
> |---|---|---|
> | 1 | BT headset connected, hold main PTT (repeated) | ✅ TX from BT mic; release stops TX |
> | 3 | BT headset disconnected, press main PTT | ✅ TX from **radio mic**. Routing mode `+0xD4` is not left stale after disconnect, so the silent-TX risk is gone |
> | 4 | Wired Kenwood headset, BT off | ✅ TX via wired mic |
> | 4b | Wired Kenwood headset PTT **while BT is connected** | TX from **BT mic** (see below) |
> | 5 | PTT in menus, scan, FM radio, dual-watch B | ✅ same as stock PTT |
> | 6, 7 | PF1 = PTT2 control; TOT | not reported |
>
> **Test 4b is expected behaviour, not a bug.** The wired headset's PTT reaches the same main-PTT key path, so it also pushes `0x2A`. The mic mux then follows the BT link state (routing mode ∈ {1,2,4}), not which PTT was pressed. The patch keys on the PTT event and cannot tell the jack PTT from the body PTT. Whether the jack PTT is a separate GPIO has not been checked. To use the wired mic with a BT headset linked, disconnect BT or use a PF-key source (`odptt`/`pf1`/`pf2`) instead of `ptt`.
>
> The concern in the paragraph below ("if test 3 or 4 fails …") no longer applies.

Build (`--bt-ptt ptt`, main PTT only; PF keys stock):

```console
$ python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin work/mainptt_m4.bin \
      --duplex-mode 4 --bt-ptt ptt --sectors work/mainptt
patches: duplex, pttdown, pttup
  flash 0x057000-0x057FFF  2 byte(s) changed  -> work/mainptt_057000.bin
  flash 0x083000-0x083FFF  1 byte(s) changed  -> work/mainptt_083000.bin
```

| Artifact | SHA256 | Diff vs live flash |
|---|---|---|
| `work/mainptt_m4.bin` (1 MiB; byte-identical to the earlier `pttkey_m4.bin`) | `A857D9219220CDE38A3D1BB5FBE477D17FEBAA23E37C204E222A747052B77206` | 3 bytes (`0x57401`, `0x574BF`, `0x83C87`) |
| `work/full_write_mainptt_m4_safe.bin` (`0x0`–`0xC9000`) | `DFD299C85D595043B41A57040A608F6C40CCA73A5DBA81378D9E9AE547515646` | same |

Writing `mainptt_057000.bin` over the current `pf_m4` sector also reverts the PF literals, so the sector route alone gives a clean main-PTT-only state.

#### What to test

| # | Test | Expected | Why it matters |
|---|---|---|---|
| 1 | BT headset connected, hold main PTT | TX from BT mic; release stops | the goal |
| 2 | Repeat many times, including long holds | stable, as on PF | same `0x2A`/`0x2B` handlers as the confirmed PF path |
| 3 | **Disconnect the BT headset**, press main PTT | TX from radio mic | ⚠️ checks that routing mode `+0xD4` is reset on disconnect; a stale 4 would give silent TX |
| 4 | Wired Kenwood headset, BT off, press PTT | TX via wired mic | same as 3 |
| 5 | PTT inside a menu, during scan, with FM radio on, on the dual-watch B channel | note any difference from stock | `0x28` and `0x2A` have different gates (`b[+0x190]`, `b[+0x89A]` vs `b[+0x47]`), and non-standby screens may handle `0x28` but not `0x2A` |
| 6 | PF1 = PTT2 (stock, since PF is unpatched here) | TX on VFO B from **radio mic** | a radio-mic control in the same session |
| 7 | TOT: hold beyond the time-out timer | TX cut as stock | `0x2A` uses the same TX start `0x01E5993C` |

If test 3 or 4 fails, the fix is to put the main-PTT behaviour behind a runtime condition: native `0x28` when no BT headset is linked. That needs a code cave, so the executor-style reuse from §9A.45 does not apply to the main key.

Restore: `work/restore_057000.bin` + `work/restore_083000.bin` (factory, mode 3), or reflash `pf_057000.bin` + `pf_083000.bin` to return to the confirmed PF setup.

### 9A.47 PF menu options "PTT" and "BT PTT" (`--pf-menu`), and new tool defaults

Goal: main PTT = BT mic when a headset is linked, otherwise radio mic (§9A.46, confirmed). Each PF key can then be set in menu 27 / 29 to either a **radio-mic-always "PTT"** or a **"BT PTT"**.

#### New tool defaults

`python tools/patch_h3plus_firmware_bluetooth.py <src> <dst>` now applies `duplex` (**mode 4**) + `pttdown` + `pttup`. The output is byte-identical to the hardware-confirmed `work/mainptt_m4.bin` (checked). `--bt-ptt` still selects `ptt` / `pf1` / `pf2` / `odptt` / `none` (repeatable). `--bt-ptt none` gives duplex only.

#### What can and cannot be repurposed

Only the two **hold-type** S Press values can serve as a PTT:

- The scanner treats a PF key as a press/release key only for values 7 and 8 (`value − 7 < 2`, §9A.41). Every other value is a tap key, and its action fires **once, on release**.
- Only values 7 and 8 have a release action (release executor `0x01E75E76`: `if r0==8 …`, `if r0==7 …`).
- So taking over Weather, Alarm, etc. would key TX on a tap with **no release event**, leaving TX stuck until TOT. Moving the hold range to cover those values would do the same to PTT2 / OD PTT. Not done.

Real *additional* menu entries are not feasible either:

- The option pointer arrays are packed back to back: English `0x01EBD728` is immediately followed by Chinese `0x01EBD748`, and 7 more lists follow at `0x01EBF08C` + n·`0x20`.
- The settings validator at `0x01E6CB22` resets a stored value > 8 to 7.
- The executor `tbb` covers values 1–8 only.
- There is no verified free space for code or strings (§9A.37, §9A.45). The zero runs found in the string pool are font bitmaps and a FAT boot-sector template.

So the two hold options are **relabelled and re-wired** instead.

#### Patch set (`--pf-menu` = `ptt2radio` + `odpttdown` + `odpttup` + `pflabels`)

| Option (value) | New label | Patch | Behaviour |
|---|---|---|---|
| PTT2 (7) | **PTT** | `ptt2radio`: `0x01E75E3E` `40 21` → `04 88` (`goto 0x01E75E50`) | Case 7 jumps into case 8's tail: `b[+0x46] = b[+0x77] >> 7` (**current VFO**), then TX start `0x01E5993C`. There is no BT involvement, so it uses the **radio mic**. Release is the stock case 7 (TX stop `0x01E5A138`). The stock `b[+0x26]` gate stays. |
| OD PTT (8) | **BT PTT** | `odpttdown` / `odpttup` (§9A.45) | pushes `0x2A` / `0x2B`, the same as the main PTT |

Labels (`pflabels`, 22 data sites, all in the app region):

| What | Sites | Change |
|---|---|---|
| "PTT" | 9 × list entry 6 (`0x01EBD740`, `0x01EBD760`, `0x01EBF0A4` … `0x01EBF164`) | pointer `0x01E8E30E` ("PTT2") → `0x01E8CE57` ("PTT", the tail of "OD PTT"; the string itself is unchanged) |
| "BT PTT" string | `0x01E8E30E` | `PTT2\0` + 2 bytes → `BT PTT\0`. "PTT2" is referenced **only** by the 9 PF lists. |
| "BT PTT" pointers | 9 × list entry 7 | `0x01E8CE54` ("OD PTT") → `0x01E8E30E` |
| Russian "НЕТ" | 3 pointers (`0x01EBF0AC`, `0x01EBF188`, `0x01EBF400`) | The string at `0x01E8E313` loses its first 2 bytes, so its only 3 pointers are moved to the existing "Нет" at `0x01E92010` (a lower-case difference in the Russian UI only) |

A pointer scan of `0x01E8E300`–`0x01E8E320` found no other references to the overwritten bytes. The Bluetooth menu's own "OD PTT" item (OD / OD+Analog) points at the unchanged string and keeps its name. The tool refuses `--pf-menu` together with `--bt-ptt pf1/pf2`, because those literals take over both options before the executor runs.

Verified in the built image: all 9 lists render `…, Weather, PTT, BT PTT`; the executor disassembles as intended; `--show` recognises every site; the legacy `pf_m4` build is byte-identical.

#### Side findings

- **Menu index → stored value:** the menu writer at `0x01E6DE7A` and the reader at `0x01E6AD8C` add or subtract 1 above index 2. S-press index 6/7 therefore stores 7/8. Value 3 is "Cancel Sq", which appears only in the L-press list (Turkish L list: `YOK, FM Radyo, Lamba, Sesi İptal, TON, Alarm, Hava Durumu`). The §9A.42 executor table is therefore probably one off for values 4–6: 4 = Tone (it uses `+0x1055`, which sits next to the 1000/1450/1750/2100 Hz list), 5 = Alarm, 6 = Weather (toggles `b[+0x26]`, which also blocks PTT). Not verified on hardware.
- Factory default: `0x01E6B9C6` sets PF1 S Press = 7 (PTT2).
- `0x01E617D2` forces PF1 S Press = 8 when the routing mode is 5/6 (Odmaster link). A mode-4 headset never takes this path.
- With `--bt-ptt none`, main PTT with a PF key on value 7 still forces VFO A (stock PTT2 behaviour, `0x01E52418`). With `ptt`, the `0x2A` handler resets `b[+0x46]` to the current VFO, so this does not matter.

#### Build and artifacts

```console
$ python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin work/pfmenu_m4.bin --pf-menu --sectors work/pfmenu
patches: duplex, pttdown, pttup, ptt2radio, odpttdown, odpttup, pflabels
plaintext bytes changed: 72
  flash 0x057000  2 byte(s)   0x07A000 18   0x083000 1   0x093000 6   0x0C2000 8   0x0C4000 37
```

| Artifact | SHA256 |
|---|---|
| `work/pfmenu_m4.bin` (1 MiB) | `6BD4DB3961DF6D442C6862E2EB4BFC288F274AB68752609D38D4EB77570480EA` |
| `work/full_write_pfmenu_m4_safe.bin` (`0x0`–`0xC9000`, device block from the dump) | `32447E29386B70393F600C0F70D40ECC1C0D811E8CBF3BE791AEE539EECD0C9B` |
| sectors | `work/pfmenu_{057000,07A000,083000,093000,0C2000,0C4000}.bin` |
| restore | `work/restore_{057000,07A000,083000,093000,0C2000,0C4000}.bin` (from the dump) |

Coming from `mainptt_m4`, sectors `0x057000` and `0x083000` are already identical. Only `0x07A000`, `0x093000`, `0x0C2000` and `0x0C4000` need writing.

#### What to test

| # | Test | Expected |
|---|---|---|
| 1 | Menu 27 / 29 option list | `None, FM Radio, Lamp, Tone, Alarm, Weather, PTT, BT PTT` |
| 2 | PF1 = **PTT**, BT headset linked, hold PF1 | TX on the **current** VFO from the **radio mic**; release stops |
| 3 | PF1 = PTT, switch VFO A/B, repeat | follows the selected VFO |
| 4 | PF2 = **BT PTT**, headset linked, hold PF2 | TX from the BT mic, same as main PTT (tones and sidetone as §9A.44) |
| 5 | PF2 = BT PTT, headset **disconnected** | expected TX from the radio mic, as main PTT in §9A.46 test 3 |
| 6 | Main PTT with BT linked, then without | BT mic, then radio mic (regression of §9A.46) |
| 7 | L Press menus 28 / 30 while S Press = PTT / BT PTT | locked, as stock for PTT2 / OD PTT |
| 8 | Bluetooth menu item 5 | still named "OD PTT" |

---

### 9A.48 Configurable `--pf-menu` mapping (`both` / `ptt` / `btptt` / `swap`)

§9A.47 hard-wired PTT2 → "PTT" and OD PTT → "BT PTT". Because the two stock
options are useful in their own right, `--pf-menu` now takes a value choosing
**which stock option is replaced by which new option**, so a user keeps
whichever stock option they actually use:

| `--pf-menu=MODE` | value 7 (stock PTT2) | value 8 (stock OD PTT) | patches |
|---|---|---|---|
| `both` (default, bare `--pf-menu`) | **PTT** | **BT PTT** | `ptt2radio` `odpttdown` `odpttup` `pflabels` |
| `ptt` | **PTT** | *stock OD PTT* | `ptt2radio` `pflabels` |
| `btptt` | *stock PTT2* | **BT PTT** | `odpttdown` `odpttup` `pflabels` |
| `swap` | **BT PTT** | **PTT** | `pf78press` `pf78release` `ptt2radio` `odpttdown` `odpttup` `pflabels` |

#### The press dispatch is a `tbb` table (new)

The §9A.42 "executor" is entered at `0x01E75DBE`. It subtracts 1, range-checks
`value-1 <= 7`, then does a table branch:

```
01E75DC6  r0 = r2 + -1
01E75DCA  if (r0 > 0x7) goto 0x01E75E74          ; out of range -> return
01E75DCE  r4 = 0x102F0 ; r5 = 0xB390
01E75DDA  tbb r0                                  ; 00 01 00 00
01E75DDC  ...                                     ; 8 entries, 1 byte each
```

Each `tbb` entry is the **target's byte offset / 2 from the table start**
(`0x01E75DDC`). Native entries `04 15 4C 19 21 25 2E 33`:

| value | entry | target | case body |
|---|---|---|---|
| 7 | `0x2E` | `0x01E75E38` | PTT2: guard `b[+0x26]`, `r0 = 1` (VFO B), `goto 0x01E75E56` |
| 8 | `0x33` | `0x01E75E42` | OD PTT: `call 0x01E72C38`, `call 0x01E56D3C`, then the current-VFO tail |

This is what makes **`swap`** possible without new code: exchange the two
entry bytes at `0x01E75DE2` (`2E 33` → `33 2E`, patch `pf78press`) and value 7
runs the OD PTT body while value 8 runs the PTT2 body. The existing
`odpttdown` / `ptt2radio` patches then land on the *other* menu value.

#### The release dispatch is two compares (new)

The release executor at `0x01E75E76` (called from `0x01E79658` with `r0` = the
stored value) has no table — just two `if (r0 == imm) goto`:

```
01E75E78  if (r0 == 0x8) goto 0x01E75E82   ; 00 f8 03 10   case 8 release
01E75E7C  if (r0 == 0x7) goto 0x01E75E92   ; 00 f8 09 0e   case 7 release
```

The compare immediate is `word1 >> 9` (`0x1003 >> 9 = 8`, `0x0E09 >> 9 = 7`;
the low 9 bits are the branch displacement). Swapping the two immediates
(`03 10 00 f8 09 0e` → `03 0E 00 f8 09 10` at `0x01E75E7A`, patch
`pf78release`) makes value 7 run the case-8 release and value 8 the case-7
release, matching the swapped press dispatch.

#### String placement per mode

"BT PTT" (6 chars + NUL = 7 bytes) does not fit over the 5-byte "PTT2" string,
so it overwrites 7 bytes starting at one of two addresses:

| MODE | "BT PTT" written at | "PTT2" string | Russian "НЕТ" (`0x01E8E313`) |
|---|---|---|---|
| `both` | `0x01E8E30E` (over `PTT2\0` + NET[0:2]) | destroyed | loses 2 bytes → 3 pointers moved to "Нет" `0x01E92010` |
| `swap` | `0x01E8E30E` | destroyed | same |
| `btptt` | `0x01E8E313` (over `НЕТ\0` exactly) | **intact** | overwritten → 3 pointers moved to "Нет" |
| `ptt` | — (no "BT PTT") | intact | intact |

"PTT" is always the tail of "OD PTT" at `0x01E8CE57`, so that string is never
modified and the Bluetooth menu's own "OD PTT" item keeps its name in every
mode. The nine PF S Press lists (entry = value 7 at the base pointer, value 8
at +4) are repointed per mode; `ptt` leaves the value-8 pointers on "OD PTT",
`btptt` leaves the value-7 pointers on "PTT2".

#### Detection across modes

All four label layouts are precomputed. `build_patches()` installs the selected
one as the `pflabels` multi-patch and attaches the other three as detection-only
*alternatives*, so `find_app_start()` still recognises an image patched with a
**different** mode. `apply_multi()` refuses to mix: if the image already carries
another mode's labels, it says so and names the mode:

```
patch 'pflabels': sites are target, native, ...; refusing to patch a partly
modified image
The image already carries the --pf-menu=swap labels; re-run with that mode
(or start from a stock image) to change them.
```

`odpttup`'s context window was narrowed to `0x01E75E80` so it no longer
overlaps the `pf78release` site at `0x01E75E7A`.

#### Verification

A byte-level suite (`work/verify_pfmenu.py`, since replaced by
`tools/verify_actions.py` / `tools/verify_cli.ps1`, see §9A.49) builds all four modes
from `Dumps/dump_internal.bin` and asserts, per mode: the duplex + main-PTT
patches; the executor wiring (value-8 press/release push `0x2A`/`0x2B`, case-7
body → current-VFO tail, stock where the mode keeps it); the `tbb` table and
release compares (untouched except in `swap`, and the decoded targets are the
intended ones); every one of the 9 language lists renders the expected label
for both values; the Russian "НЕТ" pointers; and that the **changed-byte set
equals exactly the expected set** (no collateral edits). `both` is byte-identical
to the §9A.47 `pflabels`. All four modes are idempotent, and a `.fw` build
re-detects cleanly. **0 failures.**

| MODE | bytes | sectors changed (from `BIN/…V1.0.50.bin`) |
|---|---|---|
| `both` | 72 | `0x057000` `0x07A000` `0x083000` `0x093000` `0x0C2000` `0x0C4000` |
| `ptt` | 23 | `0x057000` `0x07A000` `0x083000` `0x0C2000` `0x0C4000` |
| `btptt` | 52 | `0x057000` `0x07A000` `0x083000` `0x093000` `0x0C2000` `0x0C4000` |
| `swap` | 49 | `0x057000` `0x07A000` `0x083000` `0x093000` `0x0C2000` `0x0C4000` |

All four remain **untested on hardware**; the `both` wiring follows §9A.47 most
directly. `swap` additionally relies on the `tbb` entry format and the
compare-imm encoding decoded above.

---

### 9A.49 End-user CLI redesign: `--bluetooth-mode`, `--PTT`, `--PTT2`, `--OD-PTT`

No new firmware reverse engineering — pure tool semantics. `patch_h3plus_firmware_bluetooth.py`
was re-exposed as end-user options; the internal patch sites, addresses, and
byte sequences are unchanged from §9A.44–§9A.48, and every previously built
combination still produces **byte-identical** output (verified against the
§9A.48 artifacts).

**Rename / replacement mapping:**

| old CLI | new CLI |
|---|---|
| `--duplex-mode=N` | `--bluetooth-mode=N` (aliases `--bt`, `-b`) |
| `--bt-ptt ptt` | `--PTT=BT-PTT` (now the default) |
| `--bt-ptt none` | `--PTT=PTT` |
| `--pf-menu=both` | `--PTT2=PTT --OD-PTT=BT-PTT` |
| `--pf-menu=ptt` | `--PTT2=PTT` |
| `--pf-menu=btptt` | `--OD-PTT=BT-PTT` |
| `--pf-menu=swap` | `--PTT2=BT-PTT --OD-PTT=PTT` |
| `--bt-ptt pf1/pf2/odptt` | removed from the CLI; the legacy `pf1down`…`pf2up` scanner-literal patches remain via `--only` |

**Action model.** `--PTT`, `--PTT2`, `--OD-PTT` each take one of four actions:
`PTT`, `PTT2`, `BT-PTT`, `OD-PTT` (case-insensitive, `BTPTT`/`BT_PTT` accepted;
option *names* are also case-insensitive via an argv canonicalisation prepass).
`--PTT=PTT`, `--PTT2=PTT2`, `--OD-PTT=OD-PTT` are the respective stock actions
and are no-ops for that option. **Default when nothing is given:**
`--bluetooth-mode 4 --PTT=BT-PTT --PTT2=PTT2 --OD-PTT=OD-PTT` (stated in
`--help` and echoed on every run).

**Reachability (validated, refused otherwise).** The main PTT key has its own
scanner literals (§9A.46) and can only be `PTT` or `BT-PTT`. The two menu
options share the two executor bodies decoded in §9A.48: value 7 runs
PTT2-or-PTT, value 8 runs OD-PTT-or-BT-PTT, and the §9A.48 swap moves both
values at once — so exactly **8 pairs** are reachable:

| `--PTT2` | `--OD-PTT` | patches beyond duplex + `pttdown`/`pttup` |
|---|---|---|
| `PTT2` | `OD-PTT` | — (stock) |
| `PTT` | `OD-PTT` | `ptt2radio` + labels |
| `PTT2` | `BT-PTT` | `odpttdown`/`odpttup` + labels |
| `PTT` | `BT-PTT` | both + labels (classic §9A.47/48 `both`) |
| `OD-PTT` | `PTT2` | `pf78press`/`pf78release` + labels |
| `OD-PTT` | `PTT` | swap + `ptt2radio` + labels |
| `BT-PTT` | `PTT2` | swap + `odpttdown`/`odpttup` + labels |
| `BT-PTT` | `PTT` | swap + `ptt2radio` + `odpttdown`/`odpttup` + labels |

Not possible (yet): `--PTT=PTT2` / `--PTT=OD-PTT`; BT-PTT on value 7 while
value 8 keeps OD-PTT; PTT/PTT2 on value 8 without the swap; both options set
to the same action. The tool refuses each with the list of possible pairs.

**Label placement refinement.** When `--PTT2=BT-PTT` and no entry needs "PTT2"
anymore, "BT PTT\0" overwrites `"PTT2\0"` itself and the entry-7 pointers stay
native — those no-op pointer sites are now dropped from the `pflabels` site
list (they previously read "already applied" and made `--show` report a partly
modified image). `work/verify_pfmenu.py` was replaced by `tools/verify_actions.py`
(8 pairs × wiring/dispatch/labels/changed-byte-set, **0 failures**), with the CLI
matrix in `tools/verify_cli.ps1`, and the
§9A.48 artifacts `t_both`/`t_ptt`/`t_btptt`/`t_swap` reproduce byte-identically
through the new CLI.

### 9A.50 Direct body rewrite: all 12 `--PTT2` / `--OD-PTT` pairs

The §9A.48/§9A.49 model could only reach **8 of the 16** pairs because it kept
the two executor bodies at their native addresses and only *exchanged* them (the
`tbb` swap) or patched one literal inside them. That limit was an artefact of the
assembly layout, not of the hardware — the end user does not care which physical
body runs which option, only that each menu option performs the action they
chose. The tool now **rewrites each body in place** to the requested action, so
**every ordered pair of distinct actions builds directly** (12 pairs = the six
unique combinations in either option order). Only same-action pairs remain
refused: one menu option is one code body and can run one action.

**Press executor (unchanged layout).** Stored values 7 ("PTT2") and 8 ("OD PTT")
dispatch through a `tbb r0` at `0x01E75DDA` over an 8-entry table at `0x01E75DDC`;
entry 7 → body A `0x01E75E38` (10 B), entry 8 → body B `0x01E75E42` (8 B). The
table is now **never touched** — the bodies are rewritten instead, so the table
always reads native (`2e 33` at `0x01E75DE2`). Shared tails are never patched:
`0x01E75E50` current-VFO (`r0 = b[r4+0x77]>>7`), `0x01E75E56` TX start
(`b[r4+0x46] = r0 …`), `0x01E75E4A` OD tail (`b[r5+0xEA]` test), `0x01E75E74`
plain return `5504`.

Each body is small enough to hold any of the four actions:

| action | body A (10 B @ `0x01E75E38`) | body B (8 B @ `0x01E75E42`) |
|---|---|---|
| `PTT2` | native (`… 4021 → VFO-B tail`) | `4021` + goto TX-start tail + 2× dead `0004` |
| `PTT`  | native guard + goto current-VFO tail | 4× goto current-VFO tail (only first runs) |
| `BT-PTT` | `482A` + `call push(0x2A)` + `5504` return | `482A` + `call push(0x2A)` + `5504` |
| `OD-PTT` | `call setup` + `call refresh` + goto OD tail | native |

**Release executor.** The release path at `0x01E75E76` has no table: two
`if (r0 == imm) goto` compares select a body. The native order is **imm 8 first**
(`0x01E75E78` → `0x01E75E82`, the OD teardown) **then imm 7** (`0x01E75E7C` →
`0x01E75E92`, the TX stop). The whole 32-byte window `0x01E75E78` is re-encoded:
the two compares keep their order and only their targets change, so any pair whose
targets are the native ones stays **byte-identical** to factory. A `BT-PTT` release
body (`482B` + `call push(0x2B)` + `ret`, 8 B) replaces the OD body at `0x01E75E82`
when that slot is free.

**The one tight case — `{OD-PTT, BT-PTT}`.** Both an OD release *and* a BT release
must coexist, but there is only one free slot. Resolved by shrinking the OD release
to `call teardown; call TXstop; ret` (10 B) at `0x01E75E82` and putting the BT
release at the slot freed after it (`0x01E75E8C`). The added `TXstop` call is
**unconditional** in this combo — safe because `TXstop` (`0x01E5A138`) self-guards on
`b[0x102F0+0x24C]` and returns immediately when there is no active TX. [UNTESTED on
hardware — semantic change vs the native conditional path.]

**Verified encoders** (added to the tool, checked against stock samples):
`encode_goto2(site, target)` — 1-word conditional-true branch, `d=(t−s−2)/2`,
`w = 0x8004 | (d<<8)`, `0 ≤ d ≤ 0xF` (matches 4 stock samples); and
`encode_cmp_eq_imm(site, imm, target)` — `d=(t−s−4)/2`, bytes `00 F8 (w1&FF) (w1>>8)`
with `w1 = (imm<<9)|d` (matches native `00f80310` / `00f8090e`).

**Backward compatibility.** Images built with the obsolete swap model are detected
by their swapped `tbb` table (`33 2e` at `0x01E75DE2`) and **refused** — re-writing
the bodies at native addresses would mislabel them; the user must start from a stock
image. The three legacy release images are kept as detection-only states so
already-flashed firmware is still recognised by `--show`.

**Regression.** `tools/verify_actions.py` (self-contained) builds all 12 pairs and
checks bodies / release / native table / scanner sites / nine label lists /
changed-byte-set / idempotency / `--show`, plus the same-action, `--PTT=PTT2`/`OD-PTT`,
and swapped-table refusals — **0 failures**. `tools/verify_cli.ps1` covers the CLI
matrix (six combinations in both orders, aliases, rejections) — **0 failures**.
The four previously-reachable non-swap pairs stay byte-identical to the §9A.48/49
builds; the old swap pairs legitimately differ (they are now built directly).

---

*[<< Index](Findings.md)*
