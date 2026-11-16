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
