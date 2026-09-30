[<< Index](Findings.md)

## 13. Tooling Built During This Effort

All scripts live in `tools/`. Pure Python 3 except where noted.

| Script | Purpose | Usage |
|---|---|---|
| `analyze.py` | Entropy, index of coincidence, byte histogram, 4K-block entropy, XOR period scan, duplicate 16-byte blocks | `python tools/analyze.py [files...]` |
| `strings.py` | ASCII + UTF-16LE string extraction with keyword filter | `python tools/strings.py <file> [filter\|all] [minlen]` |
| `pedump.py` | PE header/section/data-directory dumper with per-section entropy (no external deps) | `python tools/pedump.py <exe>` |
| `region.py` | Dump all ASCII strings within a file offset range | `python tools/region.py <file> <start> <end> [minlen]` |
| `headers.py` | Print head/tail hex+ASCII of every file in `BIN/` and `FW/` | `python tools/headers.py` |
| `hexdump.py` | Range hexdump | `python tools/hexdump.py <file> <start> <end>` |
| `jl_map.py` | **The winner.** Indexes all keystream windows, scans file for matches, groups contiguous runs, tests reset block sizes | `python tools/jl_map.py <file> [window]` |
| `jl_phasemap.py` | **numpy** per-block best-phase solver (histogram vote) | `python tools/jl_phasemap.py <file> <blocksize>` |
| `jl_decrypt.py` | Decrypt whole file with a given phase → `<name>.p<phase>.dec`, print entropy, hexdump, strings | `python tools/jl_decrypt.py <file> <phase>` |
| `jl_other_ciphers.py` | Test CrcDecode/MengLi + RxGp ciphers, XOR self-correlation | `python tools/jl_other_ciphers.py <file> <offset>` |
| `jl_recover_key.py` | Per-phase mode statistics assuming a fixed-size table. **Used to disprove the 32-byte-table hypothesis** | `python tools/jl_recover_key.py <file> <period>` |
| `jl_solve.py` | Builds LFSR cycle, finds repeated non-FF runs, votes on phase | `python tools/jl_solve.py <file>` |
| `jl_bruteforce.py` | 65536-key brute force with heuristic scoring. **Too slow — superseded by `jl_phasemap.py`** | (deprecated) |
| **`jl_sfcenc.py`** ⭐ | **SFC/ENC hardware-scrambler decryptor. Solves the app region.** Symmetric — also re-encrypts. | `python tools/jl_sfcenc.py <file> [out] --key=0xF181 --start=0x5000 --end=0xC8FE0 --base=0` |
| **`patch_btname.py`** ⭐ | **Patches the Bluetooth accessory whitelist.** Decrypts, edits the name slot, re-encrypts, verifies round-trip. | `python tools/patch_btname.py <in> [out] --show \| --mic=NAME \| --ptt=NAME \| --micear=NAME` |
| **`patch_h3plus_firmware_bluetooth.py`** ⭐ | **The end-all patching tool.** Rewrites the routing-mode classifier and the 20 key-action body pairs (PTT/PTT2/BT-PTT/BT-PTT2/OD-PTT) directly, in place, on either `.bin` or `.fw` containers. Auto-detects container + version from context signatures; refuses unrecognised images. See [Ch. 12](12-bluetooth-5-patching-tool.md), [Ch. 13](13-bluetooth-6-key-remap-milestones.md) and [Ch. 23](23-bluetooth-8-bt-ptt2.md). | `python tools/patch_h3plus_firmware_bluetooth.py <src> [<dst>] [--show] [--bluetooth-mode 1-6] [--PTT2=...] [--OD-PTT=...] [--sectors=PREFIX] [--only SITE]` |

| **`pi32dis.py`** ⭐ | **pi32v2 disassembler.** Builds its decode table by parsing `tools/isa/pi32v2.md` at runtime. See [§9A.13](08-bluetooth-1-discovery-and-whitelist.md#9a13-a-working-pi32v2-disassembler--toolspi32dispy). | `python tools/pi32dis.py work/app_dec.bin --flash 0x083C40 --count 26` |
| **`bt_be_headset.sh`** ⭐ | **Makes the Linux box a discoverable Bluetooth headset** and auto-accepts inbound pairing. Sets Class of Device and the advertised name; optional 2nd arg overrides the class (use `0x5a020c` to appear as a phone). Lets the *peer* initiate. See [§9A.17](09-bluetooth-2-live-testing-and-spp.md#9a17-the-working-connection-model--let-the-radio-initiate). | `sudo ./tools/bt_be_headset.sh "TID-PTT" [0x5a020c]` |
| **`bt_spp_hold.py`** ⭐⭐ | **Holds the SPP link open so the radio stays connected**, with interactive PTT (`Enter`/`p`/`r`/`s`/`q`) or `--cycle`. Use this rather than `bt_spp_ptt.py` for anything beyond a single shot. See [§9A.21](09-bluetooth-2-live-testing-and-spp.md#9a21-the-radio-waits-for-a-profile-connection-not-just-an-acl-link). | `sudo python3 tools/bt_spp_hold.py <mac>` |
| **`bt_spp_ptt.py`** ⭐ | One-shot send of the real PTT protocol — NUL-terminated `+SPP=P` / `+SPP=R` over SPP. Note it disconnects on exit by design; prefer `bt_spp_hold.py`. See [§9A.20](09-bluetooth-2-live-testing-and-spp.md#9a20--solved-the-real-ptt-protocol-is-sppp--sppr-over-spp). | `sudo python3 tools/bt_spp_ptt.py <mac> --once --hold 3` |
| **`bt_ag_capture.py`** ⭐ | **Impersonates the radio (Audio Gateway) and logs everything a genuine PTT accessory sends** — full AT stream both directions, plus a peer identity snapshot including the PnP vendor/product ID. Answers the SLC so the accessory keeps talking. `--connect` dials the button (the correct direction); `--listen` waits instead. See [§9A.19](09-bluetooth-2-live-testing-and-spp.md#9a19--changing-approach-capture-a-genuine-accessory-instead-of-guessing). | `sudo python3 tools/bt_ag_capture.py --scan` then `--connect <mac>` |
| `bt_hf_sim.py` | HF-role client: RFCOMM AT channel + SCO audio, cycles `AT+MPTT=1`/`=0` with looping mp3. `--no-mptt` validates against a phone; `--probe-channels` maps the peer's RFCOMM endpoints when SDP is silent ([§9A.18](09-bluetooth-2-live-testing-and-spp.md#9a18-the-radios-rfcomm-channel-map-obtained-by-brute-force)). | `python3 bt_hf_sim.py <mac> ghosts.mp3 [--probe-channels]` |
| `bt_wait_and_pair.sh` | Outbound scan-and-pair watcher. **Superseded by `bt_be_headset.sh`** — outbound discovery of the radio proved unreliable ([§9A.14](08-bluetooth-1-discovery-and-whitelist.md#9a14-live-pairing-obstacle-the-radios-ble-identity-rotates-between-sessions)). | (deprecated) |
| `bt_audio_check.sh` | Diagnoses why radio audio is/isn't reaching PC speakers: checks PipeWire/WirePlumber, HF/sink role endpoints, profile connections. Run as your normal user, not root. | `./tools/bt_audio_check.sh [radio-mac]` |
| **`bt_multipoint_probe.py`** ⭐ | **Phase-0 multipoint experiment** ([§9B.6](22-bluetooth-7-multipoint-architecture.md#9b6-phase-0-live-probe-decides-everything-no-flashing)): connects SPP ch 2 (button role), holds it, tries HFP ch 6 while held, then the reverse order; prints `MULTIPOINT OK` / `KICK-ON-CONNECT` / `SECOND LINK REFUSED`. | `sudo python3 tools/bt_multipoint_probe.py <mac> [--hold 2] [--ptt-hold 3] [--no-hfp]` |

### Static-analysis helpers (decrypted app)

| Script | Purpose | Usage |
|---|---|---|
| **`xref.py`** ⭐ | Cross-reference 32-bit `call`/`goto` targets in the decrypted app (`target = addr + 4 + sign_extend_23(A:B<<1)`). `--goto` includes conditional gotos. **Finds nothing for callback-table functions — pair with `findva.py`.** | `python tools/xref.py work/app_dec.bin 0x01E50398` |
| **`findva.py`** ⭐ | Raw byte-pattern search, including 32-bit little-endian VAs — finds **pointer-table references** that `xref.py` cannot (this is how the classifier's only reference, file `0x018450`, was found). | `python tools/findva.py work/app_dec.bin 0x01E7EC28` |
| `pf78tbl.py` | Decodes the PF-menu value 7/8 dispatch machinery — the `tbb r0` jump table at `0x01E75DDC` and the two release-executor compare immediates. Read-only check behind `--PTT2`/`--OD-PTT` (§9A.47/§9A.48). | `python tools/pf78tbl.py [decrypted-app-image]` |
| `freespace.py` | Zero-run finder + free-space verifier: lists runs ≥ N bytes, flags `.word` data vs code from `full.lst`, and adds a cross-version ALLZERO column via `--other VER=file`. **Trust the ALLZERO column, not `code=`** (`0x0000` decodes as `nop`). See [§9B.7](22-bluetooth-7-multipoint-architecture.md#9b7-code-space-none-inside-the-app--but-208-kib-of-erased-flash-beyond-it). | `python tools/freespace.py work/app_dec.bin --min 64 --lst work/full.lst --other 45=work/decrypted/v45_app_dec.bin` |
| `verify_actions.py` | Test suite for the patch tool's action-pair rewrites — 0 failures expected. | `python tools/verify_actions.py` |
| `verify_cli.py` | Test suite for the patch tool CLI surface — 0 failures expected. Platform-independent (pure stdlib; port of the former `verify_cli.ps1`). | `python tools/verify_cli.py` |

### Shared LFSR helper used across tools

```python
POLY = 0x1021

def step(k):
    return ((k << 1) ^ (POLY if k & 0x8000 else 0)) & 0xFFFF

def build_cycle(seed=0xFFFF):
    states, seen, k = [], {}, seed
    while k not in seen:
        seen[k] = len(states)
        states.append(k)
        k = step(k)
    return states, bytes(s & 0xFF for s in states)   # P = 32767
```

### SFC/ENC decryptor (the one that solved the app region)

```python
POLY, LINE = 0x1021, 32

def sfc_enc_decrypt(data, base=0, chipkey=0xF181):
    out = bytearray(data)
    for off in range(0, len(data), LINE):
        k = (chipkey ^ ((base + off) >> 2)) & 0xFFFF   # reseed every cache line
        for i in range(off, min(off + LINE, len(data))):
            out[i] ^= k & 0xFF
            k = ((k << 1) ^ (POLY if k & 0x8000 else 0)) & 0xFFFF
    return bytes(out)
```

The function is its own inverse, so the same call re-encrypts a patched image.

### External ground-truth tools (2026-09-30)

- **Official pi32v2 objdump** (JieLi Linux toolchain, LLVM 4.0.1): cross-validates
  `pi32dis.py` — 12,786 common branch targets, 0 mismatches. The `.incbin` → `clang -c` →
  `ld --section-start` → `objdump -d` recipe for raw images is documented in
  [Ch. 24 §24.5](24-jieli-ecosystem-sdk-toolchain.md#245-official-toolchain--our-disassembler-validated-byte-exactly).
- **Community `jl-misctools`** (`fwunpack_newfw.py`, `keyfgen.py`, `recrypt.py`): independent
  confirmation of both ciphers and the container layout ([Ch. 24 §24.6](24-jieli-ecosystem-sdk-toolchain.md#246-containers-keys-flash-map--what-the-packagers-and-community-tools-proved)).

### Environment notes

- **Platform-independent:** every script in `tools/` is pure Python 3 (stdlib only,
  `numpy` for `jl_phasemap.py`) and runs unchanged on Windows, Linux and macOS. Use
  forward slashes in paths — Python accepts them everywhere, including Windows. The
  only OS-specific scripts are the Bluetooth test rig (`bt_*.sh`), which needs Linux
  with BlueZ.
- Analysis was carried out on Windows (Python 3.13.13, numpy 2.5.3) and Linux; UPX
  5.0.2 was used for unpacking the vendor CPS tool.

#### Historical shell gotchas (from the Windows/PowerShell phase)

Kept for the record — the tooling itself no longer depends on any of this.

- **`cd` in PowerShell does NOT change .NET's current directory.** `[IO.File]::ReadAllBytes()` therefore needs **absolute** paths.
- Long terminal output gets truncated/redirected to a temp file; read it back with the file reader rather than re-running.
- Pipe through `Select-Object -First N` to keep output manageable.

---

*[<< Index](Findings.md)*
