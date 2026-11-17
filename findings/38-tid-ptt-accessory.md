# 38. The TID-PTT accessory — make it PAGE (route chosen 2026-11-15)

> Goal context: two-device project (ch. 30). The radio-side bind route is CLOSED
> (§37.17/§37.19: 12 levers, in-image bind emulation dead). Field intel (§37.19) shows
> the ONLY missing piece for the goal is the **TID-PTT's join direction**: the radio
> dials its single remembered device; the Jabra pages actively (radio always accepts,
> P7 once/boot); the TID-PTT **never pages** — it is a pure peripheral. If the PTT paged
> the radio when disconnected, then: radio remembers the **Jabra** → audio binds
> natively (P6) → PTT pages in as an incoming joiner → does NOT steal the current-device
> slot (proven: incoming joins keep the binding, §37.19) → gets the free single-SPP
> session (`0x1A740`, Jabra uses no SPP) → BT-PTT keys (SPP command path is
> device-agnostic, ch. 22 §9B). Every link proven except the PTT initiating.
> **USER DECISION 2026-11-15: TID-PTT-side patch** (over ESP32 combo §9B.6.1 / stop at S1).

## 38.1 Device behavioral spec (user field observations, 2026-11-15)

- Commercial **TIDRADIO** accessory; single button (the PTT button). Not opened;
  chipset unknown (model label / FCC ID pending).
- OFF state: hold button ≥1 s → powers ON and enters discoverable/pairing state —
  LED blinks **red-green-red-green…**
- When paired+connected: button press = TX (hold = longer TX). No speaker observed
  (button-only SPP device; delivers `+SPP=P`/`+SPP=R` NUL-terminated over RFCOMM
  channel 2 to the radio — wire facts ch. 22/29).
- Link lost (radio kicked/off/range) → returns to the red-green blink state.
  Hold ≥3 s → powers OFF.
- **Never joins while the radio is committed to another device** (§37.19): it does not
  page its remembered host; it only waits in scan. Radio-originated dial is the only
  join path today.
- Battery/charge port type: unknown (pending user photo).

## 38.2 Identification plan (before any patch decision)

1. **BT recon** (Linux/BlueZ dongle — machine currently has none attached):
   `bash work/ch38_ptt_recon.sh` with the PTT in red-green blink and the RADIO OFF.
   Captures: BD_ADDR **OUI (chip vendor!)**, device name, Class of Device, SDP service
   records (SPP/HID/AVDTP fingerprints), and a LE scan for OTA services
   (`JL_OTA`/`AC63`/`AB` advertising = vendor smoking guns).
2. **Physical**: label photo (model + FCC ID), port types. FCC ID → public filings
   (internal photos + chip part numbers).
3. Cross-check OUI/name against known BT-remote chip vendors:
   - **JieLi (AC63xx/BR23 family)** — BEST CASE: same family as the H3+ itself.
     `fw-AC63_BT_SDK` (`apps/` include BT-remote/PTT-style demos, ch. 24/28) gives
     SOURCE for exactly this app class; the paging behavior lives in the app layer
     (`bt_tws`/`user` connect logic). Flash path: JieLi USB **HID boot** — the same
     protocol we cracked for the H3+ (`tools/jl_hidboot.py`, ch. 32 §32.10) works on
     AC63-family parts if the device exposes a USB data port and a boot entry combo.
   - **Bluetrum AB137x** — common in cheap BT PTT/audio peripherals; flashing needs a
     hardware programmer and Windows-only tooling; SDK not cleanly open → hard.
   - Bestechnic / Airoha / other → hard, likely stop.
4. If JieLi: dump the PTT firmware (read-protect status unknown), locate the
   connect/reconnect policy, and patch/add "page remembered host when idle" —
   same toolchain as this repo (pi32v2 disasm/sim/oracle apply to AC63 too, with
   core caveats: AC63 = pi32v2 like BR23 ✔).

## 38.3 Risk + ownership note

This is the user's commercial accessory; a flash can brick it (recovery unknown until
dump/read-protect status is known). Propose, don't flash — same division as the radio.
The radio itself needs NO further patch for this route beyond S1 (it already accepts
incoming joins and gives the joiner the free SPP session — §37.19 chain).

## 38.4 Recon log — PENDING

- [ ] BT recon run (`work/logs/ch38_ptt_recon_*.log`) → OUI/name/CoD/SDP/LE
- [ ] Label/FCC photo → model + filings
- [ ] Chipset verdict + patchability route
- [ ] If JieLi: firmware dump + connect-policy location

## §38.5 Recon round 1 results (2026-11-15 20:38, log work/logs/ch38_ptt_recon_20261115_203832.log)

Dongle plugged in (Controller 90:DE:80:55:E3:A6 "TID-PTT-PC"). PTT found in pairing blink:

| Addr | Name | Mode | Details |
|---|---|---|---|
| `6F:E5:E7:FB:12:4F` | **TID-PTT0cd28a-B** | BR/EDR | CoD 0x00240404 (audio-video/headset), SDP UUIDs **SPP (1101) + Handsfree (111e)** — HF-role combo peripheral; **Paired/Bonded with this PC** (earlier experiments); RSSI −56 |
| `6F:E5:E7:BC:39:37` | TIDRADIO PTT0cd28a-A | LE | flags 06, vendor UUID 0000ff00 |

Radio itself seen as `0B:FF:59:E8:85:92` "TD-H3-Plus-3511" (+ `TD-H3-Plus-3511(BLE)` 0B:FF:59:9E:37:81, UUIDs ae00/ae30/af00/af30/ff00, Modalias v05D6). Noise: moto g77, TV, three fcf1 adverts (random).

**Dump cross-check (Dumps/dump_pre_ch30.bin, read-only python):**
- Radio BD_ADDR confirmed at **BTIF 0xFD004** (stored LE) = `0B:FF:59:E8:85:92`.
- **PTT-B address found at VM 0xC95DD (LE)** — the radio's own pairing record predates this whole project ⇒ the PTT BD_ADDR is **stable** (identical in today's scan) and the pair was factory/existing. The address the mirror plan needs to page = `0B:FF:59:E8:85:92`; the address the PTT must answer to = its fixed `6F:E5:E7:FB:12:4F`.
- `0cd28a` (name token) is not a MAC byte anywhere in the dump ⇒ serial-like token, not an OUI hint.
- OUI verdict: **both** devices use locally-administered address ranges (bit1 of first octet set) ⇒ no IEEE vendor identification possible; the house style matches the radio's own JieLi BR23 (also locally administered).

**Profile insight:** the PTT presents **SPP + HFP(HF role)** — the same combo the §9B.6.1 proof-of-concept used, and exactly what the radio drives as AG/dialer. SDP browse of PTT-B was cut off in round 1 (dongle removed before the follow-up); re-run pending.

**dmesg note (user, 2026-11-15):** plugging the RADIO by USB in OFF/ON/boot states ⇒ repeated `device descriptor read/64, error -71` (EPROTO), no enumeration. EXPECTED and harmless: the normal app never brings up USB device mode — only HID downloader mode (PTT+1+power-on) enumerates, as **4C4A:4155 ("JLAU")** per `tools/jl_hidboot.py`. (Device identity of that paste assumed = radio; confirm.)

**JieLi presence probe for the PTT (next hardware step):** with the PTT powered OFF, hold its button and plug USB into the PC; watch `sudo dmesg -W` / `lsusb | grep -i 4c4a` — a `4c4a:4155` HID device (or any new hidraw) = JieLi USB-boot alive ⇒ dump route via `tools/jl_hidboot.py` opens (same as radio, ch. 32 §32.10). No enumeration at all = charge-only port or non-JieLi (still not conclusive — try button-held variants: PTT+power, 3 s hold, plug-then-hold).

## §38.4 checklist (updated 2026-11-15 late)
- [x] Recon round 1 run — PTT identified (§38.5)
- [ ] PTT label photo (model + FCC ID) + port inventory (USB-C? pogo?)
- [ ] JieLi USB-boot probe on the PTT (§38.5 procedure)
- [ ] Dongle re-plug: full SDP browse of `6F:E5:E7:FB:12:4F` (round-1 browse cut off)
- [ ] Chipset verdict → branch
- [ ] If JieLi: dump via HID boot (user action) → statics → connect-policy patch design

## §38.6 Round 2 + USB/label probes (2026-11-15 late evening)

**Recon round 2** (log work/logs/ch38_ptt_recon_20261115_221703.log): same picture — PTT-B `6F:E5:E7:FB:12:4F` visible (RSSI −44…−56), NEW: **LegacyPairing: yes** (pre-LE-SC BR/EDR stack — consistent with JieLi/Bluetrum-era firmware). `sdptool browse` of the PTT returns immediately empty (also later with an explicit `hcitool cc` page: **Host is down** — the PTT does not answer pages from the PC once idle; blink state required for any active probe).

**USB-boot probe on the PTT (user):** hold-button + plug variants → dmesg shows only attach chatter `error -71` (EPROTO), never a descriptor, never `4c4a:4155`. One `new full-speed device` entry proves D+ pull-up exists (data lines wired) but the firmware never enumerates ⇒ **no reachable USB-boot/HID mode** — the JieLi-HID dump route used on the radio is NOT available on the PTT as-is. If it is JieLi, the realistic access is **UART pads inside the puck** (AC63 UART update protocol, TTL adapter).

**Label/physical (user):** square button puck, no text except "PTT", one USB port (charging). No FCC ID ⇒ filings route dead.

**Tooling on this machine:** gatttool, btmon, sdptool, rfcomm, hcitool all present (BlueZ 5.85). bluetoothctl 5.85 has no `--device` option; device-menu syntax differs — active GATT goes through gatttool instead.

**Next hardware round — `work/ch38b_ptt_probe.sh` (sudo, dongle in, radio OFF, PTT kept blinking):**
1. btmon raw adverts (full AD structures — any manufacturer-data company ID);
2. gatttool primary+characteristics of the LE side (service/char UUID pattern = SDK fingerprint);
3. hcitool cc + full sdptool browse (vendor strings, real SPP/HFP channel numbers);
4. HFP AT probe with the PC as AG — includes **AT+JLRHI=? / AT+JLDP=? = direct JieLi vendor-command tells**;
5. SPP capture — records what the PTT *sends* when its button is pressed (first-ever look at the PTT→radio wire protocol from the other side; also feeds the ESP32-combo fallback design if that route is ever taken).
PTT accepts one link at a time → sections sequential; re-blink between them.

## §38.4 checklist (updated again)
- [x] Recon rounds 1+2 — identities stable, LegacyPairing noted
- [x] Label photo — moot (no markings); ports = charge-only USB, no data mode
- [x] JieLi USB-boot probe — NEGATIVE (no enumeration in any button/plug variant)
- [ ] Round 3 active probe (`work/ch38b_ptt_probe.sh`) — GATT/SDP/AT/SPP fingerprints
- [ ] Chipset verdict → branch (JieLi UART-open vs stop/ESP32)

## §38.7 Round 3 active probe (2026-11-16, log work/logs/ch38b_ptt_probe_20261116_074956.log)

Script `work/ch38b_ptt_probe.sh` (sudo, radio OFF, PTT blinking; user pressed the button 3× twice during the SPP window).

1. **Raw adverts / EIR (btmon):** name `TID-PTT0cd28a-B` complete; Class of Device `0x240404` (Audio/Video → Wearable Headset); page-scan R1/P0; RSSI −36. **NO manufacturer-specific data** (EIR padding all-zero) — no company-ID tell.
2. **LE GATT (gatttool, side `6F:E5:E7:BC:39:37`) — READ OK:** GAP 1800 (2A00 name); service **FF00** (handles 0x0004–0x000e): chars `ff01` notify (vh 6), `ff02` read|write-no-rsp|write (vh 9), `ff21` notify (vh 0x0b), `ff22` write-no-rsp|write (vh 0x0e); service **AE00** (handles 0x0080–0x0085): `ae01` write-no-rsp (vh 0x82), `ae02` notify (vh 0x84). The FF00/AE00 family mirrors what the RADIO advertises BLE-side (`ae00/ae30/af00/af30/ff00`) ⇒ **TIDRADIO app-level service style, same vendor code lineage — not a chip marker**. No JieLi OTA FFE0/FFF0 and no Bestechnic FFB0 advertised by either device.
3. **BR/EDR:** `hcitool cc` → Input/output error; `sdptool browse` → immediate empty; **HFP ch 6 → Connection refused** (no HFP server at 6 despite the SDP class hint); **SPP ch 2 → CONNECTED** (rfcomm /dev/rfcomm8 "Connected… on channel 2", held 16 s then timeout-disconnect).
4. **SPP capture:** button presses during the window produced **no data** on the PTT's own SPP server. Interpretation: the PTT's ch-2 server is NOT the event path — the working architecture is radio-hosts-SPP-server, PTT dials IN as client and sends `+SPP=P/R` (ch. 22 §9A). Events therefore only flow on a PTT-originated link — which never happens (the very problem). ch 2 is likely a config/CPS-style server.
5. Offline: full-16-byte UUIDs (ae00/ae30/af00/af30/ff00/ff01/ff02/ff21/ff22/ffe0/fff0/ffb0) not found in `work/app_dec.bin` — radio BLE services live in short-form/another blob; inconclusive, deprioritized.

**Verdict: chipset still unidentified — but SPP ch2 CONNECT proves the PTT answers pages while blinking.** The decisive missing datum is the **LMP subversion string + manufacturer** (`hcitool info`), which previous rounds lost to link drops. Round 4 (`work/ch38c_ptt_probe.sh`): hold the ACL open via background `rfcomm connect` ch2, then `hcitool info`/`features` + full `sdptool browse` WHILE LINKED; release ch2 and AT-probe the real HFP channel from SDP (fallback 6) incl. **AT+JLRHI=?/AT+JLDP=?** JieLi vendor tells.

## §38.4 checklist (updated again)
- [x] Recon rounds 1+2 — identities stable, LegacyPairing noted
- [x] Label photo — moot (no markings); ports = charge-only USB, no data mode
- [x] JieLi USB-boot probe — NEGATIVE (no enumeration in any button/plug variant)
- [x] Round 3 active probe — GATT = TIDRADIO-style services; SPP ch2 server connects (no events); HFP ch6 refused; no EIR mfg data
- [ ] Round 4 link-held probe (`work/ch38c_ptt_probe.sh`) — LMP subversion/manufacturer + full SDP + AT+JLRHI/JLDP
- [ ] Chipset verdict → branch (JieLi UART-open vs stop/ESP32)

## §38.8 CHIPSET VERDICT: JieLi (2026-11-16, round 4, log work/logs/ch38c_ptt_probe_20261116_081925.log)

`hcitool info` while the ACL was held (background rfcomm ch2 page):

```
BD Address:  6F:E5:E7:FB:12:4F   Device Name: TID-PTT0cd28a-B
LMP Version: 5.3 (0xc)  LMP Subversion: 0x22bb
Manufacturer: Zhuhai Jieli technology Co.,Ltd (1494)
Features page 0: 0x01 ... (<3-slot packets> only)
```

**DECISIVE: the TID-PTT is a JieLi SoC** (assigned SIG manufacturer 1494). LMP 5.3 + subversion `0x22bb` = a recent AC63/AC69/AC70x-generation part (exact SKU from the die marking). This opens the best-case branch of §38.2: `fw-AC63_BT_SDK` (ch. 24/28) is the source tree for exactly this app class, the pi32v2 toolchain + patch/packager suite in this repo applies, and JieLi parts expose **UART/USB download modes** in ROM.

Also noted: `sdptool browse` returns empty even with the link UP, and HFP ch6 refuses — the PTT's SDP server is non-responsive, **the same vendor quirk as the radio** ("Radio doesn't answer SDP", ch. 22) — further common-lineage evidence. `hcitool features` is not a command in BlueZ 5.85 (info already carried the features page).

Access reality (§38.6): USB data lines ARE wired (full-speed attach seen) but no firmware/bootloader USB mode enumerates via the charge port ⇒ realistic path = **open the puck, find the SoC marking + UART/flash pads**, TTL 3.3 V adapter:
1. Identify exact SoC from the die marking → map to SDK `cpu/` family + download protocol (USB-HID vs UART `update`).
2. Read-protect check: if OFF → dump firmware → statics → locate the connect policy → design the "page remembered host when idle" patch (propose-don't-flash, user's accessory).
3. If read-protect ON → rebuild route: SDK app for the same SKU (ch. 28 gotchas apply) — heavier, decide then.
4. Fallback stays ESP32 combo device (§9B.6.1) — the round-3 SPP finding (events only flow on PTT-originated links) already informs that design.

## §38.4 checklist (updated again)
- [x] Recon rounds 1+2 — identities stable, LegacyPairing noted
- [x] Label photo — moot (no markings); ports = charge-only USB, no data mode
- [x] JieLi USB-boot probe — NEGATIVE (no enumeration in any button/plug variant)
- [x] Round 3 active probe — GATT = TIDRADIO-style services; SPP ch2 server connects (no events); HFP ch6 refused; no EIR mfg data
- [x] Round 4 link-held probe — **JieLi (mfr 1494), LMP 5.3 sub 0x22bb; SDP non-responsive even linked**
- [x] Chipset verdict → branch: **JieLi = best case (§38.8)**
- [ ] Open puck: SoC die marking + pad inventory (photos) → download-protocol choice
- [ ] Dump (if read-protect OFF) → connect-policy statics → patch design

## §38.9 Over-the-air door: stock JieLi RCSP found on the PTT (2026-11-16, no-open constraint)

User will NOT open the puck ⇒ firmware access must be over-the-air. SDK dig (`/home/stefan/h3plus/fw-AC630N_BT_SDK`):

1. **The PTT's AE00 GATT group is BYTE-IDENTICAL to the SDK's `RCSP_BTMATE_EN` block** (`apps/common/third_party_profile/jieli/le_at_com.h`): PRIMARY ae00 @0x0080, ae01 WRITE_NO_RSP vh **0x82**, ae02 NOTIFY vh **0x84**, CCCD 0x85 — exactly what round 3 read off the PTT. ⇒ the PTT runs **stock JieLi RCSP ("bt mate") over LE**; its SPP ch-2 server is the prime suspect for RCSP-over-BR/EDR.
2. **RCSP framing** (`include_lib/ai_stack/JL_rcsp/JL_rcsp_packet.h`): `FE DC BA | head u16 (opcode b7:0, _resp b14, _type b15) | len u16 | data | EF` — no CRC field.
3. **RCSP OTA command set** (`rcsp_updata/rcsp_user_update.h`): `0xE1` get-update-file-info-offset · `0xE2` inquire-if-can-update · **`0xE3` ENTER_UPDATE_MODE — the device reboots into the RCSP uboot download mode over Bluetooth** · `0xE4` exit · `0xE5` send-fw-update-block · `0xE6` refresh-status · `0xE7` reboot · `0xE8` notify-content-size. Update gate = VID/PID match + higher VER from the device ex_cfg (`judge_remote_version_can_update`); stock flow shows **no authentication** on these opcodes (OEMs may add a des/auth layer — unknown for TID).
4. The radio's own app contains "rcsp" (@0x01E9BB7E) and advertises the same ae00/ae30 family ⇒ **the radio is a safe RCSP testbed** (reflashable) — probe framing on the radio first if PTT replies are ambiguous.
5. "Trigger uboot via Bluetooth while USB connected": the ROM does not listen over BT, but RCSP 0xE3 gets the APP to reboot into the bootloader's RCSP/USB update mode — effectively yes, if the PTT firmware includes `RCSP_UPDATE_EN`.

**Round-5 probe `work/ch38d_ptt_rcsp_probe.sh` (sudo, PTT blinking, radio OFF):** sends ONLY harmless queries E1/E2 (never E3) in 4 framing variants (head LE/BE × SN) to SPP ch2 and to BLE ae01+ff02 with notifications armed; a `FE DC BA…EF` reply = RCSP alive = firmware path open (dump still impossible OTA — but WRITE-UPDATE is: build SDK app or patched image with matching VID/PID, push via E3/E5; and the official TIDRADIO phone app, if it updates this PTT, proves an unauth-or-crackable OTA channel exists).

## §38.4 checklist (updated again)
- [x] Round 4 — JieLi verdict (§38.8)
- [ ] User constraint logged: NO opening → OTA only (§38.9)
- [ ] Round 5 RCSP probe (`work/ch38d_ptt_rcsp_probe.sh`) — framing reply on SPP ch2 / BLE ae01?
- [ ] If RCSP alive: VID/PID read (E1/E2 replies) → update-image strategy (SDK build vs patched-official)

## §38.10 Round 5 RCSP probe results (2026-11-16 evening, logs ch38d_rcsp_20261116_201603/201938/202244/202303)

- Script bugs found+fixed: bash `local a=1 b=$a` expansion gotcha (unbound `tag`), literal spaces in the SPP frame writes, and **BlueZ 5.85 gatttool has no `--char-write-cmd` long option** (the BLE writes never went out — the BLE half of RCSP is still UNTESTED, not negative).
- **SPP ch 2: connects (blink-synchronized; "Host is down" whenever the PTT left page-scan) but returns ZERO bytes to E1/E2 in 4 framings** (head LE/BE, len1/len2) ⇒ ch2 is NOT an answering RCSP server (dangling SPP server, or needs the official app's session/handshake first).
- Positive tell: **CCCD writes to 0x0085 (ae02) and 0x0007 (ff01) SUCCEEDED** — handle 0x0085 existing exactly where the SDK's `RCSP_BTMATE_EN` table puts the ae02 CCCD corroborates the stock-RCSP GATT layout on the live device.
- BR/EDR page-scan confirmed blink-only in practice (LE advert stays up after blink; pages then fail) — all SPP attempts must be re-blink-synchronized.
- **Round 5b = `work/ch38e_ptt_rcsp_probe.sh`**: single interactive gatttool session (subscribe ae02/ff01 + `char-write-cmd` frames to ae01/ff02 + capture notifications on ONE connection — the real, still-untested RCSP path) then blink-synced SPP retry loop (3 attempts). E1/E2 only — cannot reboot the device.

## §38.11 Round 5b results + POWER-CYCLE REVEALING REMARK (2026-11-16 late evening)

- ch38e run (log ch38e_rcsp_20261116_202821): BLE section LOST its commands — gatttool -I consumed the heredoc stdin before the link established (prompt printed, zero command echoes, GLib-CRITICAL warning) ⇒ BLE RCSP STILL untested (3rd script bug, not a device negative). SPP attempts: rfcomm printed "Connected … on channel 2" then instant "Disconnected" twice (PTT accepted the page while blinking, then dropped the session — single-SPP-server quirk or leftover link), attempt 3 "Device or resource busy" (stale rfcomm9 binding), user Ctrl-C'd.
- **USER REMARK (verbatim): "Poweroff / restart is really really really hard as it needs to be out of range"** — the PTT will not power-cycle/behave while its bonded host (the PC dongle, bonded since round 3) is in range. This STRONGLY suggests the PTT does not sit passive when powered on near a remembered host: either it pages that host itself, or the PC-side link re-grabs it instantly. If the PTT *can* page its remembered host, the §37.19 "pure peripheral, never pages" model needs correction — and the MIRROR scenario (radio dials Jabra = audio binds natively; PTT pages IN to the radio = free SPP session) may work on **stock S1 with ZERO further patching**. OPEN QUESTION to user: when powered on in range of the PC dongle (dongle on, nothing running), does the PTT connect to the PC by itself?
- ch38f round-5c probe: FIFO-held interactive gatttool (commands sent 8 s after connect, 2 s spacing; subscribe ae02/ff01 → E1/E2 to ae01 then ff02 → readback), section 2 optional blink-synced SPP retry on fresh port rfcomm10 with release-first. E1/E2 only — harmless.

## §38.12 Power-on behavior ANSWERED (2026-11-17): pure peripheral CONFIRMED

User question (question tool): "PTT powered ON, PC dongle on + in range, no scripts — what happens?" → **"It just blinks / stays idle."** The PTT does NOT page its remembered host; §37.19 model stands (joins only when a host dials it). The earlier "power-cycle needs out-of-range" is the connected-state quirk (3 s hold behaves differently while a link is up), not hidden paging. ⇒ Mirror scenario requires the PTT to learn paging = **PTT-side firmware patch via OTA (RCSP) remains the only route**; BLE RCSP test still pending (never executed — ch38f is the corrected attempt, FIFO-timed interactive gatttool, E1/E2 harmless queries only).

## §38.13 Round 5c (ch38f) failure post-mortem + ch38g fix (2026-11-17)

ch38f run (log ch38f_rcsp_20261117_004416): (a) `char-desc-write-req` → "command not found" (correct gatttool verb is **`desc-write-req`**); (b) every write after → "Command Failed: **Disconnected**" — **interactive gatttool does NOT auto-connect; the script never sent `connect`** (bug #5 — this is why BLE was never really tested across ch38d/e/f). §2 SPP: rfcomm10 connected to blinking PTT ("paired" per user), instant Disconnect again (ch2 dangling confirmed 3rd time).

**ch38g (`work/ch38g_ptt_rcsp_probe.sh`)**: FIFO session + explicit `connect` (8 s settle, one retry after re-blink prompt), then `desc-write-req 0x0085/0x0007 0100` (subscribe ae02/ff01), `char-write-cmd 0x0082` E1_LE/E1_BE/E2, `char-write-cmd 0x0009` E1/E2 (TID variant), `char-read-hnd 0x0009`, 8 s hold for late notifications, full gatttool output dumped. E1/E2 only — harmless. bash -n OK.

## §38.14 Round 5d (ch38g) — LE LINK ESTABLISHED; frames sent (2026-11-17)

Log ch38g_rcsp_20261117_005124: **`Attempting to connect … Connection successful`** — the PTT LE side accepts connections (blinking). All 5 `char-write-cmd` frames + read executed with NO gatttool error ⇒ frames went on the wire to ae01 (0x0082) and ff02 (0x0009). BUT: `desc-write-req`/"command not found" — this gatttool build has NO descriptor command ⇒ CCCDs never subscribed ⇒ notifications invisible even if sent; `char-read-hnd 0x0009` printed NO value (no reply or lost); gatttool segfaulted at exit (known quirk, after all commands — harmless). No visible RCSP answer = INCONCLUSIVE (write-cmd is fire-and-forget; no notify path armed).

**ch38h (round 5e)**: same session + (a) CCCD subscribe via `char-write-req` to handles 0x0085/0x0007 (valid ATT), (b) E1/E2 to ff02 via write-REQ (ff02 supports write → ATT success/error reply = device-alive proof), (c) **btmon captured in parallel** — every ATT PDU logged (link-layer ACKs of the write-cmds, any Notification/Indication, error responses). Verdict logic in script footer.

## §38.15 ROUND 5e btmon post-mortem — TWO MAJOR FINDINGS (2026-11-17)

Full /tmp/ch38h_btmon.txt read (523 lines, capture t=0..28 s):

**FINDING A — THE PTT PAGES ITS BONDED HOST WHILE BLINKING.** At t=0.803 s (before any of our commands) an **incoming** `HCI Event: Connect Request (0x04)` arrived FROM `6F:E5:E7:FB:12:4F` — the PTT paged the PC while in pairing blink. PC accepted; the PTT then opened SDP as a CLIENT (PSM 1) and searched for **Handsfree Audio Gateway (0x111f)** — PC answered RFCOMM ch 13. The PTT is a headset-class ACTIVE device (CoD Wearable Headset was literal): in pairing-blink state it pages its remembered host and hunts HFP AG. (User's earlier "power-on = just blinks, idle" was plain power-on WITHOUT the pairing blink — different state.) ⇒ **MIRROR TEST (zero patches): with the S1 radio holding the Jabra (radio-dialed = audio bound), blink the PTT. If it pages the radio and lands as incoming joiner, the goal may work TODAY** — incoming joins are accepted by the E7-ref radio (§30.14.17, P7 once/boot), the SPP session is free (Jabra uses none), and the radio's name classifier knows "TID-PTT" (mode 3/4). Caveats: PTT may hunt HFP-AG only (radio IS an HFP AG ch 6 — it would connect that); whether BT-PTT keying then rides SPP or the HFP hook is the open question — the test answers it.

**FINDING B — THE LE LINK KILLER WAS OUR OWN bluetoothd.** LE connect succeeded t=2.73; PTT sent Exchange-MTU ×2 (2.77/2.81) then idle; at t=4.88 **the PC's bluetoothd issued `Disconnect (reason 0x13)`** on handle 16 — its connection/pairing-agent policy against the bonded device tears down gatttool's "unwanted" LE link ~2 s after it comes up. Every command in ALL rounds (5c/5d/5e) was sent AFTER that teardown ⇒ BLE RCSP has still never been tested; gatttool's silent no-error output = writing into a dead connection. FIX: `systemctl stop bluetooth` (+ `hciconfig hci0 up`) around the gatttool session — raw ATT needs no daemon ⇒ `work/ch38i_ptt_rcsp_probe.sh` (round 5f).

## §38.4 checklist (updated)
- [x] Round 5e btmon: PTT pages bonded host in blink (FINDING A) + bluetoothd LE-kill root cause (FINDING B)
- [ ] MIRROR BLINK TEST on S1 (radio holds Jabra, blink PTT) — §38.15-A, zero-patch goal candidate
- [ ] Round 5f BLE RCSP (`work/ch38i_ptt_rcsp_probe.sh`, bluetoothd stopped)
- [ ] Verdict → branch (goal-native / OTA design / stop-at-S1 vs ESP32)

## §38.16 Round 5f post-mortem + round 5g (bluetoothd-owned approach) (2026-11-17)

ch38i (bluetoothd-stop attempt): LE connected t=1.97, PTT sent Exchange-MTU ×2, **local host Disconnect at t=4.08 again** — bluetoothd SURVIVED `systemctl stop` (start at script end errored "Unit bluetooth.service is masked" — the unit is masked on this host, daemon evidently dbus-socket-activated; it came back active 01:19:53). All commands again post-mortem. btmon wrote btsnoop binary (`-w`) — decoded with `btmon -r`: no ATT writes ever reached the wire; only the 2 MTU exchanges. **BONUS RE-CONFIRM: BR/EDR handle 1 = the PTT paged the PC AGAIN during this run** (local-host-cleanup disconnect at 20.8 s) — Finding A (§38.15: PTT pages bonded host while blinking) reproduced.

**Round 5g `work/ch38j_ptt_rcsp_probe.sh`**: stop fighting the daemon — connect THROUGH bluetoothd (`bluetoothctl` FIFO session: `connect` → `menu gatt` → `select <ae02/ff01 UUID>` + `notify on` → `select ae01/ff02` + `write fedcbae1…/fedcbae2…`); bluetoothd never kills its own connection. btmon captured as TEXT (`btmon > file`). E1/E2 only — harmless.

**PRIORITY NOTE**: the §38.15-A MIRROR BLINK TEST (S1 radio holding Jabra + blink PTT near it → does it page in? does BT-PTT key? does Jabra survive?) is the zero-patch goal candidate and outranks the RCSP probe — needs the S1 flash first (`sudo bash work/ch32_bt_e7.sh`).

## §38.4 checklist (updated)
- [x] Round 5f: bluetoothd survives stop (masked/dbus-activated) — link killed again; PTT page re-confirmed
- [ ] MIRROR BLINK TEST on S1 (§38.15-A) — zero-patch goal candidate
- [ ] Round 5g BLE RCSP via bluetoothctl gatt (`work/ch38j_ptt_rcsp_probe.sh`)
- [ ] Verdict → branch

## §38.17 Round 5g post-mortem + round 5h (2026-11-17 morning)

ch38j: `connect` → "Device 6F:E5:E7:BC:39:37 not available" (LE side not in bluetoothd's view — no scan was run; PTT possibly off or advertising window missed) and `select` → "Invalid command in menu gatt" (5.85 uses **select-attribute**); btmon (text) shows ZERO ATT/LE events — no link, round void. bluetoothctl 5.85 gatt-menu syntax captured from its own help: `select-attribute <UUID>`, `write <data=xx xx ...> [offset] [type]`, `notify <on/off>`, `acquire-notify`.

**Round 5h `work/ch38k_ptt_rcsp_probe.sh`**: `scan on` + 8 s before `connect`; correct `select-attribute`/`write data=…` syntax; same E1/E2 frames to ae01+ff02, notify armed on ae02+ff01; btmon text capture. E1/E2 only — harmless.

STATUS REMINDER: the §38.15-A **MIRROR BLINK TEST** (S1 radio + Jabra dialed + blink PTT) has NOT been run yet — it remains the zero-patch goal candidate and outranks the RCSP probe. Radio may still be on v4 `b91b3535` (must-not-ship) → S1 installer `sudo bash work/ch32_bt_e7.sh`.

## §38.18 Round 5h (ch38k) post-mortem — root cause of the LE teardown: dual-mode bond policy

ch38k run (log ch38k_rcsp_20261117_085904): bluetoothctl-owned connect **succeeded** (`Connection successful` + `ServicesResolved: yes`) then **local-host disconnect ~1 s later** — before the first `select-attribute` ("No device connected" ×4; zero ATT writes on the wire, btmon shows 3× Exchange-MTU then Disconnect at 16.86 s). Diagnosis: the PTT is a **dual-mode device bonded on its BR/EDR side** (our round-3 rfcomm pairing); BlueZ resolves the LE side, recognizes the classic bond, attempts classic profile bring-up, fails (BR/EDR ignores pages when idle) and tears the LE link down. Round 5i `work/ch38l_ptt_rcsp_probe.sh`: `remove` BOTH addresses first (PC-side bonds are our own probe artifacts, safe to delete and re-create), then the same notify+write sequence; if writes now answer `Error Response 0x05 (Authentication Required)` → pair the LE side and retry. E1/E2 only — harmless. **Reminder: the MIRROR BLINK TEST (§38.15) is still the top-priority run — it may reach the goal with zero patching.**

## §38.19 Round 5i (ch38l) post-mortem — the teardown culprit: the PTT's own classic paging storm

Full log read: at script start the **PTT-B classic side was already CONNECTED to the PC** (bluetoothctl prompt named it; `remove` had to disconnect it) — the blinking PTT had paged the PC (Finding A live again). During the run `LegacyPairing` flaps yes/no every ~2 s = the PTT repeatedly pages/pair-requests the PC. The LE connect itself succeeded (`Connection successful` + `ServicesResolved: yes`) but the link died ~1 s later — **the concurrent incoming BR/EDR pairing storm is the teardown agent** (BlueZ dual-mode identity/profile handling), not the bond itself. Also: my "link dropped" early-check was a false positive (grepped the removal disconnect).

Round 5j `work/ch38m_ptt_rcsp_probe.sh`: (1) PTT in **plain power-on** — no blink ⇒ no paging; its LE advert (flags 06 = general-discoverable/connectable) stays up regardless; (2) brief scan to seed the device then **`scan off`** ⇒ page scan disabled, classic pages cannot reach us even if it blinks; (3) outgoing LE connect + notify + E1/E2 writes as before; drop-check fixed (marker after connect). E1/E2 only — harmless. If bluetoothctl refuses connect with discovery off, re-run with the PTT blinking and accept the storm risk (fallback noted).

Checklist: [x] rounds 5e–5i post-mortems; [ ] round 5j run; [ ] RCSP verdict (reply / auth-required / dormant).

## §38.20 Round 5j full-capture read (2026-11-17): PTT PAGES PERSISTENTLY — even plain power-on

Full /tmp/ch38m_btmon.txt (711 KB) read directly:
1. **t=7.6 s: incoming BR/EDR Connect Request from 6F:E5:E7:FB:12:4F** — ~1 s after our `scan on`, from a **PLAIN-powered PTT (no blink)**. We accepted (Accept Connection Request 7.627, Connect Complete 7.815) then it died at 8.05 with **Reason: PIN or Key Missing (0x06)** — the PC-side bond had just been `remove`d by the script, the PTT still holds ITS key and tried to re-link encrypted. ⇒ **The PTT pages its remembered host continuously, not only while blinking.** Earlier "plain power-on = idle" was an artifact: with PC page-scan off the pages simply never landed and nothing was visible. Round 5i's LegacyPairing-flap = same storm.
2. LE side: our LE Create Connection at 27.34 → Connection Complete 27.36 → 3× Exchange-MTU + 1 response → **zero ATT write PDUs on the wire** → local Disconnect (bluetoothctl quit) at 29.48. The gatt-menu writes failed INSIDE bluetoothctl (its stdout was never captured — script flaw): select-attribute ran before ServicesResolved populated (~1 s after connect), so `write` had no selected attribute. **RCSP still untested (8th attempt)** — but see priority below.

**CONSEQUENCE — the mirror scenario is MORE alive than thought, with a bond-priming sequence:**
- PTT remembers ONE host (symmetric to the radio's single last-device register); whatever device last connected to it becomes its page target. Right now that is the PC (bond gone on PC side ⇒ its pages fail 0x06 harmlessly).
- If the RADIO becomes the PTT's last host (radio dials PTT once — stock behavior), then on next power-cycle the PTT should page the RADIO persistently. Radio S1 accepts incoming joins while connected (§30.14.17, --force-page-scan, --no-kick, 2-slot).
- CAVEAT (btmon evidence): while paging, the PTT's only observed client behavior is **SDP search for HFP AG (0x111f)** — the radio never answers SDP (known fact) and the PTT has never needed to be an SPP *client* (stock flow: radio dials PTT, radio = SPP client to PTT's ch-2 server). Whether the PTT opens SPP to the radio after an incoming page = THE open question the blink test answers.

**MIRROR PRIME+PAGE TEST (zero scripts, top priority over RCSP):**
1. S1 flashed; power radio; menu-connect **TID-PTT** (radio dials PTT ⇒ PTT's remembered host = radio). Verify BT-PTT keys.
2. Menu-connect **Jabra** (radio dials Jabra; E6-proven the SPP incumbent survives a radio-originated headset dial). Verify audio on Jabra.
3. Power-cycle the PTT (out of range first if needed) and bring it near the running radio. Observe: does the PTT join by itself (page storm hits radio's page-scan)? Does BT-PTT key with Jabra up? Does Jabra survive? Any echo?

## §38.21 Bluetooth-triggered boot entry: OTA is not USB download mode (2026-11-17)

**Verdict: plausible Bluetooth OTA entry, but NO verified Bluetooth command to enter
the PTT's USB-HID/UBOOT downloader.** This corrects the stronger claims in §38.9.

- Re-read local SDK source `apps/common/third_party_profile/jieli/JL_rcsp/rcsp_updata/rcsp_user_update.c`
  in `../fw-AC630N_BT_SDK`: `MSG_JL_ENTER_UPDATE_MODE` (lines 435–454, opcode E3)
  disables connect/scan and, for dual-bank builds, initializes `DUAL_BANK_UPDATA`.
  The separate update-start path (419–432) selects `BLE_APP_UPDATA` or
  `SPP_APP_UPDATA`, NOT `USB_UPDATA`. E3 is therefore not a generic "reboot into
  USB bootloader" instruction, and need not immediately reboot at all.
- **Probe-safety correction:** the E2 handler (360–391) can post
  `MSG_JL_LOADER_DOWNLOAD_START` on single-bank builds; its version-check block is
  compiled out (`#if 0`) in this SDK copy. Earlier descriptions of E1/E2 as
  categorically harmless/read-only, and of a mandatory VID/PID/version gate, are
  not justified. No such behavior has been confirmed on the PTT.
- The AE00/AE01/AE02 handle layout is consistent with the SDK's RCSP transport,
  but does NOT prove the PTT includes an enabled RCSP parser, OTA handler, or
  USB-update transition. Latest capture (§38.20) still has zero ATT write PDUs;
  no valid RCSP response has yet been established.
- The [vendor product page](https://tidradio.com/products/tidradio-wireless-ptt-button)
  explicitly advertises an included connecting cable and BL-1-style wireless
  programming of other radios. Thus "charging-only port" is not established by
  the marketing or failed enumeration. A USB-shaped connector can carry a
  non-USB programming interface; pinout and native USB boot support remain
  UNKNOWN. The observed USB errors alone do not establish a working data path
  to the SoC or its bootloader.

Next evidence needed: a stable BLE connection with ServicesResolved complete,
notifications subscribed, and capture-confirmed benign protocol identification
traffic (or an official-app session capture). Do not send E2/E3/E7 or firmware
blocks blindly. Establish OTA capability separately from any USB-mode switch;
no boot transition, device probe, or flash was executed in this review.

## §38.22 Programming-cable image: external data path, not yet flash readback (2026-11-17)

User supplied the vendor's [wireless-programming image](https://tidradio.com/cdn/shop/files/3_in_1_Wireless_PTT_Button_for_ODmaster_APP_Mic_Programmer_Adapt_to_H3_Plus_Bluetooth_Hands-Free_Speaker_Mic_for_PoC_Radio_Mobile_Phone_In-Car_Wireless_Speaker_Mic_for_Car_Motorcycle_Outdoor_Two-Way_Radio_Speaker_Mic_Bicycle_Helmet.jpg?v=1745656161&width=1920).
Visual inspection: TD-UV5R radio, Kenwood-style side connector, cable into the
PTT's top port, and phone displaying channel/settings programming. This is
marketing evidence of an intended external **data** connection, not a measured
pinout, a visible CH340, or proof of USB-host implementation.

Two distinct candidate topologies remain:

1. Phone → Bluetooth → PTT USB host → USB/UART chip in cable → radio UART.
   A genuine CH340 cable functioning here would establish a USB-host path and
   suitable host driver, but NOT USB-device/HID boot support or flash readback.
2. Phone → Bluetooth → PTT UART → passive cable using a USB-shaped connector →
   radio UART. This would expose an external serial path without opening the
   puck; whether those same pins offer boot-ROM download/debug is UNKNOWN.

**New extraction leads, all UNTESTED on the PTT:**

- Identify the cable independently: does it enumerate on a PC, and if so with
  which VID/PID? An actual CH340 normally reports WCH VID 0x1A86 (PID varies).
  A negative result alone does not establish a passive cable or its pinout.
- Passively observe a successful ODmaster **read-from-radio** session (phone HCI
  capture; optionally a correctly connected high-impedance serial/USB analyzer).
  Identify bridge configuration, baud changes, local management commands and any
  update/version exchange. Radio-memory reads are NOT PTT-memory reads.
- If a UART pinout is verified, passively capture PTT power-on traffic with the
  proper voltage level. A boot log or loader handshake could identify a serial
  recovery route. App UART pins need not be the ROM downloader pins; do not
  inject 5 V/RS-232 or connect unknown connector pins to an adapter.
- Inspect the official app's firmware assets/update logic, or a legitimate
  accessory-update capture, for a PTT-specific image and transport. A distributed
  update image may be encrypted/partial and is not necessarily a device dump.

Local SDK evidence: `../fw-AC630N_BT_SDK/apps/common/update/update.c:312–325`
implements `UART_UPDATA` with baud/TX/RX parameters. This establishes a JieLi SDK
mechanism, NOT its inclusion, accessible entry, pin mapping, or readback support
on this unidentified PTT SoC/build. No CH340-specific source match was found in
that SDK checkout; absence there does not rule out vendor additions.

**Verdict:** this materially improves the no-opening investigation: identify the
cable and capture the working programming protocol before further blind RCSP
probes. A serial bridge alone cannot address its own MCU flash; an explicit
read-memory/debug/loader capability is still required. No hardware commands,
boot transitions, or flashing were performed for this analysis.

## §38.23 Dated corrections to §38.7 and §38.8 (2026-11-17, ch. 39 §39.4)

**Correction 1 — §38.7 "events only flow on PTT-originated links" is NOT supported
by the record.** §9A.19/§9A.20 (2026-09) captured `+SPP=P/R` from this same button
(`6F:E5:E7:FB:12:4F`) over a **PC-originated** link. The two runs differed in every
variable that matters (comparison table: ch. 39 §39.4):

| Variable | §9A.19/20 (events ✅) | §38.7 (no events ❌) |
|---|---|---|
| Tool/handshake | `bt_ag_capture.py --connect` (full AG SLC) | raw `rfcomm connect` — no AG handshake |
| Channel | brute-force 1–30, first opener | pinned ch2 (SDP returned nothing) |
| Bond | `pair` + `trust` first | unpaired, pairing-blink |
| Link security | bonded → encrypted | blink link, no bond |

Working hypothesis (UNTESTED): the discriminator is the **link security/bond state**
(possibly + AG SLC), not the connection direction. Re-test card **P0.2** issued
2026-11-17 (procedure in the ch. 39 §39.11 / session card); verdict to be appended
here when results return.

**Correction 2 — §38.8's JieLi verdict was already in the record.** §9A.20's
peer-identity snapshot (2026-09, ch. 09) lists "Manufacturer: Zhuhai Jieli
Technology (1494), LMP 5.3, subversion `0x22bb`". §38.8 (2026-11-16) re-derived the
same facts via `hcitool info` without crediting ch. 09. The verdict stands; the
priority is corrected here.
