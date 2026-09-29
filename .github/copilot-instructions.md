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
| `findings/23-bluetooth-8-bt-ptt2.md` | §9C: BT-PTT2 (BT mic on VFO B) — trampoline + code cave design, **UNTESTED on hardware** |
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
  findings §9A.26/§9A.50.

## The main tool

`tools/patch_h3plus_firmware_bluetooth.py` (pure stdlib Python):

```
python tools/patch_h3plus_firmware_bluetooth.py <src> [<dst>] [--show]
    [--bluetooth-mode|--bt|-b 1-6]   # default 4 (duplex, HW-confirmed)
    [--PTT=BT-PTT|PTT] [--PTT2=...] [--OD-PTT=...]   # 20 action pairs build directly
    #   actions: PTT PTT2 BT-PTT BT-PTT2 OD-PTT (BT-PTT2 = BT mic forced to VFO B, UNTESTED)
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

## Current state & open frontiers (as of 2026-09-26)

Done: both ciphers broken · classifier decoded · routing modes 1–6 mapped · key-remap
patches HW-confirmed (BT-mic PTT, duplex) · patch tool + 2 test suites green ·
multipoint architecture mapped (ch. 22) · **BT-PTT2 (BT mic on VFO B) implemented, all
20 action pairs build, 784 checks green — UNTESTED on hardware** (ch. 23).

Open (in priority order):
1. **Hardware-validate BT-PTT2** (ch. 23 §9C.8): flash `--PTT2=BT-PTT2`, confirm TX on
   VFO B with the headset mic and that the one-shot flag (`gp+0xC7`) never leaks into a
   plain main-PTT/`+SPP=P` transmit.
2. **Run `tools/bt_multipoint_probe.py <mac>` on Linux/hardware** — decides whether the
   BT stack accepts two concurrent ACL links (headset + TID-PTT button). Gates Route A/B/C.
3. Ghidra + quarkslab/ghidra-jieli (pi32v2) on Linux; import `work/app_dec.bin` at
   `0x01E00000`; hunt stack-layer link policy (`btstack`/`btctrler`/`link_layer`
   component strings @`0x933xx` are log names only — no max-link config is statically visible).
4. AC635N/BR23 JieLi SDK acquisition (public `fw-AC630N_BT_SDK` targets the wrong chip).
5. SFC-mapping test for erased flash beyond `0xC8FE0` (Route B trampolines).
6. "BT Int Mic" menu item exists in firmware but is untested on hardware.

When continuing this work, update `findings/18-open-questions-next-steps.md`, the
relevant chapter, and this section.
