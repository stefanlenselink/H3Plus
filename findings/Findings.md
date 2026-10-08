# TIDRADIO H3 PLUS — Firmware Reverse Engineering Findings

> Index for the RE effort on the TIDRADIO (TID Electronics) H3 Plus handheld transceiver.
> Status: **firmware fully decrypted** — UBOOT *and* app region. Chip + chip key confirmed from hardware.
> BT headset-mic PTT **hardware-confirmed** via 3–5 byte patches.
> Last updated: 2026-10-06 late (Ch. 27: **the firmware already has 2 `conn_info` slots** — vendor-widened pools (2 RFCOMM muxes etc.), §9B.11's `[1 x conn_info]` is the SDK default only, `conn_info` widening unnecessary; all 0x13 senders action-driven; capture decode proves the radio's **controller** terminates the second link — experiment matrix E1–E5 next. Earlier same day: Ch. 26 §26.11: **Option A2 hardware round 2** — `--force-page-scan` hardware-confirmed (radio answers pages while the headset holds HFP; `Page Timeout` gone) and the kick-NOP holds; the second link now dies one layer deeper (`Connect Complete 0x13` / RFCOMM `ECONNRESET`) — statically proven to be the stack's `conn_info`-full profile refusal (§9B.11), not app code; app SPP path is device-agnostic. Also: the "PTT invisible on the radio" scare was BlueZ auto-grabbing the PTT — keep the PC adapter off for radio-side pairing tests. Previously §26.9 round 1: kick-NOP works; page-scan gate → `--force-page-scan`.) Originally 2026-10-04: [Ch. 26 — Bluetooth 9: The Eviction Decision, Located](26-bluetooth-9-eviction-decision.md) — the second-device eviction is an **app-level kick** at `0x01E5B22A` posting cmd 5 to the controller-queue relay `0x01E22890` (sole HCI-Disconnect executor); the stack never evicts. Consolidated **multipoint options analysis** (§26.7) with a 4-byte kick-NOP experiment candidate. Earlier 2026-10-03: [Ch. 25 — The Ghidra decompile ⇒ alter ⇒ compile route](25-ghidra-decompile-compile-route.md) — Ghidra 12 + ghidra-jieli decompiles the app, the official toolchain recompiles it, fixed-point proven **and hardware-validated**; `tools/disassemble_app.py` generates the full (gitignored) disassembly + decompilation tree (§25.8); multipoint root cause closed in [Ch. 22 §9B.11](22-bluetooth-7-multipoint-architecture.md) — the stack tracks one BR/EDR link; earlier: [Ch. 24](24-jieli-ecosystem-sdk-toolchain.md) ecosystem sweep, **BT-PTT2 hardware-validated** — [Ch. 23](23-bluetooth-8-bt-ptt2.md)).

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
| [04-container-formats.md](04-container-formats.md) | Layout of the `.bin` header (offsets `0x00–0x3F`) and the `.fw` package (0x400 header + payload + 64-byte `JL_FW` trailer). Documents how `.bin` and `.fw` relate. The `ufw` file table was later **located and CRC-verified** — see [Ch. 24 §24.6](24-jieli-ecosystem-sdk-toolchain.md#246-containers-keys-flash-map--what-the-packagers-and-community-tools-proved). |
| [05-lfsr-cipher-and-key-recovery.md](05-lfsr-cipher-and-key-recovery.md) | The JieLi "ENC" 16-bit LFSR stream cipher (poly `0x1021`, period 32767) protecting the UBOOT region, plus the five-step key/phase recovery methodology. Ends with the recovered phases: 32591 for `.bin`, 31567 for `.fw` — later explained as alignment artifacts of the 32767-period keystream ([Ch. 24 §24.6](24-jieli-ecosystem-sdk-toolchain.md#246-containers-keys-flash-map--what-the-packagers-and-community-tools-proved)). |
| [06-decrypted-bootloader.md](06-decrypted-bootloader.md) | What the decrypted bootloader (`0x0000–0x4FFF`) contains: upgrade strings, region markers, and the JieLi structures that pointed toward the app region. Explains how each string informed the next step. |
| [07-app-region-solved.md](07-app-region-solved.md) | The solution to the app region: the SFC ENC hardware block scrambles per 32-byte cache line with `key = chipkey ^ (addr >> 2)`. Includes the decryptor, the base-0 proof, and the historical negative results so the dead ends are not re-walked. |
| [24-jieli-ecosystem-sdk-toolchain.md](24-jieli-ecosystem-sdk-toolchain.md) | The external sweep: `fw-AC63_BT_SDK` **is** the right SDK (`cpu/br23` = AC635N), `isd_config.ini` fully decoded via its generator, SFCENC registers confirm the ch. 07 cipher at RTL level, the BT stack API proves **1-to-2 multipoint with call pre-empt** (app-layer, not stack, is the H3's limit), the official LLVM objdump **validates our disassembler (12,786 targets, 0 mismatches)**, the `.ufw` table is located, and the full flash map (incl. the VM-region caution for Route B). |
| [25-ghidra-decompile-compile-route.md](25-ghidra-decompile-compile-route.md) | The Ghidra route: ghidra-jieli (unmodified) + Ghidra 12.1.4 decompile the app at `0x01E00000` (headless import recipe, pointer-scan seeding, 6558 functions); decompiles independently confirm `is_1t2_connection`, the conn_num setter and the routing classifier; JieLi clang (`-target pi32v2 -mcpu=r3 -Oz`) recompiles the decompiled logic to the **same instruction forms**, and the spliced image re-decompiles to **byte-identical C** (fixed point). Scope limits for multipoint stated. |

### Bluetooth headset / PTT effort (former §9A chapters, plus §9B multipoint)

| File | Contents |
|---|---|
| [08-bluetooth-1-discovery-and-whitelist.md](08-bluetooth-1-discovery-and-whitelist.md) | Static discovery of full HFP support in the firmware: profile records, AT command set, menu strings, and the accessory device-name whitelist. Covers the first (failed) flash test, the `AT+MPTT=1` root-cause hypothesis, the pi32v2 disassembler, and the rotating BLE identity obstacle. |
| [09-bluetooth-2-live-testing-and-spp.md](09-bluetooth-2-live-testing-and-spp.md) | Live over-the-air testing: `AT+MPTT=1` is parsed but rejected, the working connection model is *let the radio initiate*, and the RFCOMM channel map is brute-forced. Capturing a genuine TID-PTT accessory reveals the real PTT protocol is `+SPP=P`/`+SPP=R` over SPP, and the headset name selects an audio-routing mode (full duplex achieved). |
| [10-bluetooth-3-disassembly.md](10-bluetooth-3-disassembly.md) | Locating the PTT handler dispatcher in the decrypted app and the discovery that `AT+MPTT` runs in the opposite direction — the radio *sends* it as an RX-squelch indicator. Also documents a major disassembler bug (wrong branch/call targets) and its fix. |
| [11-bluetooth-4-routing-modes-decoded.md](11-bluetooth-4-routing-modes-decoded.md) | Full decode of the routing-mode classifier and the mode switch, including the routing-mode variable and register-indexed load/branch encodings. Ends with a re-confirmation of the two PTT paths and the single audio mux using mature tooling. |
| [12-bluetooth-5-patching-tool.md](12-bluetooth-5-patching-tool.md) | The first patch tool `tools/patch_h3plus_firmware_bluetooth.py` and its hardware results: duplex works, PTT does not — overturning the earlier model. Covers the routing-mode byte's six readers, the SPP command string table, free trampoline space, and the one-virtual-key-queue model that explains everything. |
| [13-bluetooth-6-key-remap-milestones.md](13-bluetooth-6-key-remap-milestones.md) | The endgame: manual-page-to-code mapping of PF1/PF2/PTT2/OD-PTT, the key-code patches, and the hardware-confirmed milestones — a radio key transmitting the BT headset mic, then the main PTT itself. Documents the configurable PF-menu mapping, the CLI redesign, and the direct body-rewrite model covering all 12 action pairs (extended to 20 with `BT-PTT2`, [Ch. 23](23-bluetooth-8-bt-ptt2.md)). |
| [22-bluetooth-7-multipoint-architecture.md](22-bluetooth-7-multipoint-architecture.md) | The dual-device question: can a headset and the TID-PTT button connect at once? Maps the connection-callback ops table at `0xBF48`, the dispatcher that reaches the classifier, the `0x1A670` device linked list, and the decisive constraint — a **single global device struct at `0x102F0`** (809 refs). Also: no free code space inside the app, but ~208 KiB of **erased flash beyond it** — later shown to be VM-reserved ([Ch. 24 §24.6](24-jieli-ecosystem-sdk-toolchain.md#%E2%9A%A0%EF%B8%8F-flash-map-caution-for-ch-23--route-b)); the stack layer was later proven 1-to-2 capable ([Ch. 24 §24.4](24-jieli-ecosystem-sdk-toolchain.md#244-bt-stack--the-multipoint-answer-ch-22-open-question-b)). |
| [23-bluetooth-8-bt-ptt2.md](23-bluetooth-8-bt-ptt2.md) | The `BT-PTT2` action: Bluetooth-mic transmit forced onto **VFO B** (second channel), selectable as a PF-menu action. Trampoline over the key-`0x2A` standby-handler tail @`0x01E794DA` into a verified-zero code cave @`0x01EA76DE`, one-shot force-B flag at `gp+0xC7`, all 20 action pairs build. **Hardware-confirmed 2026-09-30** (`--PTT2=BT-PTT2`: works with and without a headset; normal PTT unaffected). |
| [26-bluetooth-9-eviction-decision.md](26-bluetooth-9-eviction-decision.md) | The eviction decision, located: an **app-level kick** `0x01E5B22A` reads the tracked handle at `0x102F0+0x82` and posts cmd 5 to the controller-queue relay `0x01E22890` — the **sole** HCI-Disconnect executor (`0x01E074DE`, reason 19). The stack never evicts (op 4 never posted; incoming accepted blindly). Three-layer constraint model and the consolidated **multipoint options analysis** — kick-NOP experiment (4 bytes, UNTESTED), data-model widening, vendor multipoint lib, single-link combo device. **Corrected 2026-10-06** (§26.11 note): 0x406 has 13 sites, and the "stack `[1 x conn_info]`" layer does not apply to our build — see ch. 27. |
| [27-firmware-2slot-stack-controller-wall.md](27-firmware-2slot-stack-controller-wall.md) | **Course-correction:** our firmware's host stack was built with **2 `conn_info` slots** (RAM `0x1A5B8`, stride `0x1C`) and widened pools (2 RFCOMM muxes, 6 svc, 6 ch, 20 L2CAP ch, 1900 B pool vs SDK 600 B) — the `[1 x conn_info]` wall of §9B.11 is the SDK *default*, not our build, so `conn_info` widening is **unnecessary**. Full HCI-Disconnect sender enumeration (all 0x13 paths action-driven), the round-2 capture decoded (`Connect Complete 0x13` = the radio's **controller** sends `LL_Disconnect` 644 ms after the page; host always accepts, no connected-gate), and the **controller-library verdict** with a 5-test experiment matrix (E1–E5, incl. the accept-role patch candidate). **§27.10: E3 (2026-10-08) — the incumbent-kill on a radio-initiated join is APP-LEVEL** (graceful L2CAP teardown + Disconnect Complete `0x13`; executor = `disconnect(handle,0x13)` call @`0x01E178CE`, dispatcher `0x01E1792E` case `0x4A` + cmd 8/10) → shipped as `--no-disconnect-13`. **§27.11: E6 HW-CONFIRMED 2026-10-08 — the radio holds TWO links; multipoint works radio-initiated** (incumbent PC SPP survived the headset join, SPP keys worked with both up; the controller wall is incoming-pages-only). |

### Hardware, flashing & tooling

| File | Contents |
|---|---|
| [14-differential-analysis.md](14-differential-analysis.md) | The v1.0.44 vs v1.0.45 XOR diff: 57.7% of bytes identical with a 22 KB contiguous run. This proves the cipher is position-deterministic (no chaining/nonce), which is what makes targeted binary patching viable. |
| [15-official-tooling.md](15-official-tooling.md) | Analysis of the vendor tools: UPX-unpacked `Update App.exe`, the `updata.exe` Kenwood serial updater with its protocol strings, and the .NET `TIDRadioCPS.exe` codeplug programmer. Notes the CPS symbols that identified the BK4819 RF chip. |
| [16-flashing-and-hardware-dump.md](16-flashing-and-hardware-dump.md) | The three flashing/recovery paths (USB-C, Kenwood serial, web) and the hardware SPI flash dump obtained with `jl-uboot-tool`. Confirms flash == distributed `.bin`, maps the whole 1 MiB flash, finds the 32 device-specific bytes and the plaintext VM area, and shows code execution on the chip. |
| [17-tooling-index.md](17-tooling-index.md) | Table of every script built during the effort in `tools/`, with purpose and usage lines. Includes the shared LFSR helper, the SFC/ENC decryptor (its own inverse, so it also re-encrypts), and environment notes (platform-independent Python; historical shell gotchas). |

### Planning & reference

| File | Contents |
|---|---|
| [18-open-questions-next-steps.md](18-open-questions-next-steps.md) | Prioritized next steps: BT mic enablement, disassembling the decrypted app, decrypting archived firmware, the `ufw` table, CPS decompilation, and a repack workflow. Also lists the completed items and remaining unanswered questions. |
| [19-reference-links.md](19-reference-links.md) | External links: the kagaimiq JieLi RE ecosystem, the SFC documents that broke the app cipher, pi32 architecture references, tools used, and related amateur-radio RE projects. |
| [20-risks-and-safety.md](20-risks-and-safety.md) | Legal and safety notes: RF transmission law, bricking risk, and safe experimentation practices. |
| [21-appendices.md](21-appendices.md) | Appendix A: constants cheat sheet (offsets, keys, phases, magic values). Appendix B: raw header/footer dumps of the `.bin` and `.fw` containers and decrypted bootloader regions. |

---

*Section numbering from the original document (§1–§16, §9A.1–9A.50) is preserved inside the chapter files, so old references like "§9A.44" still resolve — follow the chapter links above.*
