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
| `findings/25-ghidra-decompile-compile-route.md` | §25: Ghidra 12 + ghidra-jieli decompile ⇒ compile route — headless import recipe, pointer-scan seeding, round-trip fixed-point proof, JieLi clang `-target pi32v2 -mcpu=r3 -Oz` |
| `tools/Tools.md` | Reference for every script in `tools/` (§1 patcher, §3 crypto, §4 static analysis, §6 BT rig, §7 test suites) |
| `tools/isa/pi32v2.md` | The pi32v2 instruction-set notes; `pi32dis.py` parses it at runtime |
| `BIN/ FW/ Dumps/ work/` | User artifacts (firmware, dumps, scratch) — see `ARTIFACTS.md` |
| `disassembled/` | Generated full disassembly + decompilation tree (`tools/disassemble_app.py`) — gitignored, never publish |

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
    [--no-kick]        # NOP the app disconnect kick @0x01E5B22A (r0=3; rts); Option A = with --conn-num=2 (ch.26 §26.7)
    [--force-page-scan] # NOP page-scan disable branch @0x01E18B0E (nop;nop) — radio stays connectable while connected; Option A2 (ch.26 §26.9)
    [--force-role-keep] # ACL accept role -> 0xAA keep-role (goto 0x01E1A4C8) instead of stock 1 become-master; experiment E4 (ch.27 §27.8)
    [--no-disconnect-13] # NOP app disconnect executor @0x01E178CE (call 0x01E07B08); E6 — E3 proved the incumbent-kill on radio-initiated joins is app-level (ch.27 §27.10)
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

## Current state & open frontiers (as of 2026-10-08)

Done: both ciphers broken · classifier decoded · routing modes 1–6 mapped · key-remap
patches HW-confirmed (BT-mic PTT, duplex) · patch tool + 2 test suites green ·
multipoint architecture mapped (ch. 22) · **BT-PTT2 hardware-confirmed** (ch. 23:
`--PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT` works with and without a headset; normal
PTT unaffected, no `gp+0xC7` flag leak) · **ecosystem sweep: right SDK found (`fw-AC63_BT_SDK`
`cpu/br23` = AC635N), `.ufw` table located, official objdump validated our disassembler
(12,786 targets, 0 mismatches), stack API proves 1-to-2 multipoint** (ch. 24) ·
**multipoint gate `user_ctrl_conn_num` located + `--conn-num=2` patch built**
(ch. 22 §9B.10.2) — **hardware-tested 2026-10-03: eviction persists** (ch. 22 §9B.11 —
its "`[1 x conn_info]` data model" root cause was **corrected 2026-10-06**: our build
has 2 conn slots; the wall is the controller library, ch. 27) · **eviction decision located 2026-10-04** (ch. 26): app-level
kick `0x01E5B22A` posts cmd 5 to the controller-queue relay `0x01E22890` (sole
HCI-Disconnect executor `0x01E074DE`, reason 19); the stack never evicts; 4-byte
kick-NOP experiment + options analysis in ch. 26 §26.7.

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
   stack cannot. **Eviction decision LOCATED 2026-10-04 (ch. 26):** app kick
   `0x01E5B22A` (handle @`0x102F0+0x82`) → cmd 5 → queue `0x1A688` → relay
   `0x01E22890` case 5 (`0x01E22996`, sole executor) → `0x01E074DE` (reason 19);
   callers = BT on/off toggle `0x01E6076C(0)`, power API `0x01E83D84(1)`, command
   table @`0x01E9C9DC` entry[1]. Stack never evicts (op 4 never posted; incoming
   accepted blindly; `create_bt_new_conn` NULL when slot held — the kick frees the
   slot). **Option A implemented 2026-10-04** as `--no-kick` in the patch tool
   (kick early-return `0x01E5B22A: 75 04 c5 ff → 40 23 80 00` = `r0=3; rts`; both
   test suites green). **HW round 1 2026-10-05: kick-NOP CONFIRMED** — incoming
   attempts no longer evict the headset (readback-verified NOP), but the radio
   answers no pages while connected (btmon `Page Timeout`; scan policy re-enables
   page scan only when `is_1t2_connection()` false, vendor `multi_bd.c` compiled
   EMPTY). **Option A2 shipped 2026-10-06** as `--force-page-scan` (NOP the
   page-scan disable branch `0x01E18B0E: 80 41 24 16 → 00 00 00 00`; every setter
   call enables page scan; suites green). **NEXT: hardware test** Option A2
   (`--conn-num=2 --no-kick --force-page-scan`): PC/PTT pages the radio while the
   headset holds HFP — does the ACL + SPP come up without eviction? If SPP is
   refused, next gate = app single-device SPP/profile binding (struct `0x102F0`).
   (Side effects to expect: BT-off/menu-disconnect no longer release the link;
   radio always connectable.)
   **COURSE CORRECTION 2026-10-06 (ch. 27): the firmware already has 2 `conn_info`
   slots** — stride `0x1C`, array `0x1A5B8`–`0x1A5F0`, inused bit29 of word `+0xE`;
   pools vendor-widened (2 `rfcomm_multiplexer`s, 18 l2cap_service, 20 l2cap_channel,
   6 rfcomm_service/channel vs SDK defaults 4/5/1/3/3). §9B.11's `[1 x]` was the SDK
   default layout, not ours — **widening `conn_info` is unnecessary**. All 13 HCI-
   Disconnect (0x406) sites enumerated: kick (dead under `--no-kick`), reason-0xF
   timeout path, wrapper `0x01E07B08` (reason-0x13 callers are explicit disconnect
   commands only). Round-2 capture decode (`btmon -r`): second link dies at LL level
   ~644 ms after the page (Connect Complete 0x13, no success-then-disconnect) — the
   radio's **controller** terminates it; the host Connection Request handler
   (`FUN_01e19e44` case 4) always accepts incoming ACLs (role 1, or 0xAA if
   `DAT_0000c02b & 8`). **The wall is the prebuilt controller library.**
   **NEXT: experiments E1–E5 (ch. 27 §27.8)** — E2 (headset + outgoing page to
   TID-PTT) is the cheapest decisive test. **E4 SHIPPED 2026-10-07** as
   `--force-role-keep`: the case-4 ACL role test at `0x01E1A03A` (`lb.z
   r0,[r9+0x107]` + `jmnz`, flag = RAM `0xC02B` bit 3, init `0x00` → stock role
   1) becomes an unconditional `goto 0x01E1A4C8` (the `mov r1,#0xaa` keep-role
   load) + nops; SCO/eSCO/reject branch away earlier so they are unaffected;
   both suites green. E4 build = `--conn-num=2 --no-kick --force-page-scan
   --force-role-keep`. **E4 image BUILT 2026-10-07** (`work/e4_twodev.bin` +
   `work/e4_01F000.bin`, from the user's dump): A2→E4 is a **single 4 KiB sector
   write @flash `0x01F000`** — every other patch sector byte-identical to the radio
   (A2 rebuild reproduces the 10 flashed sectors exactly; radio readback `rb_060000`
   matches the E4 `0x060000` sector); all 4 patch bytes verified in the decrypted
   image. **E4 HW-tested 2026-10-07: FAILED** — the flashed image is byte-identical
   to `work/e4_twodev.bin`; E1 OK, but the incoming second link still dies at LL
   (~722 ms, 0x13) with the PC even offering role switch; and a radio-initiated
   headset join killed the PC's SPP link despite `--no-kick` (second eviction path:
   disconnect-current wrapper `0x01E07B08` / dispatcher cmd 8/10, or the
   controller). **E3 RUN + LOCATED 2026-10-08 (ch. 27 §27.10): the incumbent-kill is
   APP-LEVEL** — btmon shows a graceful L2CAP Disconnection Request/Response then
   Disconnect Complete `0x13` (handle 1) ~15 s into the headset join; executor =
   the `disconnect(handle,0x13)` call @`0x01E178CE` (find-conn `0x01E17420` modes
   0/2 → wrapper `0x01E07B08`), reached from dispatcher `0x01E1792E` case `0x4A`
   ("disconnect current": mode-set `0x01E60188`, BT-task UI "connect selected
   device" `0x01E61E22`) + stack dispatcher `0x01E21AF8` cases 8/10. **E6 SHIPPED
   2026-10-08** as `--no-disconnect-13` (NOP @`0x01E178CE`; suites green); E6 image
   `work/e6_twodev.bin` built — diff vs flashed E4 is 4 bytes in ONE sector,
   flash `0x01C000`. **E6 HW-TESTED 2026-10-08: PASSED (ch. 27 §27.11) —
   MULTIPOINT ACHIEVED radio-initiated.** PC SPP incumbent SURVIVED a
   radio-initiated Jabra headset join; both links stayed up (only Disconnect
   in the capture = the user's power-cycle, reason 0x08), SPP PTT keyed the
   radio with both devices connected, normal PTT unaffected. The
   "controller wall" is therefore **incoming-pages-only** (a second device
   paging the radio still dies at LL ~700 ms, 0x13); outgoing joins work.
   **Side effect:** after a second device joins, the radio's AT+MPTT
   squelch notifications arrive malformed on the first device's SPP channel
   (cr-bit flipped, "+MP" fragments; +SPP=P/R echo path unaffected) —
   root-cause = open static item. **NEXT:** user trialing the TID-PTT button
   as third device (pools are 2-slot — cap expected); confirm HFP audio to
   the headset; root-cause the malformed notifications; E5 (SCO scheduling)
   stays secondary.
   Remaining routes if the
   controller is hard-limited: vendor multipoint controller lib, SDK rebuild
   (ch. 25 decompile⇒compile route), or single-device workaround (one device
   carrying SPP+HFP, e.g. custom ESP32 combo device — profile coexistence proven).
3. ~~Ghidra + quarkslab/ghidra-jieli on Linux~~ ✅ **HARDWARE-VALIDATED 2026-10-03**
   (ch. 25): Ghidra 12.1.4 + ghidra-jieli (unmodified) decompiles
   `work/app_dec.bin` at `0x01E00000` headless (`tools/ghidra/` import recipe +
   pointer-scan seeding, 6558 functions); decompiles confirm
   `is_1t2_connection`/conn_num setter/classifier; JieLi clang
   (`-target pi32v2 -mcpu=r3 -Oz`) recompiles the decompiled logic to the same
   instruction forms, splices, and re-decompiles to byte-identical C (fixed
   point). The "unchanged" image `work/roundtrip/rt_test.bin` was **flashed and
   passed** (BT connects, BT-PTT works, normal PTT works) — the
   decompile⇒alter⇒compile route is live. `tools/disassemble_app.py` generates
   the full tree (every function decompiled + asm + indexes) under
   **`disassembled/` — gitignored, never publish**. ~~Next: find the eviction
   decision site~~ ✅ **DONE 2026-10-04** — found via the decompilation tree +
   `findva.py` (ch. 26).
4. ~~AC635N/BR23 JieLi SDK acquisition~~ ✅ `fw-AC63_BT_SDK` `cpu/br23` (ch. 24 §24.1);
   next: feasibility build of `apps/spp_and_le` for br23 with the Linux toolchain
   (`-mcpu=r3`, `ulimit -n 8192`).
5. ~~Route B (erased flash beyond `0xC8FE0`)~~ **deprioritized**: the JLFS entry list shows
   `0xC9000–0xFD000` is the VM region — writing there risks VM collisions (ch. 24 §24.6).
   SFCENC `UNENC_ADRH/L` unencrypted windows are the better hardware experiment.
6. "BT Int Mic" menu item exists in firmware but is untested on hardware.

When continuing this work, update `findings/18-open-questions-next-steps.md`, the
relevant chapter, and this section.
