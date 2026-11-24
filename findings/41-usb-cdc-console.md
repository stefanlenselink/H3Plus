# 41 — The app's USB CDC-ACM port (and why it does not open the external NOR)

Date: 2026-11-24. Trigger: the user power-cycled the radio (running normally, app mode), plugged
USB, and the kernel enumerated something new — a `ttyACM0`. Question asked: *"any thing to
experiment on this or is the nor accessable now?"* — the NOR in question being the **external
`res_nor` bank at flash `[0x100000, 0x300000)` that holds the voice samples**
([§40.12](40-radio-jlfs-filesystem.md#4012-the-voice-prompts--where-bluetooth-connected-actually-comes-from-2026-11-24)),
which the 1-MiB-masked uboot can never read.

**Short answer: the app does expose a USB serial port, but it is silent — no console, no AT
command interface — and it gives no access to the external NOR.** Details and evidence below.

## §41.1 What the USB enumeration actually shows (hardware-confirmed, 2026-11-24)

Two different faces appeared on two plugs of the same cable, which is the interesting part:

| | dev 121 (first attach) | dev 122 (after a disconnect + re-plug) |
|---|---|---|
| VID:PID | `4c4a:4155` Jieli Technology USB Composite Device | same |
| SerialNumber | **absent** | **`4150353835323003`** |
| Kernel binding | `hid-generic` → `/dev/hidraw4` (+ `hiddev3`) | `cdc_acm` → **`/dev/ttyACM0`** (iface 0), iface 1 left unbound |
| Meaning | the **uboot / HID upgrade face** (the one `tools/jl_hidboot.py` speaks) | the **running app's** USB composite device |

Kernel note on dev 122 iface 1: `endpoint 0x4 (out) / 0x84 (in) has invalid maxpacket 256,
setting to 64` — the app's descriptor declares a 256-byte bulk maxpacket, which is illegal for
full-speed; Linux clamps it. Interface 1 is a **bulk pair (0x04 OUT / 0x84 IN) that no kernel
driver claims**. In app mode there is no `hidraw`/`hiddev` node for the radio at all (checked:
`/dev/hidraw0-3` exist but are other devices, root-only).

`lsusb` shows only the one composite device; `/sys/bus/usb/devices/1-6:1.0` (cdc-acm) and
`1-6:1.1` (unbound) are present.

## §41.2 Probing `/dev/ttyACM0` — it is silent (hardware-confirmed)

The port is usable from the harness without sudo (`crw-rw---- root:dialout` plus an
ACL `user:stefan:rw-`). Set to `115200 raw -echo -crtscts`:

* **Idle listen 2–4 s: 0 bytes.** The app streams no boot/debug log.
* **Ten ASCII probes, each followed by a 1.2 s drain — every one returned 0 bytes:**
  `\r\n`, `at`, `?`, `help`, `AT+NAME?`, `AT+BAUD?`, `log`, `info`, `version`, `AT`.

Prober (stdlib, read-only, no writes beyond the probe lines):
`/tmp/opencode/ch41_acm_probe2.py` (first version `ch41_acm_probe.py`).

Verdict: **no ASCII console / AT parser on interface 0.** If the port carries anything it is a
binary protocol (JieLi RCSP / tuning-tool framing) or it is simply an unused VCOM descriptor.

## §41.3 Static evidence in the decrypted app (`work/app_dec.bin`, VA = off + 0x01E00000)

* **Zero `cdc`/`acm` strings** in the app image — the VCOM descriptor is emitted by the USB
  library without naming it, so there is nothing to grep for a console.
* The `AT+...` string cluster @file `0x15C80` is the **HFP (HF-role) AT set the radio *sends***
  (`ATA\r`, `AT+CHUP\r`, `AT+BLDN\r`, `AT+VGS=10\r`, `AT+BRSF=16`, `AT+IPHONEACCEV=1,1,9`, …) —
  Bluetooth HFP, not a serial console. Consistent with §41.2.
* **`rcsp_task`** — the name string @`0x9BB7E` sits inside a UI status string block
  (`usp : / ssp : / psr :` and `P:2W` / `P:5W` / `P CALL` / `%02d.%03d`), but it is a **real
  task**: it appears in the RTOS task table @`0x936A4`..`0x9373C+` (entry @`0x937B8`) and as a
  32-bit immediate (task-name argument) in a task-create sequence at VA `~0x01E5AF58`. The task
  body was **not** decoded (context budget) — so **whether an RCSP command handler is reachable
  over USB remains UNVERIFIED**.
* **`usb_wr_freq_task`** (name @`0x9221B`, create site `0x01E71C84`) body = `FUN_01e71734`:
  sleep 300 ms → lock → build a 288-byte request block (magic `0xfa58`, callback
  `FUN_01e717fa`, `0x12c00`) → `FUN_01eb576e()` → sleep 100 → done. That is an **asynchronous
  device-open wrapper, not a command loop**. Its name says what it does: *write frequencies over
  USB* (the PC programming-cable path, cf. findings/38 §38.22).
* OTA/update file-name table @`0xB4120`: `ble_app_ota.bin`, `spp_app_ota.bin`, **`usb_update2.bin`**,
  `ble_ota.bin`, `uart_user.bin`, `nor_ota.bin`, `VM`, `app_dir_head`, `ota.bin` — a USB update
  path exists, i.e. the app *does* accept binary USB traffic for updates. **Never exercised here**
  (writing anything to the radio is out of scope; `OTA EXIT` deliberately not probed).
* Resource-name candidates @`~0x9224x`: `filesystem`, **`voice`**, `font` — consistent with
  volume-level file names on the `res_nor` / `nor_ui` volumes (§40.12.3).

## §41.4 Verdict on "is the NOR accessible now?"

**No.** Nothing found in the app's USB surface offers a flash-read command:

* the uboot routes stay **masked to the internal 1 MiB** — `FLASH_CRC` beyond `0x100000` returns
  byte-identical aliases of the flash head (wrap mod 1 MiB, §40.12.5) and MSC reads address the
  same 1 MiB window;
* the app's CDC-ACM interface 0 answers nothing (ASCII/AT);
* interface 1's bulk pair is unclaimed by the kernel and **`pyusb` is not installed** in this
  environment, so it was not exercised.

Candidate routes to the external `res_nor` bank, all **UNTESTED** (propose, don't flash):

1. **`pip install pyusb` (no sudo) and poke iface 1 bulk `0x04`/`0x84` read-only** — cheap, and
   the maxpacket-clamp warning suggests the vendor PC tool talks to that interface.
2. **usbmon capture of the vendor PC tool** (`update.exe` under Windows, or the Jieli flashing
   tool) while it reads/writes the radio — needs sudo on Linux, user-run; reveals the real
   protocol on iface 0/1 without guessing.
3. **App-side patched reader**: a code cave that calls the `res_nor` read primitive
   (`FUN_01e4caf0` → `FUN_01e4c386(base + off)`, §40.12.4) and streams bytes out over the ACM
   port. This is the only route that is *guaranteed* to reach the bank, but it requires a flash
   and carries the usual risk (stock uboot preserved, sector-level write + read-back).
4. **SDK rebuild** (ch. 28) with a dump command — heaviest, no patch-window archaeology.

## §41.5 Route 1 EXECUTED 2026-11-24 — iface 1 is the ACM data plane, not a hidden channel

`pyusb` was installed in a scratch venv (`/tmp/opencode/usbenv`; system Python 3.14 is PEP-668
externally-managed) and `/tmp/opencode/ch41_usb_poke.py` was run **read-only** against
`4c4a:4155` (bus 1 addr 122) after the user granted node access with
`sudo chmod 666 /dev/bus/usb/001/122`. Measured descriptor layout:

| iface | alt | class/subclass/protocol | endpoints | kernel driver |
|---|---|---|---|---|
| 0 | 0 | `0x02/0x02/0x01` = **CDC ACM control** | `0x85` interrupt (8 B) | bound (`cdc_acm` → `ttyACM0`) |
| 1 | 0 | `0x0A/0x00/0x00` = **CDC DATA** | `0x04` bulk OUT, `0x84` bulk IN (device declares maxpacket **256** → invalid, kernel clamps 64) | bound (`cdc_acm`) |

Config: `bConfigurationValue=1`, `bmAttributes=0x80`, `MaxPower=50 mA`; strings readable once the
node was opened: `Jieli Technology` / `USB Composite Device` / `4150353835323003`.

**Finding: interface 1 is not a separate vendor pipe — it is the DATA side of the same CDC-ACM
pair that `/dev/ttyACM0` is.** `cdc_acm` claims both interfaces (the kernel only prints a line for
the control iface, which is why iface 1 looked "unbound" in `dmesg`). The probe detached
`cdc_acm` from iface 1, claimed it, and performed five 64-byte bulk reads on `0x84`:
**all five returned `[Errno 110] Operation timed out`** → `RESULT: iface1 silent (no bulk IN data)`.
That is the same endpoint `ttyACM0` reads, so it is exactly consistent with §41.2: the port is
idle-silent and answer-silent. The probe then released the interface; it does **not** re-attach
`cdc_acm`, so `ttyACM0` may stay dead until the cable is re-seated (harmless, app unaffected).

**Route 1 verdict: CLOSED — no hidden channel, no flash-read door.** §41.4's assumption that
iface 1 was "unclaimed by the kernel" was wrong and is corrected here. Remaining routes to the
external `res_nor` bank: (2) `usbmon` capture of the vendor PC tool, (3) an app-side patched
reader calling `FUN_01e4caf0`/`FUN_01e4c386(0x100000 + off)` and streaming out over ACM,
(4) SDK rebuild (ch. 28). All still UNTESTED; propose, don't flash.

## §41.6 Why this still matters even though the answer was "silent"

* The running app **does** present a second, app-level USB channel with a serial number — a new
  observability surface for the ch. 39 two-device work (it is *there*, just not speaking yet).
* The `usb_wr_freq_task` / `usb_update2.bin` pair confirms a working **USB write path into the
  app**, which is the mechanism any future reader (route 3) would ride on.
* The maxpacket-clamp + unbound iface 1 is a concrete, cheap next experiment (route 1).
