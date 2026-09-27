# TIDRADIO H3 PLUS — Firmware Reverse Engineering Findings

> Index for the RE effort on the TIDRADIO (TID Electronics) H3 Plus handheld transceiver.
> Status: **firmware fully decrypted** — UBOOT *and* app region. Chip + chip key confirmed from hardware.
> BT headset-mic PTT **hardware-confirmed** via 3–5 byte patches.
> Last updated: 2026-09-26 (added [Ch. 22 — multipoint architecture](22-bluetooth-7-multipoint-architecture.md)).

> [!IMPORTANT]
> **No firmware is published in this repository.** The folders `BIN/`, `FW/`, `Dumps/`
> and `work/` referenced throughout the chapters are **not included** — you must provide
> them yourself. See [ARTIFACTS.md](../ARTIFACTS.md) for what each folder must contain
> and how to acquire or generate every artifact (vendor download, hardware dump, tool output).

**Start here:** [01-overview.md](01-overview.md) for the executive summary and device identity,
[13-bluetooth-6-key-remap-milestones.md](13-bluetooth-6-key-remap-milestones.md) for the end result
(key → BT-headset-mic transmit), and [17-tooling-index.md](17-tooling-index.md) for the scripts.
The companion document for tool details is [`../tools/Tools.md`](../tools/Tools.md).

## Chapters

### Overview

| File | Contents |
|---|---|
| [01-overview.md](01-overview.md) | Executive summary with the full milestone table, and the target-device spec sheet. Confirms the JieLi BR23 SoC, Beken BK4819 RF chip, chip key `0xF181`, and the three key discoveries that made patching viable. |
| [02-artifact-inventory.md](02-artifact-inventory.md) | Inventory of every firmware artifact: `BIN/` serial images, `FW/` USB-C packages, `work/` derived files, `Dumps/` hardware reads. Includes sizes, naming quirks, and the 152 KB size drop between 1.0.41 and 1.0.42. |

### Platform & cryptography

| File | Contents |
|---|---|
| [03-platform-jieli-soc.md](03-platform-jieli-soc.md) | The decisive evidence that the SoC is a JieLi part (`JL_FW` magic) and why that matters. Covers the pi32/pi32v2 CPU architecture and the open-source RE ecosystem around the platform. |
| [04-container-formats.md](04-container-formats.md) | Layout of the `.bin` header (offsets `0x00–0x3F`) and the `.fw` package (0x400 header + payload + 64-byte `JL_FW` trailer). Documents how `.bin` and `.fw` relate and notes the `ufw` file table is still unlocated. |
| [05-lfsr-cipher-and-key-recovery.md](05-lfsr-cipher-and-key-recovery.md) | The JieLi "ENC" 16-bit LFSR stream cipher (poly `0x1021`, period 32767) protecting the UBOOT region, plus the five-step key/phase recovery methodology. Ends with the recovered phases: 32591 for `.bin`, 31567 for `.fw`. |
| [06-decrypted-bootloader.md](06-decrypted-bootloader.md) | What the decrypted bootloader (`0x0000–0x4FFF`) contains: upgrade strings, region markers, and the JieLi structures that pointed toward the app region. Explains how each string informed the next step. |
| [07-app-region-solved.md](07-app-region-solved.md) | The solution to the app region: the SFC ENC hardware block scrambles per 32-byte cache line with `key = chipkey ^ (addr >> 2)`. Includes the decryptor, the base-0 proof, and the historical negative results so the dead ends are not re-walked. |

### Bluetooth headset / PTT effort (former §9A chapters, plus §9B multipoint)

| File | Contents |
|---|---|
| [08-bluetooth-1-discovery-and-whitelist.md](08-bluetooth-1-discovery-and-whitelist.md) | Static discovery of full HFP support in the firmware: profile records, AT command set, menu strings, and the accessory device-name whitelist. Covers the first (failed) flash test, the `AT+MPTT=1` root-cause hypothesis, the pi32v2 disassembler, and the rotating BLE identity obstacle. |
| [09-bluetooth-2-live-testing-and-spp.md](09-bluetooth-2-live-testing-and-spp.md) | Live over-the-air testing: `AT+MPTT=1` is parsed but rejected, the working connection model is *let the radio initiate*, and the RFCOMM channel map is brute-forced. Capturing a genuine TID-PTT accessory reveals the real PTT protocol is `+SPP=P`/`+SPP=R` over SPP, and the headset name selects an audio-routing mode (full duplex achieved). |
| [10-bluetooth-3-disassembly.md](10-bluetooth-3-disassembly.md) | Locating the PTT handler dispatcher in the decrypted app and the discovery that `AT+MPTT` runs in the opposite direction — the radio *sends* it as an RX-squelch indicator. Also documents a major disassembler bug (wrong branch/call targets) and its fix. |
| [11-bluetooth-4-routing-modes-decoded.md](11-bluetooth-4-routing-modes-decoded.md) | Full decode of the routing-mode classifier and the mode switch, including the routing-mode variable and register-indexed load/branch encodings. Ends with a re-confirmation of the two PTT paths and the single audio mux using mature tooling. |
| [12-bluetooth-5-patching-tool.md](12-bluetooth-5-patching-tool.md) | The first patch tool `tools/patch_h3plus_firmware_bluetooth.py` and its hardware results: duplex works, PTT does not — overturning the earlier model. Covers the routing-mode byte's six readers, the SPP command string table, free trampoline space, and the one-virtual-key-queue model that explains everything. |
| [13-bluetooth-6-key-remap-milestones.md](13-bluetooth-6-key-remap-milestones.md) | The endgame: manual-page-to-code mapping of PF1/PF2/PTT2/OD-PTT, the key-code patches, and the hardware-confirmed milestones — a radio key transmitting the BT headset mic, then the main PTT itself. Documents the configurable PF-menu mapping, the CLI redesign, and the direct body-rewrite model covering all 12 action pairs. |
| [22-bluetooth-7-multipoint-architecture.md](22-bluetooth-7-multipoint-architecture.md) | The dual-device question: can a headset and the TID-PTT button connect at once? Maps the connection-callback ops table at `0xBF48`, the dispatcher that reaches the classifier, the `0x1A670` device linked list, and the decisive constraint — a **single global device struct at `0x102F0`** (809 refs). Also: no free code space inside the app, but ~208 KiB of **erased flash beyond it**, keeping the trampoline route alive. |

### Hardware, flashing & tooling

| File | Contents |
|---|---|
| [14-differential-analysis.md](14-differential-analysis.md) | The v1.0.44 vs v1.0.45 XOR diff: 57.7% of bytes identical with a 22 KB contiguous run. This proves the cipher is position-deterministic (no chaining/nonce), which is what makes targeted binary patching viable. |
| [15-official-tooling.md](15-official-tooling.md) | Analysis of the vendor tools: UPX-unpacked `Update App.exe`, the `updata.exe` Kenwood serial updater with its protocol strings, and the .NET `TIDRadioCPS.exe` codeplug programmer. Notes the CPS symbols that identified the BK4819 RF chip. |
| [16-flashing-and-hardware-dump.md](16-flashing-and-hardware-dump.md) | The three flashing/recovery paths (USB-C, Kenwood serial, web) and the hardware SPI flash dump obtained with `jl-uboot-tool`. Confirms flash == distributed `.bin`, maps the whole 1 MiB flash, finds the 32 device-specific bytes and the plaintext VM area, and shows code execution on the chip. |
| [17-tooling-index.md](17-tooling-index.md) | Table of every script built during the effort in `tools/`, with purpose and usage lines. Includes the shared LFSR helper, the SFC/ENC decryptor (its own inverse, so it also re-encrypts), and environment/PowerShell gotchas. |

### Planning & reference

| File | Contents |
|---|---|
| [18-open-questions-next-steps.md](18-open-questions-next-steps.md) | Prioritized next steps: BT mic enablement, disassembling the decrypted app, decrypting archived firmware, the `ufw` table, CPS decompilation, and a repack workflow. Also lists the completed items and remaining unanswered questions. |
| [19-reference-links.md](19-reference-links.md) | External links: the kagaimiq JieLi RE ecosystem, the SFC documents that broke the app cipher, pi32 architecture references, tools used, and related amateur-radio RE projects. |
| [20-risks-and-safety.md](20-risks-and-safety.md) | Legal and safety notes: RF transmission law, bricking risk, and safe experimentation practices. |
| [21-appendices.md](21-appendices.md) | Appendix A: constants cheat sheet (offsets, keys, phases, magic values). Appendix B: raw header/footer dumps of the `.bin` and `.fw` containers and decrypted bootloader regions. |

---

*Section numbering from the original document (§1–§16, §9A.1–9A.50) is preserved inside the chapter files, so old references like "§9A.44" still resolve — follow the chapter links above.*
