# copilot-instructions.md — TIDRADIO H3 Plus Firmware RE

Instructions for AI coding agents working in this repository. Read this before making
changes. It is distilled from `README.md`, `ARTIFACTS.md`, `findings/` (23 files),
`tools/Tools.md`, and the verified working practices of this project.

## What this repository is

Reverse-engineering notes, Python tools, and a firmware patcher for the **TIDRADIO
H3 Plus** handheld transceiver (JieLi BR23 / AC635N SoC, pi32v2 CPU, Beken BK4819 RF).
Both firmware encryption layers are broken; the Bluetooth stack is mapped; a 3–5 byte
patch makes any BT headset's mic the PTT transmit source, hardware-confirmed.

- **License:** MIT, © 2026 Stefan Lenselink (`LICENSE.md`). Every file in `tools/`
  carries an SPDX MIT header (Python: AFTER the module docstring; see `tools/jl_sfcenc.py`).
- **No firmware is published here, ever.** `BIN/`, `FW/`, `Dumps/`, `work/` are
  user-provided and gitignored in spirit — never commit firmware images, dumps, or
  derived binaries. Never add the vendor ZIPs at the repo root to any deliverable.
- All documentation, code, and analysis in this repo is AI-produced; the human runs
  tools, flashes the radio, and reports results. Keep that division: propose, don't flash.

## Repository layout

| Path | Contents |
|---|---|
| `findings/Findings.md` | **Index** of 23 numbered chapters; old §9A.x/§12A.x section numbers preserved inside chapters |
| `findings/08–13-*.md` | The Bluetooth effort (§9A.1–9A.50) |
| `findings/22-bluetooth-7-multipoint-architecture.md` | §9B: dual-device/multipoint analysis |
| `findings/23-bluetooth-8-bt-ptt2.md` | §9C: BT-PTT2 (BT mic on VFO B) — trampoline + code cave design, **hardware-confirmed 2026-09-30** |
| `findings/24-jieli-ecosystem-sdk-toolchain.md` | §24: SDK/toolchain/packager ecosystem — ufw table, SFCENC registers, stack 1拖2 multipoint, official-objdump validation, flash map |
| `tools/Tools.md` | Reference for every script in `tools/` (§1 patcher, §3 crypto, §4 static analysis, §6 BT rig, §7 test suites) |
| `tools/isa/pi32v2.md` | The pi32v2 instruction-set notes; `pi32dis.py` parses it at runtime |
| `BIN/ FW/ Dumps/ work/` | User artifacts (firmware, dumps, scratch) — see `ARTIFACTS.md` |

When adding findings: create a new numbered chapter in `findings/`, add a row to the
index table in `findings/Findings.md`, and cross-link from `18-open-questions-next-steps.md`
when relevant. GitHub anchor slugs: lowercase, punctuation dropped, spaces → dashes.

## Non-negotiable technical facts (verified — do not re-derive)

- **Chip key `0xF181`**; 1 MiB SPI NOR; app flash `0x5000`–`0xC8FE0`;
  **VA base `0x01E00000` = app offset 0 = flash `0x5000`** (so `VA − 0x01E00000 = file
  offset` in `work/app_dec.bin`, and `flash = offset + 0x5000`).
- **Two independent cipher layers.** UBOOT (`0x0000–0x4FFF`): LFSR stream, poly
  `0x1021`, phase 32591 (`.bin`) / 31567 (`.fw`) → `tools/jl_decrypt.py`.
  App region: SFC/ENC per-32-byte-line scrambler, `key = chipkey ^ (addr >> 2)`,
  base 0 relative to app start → `tools/jl_sfcenc.py` (symmetric — also re-encrypts).
- **App-decrypt recipe:** `python tools/jl_sfcenc.py BIN/<file>.bin <out>` with
  defaults. Feed it the RAW `.bin` — never an LFSR `.dec` file (that yields garbage,
  entropy 8.0). Good app plaintext has entropy ≈ 6.92.
- **Option syntax:** `jl_sfcenc.py` (and friends) require the EQUALS form
  `--key=0xF181`; the space form crashes with `ValueError`.
- **VM area** plaintext @`0x0C9000` (magic `55 AA AA 55`, dual-bank @`0x0C9490`,
  append-only): BT names + 16-byte link keys. **32 device-specific bytes @`0x0C8FE0`**
  — a full-image reflash of a stock `.bin` destroys them; splice from the user's dump
  or use `--sectors` (see `ARTIFACTS.md` §4).
- **Erased flash `0x0CA000–0x0FC000`** (~208 KiB of 0xFF) exists beyond the app end;
  no code references it. Trampoline target for future code, pending an SFC-mapping test.
- **Single global BT device struct at RAM `0x102F0`** (809 refs): the app models ONE
  remote BT device. Routing-mode byte at RAM `0xB464` (`b[0xB390+0xD4]`). Classifier
  `0x01E7EC28` (name → mode 1–4) is reached only via ops-table `[0xBF48+0x4]`.
  Details: findings ch. 22 (§9B).
- **BT protocol:** PTT events are `+SPP=P`/`+SPP=R` (NUL-terminated) over SPP
  RFCOMM ch 2; HFP AG is ch 6; the radio *sends* `AT+MPTT=1/0` as an RX-squelch
  notification (it is not an inbound command). Radio doesn't answer SDP.
- **pi32v2 encodings:** 32-bit call/goto `target = addr + 4 + sign_extend_23(A:B<<1)`;
  `if (r0==N) goto`: word0=`00 f8`, word1=`(N<<9)|disp9`; PF tbb table entries at
  `0x01E75DDC` encode `(target − 0x01E75DDC)/2`. Full notes: `tools/isa/pi32v2.md`,
  findings §9A.26/§9A.50. **Validated against the official LLVM objdump (`-mcpu=r3`):
  12,786 common branch targets, 0 mismatches** (ch. 24 §24.5). ELF machine 0xF1.
- **Ecosystem (ch. 24):** correct SDK is `fw-AC63_BT_SDK` `cpu/br23` (= AC635N; the
  AC630N SDK is q32s/bd29 — wrong core). SFCENC regs @`0x1F0C00` (`KEY` u16 +
  `UNENC/LENC_ADRH/L`). Full flash map: `app.bin` @`0x5100`, VM @`0xC9000` size
  `0x34000` (**the "erased" 0xCA000–0xFC000 span is VM-reserved**), BTIF @`0xFD000`,
  EXIF @`0xFE000`, key_mac @`0xFF000`. The btstack API supports 1拖2 multipoint
  (`__set_user_ctrl_conn_num`, `__set_hfp_switch/restore`) — single-device is app-layer.
  `.ufw` table = 0x40 hdr + N×0x50 entries (LFSR key 0xFFFF, CRC16-verified); the
  `JL_FW` trailer is its `tail.bin` entry.

## The main tool

`tools/patch_h3plus_firmware_bluetooth.py` (pure stdlib Python):

```
python tools/patch_h3plus_firmware_bluetooth.py <src> [<dst>] [--show]
    [--bluetooth-mode|--bt|-b 1-6]   # default 4 (duplex, HW-confirmed)
    [--PTT=BT-PTT|PTT] [--PTT2=...] [--OD-PTT=...]   # 20 action pairs build directly
    #   actions: PTT PTT2 BT-PTT BT-PTT2 OD-PTT (BT-PTT2 = BT mic forced to VFO B, HW-confirmed)
    [--conn-num=1|2]   # user_ctrl_conn_num gate, 1 byte; HW-tested insufficient (ch.22 §9B.10.2/§9B.11)
    [--sectors=PREFIX] [--only SITE]
```

- Understands both `.bin` and `.fw` containers; does the SFC/ENC crypto internally.
- `--show` reports per-site state (stock / patched / partly modified) — run it first.
- Direct-rewrite model (§9A.50): the tbb table is NEVER touched; bodies at
  `0x01E75E38`/`0x01E75E42` and the release window at `0x01E75E78` are rewritten.
- Legacy swap images (tbb bytes `332e`) are detected and refused — do not "fix" this.
- **After ANY change to this tool, run both suites and require 0 failures:**
  `python tools/verify_actions.py` and `python tools/verify_cli.py`.
  SystemExit messages go to stderr — check both streams.

## Static-analysis workflow (decrypted app)

- `work/full.lst` (user-generated, 19.5 MB) is the v1.0.50 disassembly; format:
  `01E00000  3e 58  [005000]  mnemonic`. Regenerate with `tools/pi32dis.py`.
- `tools/xref.py <img> <VA>` decodes call/goto xrefs; **callback functions have zero
  direct xrefs** — always follow up with `tools/findva.py <img> <VA>` which finds
  32-bit LE pointer-table entries (that's how the classifier was found at file
  `0x018450`).
- `tools/freespace.py` verifies zero-run candidates; trust the cross-version ALLZERO
  column, NOT the `code=` flag (`0x0000` decodes as `nop`). Even ALLZERO blocks need a
  pointer scan (every 2-byte-aligned LE word) before use — one candidate died as a
  runtime draw buffer.
- Verdict on free code space inside the app: **no zero-run with code alongside**, but
  verified ALLZERO caves do exist — the 364 B run @`0x01EA76DE` (ALLZERO in v44/v45/v50,
  pointer-scan clean) carries the BT-PTT2 code (ch. 23). Larger space: the erased flash
  beyond `0xC8FE0` via trampolines, or an SDK rebuild.

## Platform independence (mandatory)

**This project is platform-independent by design — do not tie new code, scripts, or
docs to any single OS.** There are no PowerShell (`.ps1`) or batch (`.bat`/`.cmd`)
scripts here, and none should be added.

- **Every tool is pure Python 3, stdlib-first** (`numpy` only for `jl_phasemap.py`),
  and must run unchanged on Windows, Linux and macOS. Invoke with `python`
  (`python3` in the Linux BT rig); inside Python, spawn sub-processes with
  `sys.executable`, never a hard-coded interpreter name.
- **Always use forward slashes in paths** — Python accepts them on Windows too. Never
  build paths by concatenating `\\`; use `os.path.join()` / `pathlib` in code, and
  `../tools/...` style relative paths in docs.
- **No OS-specific system calls, drive letters, `%VAR%`/`$env:` expansions, or
  shell-only utilities** in the tools. Read/write files as UTF-8 explicitly
  (`open(..., encoding="utf-8")`) so behaviour doesn't drift with the platform's
  locale or default newline translation.
- **The one deliberate exception:** the Bluetooth test rig (`tools/bt_*.sh`, and the
  root-requiring `tools/bt_*.py`) needs **Linux/BlueZ** (WSL works if the BT adapter is
  passed through) — the radio must usually initiate the connection. Keep that
  limitation where it is; do not spread OS coupling into the firmware/crypto/analysis
  tools.
- **Documentation examples are shell-neutral:** mark command blocks
  <code>```bash</code> (never <code>```powershell</code>) and write them so they work
  in bash, pwsh and zsh alike. The historical Windows/PowerShell gotchas are preserved
  as a record in `findings/17-tooling-index.md` only — the tooling no longer depends
  on them.
- The two `work/` helper scripts (`add_license_headers.py`, `split_findings.py`) are
  the Python ports of the former `.ps1` one-offs; `tools/verify_cli.py` is the Python
  port of `verify_cli.ps1`. Prefer extending these over reintroducing shell scripts.

## Environment notes

- Developed on both Windows and Linux; the tooling is verified to run on either.
  Python 3.13+ recommended; tools are stdlib-only except `jl_phasemap.py` (numpy).
- Bluetooth test rig (`tools/bt_*.py|sh`) runs on **Linux/BlueZ only** (WSL works if
  the BT adapter is passed through). The radio must usually initiate the connection.
- `work/` is scratch — regenerate, don't curate. Key files: `work/app_dec.bin`
  (v50 app plaintext), `work/decrypted/v44_app_dec.bin`, `v45_app_dec.bin`.

## Editing conventions in this workspace

- **Use `replace_string_in_file` / `multi_replace_string_in_file` for `.md` edits.**
  `insert_edit_into_file` has silently no-opped twice on `Findings.md` in this repo.
- Keep chapter cross-references as relative links with correct GitHub anchor slugs;
  when renaming a heading, update every link to it.
- Documentation voice: factual, evidence-first. Mark UNTESTED claims explicitly.
  Distinguish "statically inferred" from "hardware-confirmed".
- New tools: Python stdlib-first, SPDX MIT header after the docstring, document in
  `tools/Tools.md` (TOC + section) AND the table in `findings/17-tooling-index.md`.
- Never run `git push`, flashing commands, or destructive disk operations autonomously.
  Flashing is the user's action; print the exact `jl-uboot-tool` commands instead
  (`--sectors` route preferred; always `read` back and compare after `write`).

## Current state & open frontiers (as of 2026-10-02)

Done: both ciphers broken · classifier decoded · routing modes 1–6 mapped · key-remap
patches HW-confirmed (BT-mic PTT, duplex) · patch tool + 2 test suites green ·
multipoint architecture mapped (ch. 22) · **BT-PTT2 hardware-confirmed** (ch. 23:
`--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT` works with and without a headset; normal
PTT unaffected, no `gp+0xC7` flag leak) · **ecosystem sweep: right SDK found (`fw-AC63_BT_SDK`
`cpu/br23` = AC635N), `.ufw` table located, official objdump validated our disassembler
(12,786 targets, 0 mismatches), stack API proves 1-to-2 multipoint** (ch. 24) ·
**multipoint gate `user_ctrl_conn_num` located + `--conn-num=2` patch built**
(ch. 22 §9B.10.2) — **hardware-tested 2026-10-03: eviction persists; the real cap is
the stack's `[1 x conn_info]` data model, multipoint is NOT reachable by binary
patch** (ch. 22 §9B.11).

Open (in priority order):
1. ~~Hardware-validate BT-PTT2~~ ✅ **PASSED 2026-09-30** (ch. 23 §9C.8): flashed
   `--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT`; works with and without headset, normal
   PTT always works (no `gp+0xC7` leak). Label rendering verified statically for all
   nine menu languages (ch. 23 §9C.9 — stock never localises these labels; all 20 combos
   re-scan clean) and on the display (2026-10-01: `--PTT2=BT-PTT2 --OD-PTT=BT-PTT`
   shows "BT2"/"BT PTT" correctly). BT-PTT2 fully validated; nothing in ch. 23 untested.
2. ~~Run `tools/bt_multipoint_probe.py <mac>` on Linux/hardware~~ ✅ **RUN 2026-10-01**
   (ch. 22 §9B.6.1): profile-level multipoint OK (SPP+HFP concurrent over one ACL, PTT
   keys with both up); a second *physical* device (real headset) **evicts** the first —
   the cap is the app's single-active-device policy, not the stack. Reverse 2-ACL test
   done 2026-10-02: `EHOSTDOWN` — radio not connectable while connected (page-level
   refuse). Policy = one active device; radio-initiated joins evict; incoming refused.
   Gate found in SDK bitcode (ch. 22 §9B.10) and **fully located in our image
   2026-10-02** (ch. 22 §9B.10.2): `user_ctrl_conn_num` = RAM `0xBF39` bits 4–5
   (`_stack_config` base `0xBF24`; blob @`0x01EC2064` +21 = `0x11`, alignment now
   proven); inlined setter `__set_user_ctrl_conn_num(1)` @`0x01E182B0` (single caller
   `0x01E60EB0`); reader @`0x01E1787C`. One-byte patch (`0x24→0x25` @file `0x182DD`)
   shipped as `--conn-num=2`. **HW TEST 2026-10-03: FAILED — eviction persists both
   directions** (byte verified `31 25` in the written image). Root cause found
   (ch. 22 §9B.11): reader `0x01E1787C` is `is_1t2_connection()` (scan-management
   only); the 1拖2 core `multi_bd.c` compiles to ZERO functions in every br23 SDK
   build; and `user_info_t` embeds `[1 x conn_info]` in ALL public btstack.a builds
   (bd29/br23/br25/br30/bd19/br34) — the host stack tracks ONE BR/EDR link. The
   controller (bredr_table, `[4 x ...]` arrays) could do more; the precompiled host
   stack cannot. Multipoint needs a vendor multipoint library, a machine-code data
   model transplant (research-grade), or a single-device workaround (one device
   carrying SPP+HFP, e.g. custom ESP32 combo device — profile coexistence proven).
3. Ghidra + quarkslab/ghidra-jieli (pi32v2, ELF machine 0xF1) on Linux; import
   `work/app_dec.bin` at `0x01E00000`. The official toolchain objdump (ch. 24 §24.5) is
   now the ground truth for decoding; Ghidra adds decompilation.
4. ~~AC635N/BR23 JieLi SDK acquisition~~ ✅ `fw-AC63_BT_SDK` `cpu/br23` (ch. 24 §24.1);
   next: feasibility build of `apps/spp_and_le` for br23 with the Linux toolchain
   (`-mcpu=r3`, `ulimit -n 8192`).
5. ~~Route B (erased flash beyond `0xC8FE0`)~~ **deprioritized**: the JLFS entry list shows
   `0xC9000–0xFD000` is the VM region — writing there risks VM collisions (ch. 24 §24.6).
   SFCENC `UNENC_ADRH/L` unencrypted windows are the better hardware experiment.
6. "BT Int Mic" menu item exists in firmware but is untested on hardware.

When continuing this work, update `findings/18-open-questions-next-steps.md`, the
relevant chapter, and this section.
