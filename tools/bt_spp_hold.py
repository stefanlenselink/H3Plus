#!/usr/bin/env python3
"""
Persistent SPP link to the radio + interactive PTT.

WHY THIS EXISTS
---------------
The radio waits for a PROFILE-level connection before it considers itself
connected -- an ACL/baseband link alone is not enough (Findings.md 9A.21).
While it waits, its screen says "Connecting ..." with no confirmation tone,
and if poked again from its own paired-devices menu in that state it can LOCK
UP and need a power cycle.

Any profile satisfies it: HFP, A2DP or SPP. A normal headset (e.g. a Jabra
Evolve 65) satisfies it with HFP and connects perfectly. On a PC, HFP is
implemented by PipeWire/WirePlumber -- so do NOT stop those services, or
nothing answers the radio's HFP connect and it waits forever. That is safe
now: the radio's SPP endpoint is RFCOMM channel 2 while HFP is channel 6, so
PipeWire and this tool do not collide.

This tool holds the SPP channel open for as long as you want -- which keeps
the radio connected even when no other profile is up -- and lets you key PTT
at will. A one-shot tool that connects, sends a keypress and exits is the
wrong shape: it makes the radio connect and immediately disconnect.

USAGE
-----
    # leave pipewire RUNNING
    sudo python3 tools/bt_spp_hold.py 0B:FF:59:E8:85:92

Then, at the prompt:
    <Enter>     press PTT, hold, release  (duration = --hold)
    p           press and HOLD until you type r
    r           release
    s           show link status
    q           quit (releases first, then closes cleanly)

Or run hands-free with a repeating cycle:
    sudo python3 tools/bt_spp_hold.py <mac> --cycle --hold 3 --gap 5

WHAT THE PTT ACTUALLY DOES DEPENDS ON THE ADVERTISED NAME
---------------------------------------------------------
"+SPP=P" keys the transmitter under ANY advertised name -- the radio's name
whitelist does not gate PTT. What it gates is WHICH MICROPHONE feeds TX
(Findings.md 9A.22):

    TID-MIC / TID-MIC-EAR   TX from this PC, RX to this PC (full duplex)
    TID-PTT...              TX from this PC, RX on the radio's own speaker
    unrecognised name       TX from THE RADIO'S OWN MIC, RX to this PC

So under an unrecognised name PTT appears to work while transmitting the
wrong audio. Set the name with tools/bt_be_headset.sh "TID-MIC-EAR".

Bluetooth audio level is set by the RADIO'S VOLUME KNOB, not the PC mixer.

THE RADIO TALKS BACK: "AT+MPTT" = RX SQUELCH (Findings.md 9A.24, 9A.25)
-----------------------------------------------------------------------
The protocol is asymmetric. We send commands; the radio sends notifications:

    us    -> radio :  +SPP=P / +SPP=R      command: key / unkey TX
    radio -> us    :  AT+MPTT=1            RX squelch OPEN  (receiving)
                      AT+MPTT=0            RX squelch CLOSED (idle)

So AT+MPTT is NOT something to send to the radio -- doing so gets ERROR,
because it is the radio's own outbound message. That single mistake accounts
for every failed AT+MPTT experiment earlier in the project.

It is a RECEIVE indicator, confirmed by timing three distant transmissions of
different lengths against the =1/=0 pairs. Our OWN transmissions never
produce =1. Nothing acknowledges a PTT command -- +SPP=P is fire-and-forget.

KNOWN BUG (Findings.md 9A.22): in the duplex modes (TID-MIC / TID-MIC-EAR)
only the FIRST transmission carries audio. The second one gives a few
milliseconds and then silence -- and the radio then reports "Bluetooth
Disconnected" and re-connects itself a few seconds later.

This is a RADIO-SIDE FIRMWARE FAULT, not something wrong on this end:
  * wpctl shows the radio as a bluez5 device with NO sink and NO source, so
    the working audio rides a transient SCO link, not a steady stream.
  * During the silent transmission, DTMF from the radio's own keypad IS
    heard on the distant radio -- so TX, RF and the receiving end are fine.
  * Reconnecting SPP does not help; we reconnect after the stack has reset.

Nothing on the Linux side can fix a peer whose stack falls over. Use
TID-PTT... for anything that has to work reliably -- it uses a simpler audio
path and repeats indefinitely, at the cost of received audio coming out of
the radio's own speaker.

The socket stays open the whole time either way, so the radio stays connected
and you can test repeatedly without re-pairing.
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
import socket
import sys
import threading
import time

PRESS = b"+SPP=P\x00"
RELEASE = b"+SPP=R\x00"

# All traffic is timestamped relative to this, so that press -> notification
# latencies can be read straight off the log without arithmetic.
T0 = time.monotonic()


def stamp():
    """[ +12.345s 14:32:07.891 ] -- relative for deltas, wall clock for
    correlating against bluetoothctl/journal/pactl logs."""
    return "[%+9.3fs %s]" % (
        time.monotonic() - T0, time.strftime("%H:%M:%S") +
        ("%.3f" % (time.time() % 1))[1:])


def log(msg):
    print("%s %s" % (stamp(), msg), flush=True)


def connect_spp(mac, channel, log=log):
    s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    s.settimeout(15.0)
    s.connect((mac, channel))
    s.settimeout(None)
    log("SPP connected to %s channel %d" % (mac, channel))
    log("The radio should now say 'Bluetooth Connected'. Keep this running.")
    return s


def reader_thread(sock, stop_evt):
    """Log anything the radio sends us. Also detects the link dropping."""
    sock.settimeout(0.5)
    while not stop_evt.is_set():
        try:
            data = sock.recv(256)
        except socket.timeout:
            continue
        except OSError:
            break
        if not data:
            print()
            log("!! radio closed the SPP link !!")
            stop_evt.set()
            break
        print()
        log("<< %-28s %r" % (data.hex(" "), data))


class Ptt:
    def __init__(self, sock):
        self.sock = sock
        self.down = False

    def press(self):
        self.sock.sendall(PRESS)
        self.down = True
        log(">> +SPP=P   PTT DOWN -- radio should be TRANSMITTING")

    def release(self, double=True):
        self.sock.sendall(RELEASE)
        # The genuine button sends the release twice; mirror that, since the
        # radio may rely on the repeat to recover a dropped packet.
        if double:
            self.sock.sendall(RELEASE)
        self.down = False
        log(">> +SPP=R   PTT UP%s" % ("" if double else "   (single release)"))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mac", help="radio's Bluetooth MAC address")
    ap.add_argument("--channel", type=int, default=2,
                    help="radio's SPP RFCOMM channel (default 2)")
    ap.add_argument("--hold", type=float, default=3.0,
                    help="seconds to hold PTT for a one-shot press (default 3)")
    ap.add_argument("--gap", type=float, default=5.0,
                    help="idle seconds between presses in --cycle mode (default 5)")
    ap.add_argument("--cycle", action="store_true",
                    help="automatically cycle press/release instead of prompting")
    ap.add_argument("--idle", action="store_true",
                    help="just hold the link open and send NOTHING. Use when running "
                         "unattended/in the background: it keeps the radio connected "
                         "without ever keying the transmitter, and does not need a "
                         "terminal to read commands from.")
    ap.add_argument("--no-double-release", action="store_true",
                    help="send release once instead of twice")
    args = ap.parse_args()

    try:
        sock = connect_spp(args.mac, args.channel)
    except OSError as e:
        raise SystemExit(
            "SPP connect to %s channel %d failed: %s\n\n"
            "Checklist:\n"
            "  * Is PipeWire RUNNING? It implements HFP on the PC. With it stopped,\n"
            "    nothing answers the radio's profile connect and it waits forever on\n"
            "    'Connecting ...'. Channel 2 (SPP) and channel 6 (HFP) do not clash,\n"
            "    so there is no reason to stop it:\n"
            "      systemctl --user start pipewire pipewire-pulse wireplumber\n"
            "  * Is the radio showing 'Connecting ...'? Connect promptly -- it can\n"
            "    lock up if left in that state and poked again from its own menu.\n"
            "  * Is the ACL link up? Keep bt_be_headset.sh running.\n"
            "  * Wrong channel? Map endpoints with:\n"
            "      python3 tools/bt_hf_sim.py %s x.mp3 --probe-channels"
            % (args.mac, args.channel, e, args.mac))

    stop_evt = threading.Event()
    threading.Thread(target=reader_thread, args=(sock, stop_evt), daemon=True).start()

    ptt = Ptt(sock)
    double = not args.no_double_release

    try:
        if args.idle:
            print("Holding the SPP link open, sending nothing. Ctrl-C to stop.\n")
            while not stop_evt.is_set():
                time.sleep(0.5)
        elif args.cycle:
            print("Cycling: %.1fs PTT down, %.1fs idle. Ctrl-C to stop.\n"
                  % (args.hold, args.gap))
            while not stop_evt.is_set():
                ptt.press()
                time.sleep(args.hold)
                ptt.release(double)
                time.sleep(args.gap)
        else:
            print("\nCommands:  <Enter>=press+release   p=hold   r=release   "
                  "s=status   q=quit\n"
                  "Any other text is logged as a timestamped note.\n")
            while not stop_evt.is_set():
                try:
                    raw = input("ptt> ").strip()
                except EOFError:
                    break
                cmd = raw.lower()

                if cmd == "q":
                    break
                elif cmd == "p":
                    ptt.press()
                elif cmd == "r":
                    ptt.release(double)
                elif cmd == "s":
                    log("SPP link open, PTT is %s"
                        % ("DOWN" if ptt.down else "up"))
                elif cmd == "":
                    ptt.press()
                    time.sleep(args.hold)
                    ptt.release(double)
                else:
                    # Anything else is a free-text note. Typing what you are
                    # doing ("external radio transmitting") lands it in the
                    # log, timestamped and interleaved with the traffic --
                    # which is exactly what makes these captures readable
                    # afterwards. "m" alone is a bare marker.
                    log("---- %s ----" % ("MARK" if cmd == "m" else raw))
    except KeyboardInterrupt:
        print()
    finally:
        stop_evt.set()
        # Never leave the radio keyed.
        try:
            if ptt.down:
                ptt.release(double)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass
        print("SPP closed -- the radio will now report 'Bluetooth Disconnected'.")


if __name__ == "__main__":
    if sys.platform != "linux":
        sys.exit("This script requires Linux (raw AF_BLUETOOTH sockets).")
    main()
