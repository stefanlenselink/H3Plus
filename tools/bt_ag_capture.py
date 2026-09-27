#!/usr/bin/env python3
"""
Audio Gateway (AG) impersonator + full traffic logger.

PURPOSE
-------
Everything so far has been inference: we found `AT+MPTT=0/1` as strings in
flash, guessed the syntax, and got ERROR back. This tool inverts the problem.
Instead of guessing what a genuine TIDRADIO PTT accessory sends, we let a real
one tell us, by making this PC pretend to BE the radio.

The accessory is a Hands-Free (HF) unit; it expects to connect to an Audio
Gateway. So this script:

    1. registers an HFP-AG + HSP-AG SDP record so the button will connect
    2. listens on an RFCOMM channel
    3. on connect, snapshots the peer's identity (name, class, UUIDs, PnP IDs)
    4. answers the SLC handshake convincingly enough that the button proceeds
       to its *real* behaviour
    5. logs every single byte in both directions, with timestamps

IMPORTANT: this must ANSWER, not just listen. An HF unit that gets no reply to
AT+BRSF aborts within a couple of seconds and you learn nothing. Equally, we
reply OK to commands we do not recognise (--unknown-reply ok, the default),
because an ERROR may cause the accessory to give up before it ever reveals the
vendor command we are hunting for. Every unknown command is logged loudly --
those lines are the entire point of this exercise.

PREREQUISITE: bluetoothd compat mode
------------------------------------
Only needed for --listen mode (SDP registration). Not needed for --connect.

    sudo systemctl edit --full bluetooth
    # append --compat to the ExecStart line, so it reads e.g.
    #   ExecStart=/usr/libexec/bluetooth/bluetoothd --compat
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    sudo chmod 666 /var/run/sdp

USAGE
-----
TWO DIRECTIONS. The right one depends on which side initiates.

(a) OUTBOUND -- use this for the PTT button. The button has no screen and
    cannot choose a target, so it advertises and waits; the radio scans and
    connects to IT. We must do the same: connect out to the button and then
    speak as the AG.

        sudo python3 tools/bt_ag_capture.py --connect AA:BB:CC:DD:EE:FF
        sudo python3 tools/bt_ag_capture.py --connect AA:BB:CC:DD:EE:FF --channel 1

    With no --channel it probes the button's RFCOMM channels and picks the
    first that responds to AT traffic.

    Find the button first with:  sudo python3 tools/bt_ag_capture.py --scan

(b) INBOUND -- listen and let the peer connect to us. Correct for the RADIO
    (see Findings.md 9A.17), but the PTT button will never do this.

        sudo python3 tools/bt_ag_capture.py --listen --channel 6

In both cases, once connected PRESS THE PTT BUTTON -- the vendor command is
almost certainly sent on the key event, not at connect time.
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
import re
import socket
import subprocess
import sys
import threading
import time

# Commands an AG is expected to understand during / after SLC setup.
# We answer these the way a normal phone would, so the accessory is satisfied
# and moves on to whatever it actually wants to do.
#
# +BRSF value 871 = 0x367: three-way calling, EC/NR, voice recognition,
# in-band ringing, volume control, reject call, enhanced call status.
# Deliberately generous -- we want to advertise support for as much as
# possible so the accessory does not withhold features from us.
AG_BRSF = 871

CIND_TEST = ('+CIND: ("service",(0,1)),("call",(0,1)),("callsetup",(0,3)),'
             '("callheld",(0,2)),("signal",(0,5)),("roam",(0,1)),("battchg",(0,5))')
CIND_STATUS = "+CIND: 1,0,0,0,5,0,5"


class Logger:
    """Timestamped logger writing to stdout and optionally a file."""

    def __init__(self, path=None):
        self.fh = open(path, "a", buffering=1) if path else None
        self.t0 = time.time()

    def log(self, tag, msg):
        line = "[%8.3f] %-10s %s" % (time.time() - self.t0, tag, msg)
        print(line, flush=True)
        if self.fh:
            self.fh.write(line + "\n")

    def banner(self, msg):
        bar = "=" * 70
        for l in (bar, msg, bar):
            self.log("", l)


def run(cmd, timeout=15):
    """Run a command, returning its output as text; never raises."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except Exception as e:
        return "(failed: %s)" % e


def check_sdp_compat(log):
    """Warn early if bluetoothd is not in --compat mode."""
    import os
    if not os.path.exists("/var/run/sdp"):
        log.banner("WARNING: /var/run/sdp does not exist -- bluetoothd is not "
                   "running with --compat.")
        log.log("HINT", "sdptool add will fail, and the accessory will not see "
                        "an AG to connect to.")
        log.log("HINT", "sudo systemctl edit --full bluetooth   "
                        "# add --compat to ExecStart")
        log.log("HINT", "sudo systemctl daemon-reload && sudo systemctl restart bluetooth")
        log.log("HINT", "sudo chmod 666 /var/run/sdp")
        return False
    return True


def register_sdp(channel, log):
    """Advertise HFP-AG and HSP-AG records so an HF unit will connect to us."""
    for profile in ("HFAG", "HSAG"):
        out = run(["sdptool", "add", "--channel=%d" % channel, profile])
        log.log("SDP", "add %s channel %d: %s" % (profile, channel, out or "ok"))


def snapshot_peer(mac, log):
    """
    Capture everything we can about the accessory the moment it connects.

    This is half the value of the exercise: the radio's firmware very likely
    keys off some of this (name, class of device, or the PnP vendor/product
    ID), and we currently have no idea which.
    """
    log.banner("PEER IDENTITY SNAPSHOT: %s" % mac)

    log.log("INFO", "--- bluetoothctl info ---\n" + run(["bluetoothctl", "info", mac]))
    log.log("INFO", "--- hcitool info ---\n" + run(["hcitool", "info", mac]))
    log.log("INFO", "--- hcitool name ---\n" + run(["hcitool", "name", mac]))

    # Full SDP dump: which profiles it offers, on which channels. For a PTT
    # accessory this reveals whether it exposes anything beyond plain HFP.
    browse = run(["sdptool", "browse", mac], timeout=30)
    log.log("SDP", "--- sdptool browse ---\n" + (browse or "(empty)"))

    # PnP / Device ID record carries vendor + product IDs, which is the most
    # likely thing a whitelist would key off if it is not using the name.
    pnp = run(["sdptool", "search", "--bdaddr", mac, "0x1200"], timeout=30)
    log.log("SDP", "--- Device ID (PnP, 0x1200) ---\n" + (pnp or "(empty)"))

    log.banner("END SNAPSHOT -- now logging AT traffic")


def scan_for_accessory(log, seconds=20):
    """
    Classic BR/EDR inquiry, to find the PTT button while it advertises.

    Deliberately 'scan bredr' rather than 'scan on': LE scanning steals
    inquiry airtime, and an HFP accessory is a classic-Bluetooth device.
    This is the same lesson as Findings.md 9A.14/9A.17 -- LE activity
    repeatedly got in the way of finding the classic endpoint.
    """
    log.banner("Scanning for classic Bluetooth devices for %ds -- "
               "put the PTT button in pairing mode NOW" % seconds)
    script = "power on\nagent NoInputNoOutput\ndefault-agent\nscan bredr\n"
    try:
        p = subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True)
        p.stdin.write(script)
        p.stdin.flush()
        time.sleep(seconds)
        p.stdin.write("scan off\ndevices\nquit\n")
        p.stdin.flush()
        out, _ = p.communicate(timeout=15)
    except Exception as e:
        log.log("ERROR", "scan failed: %s" % e)
        return

    seen = {}
    for m in re.finditer(r"([0-9A-F]{2}(?::[0-9A-F]{2}){5})\s+(.*)", out, re.I):
        seen[m.group(1).upper()] = m.group(2).strip()

    log.banner("Devices found: %d" % len(seen))
    for mac, name in sorted(seen.items()):
        log.log("FOUND", "%s  %s" % (mac, name))
    log.log("HINT", "Re-run with: --connect <MAC of the PTT button>")


def probe_and_connect(mac, log, channel=None, lo=1, hi=30):
    """
    Open an RFCOMM connection to the accessory, acting as the AG client.

    If no channel is given we brute-force, because these devices frequently
    do not answer SDP at all (the radio itself does not -- Findings.md 9A.18).
    We return the first channel that accepts; the caller then drives AT
    traffic over it and can tell from the log whether it is the right one.
    """
    if channel is not None:
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                          socket.BTPROTO_RFCOMM)
        s.settimeout(10.0)
        s.connect((mac, channel))
        log.log("LINK", "connected to %s channel %d" % (mac, channel))
        return s, channel

    log.log("LINK", "no --channel given; probing %d-%d on %s" % (lo, hi, mac))
    for ch in range(lo, hi + 1):
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                          socket.BTPROTO_RFCOMM)
        s.settimeout(4.0)
        try:
            s.connect((mac, ch))
            log.log("LINK", "channel %d OPEN -- using it" % ch)
            return s, ch
        except OSError as e:
            log.log("LINK", "channel %2d: %s" % (ch, e))
            try:
                s.close()
            except Exception:
                pass
        time.sleep(0.2)
    return None, None


class AgSession:
    """Serves one connected HF accessory, answering AT commands and logging all."""

    def __init__(self, sock, peer, log, unknown_reply="ok"):
        self.sock = sock
        self.peer = peer
        self.log = log
        self.unknown_reply = unknown_reply
        self.buf = b""
        self.unknown_cmds = []

    def send(self, text):
        data = ("\r\n%s\r\n" % text).encode()
        self.log.log("AG->HF", repr(text))
        try:
            self.sock.sendall(data)
        except OSError as e:
            self.log.log("ERROR", "send failed: %s" % e)

    def handle(self, line):
        """Answer one message the way the radio would."""
        u = line.upper()

        # ---- The real TIDRADIO PTT protocol (captured 2026-09-19) ----
        # Sent over SPP, NUL-terminated, no AT prefix and no CR/LF:
        #     "+SPP=P\0"  key pressed
        #     "+SPP=R\0"  key released
        # The button does not wait for a reply -- it repeats these regardless.
        if u.startswith("+SPP="):
            arg = line[5:].strip()
            meaning = {"P": "PTT PRESSED", "R": "PTT RELEASED"}.get(
                arg.upper(), "unknown SPP opcode")
            self.log.log("PTT", "%-14s  (%r)" % (meaning, line))
            return

        if u.startswith("AT+BRSF"):
            self.send("+BRSF: %d" % AG_BRSF)
            self.send("OK")
        elif u.startswith("AT+CIND=?"):
            self.send(CIND_TEST)
            self.send("OK")
        elif u.startswith("AT+CIND?"):
            self.send(CIND_STATUS)
            self.send("OK")
        elif u.startswith("AT+CHLD=?"):
            self.send("+CHLD: (0,1,1x,2,2x,3,4)")
            self.send("OK")
        elif u.startswith("AT+BAC"):
            # Codec negotiation (mSBC/wideband). Accept.
            self.send("OK")
        elif u.startswith("AT+BIND=?"):
            self.send("+BIND: (1,2)")
            self.send("OK")
        elif u.startswith("AT+BIND?"):
            self.send("+BIND: 1,1")
            self.send("+BIND: 2,1")
            self.send("OK")
        elif any(u.startswith(p) for p in (
                "AT+CMER", "AT+CLIP", "AT+CCWA", "AT+CMEE", "AT+VGS", "AT+VGM",
                "AT+BIND", "AT+BIA", "AT+NREC", "AT+BTRH", "AT+COPS", "AT+CSCS")):
            self.send("OK")
        elif u.startswith("AT+CGMI"):
            self.send("TIDRADIO")
            self.send("OK")
        elif u.startswith("AT+CGMM"):
            self.send("H3-Plus")
            self.send("OK")
        else:
            # *** THE INTERESTING CASE ***
            self.unknown_cmds.append(line)
            self.log.banner("UNKNOWN / VENDOR COMMAND FROM ACCESSORY: %r" % line)
            if self.unknown_reply == "ok":
                self.send("OK")
            else:
                self.send("ERROR")

    def run(self):
        self.sock.settimeout(1.0)
        while True:
            try:
                data = self.sock.recv(1024)
            except socket.timeout:
                continue
            except OSError as e:
                self.log.log("ERROR", "recv failed: %s" % e)
                break
            if not data:
                self.log.log("LINK", "accessory closed the connection")
                break

            # Log raw bytes first -- this is what saved the investigation. The
            # TIDRADIO PTT button does NOT speak AT: it sends NUL-terminated
            # "+SPP=P" / "+SPP=R" over SPP. A CR/LF line parser sees nothing.
            self.log.log("HF->AG", "raw %s" % data.hex(" "))
            self.buf += data

            # Frame on CR, LF *or* NUL, so both AT-style and SPP-style
            # messages are decoded.
            while True:
                m = re.search(rb"[\r\n\x00]+", self.buf)
                if not m:
                    break
                line = self.buf[:m.start()].strip()
                self.buf = self.buf[m.end():]
                if not line:
                    continue
                text = line.decode(errors="replace")
                self.log.log("HF->AG", repr(text))
                self.handle(text)

        if self.unknown_cmds:
            self.log.banner("SUMMARY: %d unknown/vendor command(s) captured"
                            % len(self.unknown_cmds))
            for c in self.unknown_cmds:
                self.log.log("VENDOR", repr(c))
        else:
            self.log.banner("SUMMARY: no unknown commands seen. If the accessory "
                            "never sent a PTT command, try pressing its PTT "
                            "button while connected.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", action="store_true",
                    help="scan for classic Bluetooth devices and exit. Use this to find "
                         "the PTT button's MAC while it is in pairing mode.")
    ap.add_argument("--connect", metavar="MAC", default=None,
                    help="connect OUT to this accessory and act as its Audio Gateway. "
                         "This is the correct direction for the PTT button, which "
                         "advertises and waits to be connected to.")
    ap.add_argument("--listen", action="store_true",
                    help="listen for an INBOUND connection instead. Correct for the "
                         "radio, but the PTT button will never connect to us.")
    ap.add_argument("--channel", type=int, default=None,
                    help="RFCOMM channel. With --connect, probed automatically if "
                         "omitted. With --listen, defaults to 6.")
    ap.add_argument("--log", default="ag_capture.log", help="log file path")
    ap.add_argument("--unknown-reply", choices=("ok", "error"), default="ok",
                    help="how to answer commands we do not recognise. 'ok' (default) "
                         "keeps the accessory talking so it reveals more; 'error' "
                         "mimics what the real radio does to US, to see how the "
                         "accessory reacts to rejection.")
    ap.add_argument("--no-sdp", action="store_true",
                    help="skip sdptool registration (--listen mode only)")
    args = ap.parse_args()

    log = Logger(args.log)

    if args.scan:
        scan_for_accessory(log)
        return

    if not args.connect and not args.listen:
        raise SystemExit(
            "Choose a direction:\n"
            "  --scan                  find the PTT button's MAC\n"
            "  --connect <MAC>         dial the PTT button (CORRECT for the button:\n"
            "                          it advertises and waits, the radio connects to it)\n"
            "  --listen                wait to be connected to (correct for the radio)\n")

    # ---------- OUTBOUND: we dial the accessory ----------
    if args.connect:
        log.banner("AG capture (OUTBOUND) -- target %s, unknown->%s"
                   % (args.connect, args.unknown_reply.upper()))
        log.log("HINT", "pair the button first if needed: "
                        "bluetoothctl pair %s && bluetoothctl trust %s"
                        % (args.connect, args.connect))

        threading.Thread(target=snapshot_peer, args=(args.connect, log),
                         daemon=True).start()
        try:
            sock, ch = probe_and_connect(args.connect, log, args.channel)
        except OSError as e:
            raise SystemExit(
                "connect to %s failed: %s\n"
                "Is the button powered on and in range? Pair it first:\n"
                "  bluetoothctl\n"
                "  > scan bredr\n"
                "  > pair %s\n"
                "  > trust %s" % (args.connect, e, args.connect, args.connect))

        if sock is None:
            raise SystemExit(
                "No RFCOMM channel on %s accepted a connection.\n"
                "The button may only accept connections briefly after a button press,\n"
                "or only from a device it is already bonded to. Pair it first, then\n"
                "press its button and immediately re-run this." % args.connect)

        log.banner("CONNECTED on channel %d -- NOW PRESS THE PTT BUTTON" % ch)
        AgSession(sock, args.connect, log, args.unknown_reply).run()
        try:
            sock.close()
        except Exception:
            pass
        return

    # ---------- INBOUND: we wait to be dialled ----------
    channel = args.channel or 6
    log.banner("AG capture (INBOUND) -- channel %d, unknown->%s"
               % (channel, args.unknown_reply.upper()))

    if not args.no_sdp:
        check_sdp_compat(log)
        register_sdp(channel, log)

    srv = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("00:00:00:00:00:00", channel))
    except OSError as e:
        raise SystemExit(
            "bind to channel %d failed: %s\n"
            "Another stack may hold it. Try:\n"
            "  systemctl --user stop pipewire pipewire-pulse wireplumber\n"
            "or pick a different --channel." % (channel, e))
    srv.listen(1)

    log.log("LINK", "listening on RFCOMM channel %d -- connect the accessory now"
            % channel)
    log.log("HINT", "make sure this PC is discoverable and pairable, e.g. run "
                    "tools/bt_be_headset.sh in another terminal")

    try:
        while True:
            conn, addr = srv.accept()
            peer = addr[0] if isinstance(addr, tuple) else str(addr)
            log.banner("ACCESSORY CONNECTED: %s" % peer)

            # Snapshot identity in a thread so we start logging AT traffic
            # immediately -- the SLC handshake begins right away and we must
            # not miss its first lines.
            threading.Thread(target=snapshot_peer, args=(peer, log),
                             daemon=True).start()

            AgSession(conn, peer, log, args.unknown_reply).run()
            try:
                conn.close()
            except Exception:
                pass
            log.log("LINK", "waiting for the next connection (Ctrl-C to stop)")
    except KeyboardInterrupt:
        log.log("LINK", "stopped by user")
    finally:
        srv.close()


if __name__ == "__main__":
    if sys.platform != "linux":
        sys.exit("This script requires Linux (raw AF_BLUETOOTH sockets).")
    main()
