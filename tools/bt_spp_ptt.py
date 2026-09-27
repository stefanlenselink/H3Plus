#!/usr/bin/env python3
"""
Send the REAL TIDRADIO PTT protocol to the radio.

Captured from a genuine TID-PTT accessory on 2026-09-19 (Findings.md 9A.20).
The protocol is nothing like what we spent weeks guessing at:

    NOT  "AT+MPTT=1\r"   over HFP/RFCOMM     <- our assumption, always ERROR
    BUT  "+SPP=P\0"      over SPP            <- what the button actually sends

Three differences, each of which alone was enough to make our attempts fail:

    1. Transport is SPP (Serial Port Profile), not HFP. On the radio this is
       the channel that accepted connections but never replied, and made an
       icon appear -- see Findings.md 9A.18 channel 2.
    2. No "AT" prefix. The string is literally "+SPP=".
    3. Terminated by a single NUL byte (0x00), not CR or CRLF.

Opcodes observed:
    +SPP=P   key pressed   (PTT down -> radio should transmit)
    +SPP=R   key released  (PTT up   -> radio should stop)

The button sends these fire-and-forget; it does not wait for or expect a
reply, and it repeats "R" twice on release. No SLC handshake, no AT
negotiation of any kind precedes them.

USAGE
-----
    # cycle: 5s transmitting, 5s idle
    sudo python3 tools/bt_spp_ptt.py 0B:FF:59:E8:85:92

    # one press, hold 3s, release, then exit
    sudo python3 tools/bt_spp_ptt.py 0B:FF:59:E8:85:92 --once --hold 3

    # replay the exact release-twice quirk the real button shows
    sudo python3 tools/bt_spp_ptt.py 0B:FF:59:E8:85:92 --double-release

Channel 2 is the radio's SPP endpoint (9A.18); override with --channel.
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
import time

PRESS = b"+SPP=P\x00"
RELEASE = b"+SPP=R\x00"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mac", help="radio's Bluetooth MAC address")
    ap.add_argument("--channel", type=int, default=2,
                    help="RFCOMM channel of the radio's SPP endpoint (default 2)")
    ap.add_argument("--hold", type=float, default=5.0,
                    help="seconds to hold PTT down (default 5)")
    ap.add_argument("--gap", type=float, default=5.0,
                    help="seconds idle between presses (default 5)")
    ap.add_argument("--once", action="store_true",
                    help="single press/release, then exit")
    ap.add_argument("--double-release", action="store_true",
                    help="send the release twice, mimicking the real button exactly")
    ap.add_argument("--listen", action="store_true",
                    help="also print anything the radio sends back")
    args = ap.parse_args()

    s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    s.settimeout(10.0)
    try:
        s.connect((args.mac, args.channel))
    except OSError as e:
        raise SystemExit(
            "connect to %s channel %d failed: %s\n\n"
            "Make sure the radio is paired and connected, and that nothing else\n"
            "holds the channel:\n"
            "  systemctl --user stop pipewire pipewire-pulse wireplumber\n"
            "If the channel number is wrong, map the radio's endpoints with:\n"
            "  python3 tools/bt_hf_sim.py %s x.mp3 --probe-channels"
            % (args.mac, args.channel, e, args.mac))

    print("Connected to %s on RFCOMM channel %d (SPP)" % (args.mac, args.channel))
    print("Watch the radio for TX activity.\n")

    def send(payload, label):
        print("[%s] >> %r" % (time.strftime("%H:%M:%S"), payload))
        s.sendall(payload)
        print("    %s" % label)
        if args.listen:
            s.settimeout(0.3)
            try:
                back = s.recv(256)
                if back:
                    print("    << %s  %r" % (back.hex(" "), back))
            except OSError:
                pass

    try:
        while True:
            send(PRESS, "PTT DOWN -- radio should be TRANSMITTING now")
            time.sleep(args.hold)

            send(RELEASE, "PTT UP")
            if args.double_release:
                send(RELEASE, "PTT UP (repeat, as the real button does)")

            if args.once:
                break
            time.sleep(args.gap)
    except KeyboardInterrupt:
        print("\nInterrupted -- sending release so the radio does not stay keyed.")
    finally:
        # Never leave the radio transmitting.
        try:
            s.sendall(RELEASE)
        except OSError:
            pass
        s.close()


if __name__ == "__main__":
    if sys.platform != "linux":
        sys.exit("This script requires Linux (raw AF_BLUETOOTH sockets).")
    main()
