# TIDRADIO H3 Plus — Firmware Reverse Engineering & Bluetooth PTT Patching

Reverse-engineering notes, tools and a firmware patcher for the **TIDRADIO H3 Plus**
handheld transceiver — culminating in a small binary patch that turns any Bluetooth
headset's microphone into the transmit PTT source.

> [!WARNING]
> Flashing modified firmware always carries a bricking risk. Read
> [findings ch. 20 — Risks & Safety](findings/20-risks-and-safety.md) before writing
> anything to a radio, and take a full flash dump first. You are responsible for
> what you flash and for the legality of your radio's operation.

## Introduction

**What is here.** This repository documents the complete reverse engineering of the
H3 Plus firmware: both encryption layers broken (the UBOOT LFSR stream cipher and the
app-region SFC/ENC hardware scrambler), the Bluetooth stack mapped, and a patch tool
([`tools/patch_h3plus_firmware_bluetooth.py`](tools/patch_h3plus_firmware_bluetooth.py))
that lets you rewire what the PTT / PTT2 / OD-PTT keys do — including making the main
PTT key transmit the **Bluetooth headset microphone** in full duplex. All findings are
in the [findings index](findings/Findings.md); every script is documented in
[tools/Tools.md](tools/Tools.md).

**Why is it here.** The radio ships with a vendor-locked Bluetooth accessory whitelist
and fixed key routing. This project unlocks full-duplex BT headset audio with *any*
headset and makes the key behavior configurable — without vendor cooperation, since
none was offered.

**A few lines of history.** It started in 2026 as "can a generic BT headset be used
with this radio's PTT accessory protocol?" The firmware had to be dumped, decrypted
and disassembled to answer that: the JieLi BR23 SoC was identified from the `JL_FW`
magic, the UBOOT LFSR cipher was recovered by known-plaintext phase analysis, and the
app region fell to the SFC/ENC per-cache-line scrambler formula documented in the
[kagaimiq/jielie](https://github.com/kagaimiq/jielie) repo. Live over-the-air testing
of a genuine TID-PTT accessory revealed the real protocol (`+SPP=P`/`+SPP=R` over SPP),
and the final result is a 3–5 byte patch per behavior, hardware-confirmed. The full
milestone trail is in [findings ch. 01](findings/01-overview.md).

**⚠️ No firmware is included.** For legal reasons this repository contains **no
firmware images whatsoever**. The `BIN/`, `FW/`, `Dumps/` and `work/` folders that the
documentation refers to are **not shared** — you must acquire a firmware version for
your radio yourself (official TIDRADIO download) and create your own flash dump.
See [ARTIFACTS.md](ARTIFACTS.md) for exactly what each folder needs and how to produce it.

**Credits.** This entire effort — all code, all documentation, all analysis — was
produced by AI: **Claude Sonnet 5, Claude Opus 5, Claude Opus 5.5 and
Qwen3.8-Flash-Next**. Not a single line of code and/or documentation is written by a
human. The human contribution was running the tools, flashing the radio and reporting
back what the screen said.

## Step-by-step: alter your own firmware

### 0. Prerequisites

- A TIDRADIO H3 Plus and its USB-C cable (**data** cable, not charge-only).
- A PC with Python 3 (the patch tool is pure stdlib) and, for flashing,
  [jl-uboot-tool](https://github.com/kagaimiq/jl-uboot-tool) (see step 4).
- Your firmware dump (see [ARTIFACTS.md](ARTIFACTS.md) — dump first, always).

### 1. Enter the JieLi USB bootloader (uboot mode)

- **Power off** the radio completely.
- Plug a direct **USB-C cable** into the **side USB-C port** of the radio (ensure you
  are using the data/side port next to the mic/headset jacks, **not** the bottom
  battery-charging port!!!).
- Connect the other end directly to your computer (avoid using external USB hubs).
- Press and **hold down the PTT button and the `3` key** on the keypad.
- While holding those buttons, **turn on the radio** using the power/volume knob.
- The top indicator LEDs should show activity or double green lights (or the updater
  software will register the device status as **online**).

  > Note: On later firmware versions, holding the **`8` key** from regular standby may
  > also trigger USB upgrade mode.

### 2. Patch the firmware image

From a clone of this repository (see [ARTIFACTS.md](ARTIFACTS.md) for where to put the
firmware files):

```powershell
# inspect what the patch would do (no output file)
python tools/patch_h3plus_firmware_bluetooth.py BIN/TD-H3-PlusV1.0.50.bin --show

# produce a patched image (defaults: BT mode 4, main PTT -> BT headset mic)
python tools/patch_h3plus_firmware_bluetooth.py BIN/TD-H3-PlusV1.0.50.bin work/patched.bin

# or export only the changed 4 KiB flash sectors + the exact flash commands
python tools/patch_h3plus_firmware_bluetooth.py BIN/TD-H3-PlusV1.0.50.bin --sectors=work/sect
```

Key options (full reference: [tools/Tools.md §1](tools/Tools.md)):

| Option | Meaning |
|---|---|
| `--bluetooth-mode` / `-b` `1–6` | BT audio routing mode (default 4 = full duplex, hardware-confirmed) |
| `--PTT=BT-PTT\|PTT` | What the main PTT key does (default `BT-PTT` = transmit BT headset mic) |
| `--PTT2=` / `--OD-PTT=` | `PTT` / `PTT2` / `BT-PTT` / `BT-PTT2` / `OD-PTT` for the side/overdrive keys (`BT-PTT2` = BT headset mic forced to VFO B — UNTESTED on hardware) |
| `--sectors=PREFIX` | Export only the changed 4 KiB sectors (safer flashing, see below) |

### 3. Acquire and set up jl-uboot-tool

The open-source [jl-uboot-tool](https://github.com/kagaimiq/jl-uboot-tool) implements
the JieLi USB bootloader protocol and can read/write raw flash. Setup (Linux):

```console
$ git clone https://github.com/kagaimiq/jl-uboot-tool
$ cd jl-uboot-tool
$ pip install -r requirements.txt   # needs crcmod, pyusb, tqdm …
$ sudo python3 jluboottool.py
Searching for some JieLi devices..
Found a device: BR23 UBOOT1.00 (1.00) at /dev/sg2
...
  >> Chip key: 0xF181 <<
=>JL:
```

(`sudo` is needed because the tool talks to the USB/SCSI-generic device directly.
On Windows you may need a WinUSB/zadig driver, or run the tool in a Linux VM with
USB passthrough.)

### 4. Backup, patch, reflash

The workflow that was actually used and hardware-confirmed:

```
=>JL: read 0x00000000 0x100000 dump_internal.bin     # 1. BACKUP — always, first
```

Then patch `dump_internal.bin` (or the vendor `.bin`) with the tool from step 2, and
write back. Two flashing strategies exist:

**A. Sector writes (`--sectors`, recommended / safer).** The patch tool prints the
exact `erase`/`write` commands for only the 4 KiB sectors that changed:

```
erase 0x057000 0x1000
write 0x057000 work/sect_057000.bin
...
read 0x057000 0x1000 verify_057000.bin    # read back and compare!
```

This is safer because the blast radius is a few 4 KiB sectors: the 32 device-specific
bytes at `0x0C8FE0` and the VM area (BT identity, pairing records) are never touched,
and a mistake cannot wipe the whole chip. Details:
[findings §9A.38](findings/12-bluetooth-5-patching-tool.md).

**B. Full write.** Writing the whole image is possible but riskier: the vendor `.bin`
holds `0xFF` where your radio has real per-unit data at `0x0C8FE0`, so a full image
**must** have that block spliced from your own dump first
([ARTIFACTS.md §4](ARTIFACTS.md)). If something goes wrong mid-write you have lost
everything below the written area — which is exactly why step 1 (the backup) exists.

> A plain `.bin` or `.fw` firmware update applied through the **official** upgrade
> tooling should work just as well with a patched image (the `.fw` container carries
> the same app bytes; the patch tool understands both containers) — but this route
> was **never tested** in this project. The sector/full-write route above is the
> hardware-confirmed one.

### 5. Verify on the radio

After reflash + power cycle: pair any BT headset, press PTT, and confirm the headset
mic keys your transmission. The Radio Info menu shows the firmware version — note it
does **not** change when patched (see [findings](findings/Findings.md) for why the
version string can't be tagged; the patch sites are the source of truth).

## The Findings

Everything discovered during this effort lives in [`findings/`](findings/Findings.md), indexed by
[findings/Findings.md](findings/Findings.md) — 22 chapters covering the platform,
both cipher breaks, the Bluetooth protocol decoding, the patching milestones, the
hardware dump, the multipoint architecture analysis and the open questions.

Start with [01-overview.md](findings/01-overview.md); the patching endgame is
[12](findings/12-bluetooth-5-patching-tool.md) and
[13](findings/13-bluetooth-6-key-remap-milestones.md).

## The Tools

Every script in [`tools/`](tools/Tools.md) is documented in [`tools/Tools.md`](tools/Tools.md):
what it does, why it exists, and how to use it. The centerpiece is
`patch_h3plus_firmware_bluetooth.py` (the patcher); around it sit the decryptors
(`jl_decrypt.py`, `jl_sfcenc.py`), the pi32v2 disassembler (`pi32dis.py`), address
xref helpers (`findva.py`, `xref.py`) and the Bluetooth test-rig scripts.

## License

[MIT](LICENSE.md) — Copyright (c) 2026 Stefan Lenselink <Stefan@lenselink.org>

## References

The repositories used as source, information and tooling:

| Project | Role |
|---|---|
| <https://github.com/kagaimiq/jl-uboot-tool> | USB/UART bootloader protocol — the tool used to dump and reflash this radio |
| <https://github.com/kagaimiq/jielie> | JieLi chip docs — the [SFC/ENC notes](https://github.com/kagaimiq/jielie/blob/main/periph/sfc.md) solved the app-region cipher |
| <https://github.com/kagaimiq/jl-misctools> | JieLi firmware/package utilities |
| <https://github.com/NationalSecurityAgency/ghidra> | Disassembly of the pi32 bootloader |
| <https://github.com/upx/upx> | Unpacking the vendor `Update App.exe` |
| <https://github.com/icsharpcode/ILSpy> | Analyzing the vendor .NET CPS |
| <https://github.com/dnSpyEx/dnSpy> | Alternative .NET decompiler/debugger |
| <https://pypi.org/project/crcmod/> | CRC implementation used by jl-uboot-tool |
| <https://chirpmyradio.com/> | Chirp — codeplug programming across many radios (context) |
| <https://github.com/rogerclarkmelbourne/OpenGD77> | OpenGD77 — custom-firmware precedent (context) |
| <https://openrtx.org/> | OpenRTX — open multi-radio firmware (context) |
| <https://www.tidradio.com/> | TIDRADIO — vendor site, official firmware downloads |

Full annotated link list: [findings ch. 19](findings/19-reference-links.md).
