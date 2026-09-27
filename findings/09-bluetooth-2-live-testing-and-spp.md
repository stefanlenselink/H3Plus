[<< Index](Findings.md)

# Bluetooth HFP — 2. Live testing, the SPP PTT protocol and routing modes (9A.15–9A.22)

### 9A.15 ⭐ Live test #1 — `AT+MPTT=1` is parsed and **actively rejected**

First successful live HFP session against the radio from the Ubuntu box, using `tools/bt_hf_sim.py`.

**Getting connected at all** required making the Linux box present itself as a *real* audio device first. Simply scanning/pairing was not enough — until the adapter advertised the right service class and appeared with a headset icon on a phone, the radio would not connect. Once the adapter exposed `Handsfree`, `Handsfree Audio Gateway`, `Audio Sink`, `Audio Source` and a `Class: 0x007c0000`, pairing and connection succeeded, the radio's screen showed the box's alias (`Gekkie`), and **received audio from other radios played out of the PC speakers** — confirming the downlink audio path works end to end.

**Session transcript (abridged):**

```
Using RFCOMM channel 6
>> AT+BRSF=0
<< +BRSF:878
<< OK
>> AT+CIND=?
<< +CIND: ("service",(0-1)),("call",(0-1)),("callsetup",(0-3)),
         ("callheld",(0-2)),("signal",(0-5)),("battchg",(0-5))
<< OK
>> AT+CIND?     << +CIND: 1,0,0,0,5,5    << OK
>> AT+CMER=3,0,0,1                       << OK
>> AT+MPTT=1                             << ERROR
>> AT+MPTT=0                             << ERROR
```

**Why `ERROR` is a positive result.** The radio *received, parsed and answered* the command. An unknown-command `ERROR` is categorically different from a timeout or a dropped link — it confirms the vendor AT channel is reachable from an arbitrary third-party HF device, and that the command string reaches a parser. Something is rejecting it at the authorisation/precondition stage, not at the transport stage.

#### Unified theory — the whitelist gates the *AT parser*, not the mic path

This reconciles the contradiction that has run through §9A.5 → §9A.11 → §9A.12:

| Component | What it actually does |
|---|---|
| Name whitelist (§9A.5, §9A.13 Result 1) | Compares the peer's name against `TID-PTT` / `TID-MIC` / `TID-MIC-EAR` and stores a small **device-class integer** (1/2/3/4/6). Does **not** touch mic routing — which is why all three branches converge to shared code. |
| Vendor AT parser (§9A.12, §9A.13 Result 2) | Handles `AT+MPTT=0/1`. Very likely **checks that class integer** as a precondition and answers `ERROR` for anything not classified as a TIDRADIO accessory. |
| Mic routing | Driven by the MPTT handler, downstream of both. |

Under this model the flash test in §9A.11 failed *not* because the whitelist is irrelevant, but because patching it only mattered for a device that actually sends `AT+MPTT` — and a Jabra never does. The whitelist is therefore **necessary but not sufficient**; it is the gate on the vendor command channel.

#### Next experiments (cheapest first)

| # | Test | Rationale |
|---|---|---|
| 1 | Set the Linux adapter alias to `TID-PTT` (`bluetoothctl` → `system-alias TID-PTT`), unpair + re-pair, resend `AT+MPTT=1` | Directly tests the unified theory. The peer name is cached at pairing time, so a re-pair is required. |
| 2 | Same with `TID-MIC-EAR`, then `Jabra E` | `Jabra E` is the string currently patched into this unit's flash (§9A.11), so it should be accepted *by this radio only* — a positive here would be conclusive proof the whitelist gates the parser. |
| 3 | Send a realistic `AT+BRSF=756` (`0x2F4`) instead of `AT+BRSF=0` | We currently claim *zero* HF features. Some vendor parsers gate extensions on negotiated feature bits. |
| 4 | Re-run with the SCO fix below and check whether an established audio link changes the reply | The AG may refuse call/audio-related vendor commands while no SCO link exists. |

#### Fixed alongside — SCO socket address format

`tools/bt_hf_sim.py` failed to open the voice channel with `connect(): wrong format` / `bind(): wrong format`. Cause: unlike `BTPROTO_RFCOMM` and `BTPROTO_L2CAP`, which take a `(bdaddr, channel)` tuple, CPython's socket module expects **`BTPROTO_SCO` addresses as a bare bytes object** containing only the bdaddr. Passing a 1-tuple raises `OSError("wrong format")`. Fixed to `s.connect(mac.encode())` / `s.bind(b"00:00:00:00:00:00")`.

### 9A.16 Live test #2 — SCO link established; `AT+MPTT` still rejected

With the address-format fix, the voice channel came up (`SCO: connected outbound`) — so the radio **will** grant a third-party HF device a full SCO audio link. The vendor command was retried with that link active:

```
SCO: connected outbound
>> AT+MPTT=1
<< ERROR
```

**This eliminates experiment #4 from §9A.15:** the rejection is *not* conditional on an audio link existing. `AT+MPTT` is refused even when the radio has already agreed to open a synchronous voice channel with us. The gate is therefore upstream of audio state — consistent with the device-class/whitelist theory, which remains the leading explanation and the next thing to test.

#### Fixed alongside — SCO writes must be exactly one MTU-sized packet

The first write attempt after connecting failed with `SCO write failed: [Errno 22] Invalid argument`, which then cascaded into ffmpeg `Broken pipe` noise as the loop tore down.

Cause: SCO is a **synchronous packet** channel, not a byte stream. Every `send()` must be exactly one HCI SCO packet of the negotiated MTU — writing the tool's arbitrary 480-byte (30 ms) chunks returns `EINVAL`. This is not a codec, format or data problem, and no amount of resampling would have fixed it.

The MTU is retrievable via `getsockopt(SOL_SCO=17, SCO_OPTIONS=1)`, which returns `struct sco_options { uint16_t mtu; }` — typically 48, 60 or 64 bytes for CVSD narrowband. The tool now reads it at connect time, sizes every packet to it, and paces packets at `(mtu / 2) / 8000` seconds each using an absolute (drift-corrected) clock rather than a per-iteration sleep.

### 9A.17 The working connection model — let the *radio* initiate

Outbound discovery was a dead end (§9A.14). The approach that actually works inverts the roles: **make the Linux box look like a real headset and let the radio connect to it.**

The key insight came from a simple sanity check — *on a phone, the Linux box was not showing up with a headset icon.* Until that was true, neither a phone nor the radio would treat it as an audio peer. Fixing the adapter's presentation fixed the connection problem.

**What has to be true on the Linux side:**

| Property | Value | Why |
|---|---|---|
| Class of Device | `0x240404` | Service `0x240000` (rendering + audio), major `0x0400` (audio/video), minor `0x04` (wearable headset). This is what produces the headset icon and makes peers offer audio profiles. |
| **LE advertising** | **`off`** | **The non-obvious one — see below.** |
| Discoverable | `on`, timeout `0` | The radio browses for devices; a timeout of 0 means it never stops advertising mid-experiment. |
| Pairable | `on` | — |
| Agent | `NoInputNoOutput` | "Just works" pairing, matching a real keypad-less headset and minimising prompts. |
| Profiles | `Handsfree`, `Handsfree AG`, `Audio Sink`, `Audio Source` | Must be registered for the peer to see a usable audio service. |

#### ⭐ `advertise off` — why the headset icon wouldn't appear

Even with the correct Class of Device set, the box was still being discovered as a *generic* Bluetooth device. The fix was turning **BLE advertising off**.

The reason: **Class of Device is a BR/EDR-only concept.** BLE has no CoD field at all — it conveys device type through the GAP *Appearance* characteristic instead. While LE advertising is active, a peer scanning for devices can latch onto the LE identity and render it using LE rules, ignoring the classic CoD entirely. Killing LE advertising forces the peer to see only the classic identity, and the headset icon appears. This also dovetails with §9A.14: the LE identity was the one whose address kept rotating, and it was never the endpoint we wanted.

#### Three ways to set the class, in increasing order of persistence

```bash
# 1. legacy ioctl -- immediate, but easily reset by bluetoothd
sudo hciconfig hci0 class 0x240404

# 2. kernel mgmt API via bluetoothctl -- sticks better across profile registration
#    (major, minor) = (0x04, 0x0404)  ->  CoD 0x240404
bluetoothctl
  menu mgmt
  class 0x04 0x0404
  back

# 3. persistent across reboots and daemon restarts -- /etc/bluetooth/main.conf
[General]
Class = 0x240404
# then: sudo systemctl restart bluetooth
```

⚠️ **Class of Device gets reset.** `bluetoothd` commonly overwrites it when profiles register, so method 3 is strongly preferred; `tools/bt_be_headset.sh` additionally applies methods 1 and 2 and re-applies at +4 s and +10 s, then *verifies* the result and warns if it did not stick.

⚠️ **The peer caches the advertised name at pairing time.** Changing the alias therefore requires removing the pairing on *both* sides and pairing again, otherwise the old name remains in force. This matters directly for the §9A.15 experiments, which are all name-based.

**`tools/bt_be_headset.sh`** implements all of the above. It takes the advertised name as its argument — the variable under test — and auto-answers every pairing prompt (`Confirm passkey`, `Authorize service`, `Request PIN code`, `Request passkey`), trusts each peer once paired so it can reconnect unprompted, and prints the ready-to-run `bt_hf_sim.py` command line when a peer connects.

```bash
sudo ./tools/bt_be_headset.sh "TID-PTT"     # then connect FROM the radio
```

**Validate against a phone first.** Before trusting any result from the radio, confirm the HF/SCO plumbing is sound using a device with a known-good HFP implementation: pair a phone with the box, place a call, and check that call audio reaches the PC speakers and that the mp3 is heard by the far end. `bt_hf_sim.py --no-mptt` skips the vendor commands for exactly this purpose, since a phone answers `ERROR` to them and that noise would otherwise obscure the real question.

#### ⚠️ A2DP working is *not* evidence that HFP works

During the phone validation, music from the phone played out of the PC speakers — but that is **A2DP** (the phone's `Audio Source` → our `Audio Sink`), an entirely different profile from the one under test. A2DP streams over L2CAP/AVDTP with its own codecs; HFP runs AT commands over RFCOMM plus voice over SCO. Confirming A2DP proves the pairing and Class-of-Device work, and nothing more. The meaningful phone test is **a phone call**, not music playback.

#### ⚠️ `sdptool records` misses HFP AG on Android

The phone's SDP dump via `sdptool records` returned only GATT, PnP and `Advanced Audio Source` — no Handsfree record, despite the phone certainly running an HFP AG:

```
Service Name: Advanced Audio Source
  "Audio Source" (0x110a)      <- A2DP only; no 0x111F anywhere
```

Cause: `sdptool records` only walks the **public browse group**, and Android does not publish HFP AG there. A direct UUID query does find it. `tools/bt_hf_sim.py` now escalates automatically:

| Step | Command | Notes |
|---|---|---|
| 1 | `sdptool records <mac>` | Fast; sufficient for the radio |
| 2 | `sdptool search --bdaddr <mac> 0x111F` | Handsfree AG UUID — the one Android needs |
| 3 | `sdptool search --bdaddr <mac> 0x1112` | Headset AG UUID, older profile |
| 4 | `sdptool browse <mac>` | Full browse, last resort |

`--channel N` bypasses discovery entirely if needed. Note also that Android will often only expose HFP AG to a peer it has bonded with *as a headset* — the **"Phone calls"** toggle must be enabled for the device in the phone's Bluetooth settings, not just "Media audio".

#### ✅ Phone validation PASSED — the Linux side is fully proven

A real phone call was placed with the phone paired to the Linux box as a headset:

| Direction | Path | Result |
|---|---|---|
| Downlink | far end → phone → SCO → Linux | ✅ friend's voice heard on PC speakers |
| Uplink | Linux audio → SCO → phone → far end | ✅ friend heard audio played on the PC |

This was achieved through **BlueZ + PipeWire's own HFP implementation**, not `bt_hf_sim.py`. That makes it an even stronger result: it independently proves the adapter, the kernel SCO path, CVSD codec negotiation, the Class-of-Device/discoverability setup from §9A.17, and both audio directions all work correctly on this machine.

**Conclusion: every variable on the Linux side is now eliminated.** The sole remaining unknown is the radio's refusal of `AT+MPTT` (§9A.15, §9A.16). Any further failure against the radio is attributable to the radio, not the test rig.

⚠️ **PipeWire and `bt_hf_sim.py` contend for the same resources.** Whichever claims the HFP profile holds the RFCOMM SLC and the SCO socket exclusively. When testing the radio with the raw-socket tool, PipeWire must be stopped first:

```bash
systemctl --user stop pipewire pipewire-pulse wireplumber
```

Conversely, if a future goal is a *practical* relay rather than an experiment, PipeWire's working HFP stack may be the better foundation — the only thing it cannot do is emit the proprietary vendor AT command, which could potentially be injected over a separate RFCOMM connection alongside it.

#### Can PipeWire keep the audio while we inject `AT+MPTT` separately?

Attractive, because PipeWire's HFP implementation is already proven working (above) while `bt_hf_sim.py`'s is hand-rolled. The two resources contend differently:

| Resource | Shareable? |
|---|---|
| **SCO** | ❌ No. One synchronous link per device, period. |
| **RFCOMM AT channel** | ⚠️ Only if a *second* channel exists. A second connection to the same RFCOMM server channel from the same device is refused (same DLCI). |

So it hinges on whether the radio publishes more than one Audio Gateway record — e.g. HFP AG (`0x111F`) and HSP AG (`0x1112`) on different channels. If so, PipeWire takes one and we take the other:

```bash
sdptool browse <radio-mac>     # look for TWO Audio Gateway records
python3 bt_hf_sim.py <radio-mac> unused.mp3 --at-only --no-slc --channel <second channel>
```

`--at-only` opens only the RFCOMM channel and cycles `AT+MPTT=1`/`=0`, never touching SCO, so the audio path stays with PipeWire. `--no-slc` skips the handshake, since PipeWire has already established a service level connection. Success is observable as **TX activity on the radio itself** — no audio plumbing needed on our side to detect it.

If only one AG channel exists, this approach is impossible and PipeWire must be stopped.

Note this also has diagnostic value independent of the audio question: it isolates whether `AT+MPTT` is rejected because of *who is asking* versus *how the link was set up*. If PipeWire's fully standards-compliant SLC also yields `ERROR`, then §9A.15's experiment #3 (the `AT+BRSF` feature-bits theory) is eliminated too, since PipeWire negotiates a complete and realistic feature set.

---

### 9A.18 The radio's RFCOMM channel map (obtained by brute force)

`sdptool browse`, `sdptool records` and `sdptool search` **all return completely empty** for this radio, even while it is connected and bonded. It simply does not answer SDP queries. So the RFCOMM channel cannot be discovered the normal way; `bt_hf_sim.py --probe-channels` brute-forces channels 1–30 instead, and the response *pattern* turns out to identify each endpoint's role unambiguously:

| Ch | Probe result | Interpretation |
|---|---|---|
| 2 | accepts, never sends anything | Not an AT parser. An icon appears on the radio's screen, so likely a control/OTA/SPP-style endpoint. No reply to `AT+MPTT`. |
| 4 | accepts, then **the radio sends us `AT+BRSF=671`** | The radio's **HF role** — it believes *it* is the headset and *we* are the phone. This is its "connect me to a phone" mode. |
| 6 | `EBUSY` | **The HFP Audio Gateway.** Busy only because BlueZ grabbed it on connect. This is the channel used in §9A.15/§9A.16. |
| 10 | accepts, **echoes our bytes back verbatim** | Loopback/echo server. `<< AT+MPTT=1` here is our own string returning, *not* a reply. |
| all others | `ECONNREFUSED` | closed |

**Two traps this exposes, both of which produce convincing false positives:**

1. **The channel 10 echo.** Sending `AT+MPTT=1` and receiving `AT+MPTT=1` looks superficially like a response. It is not — there is no `OK`, no `ERROR`, and no parser. Any AT experiment must treat a byte-identical reply as evidence of an echo server, not of success.

2. **The channel 4 role inversion.** `AT+BRSF=<n>` is an *HF-side* command — the hands-free unit sends it to the audio gateway. Receiving it means the radio has taken the HF role. `AT+MPTT` sent into an HF port is meaningless: that port issues commands, it does not answer AG ones. Silence there says nothing about whether the command is supported.

**Consequence for testing:** only **channel 6** is a valid target, and `EBUSY` must be cleared first. Crucially, once we hold channel 6 exclusively we must run the **full SLC handshake** (i.e. *not* `--no-slc`, which exists only for riding alongside PipeWire's already-established connection) — an uninitialised AT parser is itself a plausible contributor to the `ERROR` responses seen so far.

```bash
systemctl --user stop pipewire pipewire-pulse wireplumber
bluetoothctl disconnect <radio-mac>    # drops BlueZ's profile grab, keeps the bond
python3 bt_hf_sim.py <radio-mac> ghosts.mp3 --at-only --channel 6
```

The general rule extracted from this: **`EBUSY` during a channel probe is a positive signal.** BlueZ only claims channels whose SDP record it recognises as a profile it supports, so a busy channel is far more likely to be the real profile endpoint than any of the freely-accepting ones.

---

### 9A.19 ⭐ Changing approach: capture a genuine accessory instead of guessing

Every test so far has been **inference**: we found `AT+MPTT=0/1` as strings in flash, guessed the syntax and the required preconditions, and received `ERROR`. The name sweep was supposed to resolve the ambiguity, but `TID-PTT` — the most privileged name in the whitelist — produced the same result as `Test456`. At that point continuing the sweep has poor expected value, because a null result cannot distinguish between:

- the name is not the gate at all,
- the name is the gate but some *other* precondition also fails,
- our command syntax or handshake is subtly wrong,
- we are talking to the wrong endpoint entirely.

A genuine TIDRADIO PTT accessory resolves all four at once, by **showing** us the protocol rather than letting us guess it. The PC impersonates the radio; the accessory tells us exactly what it sends.

**Role inversion.** The accessory is an HF unit looking for an **Audio Gateway**. This is the opposite of §9A.17, where we impersonated a headset so the radio would connect to us.

⚠️ **But the *connection* direction is the opposite of what "server" intuition suggests.** The first attempt here listened for an inbound connection from the button, and nothing ever arrived. The reason is physical: the PTT button has no screen and no input beyond its one key, so it **cannot scan and choose a target**. It advertises and waits; the **radio** does the scanning and initiates. Therefore the button is the RFCOMM *server*, and our PC must **connect outbound to it** while still speaking the AG half of the protocol.

Profile role and connection role are independent here — we are the AG, but the *client*.

| | §9A.17 (radio → PC) | §9A.19 (PC → PTT button) |
|---|---|---|
| PC's profile role | headset (HF) | **the radio (AG)** |
| Who initiates | the radio | **the PC** |
| PC's RFCOMM role | client | **client** |
| PC Class of Device | `0x240404` wearable headset | `0x5a020c` smartphone |
| Tool | `bt_be_headset.sh "<name>"` | `bt_ag_capture.py --connect <mac>` |

`bt_ag_capture.py` supports both directions: `--connect <mac>` (correct for the button) and `--listen` (retained, correct for the radio). Since these devices routinely do not answer SDP at all (§9A.18), `--connect` brute-forces the channel when none is given.

**A passive sniffer is not enough.** An HF unit that receives no reply to `AT+BRSF` aborts the connection within seconds, long before it does anything interesting. `bt_ag_capture.py` therefore implements a *convincing* AG: it answers `+BRSF`, `+CIND` test/status, `+CHLD`, codec negotiation and the rest, so the accessory completes its SLC and proceeds to real behaviour. Unrecognised commands are answered **`OK` by default** (`--unknown-reply ok`) — an `ERROR` risks the accessory giving up before it reveals the very command we are hunting. Every unknown command is logged with a banner; those lines are the entire point.

**What it captures, beyond the AT stream:** on connect it snapshots `bluetoothctl info`, `hcitool info`, the full `sdptool browse`, and critically the **Device ID / PnP record (UUID `0x1200`)**, which carries vendor and product IDs. If the radio's gate is not the device name, a PnP vendor ID is the most plausible alternative — and we currently have no way to observe that from the radio side.

**Prerequisite — bluetoothd compat mode.** Only required for `--listen`, since it is `sdptool add` that needs the legacy SDP control socket:

```bash
sudo systemctl edit --full bluetooth     # append --compat to ExecStart
sudo systemctl daemon-reload && sudo systemctl restart bluetooth
sudo chmod 666 /var/run/sdp
```

**Procedure (outbound — the one that should work for the button):**
```bash
systemctl --user stop pipewire pipewire-pulse wireplumber
sudo python3 tools/bt_ag_capture.py --scan             # find the button's MAC
bluetoothctl pair <button-mac> && bluetoothctl trust <button-mac>
sudo python3 tools/bt_ag_capture.py --connect <button-mac>
# then PRESS THE PTT BUTTON
```

Pressing the button while connected is essential — the vendor command is presumably emitted on the key event, not at connect time.

**Expected outcomes, all of them useful:**

| Observation | Conclusion |
|---|---|
| Accessory sends `AT+MPTT=1` on press | Syntax confirmed verbatim; compare its SLC against ours to find the missing precondition |
| It sends a *different* vendor command | Our whole target was wrong; the flash strings may be for a different accessory generation |
| It sends nothing on press | PTT is signalled out-of-band (e.g. HFP button/`AT+CKPD`, or a GATT characteristic) |
| Its PnP/name differs from what we impersonated | Identifies the real gate |

<!-- markdownlint-disable-next-line MD036 -->
*Supersedes the remaining name-sweep entries (`TID-MIC-EAR`, `TID-MIC`, `Jabra E`) as the highest-value next action. Those remain worth running afterwards, since the capture will tell us what a correct attempt should look like.*

---

### 9A.20 ⭐⭐ SOLVED: the real PTT protocol is `+SPP=P` / `+SPP=R` over SPP

A genuine **TID-PTT** accessory was captured with `bt_ag_capture.py --connect`. It revealed that **`AT+MPTT` was the wrong target entirely.**

Raw bytes, repeating as the button was pressed and released:

```
2b 53 50 50 3d 50 00   =   "+SPP=P\0"     PTT PRESSED
2b 53 50 50 3d 52 00   =   "+SPP=R\0"     PTT RELEASED
```

| | What we assumed (§9A.12–§9A.16) | What the button actually does |
|---|---|---|
| Transport | HFP / RFCOMM channel 6 | **SPP** (Serial Port Profile) |
| Prefix | `AT+` | **none** — literally `+SPP=` |
| Terminator | `\r` (CR) | **`\0`** (single NUL byte) |
| Handshake first | full SLC (`AT+BRSF`, `AT+CIND`…) | **none at all** |
| Reply expected | `OK` | none — fire and forget |

**Any one of these differences was sufficient to cause the `ERROR` results.** All four were wrong simultaneously.

**This retroactively explains §9A.18 channel 2** — the endpoint that accepted connections, never replied, and made an icon appear on the radio's screen. That was the SPP port. We were sending AT commands into a port speaking a completely different protocol, so silence was the only possible outcome. The `EBUSY` channel 6 we were so keen to reach was a red herring; it is the standard HFP AG, used for ordinary audio.

**Observed behaviour details:**
- Release is usually sent **twice** in one packet (`...52 00 2b 53 50 50 3d 52 00`). Press is sent once.
- Messages are fire-and-forget; the button neither waits for nor reacts to a reply. Our AG answered nothing and it carried on regardless.
- Occasionally press and both releases arrive coalesced in a single RFCOMM frame — a receiver must frame on NUL, not assume one message per packet.

**Peer identity snapshot** (also valuable, and previously unobtainable):

| Field | Value |
|---|---|
| Name | `TID-PTT0cd28a-B` |
| Class of Device | `0x00240404` — **identical to what §9A.17 has us advertising** |
| UUIDs | Serial Port (`0x1101`) **and** Handsfree (`0x111E`) |
| Manufacturer | Zhuhai Jieli Technology (1494) — same silicon vendor as the radio |
| LMP | 5.3, subversion `0x22bb` |
| Device ID (PnP, `0x1200`) | none published |

The name is `TID-PTT` + a per-unit hex suffix + `-B`, consistent with the `TID-PTT` whitelist entry found in flash (§9A.5) being matched as a **prefix** rather than an exact string. Note the accessory exposes Handsfree *as well as* SPP — so HFP likely still carries the audio, while SPP carries the key events. That division of labour is why hunting for PTT on the HFP channel was doomed.

**Tooling:** `tools/bt_spp_ptt.py` replays this protocol at the radio:

```bash
sudo python3 tools/bt_spp_ptt.py 0B:FF:59:E8:85:92            # 5s on / 5s off
sudo python3 tools/bt_spp_ptt.py 0B:FF:59:E8:85:92 --once --hold 3
```

It defaults to channel 2 and always sends a release on exit, so the radio cannot be left keyed.

**Why this matters for the whitelist question.** If `+SPP=P` keys the radio while we are advertising an arbitrary name, the name whitelist is irrelevant to PTT and §9A.5/§9A.11's contradiction dissolves. If it only works when our advertised name begins with `TID-PTT`, the whitelist is confirmed as the gate — and the name sweep becomes meaningful again, now over the correct transport. Either way the experiment is finally being run against the protocol the hardware actually uses.

**Lesson.** Logging raw bytes alongside parsed lines is what rescued this. A CR/LF line parser would have decoded nothing and reported "the accessory sent nothing on press" — a confident, completely wrong negative result.

---

### 9A.21 The radio waits for a PROFILE connection, not just an ACL link

The radio gives audio and on-screen feedback when Bluetooth connects and disconnects, but has **no menu showing an active connection**, which made this hard to pin down. Two observations together give the answer:

> 1. The radio announced "Bluetooth Connected" **at the exact moment `bt_spp_ptt.py` opened the SPP socket**, and "Bluetooth Disconnected" three seconds later when `--once` exited and the socket closed.
> 2. A stock **Jabra Evolve 65 connects normally** and the radio reports "Bluetooth Connected" — and that headset does not speak SPP at all.

So the trigger is **not SPP specifically**; it is *any successful profile-level connection*. SPP simply happened to be the one we supplied. The Jabra supplies HFP/A2DP instead.

| Stage | BlueZ says | Radio says |
|---|---|---|
| ACL/baseband connected, no profile accepted | `Connected: yes` | **"Connecting ..."** — no confirmation tone |
| Any profile connects (HFP, A2DP **or** SPP) | (unchanged) | **"Bluetooth Connected"** + on-screen |
| Last profile closes | (unchanged) | **"Bluetooth Disconnected"** |

#### ⚠️ Why our PC failed where a Jabra succeeds: stopping PipeWire

Every test procedure so far began with:

```bash
systemctl --user stop pipewire pipewire-pulse wireplumber
```

That was added to avoid contention over the HFP channel (§9A.17). But **PipeWire/WirePlumber is what implements the Handsfree profile on the PC.** With it stopped, nothing owns HFP, so the radio's profile connection is refused and it waits on "Connecting ..." indefinitely. BlueZ still reports `Connected: yes` because the ACL link is up — which is exactly the misleading state we kept seeing.

**This is no longer necessary, because SPP is a different RFCOMM channel.** The radio's endpoints (§9A.18) are channel 6 = HFP AG, channel 2 = SPP. PipeWire can hold channel 6 for audio while we independently hold channel 2 for PTT. The earlier contention worry applied only when we were trying to inject `AT+MPTT` onto the *same* HFP channel PipeWire owned — an approach §9A.20 retired.

**Revised procedure — leave PipeWire running:**

```bash
# do NOT stop pipewire
sudo ./tools/bt_be_headset.sh "Test456"
# connect from the radio; PipeWire answers HFP, radio says "Bluetooth Connected"
sudo python3 tools/bt_spp_hold.py 0B:FF:59:E8:85:92    # channel 2, PTT
```

**Consequences of the waiting state:**

1. **A one-shot PTT tool is the wrong shape** if it is the *only* thing holding a profile open: connecting, sending a keypress and exiting makes the radio connect and immediately disconnect. With PipeWire also connected via HFP this matters much less, since the HFP link persists independently.
2. ⚠️ **The "Connecting ..." state is dangerous.** If the radio is left waiting there and then poked again from its own paired-devices menu, it **locks up hard and needs a power cycle**. Observed repeatedly.
3. `Reason.Remote, Connection terminated by remote user` disconnects are the radio giving up on that wait — not a pairing or authentication failure.

**Tooling:** `tools/bt_spp_hold.py` holds the SPP link open indefinitely and offers interactive PTT (`Enter` = press+release, `p`/`r` = hold/release, `s` = status, `q` = quit), or `--cycle` for hands-free repetition. `bt_be_headset.sh` also accepts `SPP_AUTO=1` to launch it automatically when a peer connects:

```bash
SPP_AUTO=1 sudo -E ./tools/bt_be_headset.sh "Test456"
```

**Diagnostic value of the Jabra.** It is a known-good reference for the whole connection path, in the same spirit as the phone-call validation in §9A.17. If the Jabra connects and the PC does not, the fault is on the PC side, not the radio's.

#### Two `bt_be_headset.sh` bugs found in the same transcript

**Commands were being silently dropped.** The log showed `discoverable-timeout 10` (the script sends `0`) and, critically, `Discoverable: no` in the `show` output — the `discoverable on` line never executed, with no error anywhere. bluetoothctl is an interactive readline program, not a batch processor: input arriving while it is busy is **discarded silently**. Fixed by pacing every command with a short delay and re-asserting discoverability a few seconds later.

**The mgmt `class` command was wrong again**, producing `0x6c0000` this time (it produced `0x7c0000` with the previous encoding, §9A.18 notes). In both cases the subsequent `hciconfig` re-apply is what actually set `0x240404`. The mgmt call has now been **removed entirely** — it was never doing anything useful and briefly advertised a bogus class to anything scanning at that instant. `hciconfig` plus `/etc/bluetooth/main.conf` are sufficient.

---

### 9A.22 ⭐⭐⭐ FULL DUPLEX ACHIEVED — the name selects an AUDIO ROUTING MODE

**End-to-end voice both ways, plus working PTT, under the advertised name `TID-MIC-EAR`.** Desktop audio → radio → distant radio, and distant radio → radio → desktop, simultaneously.

The decisive discovery is *why* that name mattered. Four names were tested with everything else held constant:

| Advertised name | TX: PC → radio → air | RX: air → radio → PC | Notes |
|---|---|---|---|
| **`TID-MIC-EAR`** | ✅ | ✅ | **full duplex** |
| **`TID-MIC`** | ✅ | ✅ | **identical to `TID-MIC-EAR` — not a distinct mode** |
| `TID-PTT0cde28a-B` | ✅ | ❌ | simplex; received traffic **always** on the radio's own speaker |
| `TID-TEST456` / `Test456` | ❌ | ✅ | simplex; unrecognised → generic sink |

So there are **three** observed behaviours, not four:

| Mode | Names | Mic source | Received audio |
|---|---|---|---|
| Full duplex | `TID-MIC`, `TID-MIC-EAR` | Bluetooth peer | to Bluetooth peer |
| PTT-button | `TID-PTT…` | Bluetooth peer | radio's own speaker |
| Generic sink | anything unrecognised | radio's own mic | to Bluetooth peer |

**`TID-MIC` and `TID-MIC-EAR` behave identically.** The `-EAR` suffix does not select a separate routing, which is a useful negative: the whitelist has fewer distinct *behaviours* than it has *entries*, consistent with §9A.5's device-class integer mapping several names onto the same branch.

#### ⭐ PTT is NOT gated by the name — only audio ROUTING is

The single most important refinement. Under the unrecognised name `TID-TEST456`, sending `+SPP=P` **still keys the transmitter** — but the audio transmitted comes from **the radio's own microphone**, not from the Bluetooth link.

This cleanly separates two mechanisms that had been conflated for the entire investigation:

| Mechanism | Gated by the name? |
|---|---|
| **PTT / TX keying** via `+SPP=P` over SPP | ❌ **No.** Works under any name, including unrecognised ones. |
| **Which microphone feeds TX** | ✅ **Yes.** Only whitelisted names route the Bluetooth peer's audio into TX. |
| **Where received audio goes** | ✅ **Yes.** |

It also retroactively explains §9A.12's observation 4 — *"mic source follows which PTT was pressed"*. That was really the routing mode being applied at key-up time, not the PTT origin selecting a mic.

The names are descriptive of exactly what they select:

| Name | Meaning | Routing selected |
|---|---|---|
| `TID-PTT` | push-to-talk button | TX from BT mic; RX stays on the radio — a button has no earpiece |
| `TID-MIC` | speaker-mic | both directions |
| `TID-MIC-EAR` | "mic + earpiece" | both directions (same as above) |
| unrecognised | generic headset | RX to BT; TX uses the radio's own mic |

`TID-MIC-EAR` was flagged as "especially suggestive — a named mode combining microphone and earpiece" back in §9A.2. That reading was correct.

**Prefix matching is confirmed.** `TID-PTT0cde28a-B` selected the PTT-button mode, so the stored `TID-PTT` is matched as a **prefix**, not an exact string — consistent with the genuine button naming itself `TID-PTT0cd28a-B` (§9A.20). Note also that `TID-TEST456` was *not* matched despite sharing the `TID-` prefix, so the compare is longer than 4 characters — it is matching against the full stored entry, not merely the vendor prefix.

#### Volume

**Bluetooth audio level is controlled by the radio's physical volume knob**, not by the PC-side mixer. Worth knowing before concluding that audio is absent — a low knob setting looks identical to a broken route.

#### ⚠️ The radio's own PTT key always uses the radio's own microphone

Tested under `TID-MIC-EAR` with the link up and duplex audio confirmed working: pressing the **radio's physical PTT key** transmits **the radio's own mic**, immediately, with no Bluetooth involvement.

So the routing mode does *not* redirect the local PTT key. The mic source is chosen by **which PTT was pressed**, and the name only selects what the *Bluetooth-originated* PTT does:

| PTT origin | Mic used | Gated by the name? |
|---|---|---|
| Radio's own PTT key | Always the radio's own mic | ❌ No — the name is irrelevant |
| `+SPP=P` over Bluetooth | Per the routing mode (§ above) | ✅ Yes |

This **partially reverses** the retroactive re-reading of §9A.12 observation 4 given above. That observation — *"mic source follows which PTT was pressed"* — was literally correct after all for the local key. The refinement that survives is narrower but still holds: for a **Bluetooth-originated** keypress, the mic source is set by the routing mode rather than by the keypress itself, which is what the `TID-TEST456` test demonstrated.

**Consequence for the stretch goal:** a headset cannot be made to transmit its own mic via the radio's front-panel key. Any "press a physical button, transmit the headset mic" arrangement must send `+SPP=P` over a Bluetooth link — i.e. it needs the button and the headset to be *the same* device, or it needs multipoint (§9A.7).

> ✅ **Overturned by §9A.44.** True for the *stock* firmware only. A 1-byte change per key edge makes a radio key push the same virtual key code as `+SPP=P`. PF1/PF2 now transmit a generic headset's mic on hardware.

#### ⚠️ Repeated PTT fails on the duplex modes — a real, reproducible bug

> ✅ **Not reproduced with a real headset (§9A.44).** With a Jabra Evolve 65 in mode 4 and the key-code patch, every PF1/PF2 press transmitted headset audio, indefinitely. The failure below was seen with a Linux PC (BlueZ/PipeWire) acting as the headset. It is therefore most likely host-side (hypothesis 2), not a radio bug.

| Mode | Repeated press/release cycles |
|---|---|
| `TID-PTT…` | ✅ works indefinitely |
| `TID-MIC` / `TID-MIC-EAR` | ❌ **first transmission only** |

On the duplex modes, the first `+SPP=P` transmits correctly. The second and all subsequent ones produce **a few milliseconds of audio and then silence**; further toggling yields silence entirely. The link stays up and the radio still keys — only the *audio* stops.

This is the single most important open problem, since it blocks practical use of the duplex mode.

**Result of the first discriminating test (2026-09-20): disconnecting and reconnecting the SPP link does NOT restore audio.** A fresh SPP session on a still-connected radio keys the transmitter again but carries no audio. This **rules out the SPP session itself** as the stuck component — the fault lives in the audio path (the SCO/A2DP transport, or a radio-side audio-routing state), and it **survives SPP teardown**, so whatever latched is not reset by the thing we control most directly.

Remaining hypotheses, re-ranked in light of that:

1. **The SCO/eSCO voice link is torn down after the first transmission and never re-established.** Still the leading candidate and now the strongest: an audio-transport fault is exactly what survives an SPP reconnect. The few-milliseconds-then-silence signature fits a stream that starts and immediately starves. That `TID-PTT` mode is unaffected is consistent: it may keep a persistent uplink rather than re-negotiating per key-up.
2. **PipeWire drops or suspends the SCO transport** between transmissions on the PC side — a node suspending on idle produces exactly this, and is likewise untouched by an SPP reconnect. Promoted above hypothesis 3.
3. **A state machine in the radio expects something we are not sending on release.** The genuine button sends `+SPP=R` **twice** (§9A.20); if the second release doubles as an acknowledgement or reset, a single release could leave the radio half-latched. `bt_spp_hold.py` already double-releases by default, but `--no-double-release` makes this directly testable. Demoted: a purely SPP-level protocol desync would most likely have been cleared by the SPP reconnect that we now know does nothing.

**Next diagnostic steps**, in order of how much they would narrow things down:

1. **Full `bluetoothctl disconnect` + `connect`** (not just SPP) while the radio stays powered. If audio returns, the fault is in the host-side transport (hypothesis 1 or 2) and is recoverable without touching the radio. If it does **not**, the latch is inside the radio and survives the whole link.
2. **Power-cycle the radio only.** Establishes whether anything short of a reset clears it.
3. **Watch `pactl list cards` / `wpctl status` across two consecutive transmissions** to see whether the card's active profile or the SCO transport disappears between them — this separates hypotheses 1 and 2 directly.
4. Check whether a longer `--gap` recovers it, and test `--no-double-release` for hypothesis 3.

#### ⭐⭐⭐ Step 3 result (2026-09-22): the radio's Bluetooth stack is CRASHING

`wpctl status` was captured at two points, and the result reframes the whole problem.

**Immediately after "Bluetooth Connected":** the radio does not appear in PipeWire at all. No device, no sink, no source.

**After the first two `+SPP=P` sends:**

```
 ├─ Devices:
 │      48. Built-in Audio                      [alsa]
 │      49. Built-in Audio                      [alsa]
 │      75. TD-H3-Plus-6396                     [bluez5]      ← appeared
 ├─ Sinks:
 │  *   56. Built-in Audio Analog Stereo
 ├─ Sources:
 │      57. Built-in Audio Analog Stereo
```

⚠️ **The radio is present as a `bluez5` *device* but has NO sink and NO source.** A BlueZ device with no audio nodes means **no profile is actually routing audio**. So the duplex audio that does work is not flowing through a steady, PipeWire-managed stream at all — it must ride a **transient SCO link** that comes and goes around each key-up, never long enough to materialise as a persistent node. This alone explains why the audio is so fragile.

**And then, directly after the second `+SPP=P`: the radio reports "Bluetooth Disconnected" and re-connects by itself a few seconds later.**

That is the decisive observation. This is not audio routing failing — **the radio's Bluetooth stack is dropping the link and recovering.** The user's own reading is the correct one:

> *"To me it sounds like we hit / trigger a bug on the Radio's bluetooth stack"*

Every previously unexplained symptom now follows from a single cause:

| Symptom | Explained by the crash |
|---|---|
| A few ms of audio then silence | The SCO link is torn down mid-stream as the stack falls over |
| SPP reconnect doesn't help | We reconnect *after* the stack has already reset itself |
| Only the *first* TX works | The first `+SPP=P` leaves the stack in a bad state; the second finishes it |
| `TID-PTT…` mode is immune | It uses a different, simpler audio path that never triggers the fault |
| No sink/source in PipeWire | The link never stabilises long enough to build one |

#### The RF side is provably fine

During the second (silent) transmission, pressing keys on the radio produced **DTMF tones that were heard on the distant radio**. So the transmitter keyed, the RF path worked, and the distant radio received — **only the Bluetooth-sourced audio was missing**. This cleanly isolates the fault to the Bluetooth audio path and rules out any RF, PTT-keying or whitelist explanation.

It also retires hypothesis 3 entirely: a release-handshake desync cannot disconnect the link.

#### Revised conclusion

Hypotheses 1 and 2 were both too generous — they assumed an orderly transport that merely stops. The reality is a **radio-side firmware fault**: repeated SCO setup/teardown in the duplex routing mode destabilises the BR23 Bluetooth stack until it drops the ACL link entirely.

**This is not fixable from the Linux side.** No amount of PipeWire configuration, `--gap` tuning or release-protocol adjustment will stop a peer's stack from crashing. That has three consequences:

1. **The `TID-PTT…` routing mode is the reliable one** for any practical build, at the cost of received audio going to the radio's own speaker.
2. **It raises the value of the firmware route (§9A.23) considerably** — this is now a *firmware bug to be fixed*, not merely a feature to be added. But it also raises the difficulty: patching an audio-routing crash is far harder than redirecting an event.
3. **A newer firmware may already fix it.** The `FW/` directory holds versions up to `TD-H3-PlusV1.0.50`; the unit runs v1.0.50, but **older** versions are available and a differential analysis (§10) against the SCO/audio code could reveal whether this path changed. Worth checking release notes or simply testing an older build before investing in reverse engineering.

**Next step:** confirm reproducibility — does the disconnect happen on the second `+SPP=P` *every* time, and does it also happen under `TID-PTT…` if pushed harder? If the crash is specific to the duplex routing mode, that narrows the firmware search to the code that switches the BT audio path.


#### Why the earlier "whitelist is not the gate" conclusion looked right

§9A.13 tested the whitelist by sending `AT+MPTT` and watching for `OK`. That test could never succeed regardless of name, because the protocol itself was wrong (§9A.20) — so every name failed identically and the whitelist looked irrelevant. **Two independent unknowns were being varied against a broken measurement.** Only after the transport was correct did the name variable become observable.

#### Open anomalies

1. ⚠️ **Repeated PTT fails on the duplex modes** — see above. Highest priority.
2. ⚠️ **`BT Int Spk` re-enables itself.** Setting it to *off* does not stick. With `TID-PTT…`, received audio played on the radio's own speaker regardless — consistent with the routing mode overriding this menu item.
3. `BT Int Mic` stayed *off* as expected, so the two settings are not simply symmetrical.

#### Reproducing it

```bash
# leave PipeWire RUNNING
sudo ./tools/bt_be_headset.sh "TID-MIC-EAR"
# connect from the radio; the script now issues the profile connect-back itself
sudo python3 tools/bt_spp_hold.py 0B:FF:59:E8:85:92    # PTT
```

⚠️ The peer caches the name at **pairing** time (§9A.17), so changing names requires removing the pairing on **both** sides.

> **Flash state:** these results were obtained with the whitelist **unpatched**. The `Jabra E` patch at `0xA0000` (§9A.11) has been rolled back and hash-verified against the original `543addb7…8afa62`, so `TID-MIC` is once again the stock string and every result above reflects **stock firmware behaviour**.

---

*[<< Index](Findings.md)*
