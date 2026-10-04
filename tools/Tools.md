<!--
  Copyright (c) 2026 Stefan Lenselink <Stefan@lenselink.org>

  SPDX-License-Identifier: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
  SOFTWARE.
-->

# TIDRADIO H3 Plus — Tools Reference

Companion document to [`../findings/Findings.md`](../findings/Findings.md) (the index; chapters live in `findings/`). Every script in `tools/`, what it does,
why it exists, and how to use it.

**Environment:** platform-independent — every tool is pure Python 3 (stdlib only,
`numpy` only for `jl_phasemap.py`) and runs identically on Windows, Linux and macOS;
the exception is the Bluetooth test-rig scripts, which need Linux (BlueZ stack).
All paths below are relative to the repo root.

> [!IMPORTANT]
> The example command lines reference `BIN/`, `FW/`, `Dumps/` and `work/` — **none of
> which are published in this repository.** You must supply the firmware yourself
> (vendor download) and create your own dump. See
> [ARTIFACTS.md](../ARTIFACTS.md) for the acquisition procedures.

> **Key addresses used throughout** (see Findings §2, §9, §12A):
> SoC = JieLi BR23 (AC635N/AC695N), chip key `0xF181`, 1 MiB SPI NOR.
> App region: flash `0x5000`–`0xC8FE0`, loaded at VA `0x01E00000`.
> In a raw `.bin` / full dump, container offset == flash address; in a `.fw` the app sits
> at container offset `0x5200` (0x400 header + 0x100).

---

## Table of Contents

1. [⭐ Main patching tool — `patch_h3plus_firmware_bluetooth.py`](#1--main-patching-tool--patch_h3plus_firmware_bluetoothpy)
2. [Firmware patching](#2-firmware-patching)
   - [`patch_btname.py`](#21-patch_btnamepy)
3. [Crypto / decryption](#3-crypto--decryption)
   - [`jl_sfcenc.py`](#31-jl_sfcencpy-) ⭐
   - [UBOOT-era LFSR solvers: `jl_map.py`, `jl_phasemap.py`, `jl_decrypt.py`, `jl_solve.py`, `jl_recover_key.py`, `jl_bruteforce.py`, `jl_other_ciphers.py`](#32-uboot-era-lfsr-solvers)
4. [Disassembly & static analysis](#4-disassembly--static-analysis)
   - [`pi32dis.py`](#41-pi32dispy-) · [`xref.py`](#42-xrefpy) · [`tools/isa/pi32v2.md`](#43-toolsisapi32v2md) · [`pf78tbl.py`](#44-pf78tblpy) · [`findva.py`](#45-findvapy) · [`freespace.py`](#46-freespacepy)
5. [General binary inspection](#5-general-binary-inspection)
   - [`analyze.py`](#51-analyzepy) · [`strings.py`](#52-stringspy) · [`region.py`](#53-regionpy) · [`hexdump.py`](#54-hexdumppy) · [`headers.py`](#55-headerspy) · [`pedump.py`](#56-pedumppy)
6. [Bluetooth test rig (Linux)](#6-bluetooth-test-rig-linux)
   - [`bt_be_headset.sh`](#61-bt_be_headsetsh-) ⭐ · [`bt_spp_hold.py`](#62-bt_spp_holdpy-) ⭐⭐ · [`bt_spp_ptt.py`](#63-bt_spp_pttpy) · [`bt_ag_capture.py`](#64-bt_ag_capturepy) · [`bt_hf_sim.py`](#65-bt_hf_simpy) · [`bt_audio_check.sh`](#66-bt_audio_checksh) · [`bt_wait_and_pair.sh`](#67-bt_wait_and_pairsh-deprecated) · [`bt_multipoint_probe.py`](#68-bt_multipoint_probepy)
7. [Verification & regression suites](#7-verification--regression-suites)
   - [`verify_cli.py`](#71-verify_clipy) · [`verify_actions.py`](#72-verify_actionspy)
8. [Typical workflows](#8-typical-workflows)
9. [Ghidra pi32v2 decompile ⇒ compile route](#9-ghidra-pi32v2-decompile--compile-route)
   - [`ghidra/MoveBlock.java`](#91-ghidramoveblockjava) · [`ghidra/SeedFunctions.java`](#92-ghidraseedfunctionsjava) · [`ghidra/DumpDecompiled.java`](#93-ghidradumpdecompiledjava) · [`ghidra/rt_is1t2.c` + `ghidra/splice_rt.py`](#94-round-trip-example) · [`disassemble_app.py` + `ghidra/DumpAll.java`](#95-full-app-disassembly--decompilation-tree)

---

## 1. ⭐ Main patching tool — `patch_h3plus_firmware_bluetooth.py`

**The end-all tool of this project.** Patches H3 Plus firmware (v1.0.50 derived) so that:

- **A)** *any* Bluetooth headset name is treated as a duplex speaker-mic (not just the
  hard-coded `TID-PTT` / `TID-MIC` / `TID-MIC-EAR` whitelist), and
- **B)** a physical key on the radio acts as the virtual `+SPP=P` / `+SPP=R` command —
  i.e. **press the radio's own PTT and it transmits the microphone audio received over
  Bluetooth** (BT mic when a headset is linked, the radio's own mic otherwise).

Together these give the project's goal state (Findings §9A.44–§9A.47). Both the main-PTT
patch and the PF1/PF2 variants are **hardware-confirmed**.

### Why it works the way it does

- The tool **auto-detects the container type**: it looks for the scrambled app region at
  container offset `0x5200` (`.fw`) or `0x5000` (`.bin` / full dump), and accepts a
  candidate only when *every* patch site's context signature descrambles correctly with
  chip key `0xF181`. That single check validates offset, chip key **and** firmware version
  at once — it refuses to run against an unrecognised image instead of corrupting it.
- Every patch site carries a table of **known states** (factory bytes plus every value the
  tool itself can write) and a surrounding **context signature**, so an already-patched
  image — even patched with a different `--bluetooth-mode` or different key actions — is
  still recognised, and a foreign firmware version is rejected.
- Patching happens on the **decrypted** app image; the result is re-scrambled with the
  symmetric SFC/ENC transform (from `jl_sfcenc.py`) and verified by round-trip before
  writing.
- **Patch A** flips one immediate at VA `0x01E7EC86` (`41 23` → `41 2X`) so unrecognised
  headset names fall through to a routing mode other than 3.
- **Patch B** (the original "physical button → ring enqueue" at `0x01E60A7E`) is
  **KNOWN-BAD and unsafe** — it was tested on hardware, does nothing, and leaks ring
  slots. It is excluded from the default set and only retained so the tool can recognise
  and report an already-patched image. Do not use it except to inspect (`--only=ptt`).
- **`--PTT=BT-PTT`** (the default) exploits the fact that physical keys and
  `+SPP=P`/`+SPP=R` share one virtual key queue: making the main PTT key push
  `0x2A`/`0x2B` on press/release makes it byte-identical to the SPP commands, and only
  the `0x2A` standby handler switches the mic mux to the BT codec.
- **`--PTT2=` / `--OD-PTT=`** repurpose the two hold-type PF "S Press" menu options
  (radio menus 27/29). Each of the two options can be set to any of five actions —
  `PTT2`, `PTT`, `BT-PTT`, `BT-PTT2`, `OD-PTT` — and the tool **rewrites the executor
  bodies in place**, so **every pair of distinct actions works, in either order**
  (20 combinations, all ten unique unordered ones covered). Only same-action pairs are
  refused — one menu option is one code body and can only run one action; the user picks
  which option to sacrifice. Whatever an option is set to, its menu label follows in all
  nine language lists (Findings §9A.50).
- **`BT-PTT2`** is `BT-PTT` for the **second channel**: like `BT-PTT` it pushes virtual
  keys `0x2A`/`0x2B` (BT headset mic as the TX source), but it additionally forces the
  transmission onto **VFO B** — the `0x2A` standby handler's VFO select
  (`b[gp+0x46]`) is pinned to 1 by a one-shot flag (`gp+0xC7`) that the press body sets
  and the handler consumes. Implemented with a 4-byte trampoline over the native tail of
  that handler (`0x01E794DA`) into a 68-byte code cave at `0x01EA76DE` (verified ALLZERO
  in v1.0.44/v1.0.50). **Hardware-confirmed 2026-09-30.** See Findings ch. 23.

### Usage

```
python tools/patch_h3plus_firmware_bluetooth.py <src> [dst] [options]
```

| Argument / option | Meaning |
|---|---|
| `src` | Input container: `.fw`, `.bin`, or a full flash dump (e.g. `FW/TD-H3-PlusV1.0.50.fw`, `Dumps/dump_internal.bin`). |
| `dst` | Output file, same container type as `src`. Omit for a dry run / `--show`. |
| `--show` | Print the current state of **every** patch site (native / already-target / unknown) and exit. Safe, read-only. |
| `--bluetooth-mode`, `--bt`, `-b` (1–6, **default 4**) | What a connected Bluetooth headset whose name the radio does not recognise does. `1` = like `TID-PTT` (BT mic → TX, radio speaker ← RX); `2` = like `TID-MIC` (full duplex, hardware-confirmed); `3` = factory default (radio mic, = no patch); `4` = like `TID-MIC-EAR` (identical to 2 at the point of use, hardware-confirmed, **default**); `5`/`6` = link-class branch, the audio-routing-GPIO class — 6 tested (no BT mic on PTT), 5 untested. |
| `--PTT=ACTION` | What the radio's **main PTT key** does. **Default `BT-PTT`** (hardware-confirmed). `PTT` = stock (transmit on the current VFO, no patch); `BT-PTT` = transmit the Bluetooth headset's mic while one is linked, the radio's own mic otherwise. `PTT2` / `OD-PTT` / `BT-PTT2` are **not possible** for the main PTT key (the PF-menu executor is not reachable from it) and are refused. |
| `--PTT2=ACTION` | What the PF menu option **"PTT2"** does on every PF key assigned to it. **Default `PTT2`** (stock: TX forced to VFO B). Any of the five actions (`PTT`, `PTT2`, `BT-PTT`, `BT-PTT2`, `OD-PTT`) works as long as `--OD-PTT` differs from it. |
| `--OD-PTT=ACTION` | What the PF menu option **"OD PTT"** does. **Default `OD-PTT`** (stock: one-key duplex). Any of the five actions works as long as `--PTT2` differs from it. |
| `--conn-num=1\|2` | **EXPERIMENTAL / UNTESTED.** Rewrite the stack's `user_ctrl_conn_num` init (`r1 \|= 16` → `\|= 32` at VA `0x01E182DC`, one byte) — the 2-bit "how many BT connections may be active" gate ([§9B.10.2](../findings/22-bluetooth-7-multipoint-architecture.md#9b102-gate-fully-located--the---conn-num-one-byte-patch-2026-10-02-untested)). `1` = stock single-device; `2` = ask the stack for multipoint (headset + TID-PTT button). Default: site untouched (but `--show` reports both states). |
| `--only=NAME` | Apply only this internal patch (repeatable; expert / inspection). Names: `duplex`, `ptt` (known-bad), `pttdown`, `pttup`, `pf1down`, `pf1up`, `pf2down`, `pf2up` (legacy scanner literals), `pfbody7`, `pfbody8`, `pfrelease`, `pftable`, `pfhandler`, `pfcave`, `pflabels`, `connum`. Default set is `duplex` plus the key patches implied by the action options. When `--only` is given, the default `--PTT=BT-PTT` is **not** added unless `--PTT` is also given explicitly. |
| `--sectors=PREFIX` | Also export each changed 4 KiB flash sector as `PREFIX_<addr>.bin`, and print the exact `jl-uboot-tool` `erase` / `write` / `read … verify` commands. **Raw `.bin` / full dump only** — on a `.fw` container offsets ≠ flash addresses, and the tool refuses. |

Option **names** and **action values** are matched case-insensitively (`--ptt=bt-ptt`
works); `BT-PTT` may also be written `BTPTT` / `BT_PTT`, `BT-PTT2` as `BTPTT2` /
`BT_PTT2` / `BT PTT2`, `OD-PTT` as `ODPTT` / `OD_PTT`.

**Running with no options is exactly:**

```
--bluetooth-mode 4 --PTT=BT-PTT --PTT2=PTT2 --OD-PTT=OD-PTT
```

i.e. any Bluetooth headset is treated as a duplex speaker-mic (mode 4), the main PTT key
transmits the headset's Bluetooth mic while one is linked (the radio's own mic otherwise),
and the two PF menu options `PTT2` / `OD PTT` keep their stock behaviour.

### `--PTT2` / `--OD-PTT` combinations (direct-rewrite model)

Each menu option's press body and the release dispatch are rewritten in place to the
requested action, so **all 20 ordered pairs of distinct actions build directly** — the
ten unique combinations in either option order:

| combination | `--PTT2=… --OD-PTT=…` | note |
|---|---|---|
| PTT + PTT2 | `--PTT2=PTT --OD-PTT=PTT2` or reversed | |
| PTT + OD-PTT | `--PTT2=PTT --OD-PTT=OD-PTT` or reversed | |
| PTT + BT-PTT | `--PTT2=PTT --OD-PTT=BT-PTT` or reversed | |
| PTT + BT-PTT2 | `--PTT2=PTT --OD-PTT=BT-PTT2` or reversed | ✅ tested 2026-09-30 (`--PTT2=BT-PTT2 --OD-PTT=PTT`) |
| PTT2 + OD-PTT | `--PTT2=PTT2 --OD-PTT=OD-PTT` | **stock** (default) |
| PTT2 + BT-PTT | `--PTT2=PTT2 --OD-PTT=BT-PTT` or reversed | |
| PTT2 + BT-PTT2 | `--PTT2=PTT2 --OD-PTT=BT-PTT2` or reversed | BT-PTT2 HW-confirmed; this pair untested |
| OD-PTT + BT-PTT | `--PTT2=OD-PTT --OD-PTT=BT-PTT` or reversed | tightest stock combo; OD release also stops TX unconditionally (self-guarded) |
| OD-PTT + BT-PTT2 | `--PTT2=OD-PTT --OD-PTT=BT-PTT2` or reversed | BT-PTT2 HW-confirmed; this pair untested |
| BT-PTT + BT-PTT2 | `--PTT2=BT-PTT --OD-PTT=BT-PTT2` or reversed | both BT mic; A-channel vs B-channel. ✅ labels + function HW-confirmed 2026-10-01 (`--PTT2=BT-PTT2 --OD-PTT=BT-PTT` → "BT2"/"BT PTT") |

**Refused:** same-action pairs (`--PTT2=PTT --OD-PTT=PTT`,
`--PTT2=BT-PTT2 --OD-PTT=BT-PTT2` etc. — one option, one action; the tool prints the full
list of valid pairs) and `--PTT=PTT2` / `--PTT=OD-PTT` / `--PTT=BT-PTT2` (the main PTT key
cannot reach the PF-menu executor).

The obsolete *swap model* (which exchanged the `tbb` dispatch entries instead of rewriting
the bodies) is gone; images carrying it are detected (swapped table at `0x01E75DE2`) and
refused so they cannot be mislabelled — re-flash a stock image first.

The old `--bt-ptt pf1/pf2/odptt` sources are no longer CLI options; the underlying
legacy scanner-literal patches (`pf1down` … `pf2up`) remain available to experts via
`--only` (they take over PTT2 / OD PTT on one physical key before the menu action runs,
which is why they cannot be combined with the `--PTT2=` / `--OD-PTT=` patches — the tool
refuses the mix).

### Examples

```bash
# inspect the current state of every site
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin --show

# default: duplex mode 4 + main PTT = BT mic when linked, else radio mic
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin

# classic combo: PF menu "PTT" (radio mic) + "BT PTT" (BT mic)
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --PTT2=PTT --OD-PTT=BT-PTT

# keep OD PTT, only replace PTT2 with "PTT" — or the other way round
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --PTT2=PTT
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --OD-PTT=BT-PTT

# any pair of distinct actions, in either order — e.g. PTT2 slot runs OD duplex,
# OD slot runs the BT mic (no "swap" concept exists anymore, it just builds)
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --PTT2=OD-PTT --OD-PTT=BT-PTT

# BT mic on the SECOND channel: PTT2 button transmits the headset mic over VFO B
# (hardware-confirmed 2026-09-30)
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --PTT2=BT-PTT2

# both BT-mic actions at once: OD slot = BT mic on VFO A, PTT2 slot = BT mic on VFO B
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --PTT2=BT-PTT2 --OD-PTT=BT-PTT

# main PTT stays stock (BT duplex still on)
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --PTT=PTT

# another routing mode (any of --bluetooth-mode / --bt / -b)
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --bt 2

# EXPERIMENTAL (UNTESTED): ask the BT stack for two concurrent connections —
# the user_ctrl_conn_num gate (§9B.10.2); combine with the normal actions
python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin \
    --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT --conn-num=2

# minimal in-place flashing: export just the changed 4 KiB sectors + flash commands
python tools/patch_h3plus_firmware_bluetooth.py BIN/TD-H3-PlusV1.0.50.bin --sectors=work/sect
```

The default build (duplex + main PTT) changes **3 bytes in 2 sectors** (`0x057000`,
`0x083000`). Each key action adds its own sectors. Per combo (on `Dumps/dump_internal.bin`,
with the default `--PTT=BT-PTT` included): `--PTT2=PTT --OD-PTT=BT-PTT` 72 B,
`--PTT2=PTT` alone 23 B, `--OD-PTT=BT-PTT` alone 52 B, the tightest
`--PTT2=OD-PTT --OD-PTT=BT-PTT` 86 B. With BT-PTT2 (adds the trampoline + code cave):
`--PTT2=BT-PTT2` alone 117 B, `--OD-PTT=BT-PTT2` alone 123 B,
`--PTT2=PTT --OD-PTT=BT-PTT2` 146 B, `--PTT2=BT-PTT --OD-PTT=BT-PTT2` 156 B.
`--sectors` lists exactly the sectors that differ.

⚠️ Always keep the original `.fw`. Flashing is at your own risk; keep `Dumps/dump_internal.bin`
as brick-insurance.

---

## 2. Firmware patching

### 2.1 `patch_btname.py`

**What:** Patches the Bluetooth accessory **name whitelist** in place. The radio only
enables the BT mic (HFP SCO uplink) for accessories whose name prefix-matches one of three
hard-coded slots:

| Slot | Flash address | Size | Factory value |
|---|---|---|---|
| `ptt` | `0x0A0968` | 8 B | `TID-PTT` |
| `mic` | `0x0A0970` | 8 B | `TID-MIC` |
| `micear` | `0x0A0F5C` | 12 B | `TID-MIC-EAR` |

The match is a **prefix** match (proven: the real PTT button advertises `TID-PTT0cd28a`
yet matches the 7-char entry), so writing the first 7 characters of any headset's name
into a slot makes the radio treat that headset as a speaker-mic — e.g.
`"Jabra Evolve 65"` → `"Jabra E"`.

**Why:** this was the *first-generation* fix (Findings §9A.9), before the routing-mode
patch in `patch_h3plus_firmware_bluetooth.py` made whitelisting unnecessary. Still useful when you want
one specific headset whitelisted while leaving the classifier untouched; patching `mic`
leaves `ptt` intact so a genuine TIDRADIO PTT button keeps working.

Because the SFC/ENC scrambler is position-deterministic and symmetric, the tool decrypts
the app region, edits the string slot, re-encrypts, and verifies the round-trip — only the
string's own bytes change in the ciphertext.

**Usage:**

```
python tools/patch_btname.py <in> [out] [--show | --mic=NAME | --ptt=NAME | --micear=NAME]
```

| Argument / option | Meaning |
|---|---|
| `in` | Input container (`.bin` or full dump; app assumed at `0x5000`). |
| `out` | Output file. Omit (or pass `--show`) for a read-only whitelist report. |
| `--show` | Print the current contents of all three slots and exit. |
| `--mic=NAME` | Write `NAME` into the `TID-MIC` slot (max 7 chars). |
| `--ptt=NAME` | Write `NAME` into the `TID-PTT` slot (max 7 chars). |
| `--micear=NAME` | Write `NAME` into the `TID-MIC-EAR` slot (max 11 chars). |

Names longer than the slot are rejected with a helpful message (use the first N
characters — prefix matching makes that sufficient).

**Examples:**

```bash
python tools/patch_btname.py Dumps/dump_internal.bin --show
python tools/patch_btname.py Dumps/dump_internal.bin out.bin --mic="Jabra E"
python tools/patch_btname.py Dumps/dump_internal.bin out.bin --ptt="Jabra E"
```

---

## 3. Crypto / decryption

### 3.1 `jl_sfcenc.py` ⭐

**What:** The SFC/ENC hardware-scrambler decryptor that **solved the app region**
(Findings §9). On BR23, the flash controller descrambles data per 32-byte cache line,
reseeding the JieLi ENC LFSR (poly `0x1021`) each line with `key = chipkey ^ (addr >> 2)`.
With `chipkey = 0xF181` (read from hardware) the whole app decrypts.

**Why:** this is the foundation every other firmware tool imports
(`patch_h3plus_firmware_bluetooth.py`, `patch_btname.py` both `from jl_sfcenc import sfc_enc_decrypt`).
The transform is **its own inverse**, so the same function re-encrypts a patched image.

**Usage:**

```
python tools/jl_sfcenc.py <file> [outfile] [--key=0xF181] [--start=0x5000] [--end=0xC8FE0] [--base=0]
```

| Argument / option | Meaning |
|---|---|
| `file` | Input container (a `.bin`, dump, or any file containing the scrambled region). |
| `outfile` | Output. Default: `<file>.sfcdec`. |
| `--key=HEX` | Chip key (default `0xF181`). |
| `--start=HEX` | Container offset where the scrambled region begins (default `0x5000`). |
| `--end=HEX` | End of region (default: EOF). For the app region use `0xC8FE0`. |
| `--base=HEX` | Mapped address of the first byte (default `0` — the app is mapped so it begins at address 0). |

Prints input/output entropy and zero/`0xFF` counts — a good phase/key is obvious from the
zero count spiking. Also exposes `find_base()` (importable) which brute-forces the mapped
base address by maximising the zero count.

**Example — produce the plaintext app used by the disassembler:**

```bash
python tools/jl_sfcenc.py BIN/TD-H3-PlusV1.0.50.bin work/app_dec.bin --key=0xF181 --start=0x5000 --end=0xC8FE0
```

### 3.2 UBOOT-era LFSR solvers

These are the tools that broke the **outer continuous ENC stream** (UBOOT region) before
the SFC/ENC discovery. They model the plain JieLi ENC cipher:
`out[i] = in[i] ^ lfsr_low_byte`, 16-bit LFSR poly `0x1021`, cycle length 32767. Wherever
plaintext is `0x00`, the ciphertext *is* the raw keystream — that oracle drives all of them.
Kept for historical completeness and for analysing other JieLi images.

#### `jl_map.py` — keystream-window mapper (the one that broke UBOOT)

Indexes every W-byte window of the LFSR cycle, scans the file for matches, groups
contiguous runs, and tests reset/block sizes — revealing where the cipher restarts.

```
python tools/jl_map.py <file> [window]     # window default 8
```

#### `jl_phasemap.py` — per-block best-phase solver (needs `numpy`)

For each block of the file, votes for the LFSR phase that maximises decrypted `0x00`
bytes (histogram trick — fast enough for all 65k phases × every block).

```
python tools/jl_phasemap.py <file> <blocksize>     # blocksize default 0x1000, hex ok
```

#### `jl_decrypt.py` — decrypt with a known phase

XORs the whole file with the LFSR keystream started at a given phase, writes
`<name>.p<phase>.dec`, then prints entropy, per-4K entropy histogram, and hexdumps of
interesting regions so you can eyeball whether the phase is right.

```
python tools/jl_decrypt.py <file> <phase>
```

(Outputs already in `work/decrypted/` were made this way: phase 32591 for `.bin`, 31567
for `.fw`.)

#### `jl_solve.py` — phase solver from repeated zero-runs

Builds the LFSR cycle, finds repeated non-`0xFF` runs in the file, and votes on the phase.

```
python tools/jl_solve.py <file>
```

#### `jl_recover_key.py` — per-phase mode statistics

Assumes a fixed-size repeating XOR table and ranks the most-frequent byte per phase.
Historically important because it **disproved the 32-byte-table hypothesis** for the app
region (which is what eventually pointed at the per-cache-line SFC scheme).

```
python tools/jl_recover_key.py <file> [period]     # period default 32
```

#### `jl_bruteforce.py` — 65536-key brute force *(deprecated)*

Tries all 16-bit keys against sampled chunks with a heuristic score (zeros, ASCII runs,
JieLi marker strings). **Too slow — superseded by `jl_phasemap.py`.**

```
python tools/jl_bruteforce.py <file>
```

#### `jl_other_ciphers.py` — negative-result checker

Tests the other known JieLi ciphers (CrcDecode/"MengLi" and RxGp) plus XOR
self-correlation against the app region. Both were **ruled out** — kept so the dead ends
aren't re-explored.

```
python tools/jl_other_ciphers.py <file> [app_start]     # app_start default 0x5000
```

---

## 4. Disassembly & static analysis

### 4.1 `pi32dis.py` ⭐

**What:** A working **pi32v2 disassembler** for JieLi BR-series code (Findings §9A.13).
The ISA has no official documentation and Ghidra/IDA have no module for it; this tool
parses kagaimiq's reverse-engineered spec (`tools/isa/pi32v2.md`) **at runtime** and builds
its decode table from the bit-pattern tables in that file.

**Why:** it is the only way to read the decrypted app. Every patch site in
`patch_h3plus_firmware_bluetooth.py` was located and verified with it.

**Usage:**

```
python tools/pi32dis.py <file> (--va ADDR | --flash ADDR | --off OFF) [options]
```

| Argument / option | Meaning |
|---|---|
| `file` | Decrypted app image (e.g. `work/app_dec.bin`), offset 0 = VA `0x01E00000`. |
| `--va=ADDR` | Start virtual address (accepts `0x…`). |
| `--flash=ADDR` | Start **flash** address (converted: file offset = flash − `0x5000`). |
| `--off=ADDR` | Start raw file offset. |
| `--count=N` | Number of instructions to disassemble. |
| `--end=ADDR` | Stop at this VA (alternative to `--count`). |
| `--func` | Disassemble one function — stop at the first return. |
| `--base=ADDR` | Load base VA (default `0x01E00000`). |

**Examples:**

```bash
python tools/pi32dis.py work/app_dec.bin --flash 0x083C40 --count 26
python tools/pi32dis.py work/app_dec.bin --va 0x01E7EC28 --func
```

### 4.2 `xref.py`

**What:** Cross-reference finder — locates every 32-bit `call` / `goto` site in a
decrypted app image that targets a given VA. Scans the encodings documented in
`tools/isa/pi32v2.md` lines 578/579 with PC-relative signed displacement
(`target = addr + 4 + sign_extend_23(A:B << 1)`).

**Why:** how "who reads this byte / who calls this function" questions were answered
during the RE (e.g. finding the six readers of the routing-mode byte, and proving the
pressed-key set at `0xFF59` has no reader).

**Usage:**

```
python tools/xref.py <file> <targetVA> [--base=ADDR] [--goto] [--both]
```

| Argument / option | Meaning |
|---|---|
| `file` | Decrypted app image. |
| `targetVA` | Target virtual address, e.g. `0x01E50398`. |
| `--base=ADDR` | Load base (default `0x01E00000`). |
| `--goto` | Scan `goto` sites instead of `call`. |
| `--both` | Scan both `call` and `goto`. |

**Example:**

```bash
python tools/xref.py work/app_dec.bin 0x01E52362
```

### 4.3 `tools/isa/pi32v2.md`

Not a script — the reverse-engineered **pi32v2 ISA specification** (from
[kagaimiq/jielie](https://github.com/kagaimiq/jielie)) that `pi32dis.py` parses at
runtime. Keep it next to `pi32dis.py` in `tools/isa/`; if you update it, the disassembler
picks up new opcodes automatically.

### 4.4 `pf78tbl.py`

**What:** Decodes the PF-menu value 7/8 dispatch machinery of the v1.0.50 app — the
`tbb r0` jump table at `0x01E75DDC` (8 entries, `target = table + 2*entry`, so
menu value 7 → entry index 6, value 8 → index 7) and the two release-executor compare
immediates at `0x01E75E7A`/`0x01E75E7E` (`imm = word1 >> 9`). Prints each menu value
1–8 with the body VA it dispatches to, and the two release imms.

**Why:** this is the read-only check behind the `--PTT2`/`--OD-PTT` feature
(Findings §9A.47/§9A.48): stock output must show value 7 → `0x01E75E38` (PTT2-or-PTT
body), value 8 → `0x01E75E42` (OD-PTT-or-BT-PTT body) and release imms `8, 7`. After a
`--PTT2=BT-PTT`-style patch the bodies swap accordingly — run it against a patched
decrypted image to confirm the dispatch changed without disassembling anything.

**Usage:**

```
python tools/pf78tbl.py [decrypted-app-image]     # default work/app_dec.bin
```

The input is a *decrypted app* image (offset 0 = VA `0x01E00000`), e.g. produced by
`tools/jl_sfcenc.py`. Exit 1 if the table doesn't look like a dispatch table.

### 4.5 `findva.py`

**What:** Raw byte-pattern reference finder — the complement of `xref.py` (§4.2).
Searches a decrypted image for the 32-bit little-endian encoding of each given VA
(pointer tables), optionally also the 24-bit absolute `target/2` encoding used by some
jump tables (`--half`), or any literal hex byte string (`--raw`). Every hit is printed
with both the file offset and the VA of the referring byte, ready to feed to
`pi32dis.py --off`.

**Why:** `xref.py` only decodes real call/goto displacements; the interesting
references in this firmware are *data pointers* (the nine PF S Press language lists
pointing at the "PTT2"/"OD PTT" strings) and table entries, which only a byte search
finds. This is how the 9 pointer sites of `PF_LIST_PTT2_PTRS` were enumerated.

**Usage:**

```
python tools/findva.py <file> <VA> [VA...] [--half] [--raw HEXBYTES]
```

```bash
python tools/findva.py work/app_dec.bin 0x01E8E30E        # who points at "PTT2"?
python tools/findva.py work/app_dec.bin --raw D09DD095D0A200   # RU "НЕТ" bytes
```

Exit 1 when nothing was found. (Note: the `tbb` table at `0x01E75DDC` encodes
*(target − table)/2*, a relative form — use `pf78tbl.py` for that one.)

---

### 4.6 `freespace.py`

**What:** Free-space verifier for the decrypted app. Lists every run of ≥ `--min`
zero bytes, marks each run `code`/`data` from the `full.lst` disassembly (`.word`
lines ⇒ data), and — given `--other VER=file` images of other firmware versions —
reports per run how many of them are ALSO all-zero there.

**Why:** candidate code padding must be zero in *every* version to be safely
overwritable. The ALLZERO column is the verdict; the `code=` flag is misleading
because `0x0000` decodes as a valid `nop`. Even ALLZERO runs need a pointer scan
(every 2-byte-aligned LE word in the block range) before use — see
[§9B.7](../findings/22-bluetooth-7-multipoint-architecture.md#9b7-code-space-none-inside-the-app--but-208-kib-of-erased-flash-beyond-it):
the last surviving candidate died because a draw call pointed into it.

**Usage:**

```
python tools/freespace.py <app_dec.bin> [--min 64] [--lst full.lst] [--other VER=file ...]
```

```bash
python tools/freespace.py work/app_dec.bin --min 64 --lst work/full.lst \
  --other 45=work/decrypted\v45_app_dec.bin --other 44=work/decrypted\v44_app_dec.bin
```

---

## 5. General binary inspection

Small dependency-free helpers used throughout the effort. All take file paths and print to
stdout.

### 5.1 `analyze.py`

Structural analysis of firmware images: entropy, index of coincidence, byte histogram,
per-4K-block entropy, repeating-XOR period scan, duplicate 16-byte block detection.
The first tool run on every new artifact; high entropy ⇒ encrypted/compressed, the 4K
histogram reveals region structure.

```
python tools/analyze.py [files...]     # defaults to the BIN/ + FW/ inventories
```

### 5.2 `strings.py`

ASCII **and UTF-16LE** string extraction with a built-in keyword filter (firmware,
upgrade, AES, CRC, BK4819, TIDRADIO, USB, bootloader, …). This is how the `JL_FW` magic,
`JL_A2DP_SRC`/`JL_HFP_AG` roles and the `+SPP=` protocol hints were first spotted.

```
python tools/strings.py <file> [filter|all] [minlen]    # default mode filter, minlen 6
```

### 5.3 `region.py`

Dump all printable strings within a specific file offset range — the quick way to read a
known region (e.g. the VM area at `0xC9000`) without filtering the whole file.

```
python tools/region.py <file> <start> <end> [minlen]    # hex ok, minlen default 4
```

### 5.4 `hexdump.py`

Classic hex+ASCII hexdump of an arbitrary byte range.

```
python tools/hexdump.py <file> <start> <end>            # hex ok
```

### 5.5 `headers.py`

Print head/tail (64 bytes each, hex+ASCII) of **every** file in `BIN/` and `FW/`. This is
what revealed the byte-identical 64-byte headers, the `JL_FW` trailer, and the per-version
checksum bytes. No arguments — it scans the repo layout itself.

```
python tools/headers.py
```

### 5.6 `pedump.py`

Minimal PE header / section / data-directory dumper with per-section entropy — no external
deps. Used to triage the official Windows updaters (`updata.exe`, `UpdateApp.exe`): detect
UPX packing, find the CLR directory (the CPS is .NET), locate resources.

```
python tools/pedump.py <exe>
```

---

## 6. Bluetooth test rig (Linux)

Scripts that ran on a Linux box (BlueZ) to talk to the radio over Bluetooth during the
live experiments of Findings §9A. They require root (except `bt_audio_check.sh`), Python 3
with `AF_BLUETOOTH` sockets, and `bluetoothctl`. **Do not stop PipeWire** when using the
SPP/HFP tools — the radio needs *some* profile to consider itself connected (§9A.21).

Connection model that finally worked (§9A.17): make the PC a *discoverable headset* and
let the **radio** initiate. The radio's SPP endpoint is RFCOMM **channel 2**; HFP is
channel 6.

### 6.1 `bt_be_headset.sh` ⭐

**What:** Makes the Linux box present itself as a discoverable Bluetooth **headset** and
auto-accepts inbound pairing/connections. Sets Class of Device `0x240404` (wearable
headset), turns BLE advertising **off** (essential — LE identity hides the CoD), sets the
system alias (advertised name), and runs an auto-confirming agent.

**Why:** outbound scanning for the radio proved unreliable (its BR/EDR endpoint appears in
a tiny burst and its BLE identity rotates — §9A.14). Letting the radio connect to *us* is
the working direction. **The advertised name selects the audio routing mode** (§9A.22):
`TID-MIC-EAR`/`TID-MIC` = full duplex, `TID-PTT…` = TX only, unrecognised = the radio's
own mic feeds TX. The peer caches the name at pairing time — re-pair on both sides after
changing it.

**Usage:**

```bash
sudo ./tools/bt_be_headset.sh "<advertised name>" [class-of-device]
```

| Argument | Meaning |
|---|---|
| `"<name>"` | Advertised name (system alias), e.g. `"TID-MIC-EAR"`. |
| `[CoD]` | Optional Class-of-Device override (default `0x240404`). Use `0x5a020c` (phone) when impersonating an Audio Gateway so an HF accessory (the TIDRADIO PTT button) will connect to us — pair with `bt_ag_capture.py`. |

### 6.2 `bt_spp_hold.py` ⭐⭐

**What:** Holds the SPP link (RFCOMM ch. 2) open to the radio for as long as you want —
which keeps the radio in "connected" state even with no audio profile up — and provides
interactive PTT. **Use this instead of `bt_spp_ptt.py` for anything beyond a single shot**
(a one-shot tool makes the radio connect and immediately disconnect).

**Usage:**

```bash
sudo python3 tools/bt_spp_hold.py <mac> [options]
```

| Argument / option | Meaning |
|---|---|
| `mac` | Radio's Bluetooth MAC. |
| `--channel=N` | SPP RFCOMM channel (default 2). |
| `--hold=SEC` | Seconds to hold PTT for a one-shot press (default 3). |
| `--gap=SEC` | Idle seconds between presses in `--cycle` mode (default 5). |
| `--cycle` | Automatically cycle press/release instead of prompting. |
| `--idle` | Just hold the link open and send **nothing** — keeps the radio connected unattended without ever keying TX; needs no terminal. |
| `--no-double-release` | Send release once instead of twice (the real button sends `R` twice). |

Interactive keys at the prompt: `Enter` = press/hold/release, `p` = press and hold,
`r` = release, `s` = link status, `q` = release then quit cleanly.

Note the protocol asymmetry (§9A.24/25): we send `+SPP=P`/`+SPP=R`; the radio sends back
`AT+MPTT=1/0` as an **RX squelch indicator** — it is not a command to send.

### 6.3 `bt_spp_ptt.py`

**What:** One-shot sender of the real PTT protocol captured from a genuine TID-PTT
accessory (§9A.20): NUL-terminated `+SPP=P` / `+SPP=R` over **SPP** (not `AT+MPTT=1` over
HFP — that red herring cost weeks). Fire-and-forget, no handshake.

**Usage:**

```bash
sudo python3 tools/bt_spp_ptt.py <mac> [options]
```

| Argument / option | Meaning |
|---|---|
| `mac` | Radio's Bluetooth MAC. |
| `--channel=N` | RFCOMM channel of the SPP endpoint (default 2). |
| `--hold=SEC` | Seconds to hold PTT down (default 5). |
| `--gap=SEC` | Seconds idle between presses (default 5). |
| `--once` | Single press/release, then exit. |
| `--double-release` | Send release twice, mimicking the real button exactly. |
| `--listen` | Also print anything the radio sends back. |

By design it disconnects on exit — prefer `bt_spp_hold.py` (§6.2) for sustained testing.

### 6.4 `bt_ag_capture.py`

**What:** Inverts the problem: instead of guessing what a genuine TIDRADIO PTT accessory
sends, this PC pretends to **be the radio** (Audio Gateway) and logs everything the real
button says. Registers HFP-AG/HSP-AG SDP records, answers the SLC handshake so the
accessory proceeds to its real behaviour, snapshots the peer identity (name, class, UUIDs,
PnP vendor/product), and logs every byte both directions with timestamps. Unknown commands
are logged loudly — those lines were the entire point (they yielded `+SPP=P`/`+SPP=R`).

**Prerequisite (only for `--listen`):** bluetoothd compat mode
(`ExecStart=.../bluetoothd --compat`, restart, `chmod 666 /var/run/sdp`).

**Usage:**

```bash
sudo python3 tools/bt_ag_capture.py (--scan | --connect <MAC> | --listen) [options]
```

| Argument / option | Meaning |
|---|---|
| `--scan` | Scan for classic BT devices and exit — find the PTT button's MAC while it is in pairing mode. |
| `--connect=MAC` | Dial **out** to the accessory and act as its AG. **This is the correct direction for the PTT button** (it advertises and waits; the radio connects to it). |
| `--listen` | Wait for an inbound connection instead (correct direction for the radio itself). |
| `--channel=N` | RFCOMM channel. With `--connect`, probed automatically if omitted; with `--listen`, defaults to 6. |
| `--log=PATH` | Log file path (default `ag_capture.log`). |
| `--unknown-reply=ok|error` | How to answer unrecognised commands. `ok` (default) keeps the accessory talking so it reveals more; `error` mimics the real radio's rejection to observe the accessory's reaction. |
| `--no-sdp` | Skip `sdptool` registration (`--listen` mode only). |

### 6.5 `bt_hf_sim.py`

**What:** Minimal Hands-Free (HF) role simulator: raw RFCOMM AT channel + raw SCO PCM
(8 kHz/16-bit mono) straight against kernel BT sockets — deliberately **not** PipeWire/
oFono/BlueALSA, none of which let you inject a non-standard vendor AT command. Cycles
`AT+MPTT=1` + looping mp3 into SCO / `AT+MPTT=0` + silence, and plays the radio's returned
PCM live via `aplay`. Exploratory/best-effort — run `sudo btmon` alongside when something
doesn't connect.

**Why:** this is the rig that proved `AT+MPTT=1` is parsed and actively rejected by the
radio (§9A.15/16), and that mapped the radio's RFCOMM channels when SDP stays silent.

Prerequisites (Ubuntu): `bluez bluez-utils ffmpeg alsa-utils`; pair/trust the radio first;
stop PipeWire user services to avoid races (unlike the SPP tools, this one grabs HFP
itself).

**Usage:**

```bash
sudo python3 tools/bt_hf_sim.py <mac> <mp3> [options]
```

| Argument / option | Meaning |
|---|---|
| `mac` | Radio's Bluetooth MAC. |
| `mp3` | Mp3 to loop as the simulated mic input (ignored with `--at-only`). |
| `--channel=N` | HFP-AG RFCOMM channel (auto-detected via `sdptool` if omitted). |
| `--on=SEC` | Seconds of `AT+MPTT=1` + audio per cycle (default 10). |
| `--off=SEC` | Seconds of `AT+MPTT=0` + silence per cycle (default 10). |
| `--no-mptt` | Don't send the vendor commands — use when validating the rig against a normal phone (which answers ERROR); the audio cycle still runs. |
| `--at-only` | Only open the RFCOMM AT channel and cycle `AT+MPTT`; don't touch SCO/audio. Lets PipeWire keep the HFP audio path while the vendor command is injected alongside. |
| `--no-slc` | Skip the SLC handshake — for use with `--at-only` when PipeWire already established the SLC. |
| `--probe-channels` | Brute-force probe which RFCOMM channels accept a connection, then exit. Use when `sdptool browse` returns nothing (this radio ignores SDP browse). |

### 6.6 `bt_audio_check.sh`

**What:** Diagnoses why radio audio is (or isn't) reaching the PC's speakers. Checks the
whole chain: PipeWire/WirePlumber running, HF/sink role endpoints registered with BlueZ,
profile connections, etc. Explains the two audio paths (A2DP sink = one-way high quality;
HFP HF = two-way SCO, needed for PTT mic audio) and the SPP red herring — if the radio
only says "Connected" once SPP is up, that means PipeWire did **not** take the audio
connection.

**Run as your user, NOT root** — PipeWire is a per-user service and invisible from root.

**Usage:**

```bash
./tools/bt_audio_check.sh [radio-mac]
```

### 6.7 `bt_wait_and_pair.sh` *(deprecated)*

**What:** Watched a live `bluetoothctl` session and fired `pair`/`trust`/`connect` within
milliseconds of the radio's classic BR/EDR endpoint appearing in scan output (it only
broadcasts in a short burst when BT Pairing mode is entered). Matches an exact MAC or the
name pattern `TD-H3-Plus-<digits>` (the BLE identity rotates between sessions).

**Superseded by `bt_be_headset.sh`** — outbound discovery of the radio proved unreliable;
letting the radio initiate is the working model. Kept for reference.

**Usage:**

```bash
./tools/bt_wait_and_pair.sh [MAC]     # no MAC = name-pattern matching only
# Start BEFORE entering BT pairing mode on the radio; enter it ONCE and leave it.
```

---

### 6.8 `bt_multipoint_probe.py`

**What:** Phase-0 experiment for the dual-device goal (headset + TID-PTT button at the
same time). Connects SPP (ch 2, button role) and holds it, then attempts HFP (ch 6)
while held; then the reverse order. Optional `--ptt-hold` presses PTT (sends
`+SPP=P`/`+SPP=R`) during both orders. Prints one verdict:
`MULTIPOINT OK` / `KICK-ON-CONNECT` / `SECOND LINK REFUSED` (with the EBUSY caveat).

**Why:** decides whether the JieLi stack accepts two concurrent ACL links *before* any
flashing. See [§9B.6](../findings/22-bluetooth-7-multipoint-architecture.md#9b6-phase-0-live-probe-decides-everything-no-flashing).

**Usage:**

```
sudo python3 tools/bt_multipoint_probe.py <radio-mac> [--hold 2] [--ptt-hold 3] [--no-hfp]
```

Run on the Linux box with the radio paired (and preferably the only paired host).

**Result 2026-10-01:** `MULTIPOINT OK` at profile level (SPP+HFP concurrent, PTT keys
with both up, both orders) — but note both legs come from one host = one ACL link.
The follow-up two-ACL tests showed **kick-on-connect** (real headset joining while
`bt_spp_hold.py` holds SPP evicts the host) and, in reverse (headset first, then
`bt_spp_hold.py`), `[Errno 112] Host is down` — the radio is not connectable at all
while a device is connected. Policy: one active device; radio-initiated joins evict;
incoming connections are refused at the page level. The ceiling is the app's
single-active-device policy, not the stack.
Details: [§9B.6.1](../findings/22-bluetooth-7-multipoint-architecture.md).

---

## 7. Verification & regression suites

Both suites run **from the repo root** and exit non-zero on any failure. Run them after
any change to `patch_h3plus_firmware_bluetooth.py` (or its patch-site tables) before flashing anything.

### 7.1 `verify_cli.py`

**What:** The CLI matrix — self-contained end-to-end cases driving the real
`python tools/patch_h3plus_firmware_bluetooth.py ...` command line against `Dumps/dump_internal.bin`
and writing `work/cli/<name>.bin`: all ten unique `--PTT2`/`--OD-PTT` combinations
in both option orders (the direct-rewrite model builds every pair of distinct actions,
including BT-PTT2), case-insensitivity (`--ptt2=ptt`), value aliases (`OD_PTT`, `BTPTT`,
`BT PTT`, `BTPTT2`, `BT PTT2`), `--bluetooth-mode` aliases (`--bt`, `-b`), the main-PTT
restrictions (including `--PTT=BT-PTT2`), and every rejection path (same-action pairs,
bad action values) with expected exit codes. Also checks that equivalent spellings produce
**byte-identical** outputs (hash comparison) and that `--show` on a patched image reports
no `UNKNOWN`. Generated images are removed when all cases pass. Pure stdlib — runs the
same on Windows, Linux and macOS (port of the former `verify_cli.ps1`).

**Why:** catches CLI regressions (validation gaps, alias breakage, non-determinism) that
the byte-level suite below can't see.

**Usage:**

```bash
python tools/verify_cli.py     # prints one line per case, "FAILURES: N" last
```

### 7.2 `verify_actions.py`

**What:** The byte-level suite — **self-contained**: it builds all 20 ordered
`(--PTT2, --OD-PTT)` pairs itself (into `work/verify/`, removed on success unless
`--keep`) and checks each against the tables imported from `patch_h3plus_firmware_bluetooth.py`
itself: the duplex site, both main-PTT scanner sites, the rewritten press bodies
(`_pf_body7` / `_pf_body8`), the 32-byte release dispatch (`_pf_release`), the native
`tbb` table, the BT-PTT2 trampoline (`pfhandler` @`0x01E794DA`) and code cave (`pfcave`
@`0x01EA76DE`, including that the cave handler reproduces the stock tail bytes and calls
the TX-start routine), the string rewrites ("OD PTT"/"PTT" tails, RU "Нет"/"НЕТ", "BT PTT"
/ "BT PTT2"/"BT2" placement), all nine PF S Press language lists rendering the expected
labels, that the **changed-byte set equals exactly the expected patch set** (no collateral
edits), idempotency (rebuilding a patched image writes nothing), and `--show` cleanliness.
Plus the refusal cases: same-action pairs, `--PTT=PTT2`/`OD-PTT`/`BT-PTT2`, and images
carrying the obsolete swap model (swapped `tbb` table). Currently **784 checks, 0
failures**.

**Why:** proves the patches are *functionally* correct at the instruction/label level,
not just that the tool ran. Complements `verify_cli.py`: that one tests the CLI, this
one tests the emitted bytes.

**Usage:**

```bash
python tools/verify_actions.py          # builds + verifies, cleans up on success
python tools/verify_actions.py --keep   # leave work/verify/ images for inspection
```

---

## 8. Typical workflows

### Patch firmware for BT-mic PTT and flash it minimally

```bash
python tools/patch_h3plus_firmware_bluetooth.py BIN/TD-H3-PlusV1.0.50.bin --show          # verify version
python tools/patch_h3plus_firmware_bluetooth.py BIN/TD-H3-PlusV1.0.50.bin work/patched.bin --sectors=work/sect
# → flash only the exported sectors with jl-uboot-tool (commands are printed)
```

### Decrypt any archived firmware version for analysis

```bash
python tools/jl_sfcenc.py BIN/TID-H3-PlusV1.0.45.bin work/app_1045.bin --key=0xF181 --start=0x5000 --end=0xC8FE0
python tools/strings.py work/app_1045.bin all 8 > work/str_1045.txt
```

### Read a function around a flash address

```bash
python tools/pi32dis.py work/app_dec.bin --flash 0x083C40 --count 40
python tools/xref.py work/app_dec.bin 0x01E72C3C          # who calls the audio-path setter?
```

### Live BT test session (Linux)

```bash
sudo ./tools/bt_be_headset.sh "TID-MIC-EAR"        # PC becomes the headset; radio initiates
./tools/bt_audio_check.sh <radio-mac>              # (separate shell, non-root) audio sanity
sudo python3 tools/bt_spp_hold.py <radio-mac>      # hold SPP, interactive PTT
```

---

## 9. Ghidra pi32v2 decompile ⇒ compile route

Ghidra ≥ 11 with the [ghidra-jieli](https://github.com/quarkslab/ghidra-jieli)
processor module (SLEIGH, language `pi32v2:LE:32:default`) decompiles the
decrypted app; the JieLi LLVM toolchain recompiles the result. Verified
end-to-end 2026-10-03 — findings [ch. 25](../findings/25-ghidra-decompile-compile-route.md).

**Install (one-time):** copy the module into the Ghidra tree — Ghidra loads it
as a processor module with no build step (the shipped `pi32v2.sla` works
unchanged on Ghidra 12.1.4 / Java 25):

```bash
cp -r ../ghidra-jieli ../ghidra_12.1.4_PUBLIC/Ghidra/Processors/JieLi
```

### 9.1 `ghidra/MoveBlock.java`

Headless `BinaryLoader` ignores `-loader-"Base Address"` (Ghidra 12 prints
*“Skipping unsupported …”* and loads at 0). Import raw, then this pre-script
moves the block to **VA 0x01E00000** (= app offset 0).

### 9.2 `ghidra/SeedFunctions.java`

A raw import has no entry points, so auto-analysis finds nothing. This
pre-script does the `findva.py` trick inside Ghidra: every 2-byte-aligned LE
word pointing back into `[0x01E00000, 0x01EC4000)` gets a function (≈6.5 k),
plus the well-known BT seeds. Standard analyzers propagate afterwards; the
whole 784 KiB app imports + analyzes in ~2 minutes.

### 9.3 `ghidra/DumpDecompiled.java`

Post-script: `DumpDecompiled.java <outDir> [addr …]` writes one `.c` per
function (defaults to the BT-research set).

Full import recipe (from the repo root):

```bash
../ghidra_12.1.4_PUBLIC/support/analyzeHeadless work/ghidra_proj h3plus \
    -import work/app_dec.bin -processor pi32v2:LE:32:default -cspec default \
    -scriptPath tools/ghidra -preScript MoveBlock.java -preScript SeedFunctions.java \
    -postScript DumpDecompiled.java work/ghidra_out
```

### 9.4 Round-trip example

`ghidra/rt_is1t2.c` re-implements the two decompiled one-liners
(`is_1t2_connection` @`0x01E1787C`, `set_conn_num` @`0x01E182B0`). Build and
splice into a **decrypted-app-free** full image:

```bash
TC=../jieli-linux-toolchains-20250324.1/pi32v2/bin
$TC/clang -target pi32v2 -mcpu=r3 -Oz -c tools/ghidra/rt_is1t2.c -o work/roundtrip/rt_is1t2.o
$TC/objcopy -O binary -j .text work/roundtrip/rt_is1t2.o work/roundtrip/rt_is1t2.bin
python3 tools/ghidra/splice_rt.py <in.bin> <out.bin> work/roundtrip/rt_is1t2.bin
```

`splice_rt.py` context-checks both sites (stock bytes), splices, re-encrypts
(via `jl_sfcenc`), and verifies the crypto round-trip. The spliced image
re-decompiles to **byte-identical C** (fixed point, §25.5). Regenerate the
blob from the `.c` rather than committing binaries.

### 9.5 Full-app disassembly & decompilation tree — `disassemble_app.py` + `ghidra/DumpAll.java`

One command turns the decrypted app into a browsable `disassembled/` tree —
decompiled C for **every** function (Ghidra `ParallelDecompiler`, all cores),
per-function assembly, a linear listing, and function/symbol/string indexes:

```bash
python3 tools/disassemble_app.py                 # input defaults to work/app_dec.bin
python3 tools/disassemble_app.py BIN/TD-H3-PlusV1.0.50.bin   # full image: auto-decrypted
# options: --out DIR (default disassembled/) --ghidra DIR --project DIR --no-linear
```

| Output | Contents |
|---|---|
| `disassembled/decompiled/<addr>_<name>.c` | one file per function (~6.5 k) |
| `disassembled/decompiled_all.c` | concatenated — grep-friendly |
| `disassembled/disasm/<addr>_<name>.asm` | per-function assembly (Ghidra listing) |
| `disassembled/full.lst` | linear disassembly via `pi32dis.py` |
| `disassembled/functions.txt` | `addr size name` index |
| `disassembled/symbols.txt` · `strings.txt` | symbol table · defined strings (VA + flash) |

**`disassembled/` is gitignored on purpose** — it is derived from
user-provided firmware and never published; regenerate instead of curating.
The driver refuses to overwrite a directory without its
`.h3plus-generated` marker. Ghidra projects land in `work/ghidra_disasm_proj/`
(scratch). `DumpAll.java` is the post-script that does the dumping
(`<outDir>` as its only script arg). Findings:
[ch. 25 §25.8](../findings/25-ghidra-decompile-compile-route.md).
