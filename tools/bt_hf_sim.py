#!/usr/bin/env python3
"""
Minimal Bluetooth Hands-Free (HF) role simulator, built to test whether the
TIDRADIO H3 Plus's proprietary AT+MPTT command is what gates Bluetooth mic
routing (see Findings.md 9A.12).

This intentionally does NOT use PulseAudio / PipeWire / oFono / BlueALSA --
none of them will let you inject a non-standard vendor AT command. Instead
it opens two raw Bluetooth sockets directly against the kernel's Bluetooth
stack:

    1. RFCOMM  - the HFP AT command channel (the "Service Level Connection")
    2. SCO     - the synchronous voice channel: raw 8 kHz, 16-bit, mono PCM.
                 (CVSD encode/decode happens in the Bluetooth chip itself;
                 userspace just reads/writes plain PCM samples.)

Behaviour: connects, performs the minimal HF-side SLC handshake, then
forever cycles:
    10s "on"  -> send AT+MPTT=1, stream <mp3> (via ffmpeg) into the SCO link
    10s "off" -> send AT+MPTT=0, stream silence
while continuously forwarding whatever PCM the radio sends back to `aplay`,
so you can listen live.

This is exploratory/best-effort: the exact SCO establishment direction and
codec parameters are not documented for this radio. Run `sudo btmon` in a
second terminal while testing -- if this script doesn't work first try, the
btmon trace will show exactly what the radio actually asked for, which is
more informative than guessing further from this side.

Prerequisites (Ubuntu):
    sudo apt install bluez bluez-utils ffmpeg alsa-utils
    systemctl --user stop pipewire pipewire-pulse wireplumber   # avoid races
    # pair + trust the radio first via bluetoothctl (see Findings.md)

Usage:
    sudo python3 tools/bt_hf_sim.py AA:BB:CC:DD:EE:FF audio.mp3
    sudo python3 tools/bt_hf_sim.py AA:BB:CC:DD:EE:FF audio.mp3 --channel 13
    sudo python3 tools/bt_hf_sim.py AA:BB:CC:DD:EE:FF audio.mp3 --on 10 --off 10
"""
# Copyright (c) 2026 Stefan Lenselink <Stefan@lenselink.org>
#
# SPDX-License-Identifier: MIT
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
import errno
import re
import socket
import struct
import subprocess
import sys
import threading
import time

SAMPLE_RATE = 8000       # narrowband HFP: 8 kHz, 16-bit signed mono PCM
BYTES_PER_SAMPLE = 2
CHUNK_MS = 30            # write PCM in ~30ms chunks, paced to real time
CHUNK_BYTES = int(SAMPLE_RATE * BYTES_PER_SAMPLE * CHUNK_MS / 1000)

# HF's supported-features bitmap sent in AT+BRSF. Minimal/conservative set:
# bit0 EC/NR, bit1 3-way calling (unused), bit3 CLI presentation (unused).
# Kept simple; the radio's own AT+BRSF reply tells us what it supports.
HF_BRSF = 0


def _scan_sdp_text_for_channel(out):
    """Find an RFCOMM channel in a block of sdptool output mentioning HFP/HSP AG."""
    blocks = re.split(r"(?=Service RecHandle:)", out)
    # Prefer Handsfree AG, then generic Audio Gateway, then Headset AG.
    for needle in ("Handsfree Audio Gateway", "Handsfree", "Audio Gateway",
                   "Headset Audio Gateway", "0x111f", "0x1112"):
        for b in blocks:
            if needle.lower() in b.lower():
                m = re.search(r"Channel:\s*(\d+)", b)
                if m:
                    return int(m.group(1))
    return None


def probe_rfcomm_channels(mac, lo=1, hi=30):
    """
    Brute-force which RFCOMM channels accept a connection.

    Needed because this radio does not answer SDP browse requests at all --
    `sdptool browse <mac>` returns an empty list even while connected, so
    there is no record to read the AG channel from. Trying to connect to each
    channel in turn is crude but definitive.

    Returns a list of channels that accepted a connection.
    """
    print("Probing RFCOMM channels %d-%d on %s (SDP gave us nothing)..." % (lo, hi, mac))
    open_channels = []
    busy_channels = []
    for ch in range(lo, hi + 1):
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        s.settimeout(3.0)
        try:
            s.connect((mac, ch))
            print("  channel %2d: OPEN" % ch)
            open_channels.append(ch)
            # Some channels only speak when spoken to, others greet us first.
            # Listen briefly so the caller can tell an AT parser from an echo
            # server from a silent endpoint.
            s.settimeout(1.5)
            try:
                greeting = s.recv(256)
                if greeting:
                    print("      unsolicited: %r" % greeting)
            except OSError:
                pass
        except OSError as e:
            if e.errno == errno.EBUSY:
                print("  channel %2d: BUSY (held by another stack)" % ch)
                busy_channels.append(ch)
            else:
                print("  channel %2d: %s" % (ch, e))
        finally:
            try:
                s.close()
            except Exception:
                pass
        time.sleep(0.2)

    if open_channels:
        print("\nOpen RFCOMM channels: %s" % open_channels)
        print("Re-run with --channel <N> against one of these.")
    else:
        print("\nNo RFCOMM channels accepted a connection. Is the radio still connected?")

    if busy_channels:
        print("\nBUSY channels: %s" % busy_channels)
        print("EBUSY means the channel exists but something else (BlueZ/PipeWire/oFono)\n"
              "already holds it. On this radio that is the STRONGEST signal that the\n"
              "channel is the real HFP Audio Gateway -- BlueZ only grabs channels whose\n"
              "SDP record it recognises as a profile it supports. Free it with:\n"
              "  systemctl --user stop pipewire pipewire-pulse wireplumber\n"
              "  bluetoothctl disconnect <mac>        # keeps the bond, drops the grab\n"
              "then retry --channel %d WITHOUT --no-slc." % busy_channels[0])

    print("\nHow to read the other results:")
    print("  * a channel that accepts but NEVER replies      -> not an AT parser")
    print("  * a channel that ECHOES your bytes back exactly -> loopback/SPP, not AT")
    print("  * a channel that sends YOU 'AT+BRSF=<n>'        -> the radio's HF role:")
    print("      it believes IT is the headset and YOU are the phone. AT+MPTT sent")
    print("      into that port is meaningless -- HF ports issue commands, they do")
    print("      not answer AG ones.")
    return open_channels


def sdptool_find_ag_channel(mac):
    """
    Look up the Handsfree Audio Gateway RFCOMM channel.

    `sdptool records` only walks the PUBLIC BROWSE GROUP, and some peers
    (notably Android phones) do not publish HFP AG there -- you get back only
    GATT/PnP/A2DP entries and no Handsfree record at all, even though the
    phone absolutely does run an HFP AG. So we escalate:

        1. sdptool records          (fast, works for the radio)
        2. sdptool search 0x111F    (Handsfree AG UUID, direct query)
        3. sdptool search 0x1112    (Headset AG UUID, older profile)
        4. sdptool browse           (full browse, last resort)

    If all of that fails we raise with the collected output, since at that
    point the peer genuinely may not be offering an HFP AG.
    """
    attempts = [
        (["sdptool", "records", mac], "records"),
        (["sdptool", "search", "--bdaddr", mac, "0x111F"], "search HFP-AG (0x111F)"),
        (["sdptool", "search", "--bdaddr", mac, "0x1112"], "search HSP-AG (0x1112)"),
        (["sdptool", "browse", mac], "browse"),
    ]

    collected = []
    for cmd, label in attempts:
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise RuntimeError(
                "sdptool not found. Install bluez-utils, or pass --channel N."
            )
        except subprocess.CalledProcessError as e:
            collected.append("--- %s: failed (%s) ---" % (label, e))
            continue

        ch = _scan_sdp_text_for_channel(out)
        if ch is not None:
            print("Found HFP/HSP AG via 'sdptool %s'" % label)
            return ch
        collected.append("--- %s ---\n%s" % (label, out.strip() or "(empty)"))

    raise RuntimeError(
        "Could not find a Handsfree/Headset Audio Gateway RFCOMM channel for %s.\n\n"
        "If this is an Android phone: HFP AG is often only advertised while the\n"
        "phone considers a headset connected, and it may refuse to publish the\n"
        "record to a peer it has not bonded with as an audio device. Make sure\n"
        "the phone shows this machine as a paired HEADSET (not just 'connected\n"
        "for media'), and that 'Phone calls' is enabled for it in the phone's\n"
        "Bluetooth device settings.\n\n"
        "You can also bypass this entirely with --channel N. Common AG channels\n"
        "are 1-13; try: sdptool browse %s\n\n"
        "Collected SDP output:\n%s" % (mac, mac, "\n\n".join(collected))
    )


class RfcommAt:
    """Very small HFP AT command helper over a blocking RFCOMM socket."""

    def __init__(self, mac, channel):
        self.sock = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
        )
        self.sock.connect((mac, channel))
        self.buf = b""
        self._lock = threading.Lock()

    def send(self, cmd):
        print(">> %s" % cmd)
        with self._lock:
            self.sock.sendall((cmd + "\r").encode())

    def read_line(self, timeout=3.0):
        """Read until \\r or \\n terminated line, or return None on timeout."""
        self.sock.settimeout(timeout)
        while b"\r" not in self.buf and b"\n" not in self.buf:
            try:
                data = self.sock.recv(512)
            except socket.timeout:
                return None
            if not data:
                return None
            self.buf += data
        line, _, self.buf = self.buf.partition(b"\n")
        line = line.strip(b"\r\n ")
        if line:
            print("<< %s" % line.decode(errors="replace"))
        return line.decode(errors="replace") if line else ""

    def expect_ok(self, timeout=3.0):
        """Drain lines until OK/ERROR or timeout; return True on OK."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.read_line(timeout=max(0.1, deadline - time.time()))
            if line is None:
                return False
            if line == "OK":
                return True
            if line.startswith("ERROR"):
                return False
        return False


def slc_handshake(at):
    """Minimal HF-side Service Level Connection establishment."""
    at.send("AT+BRSF=%d" % HF_BRSF)
    at.expect_ok(timeout=3)
    at.send("AT+CIND=?")
    at.expect_ok(timeout=3)
    at.send("AT+CIND?")
    at.expect_ok(timeout=3)
    at.send("AT+CMER=3,0,0,1")
    at.expect_ok(timeout=3)
    print("--- SLC handshake done (AG may not have understood every line; "
          "check the << replies above) ---")


def open_sco(mac):
    """
    Try to establish the SCO audio link. Direction of who opens SCO first is
    not documented for this radio, so we try both:
      1. connect out to the AG ourselves (mirrors how some HF units request audio)
      2. if that fails, listen for an incoming SCO connection from the AG

    NOTE on address format: unlike BTPROTO_RFCOMM / BTPROTO_L2CAP (which take a
    (bdaddr, channel/psm) tuple), CPython's socket module expects BTPROTO_SCO
    addresses as a BARE bytes object containing just the bdaddr string.
    Passing a tuple here raises OSError("wrong format").
    """
    addr = mac.encode() if isinstance(mac, str) else mac

    try:
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_SCO)
        s.settimeout(4.0)
        s.connect(addr)
        print("SCO: connected outbound")
        return s
    except OSError as e:
        print("SCO: outbound connect failed (%s), listening instead..." % e)

    try:
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_SCO)
        s.bind(b"00:00:00:00:00:00")
        s.listen(1)
        s.settimeout(8.0)
        conn, addr = s.accept()
        print("SCO: accepted inbound from %s" % (addr,))
        return conn
    except OSError as e:
        print("SCO: inbound accept also failed (%s). No audio path." % e)
        return None


# SOL_SCO / SCO_OPTIONS are not exposed by Python's socket module.
SOL_SCO = 17
SCO_OPTIONS = 1


def get_sco_mtu(sco_sock, default=48):
    """
    SCO is a SYNCHRONOUS packet channel: every send() must be exactly one
    HCI SCO packet of the negotiated MTU. Writing any other size returns
    EINVAL ("Invalid argument") -- this is NOT a data or codec problem.

    The MTU is exposed via getsockopt(SOL_SCO, SCO_OPTIONS), which returns
    `struct sco_options { uint16_t mtu; }`. Typical values are 48, 60 or 64
    bytes for CVSD narrowband.
    """
    try:
        raw = sco_sock.getsockopt(SOL_SCO, SCO_OPTIONS, 4)
        mtu = struct.unpack_from("<H", raw)[0]
        if mtu > 0:
            return mtu
    except OSError as e:
        print("SCO: could not read MTU (%s)" % e)
    return default


def ffmpeg_pcm_reader(mp3_path):
    """Spawn ffmpeg to decode the mp3 into raw 8kHz mono s16le PCM on stdout."""
    proc = subprocess.Popen(
        [
            "ffmpeg", "-loglevel", "error", "-stream_loop", "-1",
            "-i", mp3_path,
            "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-",
        ],
        stdout=subprocess.PIPE,
    )
    return proc


def sco_reader_thread(sco_sock, stop_evt):
    """Continuously forward radio->PC audio into aplay so you can hear it."""
    aplay = subprocess.Popen(
        ["aplay", "-q", "-t", "raw", "-r", str(SAMPLE_RATE), "-f", "S16_LE", "-c", "1", "-"],
        stdin=subprocess.PIPE,
    )
    try:
        while not stop_evt.is_set():
            try:
                data = sco_sock.recv(4096)
            except OSError:
                break
            if not data:
                break
            try:
                aplay.stdin.write(data)
            except (BrokenPipeError, OSError):
                break
    finally:
        try:
            aplay.stdin.close()
        except Exception:
            pass
        aplay.terminate()


def sco_writer_loop(sco_sock, at, mp3_path, on_seconds, off_seconds, stop_evt,
                    send_mptt=True):
    """Cycle: AT+MPTT=1 + mp3 audio for on_seconds, AT+MPTT=0 + silence for off_seconds.

    With send_mptt=False the AT+MPTT commands are skipped entirely and only the
    audio cycle runs -- used to validate the SCO path against a normal phone.
    """
    ffmpeg_proc = None

    # One send() == one SCO packet of exactly MTU bytes, paced at the rate the
    # air interface consumes them (mtu bytes / 2 bytes-per-sample / 8000 Hz).
    mtu = get_sco_mtu(sco_sock)
    frame_period = (mtu / BYTES_PER_SAMPLE) / float(SAMPLE_RATE)
    print("SCO: MTU %d bytes (%.1f ms per packet)" % (mtu, frame_period * 1000))

    silence = b"\x00" * mtu

    def write_frames(get_chunk, t_end):
        """Pump MTU-sized packets until t_end; get_chunk() returns mtu bytes or None."""
        next_t = time.time()
        while time.time() < t_end and not stop_evt.is_set():
            data = get_chunk()
            if data is None:
                return False
            if len(data) < mtu:
                data += b"\x00" * (mtu - len(data))
            try:
                sco_sock.send(data)
            except OSError as e:
                print("SCO write failed: %s" % e)
                stop_evt.set()
                return False
            next_t += frame_period
            dt = next_t - time.time()
            if dt > 0:
                time.sleep(dt)
            else:
                next_t = time.time()
        return True

    while not stop_evt.is_set():
        # ---- ON: transmit ----
        if send_mptt:
            at.send("AT+MPTT=1")
            at.expect_ok(timeout=1.5)
        ffmpeg_proc = ffmpeg_pcm_reader(mp3_path)
        t_end = time.time() + on_seconds
        print("--- ON: streaming %s for %ds ---" % (mp3_path, on_seconds))

        def next_mp3_frame():
            data = ffmpeg_proc.stdout.read(mtu)
            return data if data else None

        write_frames(next_mp3_frame, t_end)

        ffmpeg_proc.terminate()
        try:
            ffmpeg_proc.stdout.close()
        except Exception:
            pass

        if stop_evt.is_set():
            break

        # ---- OFF: silence ----
        if send_mptt:
            at.send("AT+MPTT=0")
            at.expect_ok(timeout=1.5)
        t_end = time.time() + off_seconds
        print("--- OFF: silence for %ds ---" % off_seconds)
        write_frames(lambda: silence, t_end)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mac", help="radio's Bluetooth MAC address, AA:BB:CC:DD:EE:FF")
    ap.add_argument("mp3", help="mp3 file to loop as the simulated mic input")
    ap.add_argument("--channel", type=int, default=None,
                     help="HFP-AG RFCOMM channel (auto-detected via sdptool if omitted)")
    ap.add_argument("--on", type=int, default=10, help="seconds of AT+MPTT=1 + audio")
    ap.add_argument("--off", type=int, default=10, help="seconds of AT+MPTT=0 + silence")
    ap.add_argument("--no-mptt", action="store_true",
                    help="do not send the proprietary AT+MPTT commands. Use this when "
                         "validating the setup against a normal phone, which will answer "
                         "ERROR to vendor commands -- the audio cycle still runs.")
    ap.add_argument("--at-only", action="store_true",
                    help="only open the RFCOMM AT channel and cycle AT+MPTT; do NOT touch "
                         "SCO and do NOT stream audio. Lets PipeWire keep the HFP audio "
                         "path while we inject the vendor command alongside it. The mp3 "
                         "argument is ignored.")
    ap.add_argument("--no-slc", action="store_true",
                    help="skip the SLC handshake. Useful with --at-only when another stack "
                         "(PipeWire) has already established the service level connection, "
                         "so re-running the handshake would be redundant or disruptive.")
    ap.add_argument("--probe-channels", action="store_true",
                    help="brute-force probe which RFCOMM channels accept a connection, "
                         "then exit. Use when 'sdptool browse' returns nothing -- this "
                         "radio does not answer SDP browse requests.")
    args = ap.parse_args()

    if args.probe_channels:
        probe_rfcomm_channels(args.mac)
        return

    channel = args.channel or sdptool_find_ag_channel(args.mac)
    print("Using RFCOMM channel %d" % channel)

    try:
        at = RfcommAt(args.mac, channel)
    except OSError as e:
        raise SystemExit(
            "RFCOMM connect to channel %d failed: %s\n\n"
            "If another stack (PipeWire/oFono) already holds this channel, that is\n"
            "expected -- a second connection to the same RFCOMM server channel from\n"
            "the same device is refused. Try:\n"
            "  sdptool browse %s\n"
            "and look for a SECOND Audio Gateway record (HSP AG, UUID 0x1112) on a\n"
            "different channel, then pass it explicitly:\n"
            "  --at-only --channel <that channel>\n"
            "Otherwise stop PipeWire first:\n"
            "  systemctl --user stop pipewire pipewire-pulse wireplumber"
            % (channel, e, args.mac)
        )

    if not args.no_slc:
        slc_handshake(at)
    else:
        print("--- skipping SLC handshake (--no-slc) ---")

    # --at-only: never touch SCO, so whatever owns the audio path keeps it.
    if args.at_only:
        print("--- AT-only mode: not opening SCO. Audio stays with PipeWire/whoever owns it. ---")
        print("--- Watch the radio for TX activity while AT+MPTT=1 is asserted. ---")
        try:
            while True:
                at.send("AT+MPTT=1")
                at.expect_ok(timeout=1.5)
                print("--- MPTT ON for %ds ---" % args.on)
                time.sleep(args.on)
                at.send("AT+MPTT=0")
                at.expect_ok(timeout=1.5)
                print("--- MPTT OFF for %ds ---" % args.off)
                time.sleep(args.off)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                at.send("AT+MPTT=0")
            except Exception:
                pass
        return

    sco = open_sco(args.mac)
    stop_evt = threading.Event()

    if sco is not None:
        reader_t = threading.Thread(target=sco_reader_thread, args=(sco, stop_evt), daemon=True)
        reader_t.start()
    else:
        print("!! Proceeding WITHOUT an audio path -- you can still watch whether "
              "AT+MPTT gets an OK/ERROR reply, but you won't hear anything. !!")

    try:
        if sco is not None:
            sco_writer_loop(sco, at, args.mp3, args.on, args.off, stop_evt,
                            send_mptt=not args.no_mptt)
        elif args.no_mptt:
            print("!! No audio path and --no-mptt given: nothing to do. !!")
        else:
            # No SCO: just cycle the AT command alone so you can still observe
            # the radio's reaction (menu state, LEDs, TX indicator, etc.)
            while True:
                at.send("AT+MPTT=1")
                at.expect_ok(timeout=1.5)
                time.sleep(args.on)
                at.send("AT+MPTT=0")
                at.expect_ok(timeout=1.5)
                time.sleep(args.off)
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        try:
            at.send("AT+MPTT=0")
        except Exception:
            pass


if __name__ == "__main__":
    if sys.platform != "linux":
        sys.exit("This script requires Linux (raw AF_BLUETOOTH sockets).")
    main()
