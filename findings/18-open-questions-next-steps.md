[<< Index](Findings.md)

## 14. Open Questions / Next Steps

### Priority 1 — Enable the Bluetooth microphone ⭐

**Root cause identified: the accessory must send the proprietary `AT+MPTT=1` command over HFP.** The name whitelist is real but is *not* the gate on its own — see [§9A.12](08-bluetooth-1-discovery-and-whitelist.md#9a12--actual-root-cause--the-accessory-must-send-atmptt1).

**Status:** live testing is underway and the test rig is fully validated. A Linux box presenting as a headset ([§9A.17](09-bluetooth-2-live-testing-and-spp.md#9a17-the-working-connection-model--let-the-radio-initiate)) connects to the radio, establishes both RFCOMM and SCO, and passes a real bidirectional phone call — so the rig is proven good. Against the radio, `AT+MPTT=1` is **parsed and actively rejected with `ERROR`**, both with and without an SCO link active ([§9A.15](09-bluetooth-2-live-testing-and-spp.md#9a15--live-test-1--atmptt1-is-parsed-and-actively-rejected), [§9A.16](09-bluetooth-2-live-testing-and-spp.md#9a16-live-test-2--sco-link-established-atmptt-still-rejected)).

**Next step (historical):** the leading hypothesis was that the whitelist's device-class integer gates the vendor AT parser. Test it by advertising as `TID-PTT` / `TID-MIC` / `TID-MIC-EAR` (removing the pairing on both sides between each, since the name is cached at pairing time) and re-issuing `AT+MPTT=1`. `Jabra E` is also worth testing, as it is patched into this unit's flash. If all names are rejected, fall back to disassembling the PTT handler at `0x05FDE2` / `0x07834C`.

*(Superseded by the key-remap patches — [Ch. 13](13-bluetooth-6-key-remap-milestones.md) — which are hardware-confirmed; kept for the record.)*

Configuration workarounds are **ruled out** — `BT Int Mic` has no effect on a non-whitelisted device, and the VM stores no device-type flag ([§9A.8](08-bluetooth-1-discovery-and-whitelist.md#9a8-vm-differential-test--negative-and-that-is-informative)). A firmware patch is required.

1. **Flash the 7-byte patch.** `work/dump_jabra.bin` is built and verified; apply via the single-sector route in [§9A.9](08-bluetooth-1-discovery-and-whitelist.md#9a9-how-to-actually-apply-the-patch).
2. **Confirm the headset's mic works**, then re-check `BT Int Mic` / `BT Mic Gain` — they should become meaningful.
3. **Verify the PTT button still pairs** (its slot was left untouched).
4. **Disassemble `0x083C00–0x083D00`** to read off the exact compare length.

### Priority 1b — The PTT-button + separate-headset stretch goal

See [§9A.7](08-bluetooth-1-discovery-and-whitelist.md#9a7-the-stretch-goal--ptt-button--separate-headset) and now [§9B](22-bluetooth-7-multipoint-architecture.md). The app layer is mapped: it models **one** remote device (single global struct at `0x102F0`, 809 refs). **Update 2026-09-30:** the stack layer is no longer undecided — the SDK's `btstack.a` API proves 1-to-2 multipoint with call pre-empt/restore is a supported stack feature ([Ch. 24 §24.4](24-jieli-ecosystem-sdk-toolchain.md#244-bt-stack--the-multipoint-answer-ch-22-open-question-b)), so an SDK rebuild is only needed if the H3's own build has the feature disabled or the app layer cannot be coaxed. `tools/bt_multipoint_probe.py` still settles it in one run on hardware. With the `mic` slot patched and the `ptt` slot intact, both devices are whitelisted — so this is now purely a question of multipoint capability.

### Priority 1c — Hardware-validate `BT-PTT2` (BT mic on VFO B)

`--PTT2=BT-PTT2` / `--OD-PTT=BT-PTT2` ([§9C](23-bluetooth-8-bt-ptt2.md)) builds and passes
the byte-level suite, but is **UNTESTED on hardware**. Flash a build and check: PF key
assigned to S Press = "BT PTT2" transmits the headset mic on **VFO B** while VFO A is the
working VFO, and the one-shot flag leaks nothing — a subsequent main-PTT press must still
transmit on the current VFO. Test label rendering in each menu language, and the
`--PTT2=BT-PTT2 --OD-PTT=BT-PTT` combo (both BT labels at once).

### Priority 2 — Disassemble the decrypted app

- `work/app_dec.bin` (802,784 bytes) is now plaintext `pi32v2` code. Load at the correct base and find the string cross-references above.
- Parse `app_area_head` at `0x5010` — likely a directory structure giving the real sub-region layout.
- Separate code from the compressed audio resources (`storage/res_nor/C/tone/*`), which account for the residual 6.9 entropy.

### Priority 3 — Apply the decryption to the archived firmware

- Decrypt the app region of every version in `BIN/` with `tools/jl_sfcenc.py` and **re-run the differential analysis on plaintext**. Far more informative than the ciphertext diff, and will show exactly what changed between versions.
- Note: archived files were built for **this chip key**; if other units have different keys the same file would not work, which explains the updater's key-matching errors.

### Priority 4 — Locate the `ufw` file table ✅ CLOSED (2026-09-30)

Solved from the official packager (`ufw_maker 1.1.14`) and the community unpacker: the table
is 0x40 header + N×0x50 LFSR-descrambled (key `0xFFFF`) entries, all CRC16-verified, and the
64-byte `JL_FW` trailer **is** the `tail.bin` entry. See
[Ch. 24 §24.6](24-jieli-ecosystem-sdk-toolchain.md#246-containers-keys-flash-map--what-the-packagers-and-community-tools-proved).

### Priority 5 — Decompile `TIDRadioCPS.exe`

- ILSpy / `ilspycmd` (may need the .NET SDK). Recover the codeplug format and any crypto helpers.
- **Diff `H3_Plus(GMRS).td` vs `H3_Plus(HAM).td` vs `H3_Plus(Normal).td`.**
- Look specifically for BT fields; `CPS_MIC_GAIN_START` is already known to exist.

### Priority 6 — Build a repack workflow

- `tools/jl_sfcenc.py` is symmetric, so re-encrypting a patched app region is already solved.
- Determine which CRCs must be fixed after patching (`jl_crc16`, `jl_crc32` with init `0x26536734`).
- Evaluate `Update App.exe --merge --target` for official repacking.
- Validate against the dual-bank OTA mechanism so a bad image falls back safely.

### Completed

- ~~Dump decrypted app code out of RAM~~ — **unnecessary**; solved offline ([§9.0](07-app-region-solved.md#90-the-solution)).
- ~~Crack the app region~~ ✅ **DONE.**
- ~~Read the real chipkey off hardware~~ ✅ **DONE — `0xF181`**, and it turned out to be the ENC key.
- ~~Determine the exact JieLi part number~~ ✅ **BR23 / AC635N / AC695N.**
- ~~Does the SoC's BT stack include HFP/HSP (mic) support?~~ ✅ **YES** ([§9A](08-bluetooth-1-discovery-and-whitelist.md#9a-bluetooth-hfp--microphone-support--confirmed)).
- ~~Locate the `ufw` file table~~ ✅ **DONE** — official packager + community unpacker ([Ch. 24 §24.6](24-jieli-ecosystem-sdk-toolchain.md#246-containers-keys-flash-map--what-the-packagers-and-community-tools-proved)).
- ~~Acquire a usable JieLi SDK for the chip~~ ✅ **DONE** — `fw-AC63_BT_SDK` `cpu/br23` = AC635N, with datasheets and prebuilt libs ([Ch. 24 §24.1](24-jieli-ecosystem-sdk-toolchain.md#241-chipfamily-map--we-have-the-right-sdk-now)).
- ~~Does the BT stack support concurrent multi-device links?~~ ✅ **YES at the stack API level** (1拖2 with pre-empt/restore); H3 build pending probe ([Ch. 24 §24.4](24-jieli-ecosystem-sdk-toolchain.md#244-bt-stack--the-multipoint-answer-ch-22-open-question-b)).
- ~~Validate our pi32v2 disassembler~~ ✅ **DONE** — official LLVM objdump: 12,786 common branch targets, **0 mismatches** ([Ch. 24 §24.5](24-jieli-ecosystem-sdk-toolchain.md#245-official-toolchain--our-disassembler-validated-byte-exactly)).

### Unanswered questions

- What caused the 152 KB size drop between 1.0.41 and 1.0.42?
- Are `TID-H3-PlusV1.0.42.bin` and `TID-H3-PlusV1.0.42(1).bin` byte-identical?
- What are the 8 unknown bytes at BIN offset `0x08`?
- What is the `.fw` header's 4-byte checksum algorithm (offset `0x00`)?
- Full URL of the `https://fmup.g...` firmware server.
- **What are the 32 device-specific bytes at `0x0C8FE0`?** ([§12A.6](16-flashing-and-hardware-dump.md#12a6-the-32-device-specific-bytes-at-0x0c8fe0))
- **Where is the "128 Mb external storage"?** The dumped SPI0 NOR is only 1 MiB. Try reading other chip-selects.
- **Full schema of the VM area at `0x0C9000`** — item tag/length framing, and which item IDs control Bluetooth behaviour.
- Does `jl_key::getMappingKey` map `"X12345678"` → `0xF181`? (Now a **verifiable oracle** — useful for generating images for *other* chip keys.)
- **Why is `BT Int Mic` apparently not reachable**, given the strings and HFP stack are present?
- **New (2026-09-30):** does the H3's `btstack.a` build include the 1拖2 code paths (SDK API proves the family does)? Function-pattern diff SDK lib vs app, or run the probe.
- **New:** feasibility build — compile `apps/spp_and_le` for br23 with the official Linux toolchain (`-mcpu=r3`) to prove we can build for the chip (prerequisite for the SDK-rebuild route).
- **New:** SFCENC `UNENC_ADRH/L` / `LENC_ADRH/L` unencrypted windows — hardware experiment for patched-region handling ([Ch. 24 §24.3](24-jieli-ecosystem-sdk-toolchain.md#243-sfcenc-hardware-block--register-level-confirmation-of-ch-07)).
- **New:** H3 entry point `0x1E00100` vs SDK default `0x1E00120` — version fingerprint across v44/v45/v50.
- **Route B (erased flash beyond app) deprioritized:** the JLFS entry list shows it is inside the `VM` region (`0xC9000`+`0x34000`) — see the caution in [Ch. 24 §24.6](24-jieli-ecosystem-sdk-toolchain.md#%E2%9A%A0%EF%B8%8F-flash-map-caution-for-ch-23--route-b).

---

*[<< Index](Findings.md)*
