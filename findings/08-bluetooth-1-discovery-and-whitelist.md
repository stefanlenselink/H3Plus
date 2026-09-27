[<< Index](Findings.md)

# Bluetooth HFP — 1. Discovery, whitelist and the AT+MPTT hypothesis (9A.1–9A.14)

## 9A. Bluetooth HFP / Microphone Support — CONFIRMED

> **This answers the project's feature goal: full Bluetooth headset support (mic + listen).**
>
> **The firmware already contains a complete HFP implementation, mSBC wideband codec support, and user-facing menu items for Bluetooth microphone control.** This is not a feature that needs to be written from scratch.

### 9A.1 Bluetooth profile service records

Found at `0x01B03A`–`0x01B300` in the decrypted app:

```
0x01b03a  JL_A2DP_SRC      <- A2DP Source (radio sends audio out)
0x01b090  JL_HFP_AG        <- Hands-Free Profile, AUDIO GATEWAY role  ***
0x01b0e0  JL_A2DP          <- A2DP Sink
0x01b12e  JL_HFP           <- Hands-Free Profile, HF role             ***
0x01b18b  JL_HID
0x01b300  JL_SPP
```

**`JL_HFP_AG` is the decisive find.** For a radio talking to a headset, the radio must act as the **Audio Gateway** and the headset as the Hands-Free unit. That service record is compiled into the firmware. HFP is the profile that carries **bidirectional** voice over a SCO/eSCO link — i.e. microphone audio *from* the headset.

### 9A.2 Full HFP AT command set

Immediately preceding the service records, at `0x01AE04`–`0x01AFAC`:

```
AT+BRSF=16             Supported features exchange
AT+BAC=1,2             Available codecs: 1 = CVSD (narrowband), 2 = mSBC (wideband)
AT+BCS=2               Codec Selection -> mSBC
AT+BCC                 Bluetooth Codec Connection (trigger SCO setup)
AT+CIND=? / AT+CIND?   Indicator support / status
AT+CMER=3,0,0,1        Event reporting
AT+CHLD=?              Call hold capabilities
AT+BIND=2 / =? / ?     HF indicators
AT+CMEE=1              Extended error reporting
AT+CLIP=1              Caller line ID
AT+CCWA=1              Call waiting
AT+NREC=0              Disable noise reduction / echo cancellation
AT+CGMI?               Manufacturer ID
AT+VGS=07              Gain of Speaker
AT+VGM=07              Gain of MICROPHONE                             ***
AT+XAPL=ABCD-1234-0100,10   Apple accessory identification
```

Two of these matter enormously:

- **`AT+VGM`** — *Gain of Microphone*. This command only exists to control a **remote microphone over HFP**. Its presence proves the microphone audio path is implemented, not merely stubbed.
- **`AT+BAC=1,2` / `AT+BCS=2`** — the firmware negotiates **mSBC**, the 16 kHz wideband codec. A device that only ever plays audio out would have no reason to implement mSBC codec negotiation, which exists specifically for HFP voice links.

The string `msbc` also appears independently at `0x0A0580`.

### 9A.3 User-facing menu strings ALREADY EXIST

From the multi-language menu string table around `0x091E28`–`0x0920B6`:

| Offset | String | Language | Meaning |
|---|---|---|---|
| `0x091F98` | **`BT Int Mic`** | EN/DE | **Bluetooth Internal Mic** |
| `0x091FA3` | `BT Int Laut` | DE | BT Internal Speaker |
| `0x091FAF` | **`BT Mic Gain`** | EN | **Bluetooth microphone gain** |
| `0x091FBB` | `BT Spk Gain` | EN | Bluetooth speaker gain |
| `0x09200F` | **`BT Mic Int`** | ES | BT Mic Internal |
| `0x092025` | `BT Ganancia` | ES | BT Gain |
| `0x091E7E` | `BT Mikrofon` | TR | BT Microphone |
| `0x091E8A` | `BT Hoparl` | TR | BT Speaker |
| `0x0920AA` | `BT Haut Int` | FR | BT Internal Speaker |
| `0x0920B6` | `BT Gain` | FR | BT Gain |

**`BT Int Mic` is almost certainly the exact toggle required** — a setting selecting whether the *internal* (radio body) microphone or the *external* (headset) microphone is used as the TX audio source. The fact that it is translated into 8+ languages means it is a shipping, supported menu item.

### 9A.4 Supporting audio-path symbols

```
0x08BB09  usb_audio
0x08BB39  mic_stream          <- microphone streaming path
0x097F2E  audio_mc_device
0x097F44  audio_dec_init
0x097F53  audio_dec
0x097F5D  bt_dec              <- Bluetooth decoder
0x097F7E  audio_adc_demo      <- ADC = microphone capture
0x097F8D  audio_enc           <- ENCODER (required to send mic audio out)
0x097F97  mic_demo
0x0A0970  TID-MIC             <- device/profile name
0x0A0F5C  TID-MIC-EAR         <- "mic + earpiece" — a headset mode name!
0x0A05CB  (BLE)
0x0C7F2F  H3_Plus_BLE
0x097249  bt_paired
```

`audio_enc` and `mic_stream` are the encode-side counterparts to `audio_dec`/`bt_dec`. **`TID-MIC-EAR` is especially suggestive** — a named mode combining microphone and earpiece.

### 9A.4a The app's memory-mapped load base — `0x01E00000`

Determined by collecting every 4-byte little-endian value in the plausible pointer range and testing which base value makes the most of them land exactly on null-terminated string starts:

```
base=0x01E00000  hits=2368      <<<< winner (9.5x the runner-up)
base=0x01E02000  hits=250
base=0x01E07000  hits=241
base=0x01DFF000  hits=177
```

**Conversion rules:**

```
VA         = 0x01E00000 + offset_in_app_dec.bin
flash addr = 0x00005000 + offset_in_app_dec.bin
VA         = flash_addr + 0x01DFB000
```

This makes **cross-reference search possible**: to find code referencing a string, search the image for its VA as a 4-byte LE value. Essential for any further analysis, and the basis for all the xrefs below.

### 9A.4b Confirmed Bluetooth menu structure

The menu pointer table at flash `0x0C2288`–`0x0C22B4` (4-byte stride) resolves exactly to the menu observed on the device:

| # | Table addr | → VA | String |
|---|---|---|---|
| 1 | `0x0C2288` | `0x01E8CFDE` | `BT On/Off` |
| 2 | `0x0C228C` | `0x01E8A30A` | `BT Mode` |
| 3 | `0x0C2290` | `0x01E8A312` | `BT Name` |
| 4 | `0x0C2294` | `0x01E8A31A` | `BT Pairing` |
| 5 | `0x0C2298` | `0x01E8CE54` | `OD PTT` |
| 6 | `0x0C229C` | `0x01E8A325` | `OD Mode` |
| 7 | `0x0C22A0` | `0x01E8CF98` | **`BT Int Mic`** |
| 8 | `0x0C22A4` | `0x01E8A32D` | `BT Int Spk` |
| 9 | `0x0C22A8` | `0x01E8CFAF` | `BT Mic Gain` |
| 10 | `0x0C22AC` | `0x01E8CFBB` | `BT Spk Gain` |
| 11 | `0x0C22B0` | `0x01E8A338` | `BT PIN Code` |
| 12 | `0x0C22B4` | `0x01E8A344` | `BT Reset` |

The Chinese translations follow immediately at `0x0C22B8`+. Two are informative: `OD Mode` → `Odmaster模式` ("Odmaster mode") and `OD PTT` → `Od PTT按键` ("Od PTT button"). **"OD" is a TIDRADIO accessory-ecosystem brand name**, not a generic Bluetooth term — further evidence that the wireless-accessory path is vendor-specific by design.

> Notably, there are **no `Headset` / `Speaker` / `Handsfree` mode-option strings anywhere in the image.** `BT Mode` does not offer a generic-headset profile choice.

### 9A.5 The accessory **device-name whitelist** — real, but NOT the gate

> **⚠️ SUPERSEDED as root cause.** The whitelist exists, but flash tests and live pairing tests proved it is **not** what blocks Bluetooth mic. See [§9A.12](#9a12--actual-root-cause--the-accessory-must-send-atmptt1) for the real mechanism. This section is retained because the strings and offsets are still accurate and still useful.

This section originally attributed the vendor's statement—

> *"Currently, this feature only supports our Bluetooth products. Testing of other Bluetooth products not from our company will take some time."*

—to a name check. The statement is true, but for a **protocol** reason, not a name reason.

#### The whitelist

Three accessory names are compiled into the firmware:

| Flash addr | VA | String | Slot size | Product |
|---|---|---|---|---|
| `0x0A0968` | `0x01E9B968` | `TID-PTT` | 8 B (7 chars + NUL) | Wireless PTT Button |
| `0x0A0970` | `0x01E9B970` | `TID-MIC` | 8 B (7 chars + NUL) | Wireless Speaker Mic |
| `0x0A0F5C` | `0x01E9BF5C` | `TID-MIC-EAR` | 12 B (11 chars + NUL) | Speaker Mic + earpiece |

`TID-PTT` and `TID-MIC` are **exactly 8 bytes apart**, immediately following the standard HFP AT commands in the same literal pool:

```
000a0950  41 54 2b 42 4c 44 4e 00 41 54 2b 43 48 55 50 00  |AT+BLDN.AT+CHUP.|
000a0960  41 54 2b 43 4c 43 43 00 54 49 44 2d 50 54 54 00  |AT+CLCC.TID-PTT.|
000a0970  54 49 44 2d 4d 49 43 00 6c 0a e8 01 b0 0a e8 01  |TID-MIC.........|
```

#### The check

`TID-PTT`'s address `0x01E9B968` appears **exactly once** in the whole image, embedded inline in code at **flash `0x083C5A`**:

```
00083c50  52 ee 54 0d 41 26 04 9c c6 ff 68 b9 e9 01 42 27  |R.T.A&....h...B'|
                                    ^^^^^^^^^^^ = 0x01E9B968
```

`TID-MIC` has **no absolute reference anywhere in the image** (verified: pointer count = 0), and sits exactly 8 bytes after `TID-PTT` in an 8-byte-aligned literal pool:

```
0x0A0950  'AT+BLDN'   len 7
0x0A0958  'AT+CHUP'   len 7
0x0A0960  'AT+CLCC'   len 7
0x0A0968  'TID-PTT'   len 7   <- the only referenced entry
0x0A0970  'TID-MIC'   len 7   <- reached as TID-PTT_ptr + 8
```

So the code walks a **two-entry table** from the `TID-PTT` pointer with stride 8. The comparison routine is the function around `0x083C00`–`0x083D00`.

#### ⭐ The match is a PREFIX match — confirmed by observation

The paired name of the real accessory, read off the radio, is:

```
TID-PTT0cd28a          <- 13 characters: "TID-PTT" + MAC suffix
```

But the firmware only stores the 7-character `"TID-PTT\0"`. **An exact `strcmp` could never match** — yet the PTT button works. Therefore the comparison must be a bounded/prefix compare (`strncmp`/`memcmp` over ~7 bytes).

This is the decisive finding, and it is what makes the whole thing practical:

> **Writing the first 7 characters of *any* headset's Bluetooth name into the `TID-MIC` slot is sufficient to whitelist it.** The trailing characters are never compared.

It also explains the design: every TIDRADIO accessory ships as `TID-XXX` + its own MAC suffix, so the firmware *has* to prefix-match to recognise them all.

#### Proprietary AT commands — the accessory protocol

The radio acts as an HFP **Audio Gateway**; TIDRADIO accessories connect as Hands-Free units and drive the radio with **non-standard vendor AT commands**:

| Flash addr | String | Meaning |
|---|---|---|
| `0x0A0C3C` | `AT+MPTT=0` | **Mic PTT release** (unkey TX) |
| `0x0A0C46` | `AT+MPTT=1` | **Mic PTT press** (key TX) |
| `0x0A0E18` | `AT+BGMODE=1` | Background mode on |
| `0x0A0E24` | `AT+BGMODE=0` | Background mode off |

`AT+MPTT` is **not part of any Bluetooth standard** — it is TIDRADIO's own extension. This is how the wireless PTT button keys the radio: over the HFP control channel, not via a separate profile.

`xrefs` to `AT+MPTT=0` at `0x05FDE2` and `0x07834C` mark the PTT command handler.

#### Why "hear but not speak"

- **A2DP / speaker path** is opened for *any* paired device → you hear received audio. ✅
- **HFP SCO uplink (microphone)** is only established, and `BT Int Mic` only allowed to switch away from the internal mic, when the name matches the whitelist → your headset's mic is ignored and the radio falls back to the internal/Kenwood-connector mic. ❌

This exactly reproduces the observed behaviour.

### 9A.6 The fix — patch the whitelist strings (data-only, no code change)

Because the match is a prefix match, the fix is to **write the first N characters of the target headset's name into a whitelist slot**. This changes *string data only* — no instructions are touched, no lengths shift, nothing moves.

| Slot | Flash addr | Max chars |
|---|---|---|
| `ptt` | `0x0A0968` | 7 |
| `mic` | `0x0A0970` | 7 |
| `micear` | `0x0A0F5C` | 11 |

**Patch the `mic` slot, not `ptt`** — that keeps the TIDRADIO wireless PTT button working while adding the headset as a "wireless speaker-mic".

Tool: [`tools/patch_btname.py`](../tools/patch_btname.py)

```console
$ python tools/patch_btname.py Dumps/dump_internal.bin --show
slot          flash  max  current
--------------------------------------------
ptt      0x000A0968    7  'TID-PTT'
mic      0x000A0970    7  'TID-MIC'
micear   0x000A0F5C   11  'TID-MIC-EAR'

$ python tools/patch_btname.py Dumps/dump_internal.bin work/dump_jabra.bin --mic="Jabra E"
mic: 'TID-MIC' -> 'Jabra E'  @ flash 0x000A0970
plaintext bytes changed: 7
ciphertext bytes changed: 7  (0xA0970 - 0xA0976)
wrote work/dump_jabra.bin (1048576 bytes)
```

**Verification of the produced image:**

```
size equal: True
total differing bytes in 1MB image: 7   (0xA0970 .. 0xA0976)
UBOOT 0x0-0x5000 untouched:      True
device data 0xC8FE0 untouched:   True
VM area 0xC9000+ untouched:      True
slots now: b'TID-PTT\x00'  b'Jabra E\x00'
```

Seven bytes changed in a 1 MB image, all inside the app region, with the bootloader, the device-specific data and the Bluetooth identity all bit-identical. This is about as low-impact as a firmware patch can be.

> ⚠️ **Not yet flashed.** `work/dump_jabra.bin` is a full 1 MB *flash image*, not a `.bin` update package — see [§9A.9](#9a9-how-to-actually-apply-the-patch) before writing it.

### 9A.7 The stretch goal — PTT button + separate headset

Target: `TID-PTT` supplies the PTT button while a *different* Bluetooth headset supplies mic and audio.

This requires the radio to hold **two simultaneous Bluetooth links** (multipoint). Open questions:

- Does the BR23 stack as built allow 2 concurrent HFP/A2DP connections? JieLi silicon supports multipoint, but the firmware may cap `max_connections` at 1.
- If only one link is allowed, the alternative is a **single device that does both** — i.e. patch `TID-PTT`'s slot to the headset name so the headset provides mic+audio, and accept PTT from the radio body.
- `AT+MPTT` is link-agnostic at the protocol level, so if multipoint works, the PTT button and the headset could be serviced independently.

Investigate the connection-count limit before attempting this.

### 9A.8 VM differential test — NEGATIVE (and that is informative)

Two 4 KiB reads of the plaintext VM area were taken with different accessories paired:

```
=>JL: read 0xC9000 0x1000 vm_tidmic.bin     # TIDRADIO PTT button paired
=>JL: read 0xC9000 0x1000 vm_generic.bin    # Jabra Evolve 65 paired
```

Result:

```
sizes 4096 4096
differing bytes: 82   in 4 runs
  0xC9602-0xC9615 (20)
  0xC9618-0xC9633 (28)
  0xC9654-0xC965D (10)
  0xC9660-0xC9677 (24)
```

All four runs are in previously-erased (`0xFF`) space, and the `generic` dump simply has **82 more non-`0xFF` bytes** than the `tidmic` one (1203 vs 1121). The VM is an **append-only log**: new pairings are appended to free space rather than rewriting existing records.

The appended records have the shape:

```
000c9610  f0 cc 06 00 00 00 ff ff 30 00 34 73 e2 4b 5c 74  |........0.4s.K\t|
000c9620  79 7b b3 c7 ca 17 fc a7 79 32 f2 e0 82 49 7f a9  |y{......y2...I..|
000c9630  b4 51 00 02 ...                                  |.Q..            |
```

— an item header, the constant 6-byte field `34 73 e2 4b 5c 74` (present in every pairing record, including in the original full dump at `0xC9280`), then a **16-byte Bluetooth link key**.

**Crucially, string extraction finds no remote device names at all:**

```
0x0C9012 'TD-H3-Plus-3511'        <- the radio's own BR/EDR name
0x0C9036 'TD-H3-Plus-3511-ble'    <- the radio's own BLE name
0x0C9490 'TD-H3-Plus-9320'        <- second VM bank
0x0C94B4 'TD-H3-Plus-9320-ble'
```

Neither `TID-PTT0cd28a` nor `Jabra Evolve 65` is stored anywhere.

**Conclusions:**

1. The VM stores **only link keys**, not remote names and **not a device-type flag**.
2. Therefore the whitelist decision is made **entirely in code, at connection time, against the live advertised name**. There is no persisted "this device is approved" bit to flip.
3. This **rules out a configuration-only workaround** and confirms the firmware patch is the required route.
4. A second device-name pair (`TD-H3-Plus-9320`) at `0xC9490` indicates a **dual-bank VM** — consistent with `jlfs_dual_bank_check` in the bootloader.

> Note: entering UBOOT mode drops all Bluetooth connections instantly (the bootloader does not run the BT stack), so these dumps reflect *stored pairing records*, never live link state.

### 9A.9 How to actually apply the patch

`work/dump_jabra.bin` is a **full 1 MB raw flash image**, which is not the same thing as a distributable `.bin` update package. Two routes:

**Route A — write the app region directly (recommended, minimal).**
Only 7 bytes changed, all within one 4 KiB sector (`0xA0000`–`0xA0FFF`). With `jl-uboot-tool`:

```
erase 0xA0000 0x1000            # erase the one sector
write 0xA0000 sector_patched.bin
```

Carve the replacement sector from `work/dump_jabra.bin[0xA0000:0xA1000]` first. This never touches UBOOT, the device-specific bytes at `0xC8FE0`, or the VM area.

**Route B — build a proper update package.** Apply the same 7-byte patch to `BIN/TD-H3-PlusV1.0.50.bin` (identical content at identical offsets — proven in [§12A.4](16-flashing-and-hardware-dump.md#12a4-the-big-result--flash-content--distributed-bin)) and flash through the normal updater. Requires resolving the package CRC — see [§14 Priority 6](18-open-questions-next-steps.md#priority-6--build-a-repack-workflow).

> ⚠️ Before any write: `Dumps/dump_internal.bin` is the restore image for this unit. Keep an off-machine copy.

### 9A.10 Remaining verification steps

1. ~~Confirm `BT Int Mic` toggling has no effect with a non-whitelisted headset~~ ✅ **Confirmed — no effect.** The whitelist overrides the menu setting, exactly as predicted.
2. ~~Diff the VM area~~ ✅ **Done — negative** ([§9A.8](#9a8-vm-differential-test--negative-and-that-is-informative)). No device-type flag is persisted.
3. **Disassemble `0x083C00`–`0x083D00`** to read off the exact compare length. ⬅ **now the critical blocker** — see [§9A.11](#9a11-flash-test-1--negative-the-prefix-match-assumption-was-wrong).
4. **Check multipoint support** for [§9A.7](#9a7-the-stretch-goal--ptt-button--separate-headset).

### 9A.11 Flash test #1 — NEGATIVE: the prefix-match assumption was wrong

The 7-byte patch (`TID-MIC` → `Jabra E` at flash `0x0A0970`) was flashed to hardware and **verified on-chip**:

| Stage | sha256 of sector `0xA0000`–`0xA0FFF` | Result |
|---|---|---|
| before write | `543addb7492e0f83717e7b123a97193908c54c277d81fc4e6acb9226db8afa62` | matches original ✅ |
| after write | `34675f38361cfd71964412ac0699e5fa3d81bc71fa7e0bec1bc8c098a04a8a20` | matches patched ✅ |
| after reboot | unchanged | patch persists ✅ |

**The patch applied perfectly and the behaviour did not change.** The Jabra Evolve 65 still plays receive audio but the radio still takes mic input from the Kenwood connector.

#### What this rules out

The write itself is not in question — it was hash-verified on the physical chip before and after. So one of the two underlying assumptions is wrong:

1. **The match is full-length, not a prefix.** `"Jabra E"` ≠ `"Jabra Evolve 65"`, so a full-length compare would reject it. This is the user's hypothesis and is consistent with everything observed.
2. **Or the `mic` slot is not actually consulted.** Re-confirmed by pointer scan:

```
TID-PTT     VA=0x01E9B968  refs: ['0x083C5A']
TID-MIC     VA=0x01E9B970  refs: []
TID-MIC-EAR VA=0x01E9BF5C  refs: []
```

Only `TID-PTT` has an absolute reference. The assumption that `TID-MIC` is reached as `ptt_ptr + 8` (an 8-byte-stride table walk) is **inferred from the literal-pool layout, never proven**. If the code only ever dereferences the `TID-PTT` pointer directly, patching the `mic` slot changes a string nothing reads.

#### The reference site, confirmed

```
083C50  52 ee 54 0d 41 26 04 9c c6 ff 68 b9 e9 01 42 27  |R.T.A&....h...B'|
                                ^^^^^ ^^^^^^^^^^^
                                 |     literal 0x01E9B968 ("TID-PTT")
                                 └── `c6 ff` = load-imm32 into r6
```

The `cX ff <imm32>` load-immediate form is consistent across the whole function (`c1 ff` → `0x01E7E814`, `c5 ff` → `0x01E9B74D`, `c7 ff` → `0x000102F0`), so the decode is solid. What follows it (the actual compare call and its length argument) still needs a real pi32v2 disassembler.

#### The decisive next experiment — zero risk, no flashing

Rather than guess again, distinguish the hypotheses with a **renameable** Bluetooth device (an Android phone, a laptop, or any headset with a companion app that allows renaming):

| Test | Set device BT name to | If mic works | If mic does not work |
|---|---|---|---|
| A | exactly `Jabra E` | **full-length match confirmed** — whitelist theory correct, and the fix is to find a longer slot | `mic` slot is not consulted at all |
| B | exactly `TID-MIC` | `mic` slot *is* consulted, full-length | `mic` slot is dead — only `TID-PTT` matters |
| C | exactly `TID-PTT` | the single referenced slot is the real gate | the gate is not name-based at all |

Run A → B → C in order and stop at the first success. This settles in minutes what would otherwise take a full disassembly, and needs no writes to the radio.

> Note the 7-character ceiling is a real constraint: the `mic` slot is bounded by the next string at `+8`. If the match turns out to be full-length, the fix cannot be an in-place rename — it requires either relocating the pointer to a longer string in free space, or patching the compare itself.

### 9A.12 ⭐ ACTUAL ROOT CAUSE — the accessory must send `AT+MPTT=1`

Tests A, B and C (renaming a device to `Jabra E`, `TID-MIC`, `TID-PTT`) **all failed**. The name is not the gate. Four hardware observations identify the real mechanism:

1. **The PTT button exposes two Bluetooth endpoints**, visible from a phone:
   - `TID-PTT0cd28a-B` — headset icon → **Classic BR/EDR, HFP** (the audio path)
   - `TIDRADIO PTT0cd28a-A` — plain BT icon → **BLE** (the control path)
2. **The radio's BT Pairing screen has three slots**, with slot 2 empty — consistent with the radio tracking these as separate bindings.
3. **`BT Int Mic` refuses to stay off** with the real button attached: set it to off, press PTT once (either on the radio or the button), and it flips back on. Something in the PTT handler **writes** that setting.
4. **⭐ Mic source follows which PTT was pressed**, not which device is connected:
   - press PTT **on the radio** → only the radio's mic is live
   - press PTT **on the BT button** → only the button's mic is live

Observation 4 is decisive. Both devices are connected the whole time, so no name check, no pairing state and no menu setting can explain the difference. **The mic route is selected by the origin of the PTT event.**

#### The protocol evidence

```
AT+MPTT=0   flash=0x0A0C3C  va=0x01E9BC3C  refs=['0x05FDE2', '0x07834C']
AT+MPTT=1   flash=0x0A0C46  va=0x01E9BC46  refs=[]
```

`AT+MPTT=1` sits exactly 10 bytes after `AT+MPTT=0` and has no pointer of its own — reached as `base+10`, or matched by comparing the trailing digit. These are **inbound** vendor AT commands: the button sends `AT+MPTT=1` on press and `AT+MPTT=0` on release over the HFP link, and the radio's handler keys TX **and mic routing** off them.

This fully explains the vendor's statement. A TIDRADIO accessory is not privileged by its *name* — it is the only thing that speaks this proprietary command. A Jabra has no way to send `AT+MPTT`, so the BT mic branch is never entered, and pressing the radio's own PTT takes the local path that routes the internal/Kenwood mic.

#### What this means for the fix

The goal is no longer "get past a whitelist." It is: **make a locally-initiated PTT press take the same mic-routing branch that `AT+MPTT=1` takes.**

That is a genuine code patch in the PTT handler, not a data patch — materially harder than the 7-byte string edit, and it needs the handler around `0x05FDE2` / `0x07834C` disassembled first. A pi32v2 disassembler is now a hard prerequisite rather than a nice-to-have.

One encouraging implication: since the radio already routes mic audio *from* a Bluetooth HFP device when `AT+MPTT=1` arrives, the SCO/mSBC uplink path is fully implemented and working. Nothing needs to be built — only re-triggered.

#### A cheap experiment worth trying first

If anything can inject `AT+MPTT=1` into the radio over HFP, the BT mic should activate with no firmware change at all. On Linux, a Bluetooth stack acting as an HF unit can send arbitrary AT commands to the radio's AG. That would confirm the theory outright and might even be a usable workaround via a phone app relaying PTT.

### 9A.13 A working pi32v2 disassembler — `tools/pi32dis.py`

No public disassembler exists for pi32v2 (GitHub search returns zero repositories). However kagaimiq's reverse-engineered [`cpu/pi32v2.md`](https://github.com/kagaimiq/jielie/blob/main/cpu/pi32v2.md) documents every known opcode as a bit-pattern table. Rather than hand-transcribe it, `tools/pi32dis.py` **parses the spec at runtime** and builds its decode table from it — 577 patterns (207 × 16-bit, 352 × 32-bit, 18 × 48-bit), all parsed cleanly.

Decoding rules implemented: fields are uppercase-led letter runs (`Xxxx` = 4-bit field X); operand text is built MSB-first from field bits and literal runs; the compressed `WeirdIMM` 12-bit immediate form is decoded per the spec's Definitions table; instruction length is resolved by picking the matching pattern with the most fixed bits.

Three encoding details were **not** in the spec and had to be determined empirically:

| Detail | Finding | How verified |
|---|---|---|
| 48-bit 32-bit immediates | stored **little-endian across the two trailing iwords**, i.e. halves swapped vs. the MSB-first bit listing | `c6 ff 68 b9 e9 01` must yield `0x01E9B968` (known `TID-PTT` pointer) |
| `call`/`goto` displacements | **PC-relative**, not absolute | three consecutive calls encode *decreasing* displacements that all resolve to one constant target |
| Register fields | render as decimal `r6`, not as an immediate | — |

Usage:
```
python tools/pi32dis.py work/app_dec.bin --flash 0x083C40 --count 26
python tools/pi32dis.py work/app_dec.bin --va 0x01E5AEF0 --count 20
python tools/pi32dis.py work/app_dec.bin --flash 0x05FDC0 --func
```

#### Result 1 — the whitelist compare, finally read directly

```
01E7EC58  c6 ff 68 b9 e9 01   r6 = 0x1E9B968          ; "TID-PTT"
01E7EC5E  42 27               r2 = 0x7                ; length = 7
01E7EC60  90 16               r0 = r9                 ; remote device name
01E7EC62  61 16               r1 = r6
01E7EC64  94 ea ae 9d         call 0x021127C0         ; memcmp-alike
01E7EC68  00 50               if (r0 == 0) goto 0x01E7EC88
01E7EC6A  01 e1 f4 65         r1 = r6 + 0x5F4         ; "TID-MIC-EAR"
01E7EC6E  42 2b               r2 = 0xB                ; length = 11
01E7EC72  94 ea a7 9d         call 0x021127C0
01E7EC76  00 4b               if (r0 == 0) goto 0x01E7EC8C
01E7EC78  69 88               r1 = r6 + 0x8           ; "TID-MIC"
01E7EC7A  42 27               r2 = 0x7                ; length = 7
01E7EC7E  94 ea a1 9d         call 0x021127C0
```

This **vindicates two earlier inferences and refutes a third**:

- ✅ It *is* a bounded prefix compare — explicit lengths 7, 11, 7. The `TID-PTT0cd28a` observation was read correctly.
- ✅ `TID-MIC` *is* reached as `ptt_ptr + 8`, and `TID-MIC-EAR` as `ptt_ptr + 0x5F4`, despite having no absolute pointer of their own. The 8-byte-stride table-walk guess was right.
- ❌ But [flash test #1](#9a11-flash-test-1--negative-the-prefix-match-assumption-was-wrong) still failed with a correct 7-char patch. So this function's verdict **does not gate mic routing** — it selects an accessory *class* (three distinct branch targets: `0x01E7EC88` / `0x01E7EC8C` / fallthrough) for something else, e.g. button-event decoding or UI labelling.

#### Result 2 — the inbound AT dispatcher, confirming §9A.12

```
01E5ADE0  c5 ff 3c bc e9 01   r5 = 0x1E9BC3C          ; "AT+MPTT=0"
01E5ADE6  59 8a               r1 = r5 + 0xA           ; "AT+MPTT=1"
01E5ADE8  42 29               r2 = 0x9
01E5ADEC  95 ea ea bc         call 0x021127C0
01E5ADF0  00 f8 80 00         if (r0 == 0x0) goto 0x01E5AEF0    ; PTT press
01E5ADF6  40 15               r1_r0 = r5_r4           ; "AT+MPTT=0"
01E5ADF8  95 ea e4 bc         call 0x021127C0
01E5ADFC  30 5e               if (r0 == 0) goto 0x01E5AEF8      ; PTT release
01E5ADFE  01 e1 dc 51         r1 = r5 + 0x1DC         ; "AT+BGMODE=1"
01E5AE06  95 ea dd bc         call 0x021127C0
01E5AE0A  30 5a               if (r0 == 0) goto 0x01E5AEFE
```

This is an **inbound** vendor-AT parser, exactly as predicted in §9A.12 — the accessory sends these to the radio. Each arm is a `call <handler>; goto <common epilogue at 0x01E5AF10>`. Note `AT+MPTT=1` is reached as `base + 0xA`, the same pointer-arithmetic idiom as the whitelist strings, which is why it has no absolute xref.

#### ⚠️ Unresolved — call targets land outside the image

Every `call` resolves above `0x02000000` (`memcmp` at `0x021127C0`, MPTT handlers at `0x0265993A` / `0x0265A206`), while the app image only spans `0x01E00000`–`0x01EC4020`. The PC-relative decode is almost certainly right (the three-call constant-target proof is strong), so these are most likely **mask-ROM** addresses — the JieLi SDK keeps libc and much of the BT stack in on-chip ROM. That would explain why `memcmp` is not in the flash image.

**Consequence:** the MPTT press/release handlers may not be patchable in flash at all. Before designing a code patch, this must be settled — e.g. by dumping the BR23 mask ROM, or by checking whether an overlay is copied to RAM at boot. This is now the top open question.

### 9A.14 Live-pairing obstacle: the radio's BLE identity rotates between sessions

While trying to pair the Ubuntu test box (`stefan@Stefan-PC`, BlueZ `bluetoothctl`) with the radio to run `tools/bt_hf_sim.py`, repeated `pair <MAC>` attempts against the previously-captured classic BR/EDR address (`0B:FF:59:E8:85:92`, name `TD-H3-Plus-9320`) all failed with `Device ... not available` — BlueZ never has a live `Device` D-Bus object for that address after its one-time initial sighting.

A later scan revealed why the classic address can't just be re-typed from memory: the radio's **BLE** identity is not fixed either. In the same physical unit, with no reflash in between:

| | earlier session | this session |
|---|---|---|
| BLE MAC | `0B:FF:59:9E:37:81` | `CD:90:4D:05:A1:81` |
| BLE name | `TD-H3-Plus-9320(BLE)` | `TD-H3-Plus-7934(BLE)` |

Both the MAC *and* the numeric name suffix changed. The new MAC's top bytes (`CD:90:4D`) don't look like a real registered OUI, which is the signature of a BLE **resolvable/random private address** — the radio (or its BT stack) appears to mint a fresh session identity each time BT is (re-)power-cycled or pairing mode is re-entered, rather than advertising a fixed hardware address. Static analysis in [§12A.6](16-flashing-and-hardware-dump.md#12a7-the-settings--vm-area-at-0x0c9000--plaintext) had already found two *different* banked name strings baked into flash (`TD-H3-Plus-3511` and `TD-H3-Plus-9320`), but `7934` matches neither — confirming this suffix is generated at runtime, not just toggled between two fixed flash-stored strings.

It is not yet confirmed whether the **classic** BR/EDR address rotates the same way, or whether it's simply only discoverable for a very short inquiry-scan burst each time pairing mode is entered (the original theory). Both explanations are consistent with "never seen again after one sighting."

**Practical fix — `tools/bt_wait_and_pair.sh` updated:**
- Uses `scan bredr` instead of `scan on`, so the adapter dedicates its inquiry cycles to classic discovery instead of splitting time with LE advertising scans.
- Matches **either** an exact MAC (if you pass one as an argument) **or** any newly-seen non-`(BLE)` device whose name matches `TD-H3-Plus-<digits>` — so a MAC rotation doesn't strand the script again.
- Recommended sequence changed: start the script *first* (scanning already active), *then* enter the radio's BT Pairing screen once and leave it — don't toggle repeatedly, since each re-entry may mint a new session identity and restart whatever burst window exists.

---

*[<< Index](Findings.md)*
