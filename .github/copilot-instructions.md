# copilot-instructions.md — TIDRADIO H3 Plus Firmware RE

Instructions for AI coding agents working in this repository. Read this before making
changes. It is distilled from `README.md`, `ARTIFACTS.md`, `findings/` (36 files),
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
- **⚠️ ABSOLUTE RULE — THE STOCK UBOOT (flash `0x0000–0x4FFF`) MUST SURVIVE EVERY
  IMAGE WE BUILD OR FLASH.** Every image must contain the OEM uboot byte-identical to
  `Dumps/dump_pre_ch30.bin`, and no flash operation may ever write that region. The uboot
  is the ONLY way back into the chip: **PTT + 1 + power-on -> HID mode ->
  `python3 tools/jl_hidboot.py`** (findings/32 §32.10.2, hardware-verified restore) is the
  ultimate recovery fallback and works no matter which app — or no app — is installed.
  The H3+ cannot be opened, soldered, JTAGged or externally flashed: corrupting the uboot
  region = UNRECOVERABLE BRICK. Stage scripts and packagers must assert uboot-region
  equality with the stock dump before writing anything.
- All documentation, code, and analysis in this repo is AI-produced; the human runs
  tools, flashes the radio, and reports results. Keep that division: propose, don't flash.

## Repository layout

| Path | Contents |
|---|---|
| `findings/Findings.md` | **Index** of 35 numbered chapters; old §9A.x/§12A.x section numbers preserved inside chapters |
| `findings/08–13-*.md` | The Bluetooth effort (§9A.1–9A.50) |
| `findings/22-bluetooth-7-multipoint-architecture.md` | §9B: dual-device/multipoint analysis |
| `findings/23-bluetooth-8-bt-ptt2.md` | §9C: BT-PTT2 (BT mic on VFO B) — trampoline + code cave design, **hardware-confirmed 2026-09-30** |
| `findings/24-jieli-ecosystem-sdk-toolchain.md` | §24: SDK/toolchain/packager ecosystem — ufw table, SFCENC registers, stack 1拖2 multipoint, official-objdump validation, flash map |
| `findings/25-ghidra-decompile-compile-route.md` | §25: Ghidra 12 + ghidra-jieli decompile ⇒ compile route — headless import recipe, pointer-scan seeding, round-trip fixed-point proof, JieLi clang `-target pi32v2 -mcpu=r3 -Oz` |
| `findings/26-bluetooth-9-eviction-decision.md` | §26: the eviction decision located — app kick `0x01E5B22A` → controller-queue relay `0x01E22890`; multipoint options analysis |
| `findings/27-firmware-2slot-stack-controller-wall.md` | §27: 2-slot stack course-correction + the E1–E11 experiment log; **§27.19: NOP route exhausted, rollback to E7 prepared** |
| `findings/28-sdk-forks-survey.md` | §28: `fw-AC63_BT_SDK` fork survey for the SDK-rebuild route (12 forks, tree/API data); **§28.7: full git-history deep-dive — commit-level proof no fork touches the BT libs, Linux-build gotcha catalog, native-Linux `isd_download`, entry-point question answered** |
| `findings/29-static-analysis-reference-map.md` | §29: consolidated reference map — every SDK btstack/controller function VA, RAM structure, all patch sites (stock→patched + verdict) and wire-protocol facts from the E1–E11 hunt |
| `findings/30-two-device-plan.md` | §30: **PLAN OF RECORD** — goal = one SPP command device (TID-PTT) + one HFP audio device (Jabra) connected simultaneously, either order (two-SPP never intended); full-image clean-baseline reflash protocol, per-experiment recording discipline, M1–M4 stage ladder with six detailed cards per stage, fallbacks F1–F4; **§30.14.14–17: root causes — `0x1A5F1` is the stack's RE-PAGE MAILBOX (presst poisoned R1-e*/R2-a); E7-ref bisect CONFIRMED the 2-byte cmd-5 handle test (accessory-incumbent survival) itself freezes the app press flow ⇒ targeted-kill-on-manual-press DEAD on stock app; §30.14.17: STABLE press-free TWO-DEVICE state characterized on E7-ref (TID-PTT first, Jabra pages in at its own power-on; crippling = app audio routing bound to first device); §30.14.18–19: routing chain FULLY DECODED (classifier `0x01E7EC28` name-only via `DAT_0000bf4c`, sole caller btstack dispatcher case 7 name-result; teardown 0xF0 sentinel; connect-complete setup block + mode tbh @`0x01E61270`: mode 1 = NO-OP exit) ⇒ UNIFIED MODEL: incoming join never classifies (H-name) → mode-1 no-op = the crippling; fix candidate `--incoming-mode3`; **§30.14.20: P6 = PASS (Jabra-alone mic/RX fine), P7 exposed incoming-join accepted only ONCE per radio boot (stuck-record suspect); discriminator moot — fix must set the byte at tbh time; R3 BUILT 2026-11-02 (§30.14.21): `--incoming-mode3` implemented (tbh hook `0x01E61270` + 54 B cave `0x01EA77F6`, byte==1 && both conn records inused → byte:=3), objdump + both suites green; image `work/ch30_r3.bin` `d9c35315…` = E7-ref + sectors `0x066000`+`0x0AC000` only; stage `work/ch30_r3.sh` + card `work/ch30_r3c.sh`; **§30.14.22 field run: Jabra paged in (S1a PASS), but after the Jabra powered off a loud ECHO LOOP = TID-PTT mic broadcast on the radio speaker (teardown/restore gap after the forced bind) + RX back on speaker; **FULL VERDICT FAIL §30.14.23: both-up TX stayed TID-PTT mic + RX total silence ⇒ forced mode-3 binds nothing (no HFP/SCO to incoming device, H-noprofile leading); echo latched until reboot; **STATIC CORRECTION 2026-11-02 (§30.14.24): ch. 11 identities recovered (`0x50398`/`0x503CA` = local mic/speaker enablers, flags `0xB476`/`0xB477`) + tbh table off-by-one FIXED (indexed mode−1: mode1→`0x614A0`, mode3/5→`0x6128C` — state paths, not binds); R3 silence+echo explained (forced path + no incoming SCO). teardown dump §30.14.25: restores mic/speaker enables + routing byte but NOT the RX-source ⇒ echo latch root cause; **R4 STATIC 2026-11-03 (§30.14.26): outgoing connect = `user_send_cmd_prepare(1, 6, addr)` (START_CONNEC_VIA_ADDR) @`0x01E60114` — profiles/SCO ride on it; incoming joins never post it. R4 = replay cmd 1 at tbh hook `0x01E61270` (byte unchanged, far path avoided). **R4 BUILT + FLASHED + FIELD-FAILED 2026-11-03 (§30.14.27-28): `--incoming-hfp` = tbh hook + 58 B cave posting cmd 1 (START_CONNEC_VIA_ADDR) for the joining addr `[sp+20]` with routing byte UNCHANGED + cmd-1 `is_1t2` bail NOP `0x01E17A2A`; objdump + both suites green; image `work/ch30_r4.bin` `9168ac96…` = E7-ref + 3 sectors `0x01C000`+`0x066000`+`0x0AC000` (56 B). FIELD: Jabra paged in but TX stayed TID-PTT mic + RX SILENT — the replay fires (S4a SCO disturbance) but opens no HFP/SCO to an already-connected ACL (cmd 1 is a DIAL command; same-address guard `0x01E16824` no-ops it); echo at first RX after Jabra-off ⇒ worse than E7-ref. NEXT: R5 static — profile-start command family (far-path 12/14/18/74, NEVER 5) replayed at incoming tbh.** R5 BUILT 2026-11-03 (§30.14.29–32): kick+redial design — `--incoming-redial` = tbh hook `0x01E61270` + 174 B cave `0x01EA7722` (ends exactly `0x01EA77D0`): byte==1 && both conn records inused → copy joiner BD_ADDR `[sp+20]` byte-wise into re-dial mailbox `0x1A5F1` (ODD cell) + HCI-Disconnect the joiner (find-conn `0x01E17420` → `0x01E07B08(h,0x13)`); dispatcher epilogue `0x01E2232E`→`0x01E21E46` posts cmd 1 = radio-originated dial (E6/P6-proven); loop guard; teardown `0xF0`+match → byte:=3; NO cmd-1 bail NOP; objdump + both suites green (static legacy-window recognition states — `find_app_start` gates on DEFAULT `build_patches()`); image `work/ch30_r5.bin` `dc4b2704…` = E7-ref + sectors `0x066000`+`0x0AC000` (158 B); stage `work/ch30_r5.sh` + card `work/ch30_r5c.sh` ready. NEXT: user flashes + card; verdict §30.14.33 — **FIELD-FAILED 2026-11-03: two-device STABLE, ZERO freezes anywhere, but audio never bound to the Jabra (TX TID-PTT mic + RX silence — same signature as R3/R4); kick+redial firing UNCONFIRMED; R6 STATIC PASS DONE 2026-11-03 (§30.14.34): all three suspects CLEARED — slot reads correct, epilogue event-0→cmd-1 dial confirmed (vendor arm `0x21C3E` only writer, NO clear), find-conn walks both records ⇒ R5 kick+redial FIRED; wall = **app struct `0x102F0` never re-pointed on stack-originated redial**. **R6a BUILT 2026-11-04 (§30.14.35): `--redial-bind` = the ONE-byte cave change (cave +73 `0x41→0x44`, loop-guard RET→DONE stamps byte 3 at our redial's connect-complete); objdump + both suites green (new STATIC `inchrdlbind` recognition state); image `work/ch30_r6a.bin` `62214f14…` = E7-ref + sectors `0x066000`+`0x0AC000` (= R5 + 1 byte @ flash `0xAC76B`); stage `work/ch30_r6a.sh` + card `work/ch30_r6ac.sh` ready; **R6a FLASHED + FIELD-FAILED 2026-11-04 (§30.14.36): stamp EXECUTED (S1a redial delay + S3 CLEAN teardown, no echo unlike R5) yet audio never bound (TX radio mic, RX speaker — 4th identical signature) ⇒ byte-3 at redial connect-complete is a STATE path, not a bind; S5 repair press REGRESSION (kicks both, nothing reconnects) ⇒ R6a must not ship. Wall CONFIRMED = app current-device struct `0x102F0` (byte/command-level tbh tricks exhausted). Routes: R6b re-point design pass / SDK rebuild (ch. 28) / ch. 25 compile route. Radio on R6a `62214f14`; daily-use rollback recipe = 2 sectors `0x066000`+`0x0AC000` from E7-ref `90bec320`.** **R6b BUILT 2026-11-04 (§30.14.37–38): `--redial-current` = guard branch at cave +72 `70 41`→`10 52` → new 90 B CUR window @`0x01EA77D0` entered at OUR redial's connect-complete: zero re-dial mailbox `0x1A5F1` (fixes S5 regression + releases P7), write the STACK current-device record (BD_ADDR `0xBF41..46` + valid `b[0xBF3A]|=0x40`; `is_current_device` `0x01E184D6` — offsets corrected), post `user_send_cmd_prepare(6 = READ_REMOTE_NAME, 6, joiner)` → btstack dispatcher event 5 → classifier `0x01E7EC28` self-stamps routing byte 3 on the app's own classification path (tbh table off-by-one also corrected: mode−1 indexed, mode 3 → `0x61784`, tbh = enabler switch only). Objdump pixel-perfect + both suites green (new `inchrdlcur` states + `inchrdlcurcave` site); image `work/ch30_r6b.bin` `7f2af259…` = E7-ref + sectors `0x066000`+`0x0AC000` (237 B); stage `work/ch30_r6b.sh` + card `work/ch30_r6bc.sh` ready. **UNTESTED — if goal-miss again, byte/command-level tbh route DEAD for good ⇒ SDK rebuild (ch. 28) / ch. 25 compile route.** Radio still on R6a `62214f14`.** **R6b FLASHED + FIELD-FAILED 2026-11-04 (§30.14.39): flash clean; goal-miss = 5th identical signature (TX TID-PTT mic + RX silence; CUR firing unconfirmed, no redial delay heard) + NEW regressions: S4 press-FREEZE (E7-ref never froze), S5 both-kicked + TX completely dead, S3c no re-join (P7 self-heal dead). ⇒ BYTE/COMMAND-LEVEL tbh ROUTE DEAD FOR GOOD — the app audio bind needs the FULL app-originated connect flow (task-level state machine writing struct `0x102F0`); five levers exhausted (force byte 3 / replay cmd 1 / mailbox re-dial / stamp at redial-complete / current-device write + cmd 6 name replay). R6b must NOT ship. Radio on R6b `7f2af259`; daily-use rollback = 2 sectors `0x066000`+`0x0AC000` from E7-ref `90bec320` (no script). ESCALATION (user's choice): SDK rebuild ch. 28 / ch. 25 decompile⇒compile route / ESP32 combo device (single ACL presenting SPP+HFP = §9B.6.1-proven stock happy path).** **ROUTE CHOSEN = ch. 25 decompile⇒compile (§30.14.40). R7 BUILT 2026-11-04 (§30.14.41–42): Phase A DECODED THE BIND — tbh hook lives in the bt-task main loop `FUN_01e60e44`; event case `0xB` = bind block @`0x01E61292` (b[0xB4FA]:=120, addr copy `[sp+16]→[sp+12]`, free `[0x102F0+0x280]`, `is_current_device` abort-if-2, `b[0x10E00]&1` abort, state `|=5`, 500 ms timer, post stack cmd `0x1E`); poster lives in precompiled btstack. `--redial-bind2` = CUR window @`0x01EA77D0` with new tail: R6b prefix (mailbox zero + current-device write) then **byte:=3 + payload synth + direct `goto 0x01E61292`** = stock bind runs in-task. Objdump pixel-perfect + both suites green; image `work/ch30_r7.bin` `575e593d…` = E7-ref + sectors `0x066000`+`0x0AC000` (238 B); stage `work/ch30_r7.sh` + card `work/ch30_r7c.sh` ready. **UNTESTED — verdict §30.14.43; if goal-miss ⇒ in-image bind emulation dead ⇒ SDK rebuild (ch. 28).** **R7 FLASHED + FIELD-FAILED 2026-11-06 (§30.14.43): flash clean (first attempt stopped by the stage script's own stale 237 B assert — image innocent, script fixed); S1 GOAL FAIL — 6th identical signature (TX TID-PTT mic + RX silence; bind2 firing unconfirmed, no redial delay heard); S4 no freeze (R6b's press-freeze did NOT reproduce); S5 both-kick + TX-dead regression persists; S3c P7 self-heal dead. ⇒ IN-IMAGE BIND EMULATION DEAD — direct bind-block goto still goal-miss: the bind needs the app-originated dial flow setting struct `0x102F0` state BEFORE connect-complete (six levers exhausted). R7 must NOT ship. Radio on R7 `575e593d`; daily-use rollback = 2 sectors `0x066000`+`0x0AC000` from E7-ref `90bec320` (no script). NEXT: user picks final route — SDK rebuild (ch. 28) / ch. 25 deep rewrite / ESP32 combo device.** **R8 BUILT + STAGED 2026-11-10 (§§30.14.47–48): the app-slot swap — statics found app handle `_DAT_00010372` (0x102F0+0x82) written ONLY by the 0x3e connect-complete sink `FUN_01e5af40` (root cause of all 6 goal-misses); `--redial-appswap` = CUR window 106 B @`0x01EA77D0`: R6b prefix + `call 0x01E16E0E` live handle + guard + `h[0x10372]=r0` + R7 bind tail (goto re-encoded `fd ea 2c cd` — position-dependent catch); image `work/ch30_r8.bin` `4bb75a2c…` = E7-ref + sectors `0x066000`+`0x0AC000` (252 B), suites green + jl_sim window PASS lands exactly on the bind entry; stage `work/ch30_r8.sh` + card `work/ch30_r8c.sh` ready. **R8 FLASHED + FIELD-FAILED 2026-11-10 (§30.14.49): S0 clean; S1 join never landed yet TX TID-PTT mic + RX silent; S3a no echo (clean teardown); S3c P7 SELF-HEAL REVIVED (mailbox zeroing works) + the FIRST audio-state movement of the R-series — on rejoin the TX mic source followed the swap onto the Jabra path (SILENT: no live SCO) and RX fell back to the speaker; S4b transient menu-Connect stall (regression vs S1); S5 both-up = 7th identical goal-miss ⇒ IN-IMAGE BIND-EMULATION ROUTE CLOSED FOR GOOD (the wall is the app-originated HFP/SCO channel; seven levers exhausted). Radio currently on R8 `4bb75a2c…` — restore the S1 daily driver with `sudo bash work/ch32_bt_e7.sh`. ESCALATE: SDK rebuild (ch. 28) / compiled-C splice (ch. 35 §35.9) / ESP32 combo (§9B.6.1).** |
| `findings/31-bluetooth-10-connect-press-flow.md` | §31: R2 static analysis of the Connect-press flow (official-objdump-authoritative, 2026-10-28) — wait loops = *transitional*-link checks, freeze re-attributed to the same-address page guard `0x01E16824`; D1 = GO / D2 = NO-GO; corrections register vs §30.14.10 |
| `findings/32-sdk-rebuild.md` | §32: SDK-rebuild route (fw-AC63_BT_SDK fork) — P0 feasibility build PASSED, P1 SDK image flash-gate FIELD-PASSED (boots, `JL_SPP`, pairs); entry `0x1E00100`; §32.10: bootloader-entry incident + fw-Bootloader HID upgrade protocol CRACKED (`tools/jl_hidboot.py`, HW-verified restore); **§32.11: `tools/jl_rt_asm.py` BYTE-EXACT asm round-trip (disasm→editable asm→reassemble, fixed-point + byte-strict pinning) — Ghidra-C splice route DEAD (4 field-dead images), asm route HARDWARE-PROVEN 2026-11-09 (marker image PASS §32.11.7 = first successful source edit on chip)** |
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
  **Re-confirmed 2026-11-10 against the open oracle-verified table
  [`jvitkauskas/pi32v2-isa`](https://github.com/jvitkauskas/pi32v2-isa) (ch. 34): every
  H3+ patch-site encoding correct, 0 length mismatches over 327,211 decoded words;
  length rule = first word `<0xE000` → 2 B, `0xFF00–0xFFEF` → 6 B, else → 4 B.
  One spelling corrected: `00 23 80 00` (`--no-l2cap-disconnect` entry no-op) is
  `r0 = [sp+12]; rts` (early return, garbage r0 — callers ignore it), NOT
  `mov r0,#0; rts`; true `mov r0,#0; rts` = `40 20 80 00`.**
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
    [--no-pairing-kick] # NOP reason-0x16 pairing kick @0x01E21DE4 (disconnect-ALL loop) + @0x01E21EC4 (single) via thunk 0x01E19492; E7 field-FAILED 2026-10-09 for accessory incumbent (ch.27 §27.12/§27.13)
    [--no-cleanup-kick] # NOP the three remaining 0x13-capable wrapper callers @0x01E19AD0/0x01E19B14/0x01E20AB2; E8 HW 2026-10-19 PARTIAL SUCCESS — HCI-level eviction fully dead (ch.27 §27.14/§27.15)
    [--no-l2cap-teardown] # NOP the two user_send_cmd_prepare(0x4a) L2CAP-teardown posts @0x01E61E22 (Paired->Connect UI) / 0x01E60188 (mode setter); E9 field-FAILED 2026-10-20 (close persisted) (ch.27 §27.15/§27.16)
    [--no-spp-close]     # no-op spp_channel_disconnect() entry after push-rets @0x01E173EE (r0=0; pc=[sp++] -> return 0) — E10 field-FAILED 2026-10-20 (all-channel walk bypasses it) (ch.27 §27.16/§27.17)
    [--no-l2cap-disconnect] # NOP je r11,#0x4a dispatch branch @0x01E17974 + entry-no-op l2cap_disconnect() @0x01E173D0 (early return `r0=[sp+12]; rts` — r0 garbage, callers ignore; ch.34 correction); E11 HW 2026-10-20 EVICTOR DEAD — new walls = pairing lockup + single-SPP-session (ch.27 §27.17/§27.18)
    [--incoming-mode3] # R3 FIELD-FAILED: force routing byte 3 at incoming tbh (ch.30 §30.14.18-23)
    [--incoming-hfp]   # R4 FIELD-FAILED: replay user_send_cmd_prepare(1,6,joining-addr) at tbh hook 0x01E61270 + cmd-1 is_1t2 bail NOP 0x01E17A2A (ch.30 §30.14.26-28)
    [--incoming-redial] # R5 FIELD-FAILED (goal) 2026-11-03: at tbh hook 0x01E61270, byte==1 && 2 conn recs inused -> arm re-dial mailbox 0x1A5F1=joiner (byte-wise) + HCI-Disc the incoming ACL -> stack epilogue re-dials with profiles; teardown 0xF0+match -> byte:=3. Field: two-device STABLE, ZERO freezes, audio never bound to Jabra (ch.30 §30.14.29-33)
    [--redial-bind] # R6a FIELD-FAILED 2026-11-04: requires --incoming-redial; ONE cave byte (+73 0x41->0x44) retargets the loop-guard RET->DONE = stamps routing byte 3 at our redial's connect-complete. Field: stamp EXECUTED (clean teardown) but audio never bound (mode-3 = state path, not a bind); S5 repair-press regression (ch.30 SS30.14.35-36)
    [--redial-current] # R6b FIELD-FAILED 2026-11-04: requires --incoming-redial; exclusive --redial-bind/--d1-target-wait. Guard branch cave +72 70 41->10 52 -> 90 B CUR window @0x01EA77D0: zero mailbox 0x1A5F1 + write stack current-device record (0xBF41..46 + b[0xBF3A]|=0x40) + post cmd 6 READ_REMOTE_NAME -> classifier 0x01E7EC28 self-stamps byte 3. Field: 5th identical goal-miss + S4 press-freeze + S5 TX-dead => byte/command tbh route DEAD (ch.30 SS30.14.37-39)
    [--redial-bind2] # R7 FIELD-FAILED 2026-11-06: requires --incoming-redial; exclusive --redial-bind/--redial-current/--d1-target-wait. Same CUR window @0x01EA77D0, new tail: R6b prefix (zero mailbox + current-device write) then byte:=3 + synth [sp+12]/[sp+16] payload + DIRECT goto bind block 0x01E61292 (bt-task loop FUN_01e60e44 case 0xB; is_current_device gate satisfied by the write; block posts cmd 0x1E SCO start). Phase A decoded the bind (ch.30 SS30.14.41-42); image work/ch30_r7.bin 575e593d. Field (SS30.14.43): 6th identical goal-miss (TX TID-PTT mic + RX silence) + S5 both-kick/TX-dead regression persists => IN-IMAGE BIND EMULATION DEAD; must not ship
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

- **Before re-deriving anything:** check [findings/29](../findings/29-static-analysis-reference-map.md)
  first — it is the single lookup table of every SDK function VA, RAM structure and patch
  site already located (btstack/controller/app layers + wire facts).

- **Open ISA reference (2026-11-10, [findings/34](../findings/34-pi32v2-isa-open-reference.md)):**
  [`jvitkauskas/pi32v2-isa`](https://github.com/jvitkauskas/pi32v2-isa) is a CC0,
  oracle-verified pi32v2 table (1165 forms, 1079 hardware-confirmed on AC791N,
  `-mcpu=r3` — our CPU model). It resolves nearly all `???` entries of
  `tools/isa/pi32v2.md` (6-byte `FF00–FFEF` compare-branches, `if (...) {` blocks,
  hw `div.u/s.rrr`, 32-bit stack ld/st, SFR `rmw.*`, named DSP group). Cross-check
  with `python3 tools/isa_xcheck.py work/app_dec.bin`; decode the gaps with
  `tools/pi32dis.py --upstream=../pi32v2-isa` (additive fallback, marked `;upstream`).
  Caveat: hardware facts are AC791N, unmeasured on our BR23 die.

- **MANDATORY SECOND OPINION (user directive, 2026-11-10):** every NEW cave body,
  trampoline, patch encoding or hand-written instruction sequence must be verified
  against the upstream oracle table BEFORE flashing - run the bytes through
  `python3 -m pi32v2isa disasm <hex>` (or `tools/pi32dis.py --upstream=../pi32v2-isa`
  on a staged image) and confirm the decode matches intent, instruction lengths and
  re-entry alignment. Reason: our hand spec has ~23k-word decode gaps and 6-byte
  `FF00-FFEF` forms that desynced old listings and silently corrupted xref
  conclusions ([findings/34 SS34.2, SS34.12](../findings/34-pi32v2-isa-open-reference.md));
  a cave that lands on a form our table misses decodes as garbage in `work/full.lst`
   yet runs fine - only the upstream table shows the truth. Additionally run `tools/jl_sim.py` pre-flash on every cave - `--patch VA:HEX` overlay + `--expect rN=VAL` assertions execute the patched code on the AC791N hardware-fitted CPU model (ch. 35; sim PASS = logic evidence, flashing stays the final authority) - and, once the pinned toolchain is fetched (`tools/jl_oracle.py fetch`), `tools/jl_oracle.py site VA:HEX` for the JieLi-authority decode/length/re-entry verdict ([findings/35](../findings/35-pre-flash-simulation-and-pinned-oracle.md)).

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

- **Write findings down IMMEDIATELY (user directive, 2026-10-29).** The moment anything
  is discovered, executed, or created, record it in the findings documents — do not
  batch documentation to the end of a session. Analysis results → the relevant chapter
  (new §number as needed); builds/flashes/experiment runs → the ch. 30 ledger + the
  chapter under test; tool changes → `tools/Tools.md` + `findings/17`. The repo is the
  durable memory: any interruption must leave it current enough to recover from.
- **Use `replace_string_in_file` / `multi_replace_string_in_file` for `.md` edits.**
  `insert_edit_into_file` has silently no-opped twice on `Findings.md` in this repo.
- **NEVER open a CRLF file with `newline="\r\n"` and write it back the same way**
  (incident 2026-11-03: this appended a stray `\r` to every line on each write and
  eventually duplicated whole sections of this file). Correct pattern: read and write
  with `newline=""` (no translation), or restore from git and re-apply edits.
- Keep chapter cross-references as relative links with correct GitHub anchor slugs;
  when renaming a heading, update every link to it.
- Documentation voice: factual, evidence-first. Mark UNTESTED claims explicitly.
  Distinguish "statically inferred" from "hardware-confirmed".
- New tools: Python stdlib-first, SPDX MIT header after the docstring, document in
  `tools/Tools.md` (TOC + section) AND the table in `findings/17-tooling-index.md`.
- Never run `git push`, flashing commands, or destructive disk operations autonomously.
  Flashing is the user's action; print the exact `jl-uboot-tool` commands instead
  (`--sectors` route preferred; always `read` back and compare after `write`).
  **Sector-level writes additionally verify the whole starting point:** after writing,
  `read 0x00000000 0x100000` and byte-compare the strict region `0x0000–0x0C8FDF`
  (bootloader + app) against the expected image — excluding the 32 device-specific
  bytes @`0x0C8FE0` and the VM/metadata region @`0x0C9000+` (pairing data legitimately
  differs). Any mismatch outside those is a STOP (see `findings/30` §30.3).
  **And remember the absolute rule above: the stock uboot `0x0000-0x4FFF` must be
  present in every image — `tools/jl_hidboot.py` (PTT+1+power-on HID) is the ultimate
  fallback and only exists while that region is intact.**
- **Never produce rollback material of any kind (user directives 2026-11-03 + 2026-11-11).**
  No `*rb.sh` rollback scripts, and — new 2026-11-11 — do not even record rollback
  **recipes** in findings or reply text: the user restores or builds any image they want
  themselves. Omit rollback sections entirely; spend the effort on the experiment instead.

## Current state & open frontiers (as of 2026-11-10)

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
kick-NOP experiment + options analysis in ch. 26 §26.7 · **open ISA reference adopted
2026-11-10** (ch. 34): [`jvitkauskas/pi32v2-isa`](https://github.com/jvitkauskas/pi32v2-isa)
CC0 oracle-verified table cross-checked against all our hand encodings (0 length
mismatches over 327,211 words; one `00 23` spelling corrected) + new
`tools/isa_xcheck.py` + `pi32dis.py --upstream` gap fallback; its LLVM fork
(`pi32v2-llvm`, releases `pi32v2-23.1.5-5`, reads JieLi LLVM-4 bitcode 4898/4900)
supercharges the ch. 25 compile route and ch. 28 SDK rebuild.

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
   **E6 FIELD OBSERVATIONS + E7 SHIPPED 2026-10-09 (ch. 27 §27.12):** user
   reports (a) mic audio on the headset speakers during BT-PTT TX = the SCO
   downlink is live in the 2-link state (first HFP-audio evidence in
   multipoint), (b) pairing mode / Connect-on-new-device **still kicks** the
   incumbent — a THIRD executor: reason-`0x16` disconnect-ALL in stack
   dispatcher `0x01E21AF8` (sites `0x01E21DE4` loop + `0x01E21EC4` single,
   both via thunk `0x01E19492` → wrapper `0x01E07B08`; E6 only NOP'd the
   `0x13` one), and (c) power-cycle reconnects the last device = expected
   single-device reconnect flow (struct `0x102F0`). Shipped
   `--no-pairing-kick` (8-byte NOP, both sites; suites green); E7 image
   `work/e7_twodev.bin` = E6 + NOPs — one sector write @flash `0x026000`,
   pairings survive. **E7 FIELD TEST 2026-10-09: FAILED for the accessory-incumbent
   case (ch. 27 §27.13)** — with the TID-PTT button as incumbent, Paired→Jabra→Connect
   still kicks it instantly, while the same flow with a **PC** incumbent stays clean
   (E6): the surviving kick is **device-class-dependent** through an executor NOT yet
   located (all known `0x13`/`0x16`/kick sites NOP'd or action-gated; `0x01E20AB2` and
   the `FUN_01e1792e` jumptable probes negative). `0x026000` flash readback pending.
   Also confirmed from the field: **SCO stays open after BT-PTT release** (radio-mic
   sidetone to the headset; press → headset mic = BT-PTT working) = first end-to-end
   HFP-audio-in-multipoint evidence; **Pairable is gated while connected**; **Delete
   leaves the link up** (our NOPs) and wedges pairing until power-cycle. Multipoint
   stands as **confirmed with a PC-class incumbent only**. **NEXT:** readback, then
   V2a (PC incumbent + Jabra Connect regression) and V2b (PC incumbent + TID-PTT
   Connect under `btmon -w`) to pin the kick's reason code; a third ACL stays
   impossible (2-slot pools).
   **V2b RUN + E8 SHIPPED 2026-10-19 (ch. 27 §27.14):** readback **clean**; V2b evicted the
   **PC** (graceful L2CAP + HCI `0x13`) when the accessory was the connect target → shipped
   `--no-cleanup-kick` (NOPs the three remaining 0x13-capable wrapper callers
   `0x01E19AD0`/`0x01E19B14`/`0x01E20AB2`; E8 image = two sectors `0x01E000`+`0x025000`).
   **E8 HW-TESTED 2026-10-19: PARTIAL SUCCESS (ch. 27 §27.15)** — behavior changed exactly as
   designed: the radio sent **no HCI Disconnect at all** (PC bluetoothd dropped the ACL
   locally, 0x16/MGMT 0x02, after the radio closed only the RFCOMM channel: L2CAP
   Disconnection Request ident 17 DCID 64 SCID 67). HCI-level eviction fully dead. Closer =
   app **L2CAP channel-close** `user_send_cmd_prepare(0x4a)` = `l2cap_disconnect_all_channel()`
   (`l2cap_run` state `0xd` sends the L2CAP Disconnect Request), posted **unconditionally** by
   the Paired→Connect UI `0x01E61E22` + routing-mode setter `0x01E60188`; **no class check
   exists** — the class-dependence was a flow artifact (fresh-pairing posts no `0x4a`; PC
   keeps the ACL on a channel-only close; SPP-only accessories drop their ACL instantly).
   **E9 SHIPPED as `--no-l2cap-teardown`** (NOPs both posters; 8 bytes; two sectors
   `0x065000`+`0x066000`; pairings survive; suites green, all twelve sites verified).
   **NEXT: E9 HW test** T1 = repeat V2b under btmon (expect NO L2CAP Disconnection Request,
   PC alive; watch whether the TID-PTT SPP binds — single-SPP-session `0x1A740` = candidate
   next wall) + T2 (E7 scenario); E10 fallback = je-NOP dispatcher branch `0x01E17974`.
   **E9 HW-TESTED 2026-10-20: FAILED (ch. 27 §27.16)** — with both `0x4a` posters NOP'd
   (readback-verified) the radio still sent the L2CAP Disconnection Request identically
   (ident 20, DCID 64, SCID 69; closing channel SPP-confirmed). **Closer root-caused:**
   `spp_channel_disconnect()` `0x01E173EC` (SPP control block `0x1A740`, live CID `[cb+2]`
   → `l2cap_disconnect` `0x01E173D0` → state `0xd` → `l2cap_run`) — reached press-time via
   the `spp_connect` **single-SPP-session chokepoint** (`0x01E1750c`, busy-path `0x01E1751E`:
   close incumbent, return −2, retry) + the `0xB` DISCONN_SDP_MASTER path
   (`0x01E20BD2`/`0x01E20E92` → `FUN_01e21af8` case `0xB` → `0x01E1786C`). The dependence is
   on target **profile**, not class (SPP targets close the incumbent's SPP channel; HFP never
   touches it — E6); `0x4a` was a co-actor. **E10 SHIPPED as `--no-spp-close`** (entry no-op
   `r0=0; pc=[sp++]` @`0x01E173EE` (after `push rets` -> return 0); 4 bytes; **ONE sector `0x01C000`**; pairings survive;
   suites green, all thirteen sites verified). **NEXT: E10 HW test** T1 = repeat V2b under
   btmon (expect NO L2CAP Disconnection Request, PC alive; TID-PTT SPP bind = candidate next
   wall, single-SPP-session `0x1A740`); E11 fallback = NOP the 4 SPP-SM `FUN_01e173d0` calls
   (`0x01E235B8`/`0x01E2376A`/`0x01E23A50`/`0x01E23BF4`) or the `l2cap_disconnect` entry.
   **E10 HW-TESTED 2026-10-20: FAILED (ch. 27 §27.17)** — with `spp_channel_disconnect` NOP'd
   (readback-verified) the radio still closed the PC link with **TWO** L2CAP Disconnection
   Requests (idents 6/7, CIDs 65/64) = the `l2cap_disconnect_all_channel` walk bypassing the
   SPP primitive; E9 had only NOP'd the two `0x4a` posters, not the dispatcher branch
   `0x01E17974` nor the four direct `l2cap_disconnect` callers. (TID-PTT did pair+join but its
   key-presses never arrived = the single-SPP-session wall `0x1A740` already visible.)
   **E11 SHIPPED as `--no-l2cap-disconnect`** (NOP je-branch `0x01E17974` + entry-no-op
   `l2cap_disconnect()` `0x01E173D0` `r0=[sp+12]; rts` early return (r0 garbage, callers ignore — ch. 34 correction); 8 bytes; **ONE sector `0x01C000`**;
   pairings survive; suites green, all fifteen sites verified). **NEXT: E11 HW test** T1 =
   repeat V2b under btmon (expect NO L2CAP Disconnection Request at all, PC alive; TID-PTT
   SPP bind = candidate next wall); E12 fallback = gate the `l2cap_run` state-`0xd` send.
   **E11 HW-TESTED 2026-10-20: THE EVICTOR IS DEAD (ch. 27 §27.18)** — full-capture btmon
   shows **zero** radio-originated L2CAP Disconnection Requests and zero HCI Disconnects;
   the PC held its SPP session through an accessory pairing attempt for the first time (only
   teardown = power-cycle 0x08 timeout). Two NEW architectural walls: (1) pairing an SPP
   accessory while the PC holds SPP now **locks the radio up** (the app's connect flow waits
   on the blocked channel-close completion); (2) with two SPP devices connected, PC frames
   come back **echoed verbatim, no keying**, and the button's events don't key either —
   single SPP session `0x1A740` (last-connection-wins) vs current-device command routing
   (struct `0x102F0`). NOPs cannot fix this layer; **E12 deprioritized**. Remaining routes
   for two-SPP: code-cave SPP multi-session rewrite (ch. 23 cave + ch. 25 compile route),
   SDK rebuild, or the ESP32 combo-device workaround. **E11 FOLLOW-UPS 2026-10-20 late
   (ch. 27 §27.19): the Connect-press deadlock is GENERIC** (HFP/Jabra target deadlocks
   the app task too whenever a live SPP session exists — stack task alive, app wedged);
   sequential pairing avoids the lockup **but E11 corrupts normal operation from the
   first connect** (doubled `+SPP` echo, zero `AT+MPTT`, button keys nothing; reboot +
   re-pair no help). **Verdict: blocking closes → deadlock, allowing closes → eviction —
   NOP route EXHAUSTED, E12 deprioritized. Rollback to E7 prepared** (`work/e7rb_*.bin`;
   E11→E7 = 32 B across five sectors `0x01C000`/`0x01E000`/`0x025000`/`0x065000`/`0x066000`).
   Two-SPP = **rewrite** routes only: code-cave SPP multi-session (ch. 23/25), SDK rebuild
   (fork survey done, ch. 28), ESP32 combo device.
   **Ch. 30 R-series (2026-10-26/29):** F3-v3 = known-best base (full-image sha
   `1a1eaca1`); R1-a/b/c all field-FAILED with the identical Connect freeze;
   **R2 static analysis DONE 2026-10-28 → [Ch. 31](../findings/31-bluetooth-10-connect-press-flow.md):**
   the freeze is the **same-address page guard** `0x01E16824` (call @`0x01E21E76`), not an
   any-link wait (the loops read *transitional* controller links); press = settings handler
   `FUN_01e6ec9e`, cmd-5 post `call 0x01E1792E` @`0x01E6ECDA`; D1 = GO (optional R1-f),
   D2 = NO-GO. The **R1-e design** (press-store + target-aware cmd-5 kill on F3-v3) is
   specified in ch. 30 §30.14.11 — `--cmd5-target` implemented 2026-10-30, **R1-e/e2/e3
   all FIELD-FAILED** (hard freeze; async-kill-race model busted as sole cause; BISECT
   §30.14.12: **F3-v3 itself freezes on the Connect press** ⇒ R1-e innocent of the freeze;
   freeze onset correlates 1:1 with blocking channel closes across the E/F series).
   **R2-a = E7 recipe + `--cmd5-target --d1-target-wait`: FIELD-FAILED** (froze on every
   press; root cause `0x0001A5F1` = btstack dispatcher RE-PAGE MAILBOX poisoned by the
   presst cave). **R2-b = E7 + `--cmd5-handle` only: FIELD-FAILED** (same freeze). **BYTE
   PROOF + BISECT VERDICT 2026-11-01 (§30.14.15-16): `work/ch30_e7ref.bin` (`90bec320…`) =
   exact E7 rebuild, never freezes, press = stock kick ⇒ incumbent SURVIVAL under cmd 5
   for mask==0 accessory records itself deadlocks the app press flow — targeted-kill-on-
   manual-press DEAD on the stock app.** **§30.14.17: STABLE press-free TWO-DEVICE state
   on E7-ref** (TID-PTT first, Jabra pages in at its own power-on; crippling = app audio
   routing bound to first device). **§30.14.18-19: routing chain FULLY DECODED**
   (classifier `0x01E7EC28` name-only; teardown 0xF0 sentinel; connect-complete mode tbh
   @`0x01E61270` mode-1 NO-OP = the crippling). **§30.14.20: P6 PASS (Jabra-alone audio
   healthy); P7 incoming join accepted only ONCE per radio boot.** **R3
   `--incoming-mode3` BUILT + FLASHED + FIELD-FAILED 2026-11-02 (§30.14.21-25)** (forced
   mode-3 binds nothing — no HFP/SCO to incoming device; echo latched until reboot;
   teardown restores mic/speaker enables but NOT the RX-source). **§30.14.24 static
   correction: ch. 11 identities recovered (`0x50398`/`0x503CA` = local mic/speaker
   enablers, flags `0xB476`/`0xB477`) + tbh table off-by-one FIXED (mode1→`0x614A0`,
   mode3/5→`0x6128C` — state paths, not binds).** **R4 STATIC 2026-11-03 (§30.14.26):
   outgoing connect = `user_send_cmd_prepare(1, 6, addr)` (START_CONNEC_VIA_ADDR)
   @`0x01E60114` — profiles/SCO ride on it; incoming joins never post it.**
   **R4 BUILT + FLASHED + FIELD-FAILED 2026-11-03 (§30.14.27-28): `--incoming-hfp` = tbh
   hook `0x01E61270` + 58 B cave `0x01EA77F6` posting cmd 1 for the joining addr `[sp+20]`
   (routing byte UNCHANGED) + cmd-1 `is_1t2` bail NOP `0x01E17A2A`; image `work/ch30_r4.bin`
   `9168ac96…` = E7-ref + 3 sectors `0x01C000`+`0x066000`+`0x0AC000` (56 B). FIELD: Jabra
   paged in but TX stayed TID-PTT mic + RX SILENT — the replay fires (S4a SCO disturbance
   with incumbent) but opens no HFP/SCO to an already-connected ACL (cmd 1 is a DIAL
   command; same-address guard `0x01E16824` no-ops it); echo at first RX after Jabra-off ⇒
   worse than E7-ref. NEXT: R5 static — profile-start command family (far-path 12/14/18/74,
   NEVER 5) replayed at incoming tbh.** **R5 BUILT 2026-11-03 (§30.14.29–32): the
   kick+redial route — static rounds located the stack re-dial mailbox `0x1A5F1` (ODD,
   byte-wise) folded by dispatcher epilogue `0x01E2232E` → cmd 1 at `0x01E21E46`;
   `--incoming-redial` = tbh hook `0x01E61270` + 174 B cave `0x01EA7722` (ends exactly
   `0x01EA77D0`): arm mailbox with the joiner's BD_ADDR + HCI-Disconnect the incoming
   ACL → stack re-dials it = radio-originated dial, the E6/P6-proven profile path; loop
   guard + teardown `0xF0`+match → byte:=3; NO cmd-1 bail NOP; objdump + both suites green;
   image `work/ch30_r5.bin` `dc4b2704…` = E7-ref + sectors `0x066000`+`0x0AC000`
   (158 B); stage `work/ch30_r5.sh` + card `work/ch30_r5c.sh` ready (no rollback script
   per directive 2026-11-03 — recipe: 2 sectors from E7-ref). FLASHED 2026-11-03; card run —
   + card; verdict §30.14.33.** **R6a `--redial-bind` BUILT + FLASHED + FIELD-FAILED 2026-11-04 (§30.14.35–36): stamp EXECUTED (clean teardown, no echo) yet audio never bound — mode-3 at redial connect-complete is a state path, not a bind; S5 repair-press regression ⇒ R6a must not ship. Wall CONFIRMED = app current-device struct `0x102F0`.** **R6b `--redial-current` BUILT 2026-11-04 (§30.14.37–38): at OUR redial's connect-complete, branch to a 90 B CUR window @`0x01EA77D0` — zero re-dial mailbox, write the stack current-device record (`0xBF41..46` + `b[0xBF3A]|=0x40`), post cmd 6 READ_REMOTE_NAME → classifier `0x01E7EC28` self-stamps byte 3; objdump + both suites green; image `work/ch30_r6b.bin` `7f2af259…` = E7-ref + sectors `0x066000`+`0x0AC000` (237 B); stage `work/ch30_r6b.sh` + card `work/ch30_r6bc.sh` ready; **R6b FLASHED + FIELD-FAILED 2026-11-04 (§30.14.39): 5th identical goal-miss signature (TX TID-PTT mic + RX silence; CUR firing unconfirmed, P7 self-heal dead) + NEW regressions S4 menu-Connect freeze + S5 repair-press TX-dead ⇒ R6b must not ship; byte/command-level tbh route DEAD FOR GOOD (five levers exhausted — app bind needs the full app-originated connect flow writing struct `0x102F0`). NEXT = user's escalation choice: SDK rebuild (ch. 28) / ch. 25 decompile⇒compile route / ESP32 combo device.** **ROUTE CHOSEN = ch. 25 decompile⇒compile (§30.14.40). R7 BUILT + STAGED 2026-11-04 (§30.14.41–42): Phase A decoded the bind — bt-task main loop `FUN_01e60e44`, event case `0xB` = bind block @`0x01E61292` (`is_current_device` gate + state `|=5` + cmd `0x1E` SCO start; poster in precompiled btstack); `--redial-bind2` = CUR window @`0x01EA77D0`, R6b prefix then byte:=3 + payload synth + DIRECT `goto 0x01E61292` (stock bind runs in-task); objdump pixel-perfect + both suites green; image `work/ch30_r7.bin` `575e593d…` = E7-ref + sectors `0x066000`+`0x0AC000` (238 B); stage `work/ch30_r7.sh` + card `work/ch30_r7c.sh`. UNTESTED — verdict §30.14.43; if goal-miss ⇒ in-image bind emulation dead ⇒ SDK rebuild (ch. 28).** **R7 FLASHED + FIELD-FAILED 2026-11-06 (§30.14.43): flash clean (after fixing the stage script's stale 237 B assert — image innocent); S1 GOAL FAIL — 6th identical signature (TX TID-PTT mic + RX silence; bind2 firing unconfirmed); S4 no freeze (R6b's did not reproduce) but S5 both-kick + TX-dead regression persists; S3c P7 self-heal dead. ⇒ IN-IMAGE BIND EMULATION DEAD — the bind needs the app-originated dial flow setting struct `0x102F0` state before connect-complete; six levers exhausted. R7 must not ship.** Radio currently on **`work/ch30_r8.bin` `4bb75a2c…`** (R8 field card 2026-11-10 late — §30.14.49 GOAL FAIL, restore S1 via `sudo bash work/ch32_bt_e7.sh`; earlier same day on **`work/ch33_p9.bin` `6c9c94218e4b3385`** (ch. 33 P9 = S1 + dial-eviction NOPs — FIELD-FAILED 2026-11-10: menu Connect locks the radio with a link up, the NOPped posts are load-bearing; restore S1 via `sudo bash work/ch32_bt_e7.sh`, Card P10 = findings/33 §33.9). S1 was **`work/ch32_bt_e7.bin` `d7a29a3eaeffbe67`** ( clean stock v1.0.50 via the asm route + FULL E7 feature set (`--bt 4 --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT` + kick-NOPs + conn-num=2, 172 B / 13 sectors) + `-BT` postfix — FIELD-PASSED 2026-11-10: boots, BT-PTT, two-device stable (Jabra joins, both stay connected), BT-PTT2 works; RX audio still bound to first device = the S2 target; daily-driver rollback = sectors from E7-ref `90bec320`). Ch. 32: P0 build PASSED, P1 SDK image FIELD-PASSED, HID re-flash path hardware-verified; **Ghidra-C splice route DEAD (P2/P2b/P2c/P2d all field-DEAD, §32.6)**; **BYTE-EXACT ASM ROUND-TRIP ROUTE HARDWARE-PROVEN 2026-11-09** (`tools/jl_rt_asm.py`; e7ref lossless §32.11.5, marker edit PASS §32.11.7 — 10-byte string edit, boots, all functions normal). **NEXT: user directs development on the asm route.**
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
