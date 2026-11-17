#!/usr/bin/env python3
"""
TID-PTT accessory emulator — a PC that behaves like the genuine TID-PTT button.

WHY THIS EXISTS
---------------
Phase 1 observability (ch. 39 §39.5): radio-side two-device experiments must be
driven and OBSERVED from the accessory side with btmon, without burning real
button/radio cycles. The genuine button's behaviour is fully characterised
(ch. 38 §38.1, §9A.20) and every quirk is reproduced here:

    * RFCOMM SPP **server** on channel 2 (the button hosts SPP ch2).
    * NEVER pages / never initiates — pure peripheral. The radio dials us.
    * Class of Device 0x240404 (identical to the real button, §9A.20 snapshot).
    * Name "TID-PTT000000-E" — matches the radio's "TID-PTT" prefix gate
      (classifier 0x01E7EC28, ch. 22) while the "-E" suffix keeps it
      distinguishable from the real unit in captures and menus.
    * Sends "+SPP=P\\0" on press, "+SPP=R\\0" twice on release (§9A.20).
    * Drops the WHOLE ACL when its SPP channel closes (§38.1 — the quirk that
      kills it on every 0x4A). Override with --hold-acl to emulate a patched
      button (ch. 39 §39.6 step 2.4b).
    * No SDP record (the real button does not answer SDP either, §38.8; the
      radio dials ch2 without it).

PAIRING (one-time)
------------------
The emulator is passive, so pair FROM the PC while the radio is pairable:
    radio: BT menu -> Pairable
    PC:    bluetoothctl pair <radio-mac> && bluetoothctl trust <radio-mac>
BlueZ then answers the radio's later pair/link-key lookups automatically.
(Run this tool BEFORE the radio connects; it must be listening.)

USAGE
-----
    # one-time adapter identity (script does it too, --no-setup to skip):
    sudo python3 tools/bt_ptt_emulator.py                 # listen, interactive
    sudo python3 tools/bt_ptt_emulator.py --cycle 3 8     # auto press 3 s, gap 8 s
    sudo python3 tools/bt_ptt_emulator.py --hold-acl      # patched-button mode
    sudo python3 tools/bt_ptt_emulator.py --name TID-PTT000000-E --channel 2

Interactive keys (after a client connects):
    <Enter>/p  press        r  release        s  status        q  quit

VALIDATION (Phase 1.2 gate, on S1): the emulator must reproduce the real
button's kick + rejoin signature on btmon — same connect flow, same +SPP
framing, same ACL-drop-on-channel-close. Record with:
    sudo btmon -w /tmp/emu_vs_button.pcap

Linux/BlueZ only (raw AF_BLUETOOTH sockets), like the rest of the bt_* rig.
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
import shutil
import socket
import subprocess
import sys
import threading
import time

PRESS = b"+SPP=P\x00"
RELEASE = b"+SPP=R\x00"

T0 = time.monotonic()


def stamp():
    return "[%+9.3fs %s]" % (
        time.monotonic() - T0, time.strftime("%H:%M:%S") +
        ("%.3f" % (time.time() % 1))[1:])


def log(msg):
    print("%s %s" % (stamp(), msg), flush=True)


def run(cmd):
    """Best-effort external command; returns (ok, output)."""
    exe = cmd[0]
    if not shutil.which(exe):
        return False, "%s not installed" % exe
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except Exception as e:  # noqa: BLE001 - report, never crash the rig
        return False, str(e)


def setup_adapter(name, cod):
    """Inquiry+page scan on, CoD and name like the real button."""
    ok, out = run(["btmgmt", "power", "on"])
    log("btmgmt power on: %s" % ("ok" if ok else out))
    ok, out = run(["btmgmt", "name", name])
    log("name -> %s: %s" % (name, "ok" if ok else out))
    ok, out = run(["btmgmt", "class", "0x%06x" % cod])
    if not ok:
        # older bluez fallback
        ok2, out2 = run(["hciconfig", "hci0", "class", "0x%06x" % cod])
        log("class -> 0x%06x: btmgmt(%s) hciconfig(%s)"
            % (cod, out or "ok", out2 or "ok"))
    else:
        log("class -> 0x%06x: ok" % cod)
    # scan enable: inquiry scan + page scan (radio must be able to page/find us)
    ok, out = run(["hciconfig", "hci0", "piscan"])
    log("piscan (inquiry+page scan on): %s" % ("ok" if ok else out))


def serve(channel):
    srv = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                        socket.BTPROTO_RFCOMM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("00:00:00:00:00:00", channel))
    srv.listen(1)
    log("SPP server listening on channel %d -- connect the radio now" % channel)
    return srv


class Session:
    """One accepted RFCOMM connection (one radio dial)."""

    def __init__(self, sock, peer, hold_acl):
        self.sock = sock
        self.peer = peer
        self.hold_acl = hold_acl
        self.down = False
        self.alive = True
        self.stop_evt = threading.Event()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        self.sock.settimeout(0.5)
        while not self.stop_evt.is_set():
            try:
                data = self.sock.recv(256)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            log("<< %-28s %r" % (data.hex(" "), data))
        self.alive = False
        print()
        log("!! radio closed SPP / link lost !!")
        if not self.hold_acl:
            # the genuine button drops its WHOLE ACL when SPP closes (§38.1)
            ok, out = run(["hcitool", "dc", self.peer])
            log("ACL %s dropped (button quirk): %s"
                % (self.peer, "ok" if ok else out))
        else:
            log("--hold-acl: ACL left up (patched-button emulation)")

    def send(self, payload, desc):
        if not self.alive:
            log("!! not sending %s -- session dead !!" % desc)
            return False
        try:
            self.sock.sendall(payload)
            log(">> %-10s %s" % (desc, " ".join("%02x" % b for b in payload)))
            return True
        except OSError as e:
            log("!! send %s failed: %s -- link dead" % (desc, e))
            self.alive = False
            return False

    def press(self):
        if self.send(PRESS, "+SPP=P"):
            self.down = True
            log("   PTT DOWN -- radio should be TRANSMITTING")

    def release(self, double=True):
        ok = self.send(RELEASE, "+SPP=R")
        if double:  # the genuine button sends release twice (§9A.20)
            self.send(RELEASE, "+SPP=R")
        if ok:
            self.down = False
            log("   PTT UP")

    def close(self):
        self.stop_evt.set()
        try:
            if self.down:
                self.release()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channel", type=int, default=2,
                    help="RFCOMM server channel (real button: 2)")
    ap.add_argument("--name", default="TID-PTT000000-E",
                    help="adapter name (must keep the TID-PTT prefix)")
    ap.add_argument("--cod", default="0x240404",
                    help="Class of Device (real button: 0x240404)")
    ap.add_argument("--cycle", nargs=2, type=float, metavar=("HOLD", "GAP"),
                    help="auto-cycle: press for HOLD s, wait GAP s")
    ap.add_argument("--hold-acl", action="store_true",
                    help="keep the ACL up when SPP closes (patched-button mode, "
                         "ch.39 2.4b emulation)")
    ap.add_argument("--no-setup", action="store_true",
                    help="skip adapter name/class/scan setup")
    args = ap.parse_args()

    if not args.name.startswith("TID-PTT"):
        raise SystemExit("name must start with 'TID-PTT' (radio prefix gate)")

    if not args.no_setup:
        setup_adapter(args.name, int(args.cod, 16))

    srv = serve(args.channel)
    log("Emulator ready. Radio: BT menu -> Connect (it dials US; we never page).")

    sess = None
    try:
        while True:
            # accept is blocking; poll loop with short timeout via select-free
            # trick: run accept in a thread only when no session exists.
            if sess is None or not sess.alive:
                if sess is not None:
                    sess.close()
                    sess = None
                try:
                    conn, addr = srv.accept()
                except OSError:
                    break
                peer = addr[0] if isinstance(addr, tuple) else addr
                log("== radio %s connected on channel %d ==" % (peer, args.channel))
                sess = Session(conn, peer, args.hold_acl)

            if args.cycle and sess and sess.alive:
                hold, gap = args.cycle
                sess.press()
                time.sleep(hold)
                sess.release()
                time.sleep(gap)
                continue

            try:
                raw = input("emu> ").strip().lower()
            except EOFError:
                break
            if raw in ("", "p"):
                if sess:
                    sess.press()
            elif raw == "r":
                if sess:
                    sess.release()
            elif raw == "s":
                log("session: %s  PTT: %s"
                    % ("up" if sess and sess.alive else "none",
                       "DOWN" if sess and sess.down else "up"))
            elif raw == "q":
                break
            elif raw:
                log("---- %s ----" % raw)
    except KeyboardInterrupt:
        print()
    finally:
        if sess:
            sess.close()
        srv.close()
        log("emulator stopped")


if __name__ == "__main__":
    if sys.platform != "linux":
        sys.exit("This script requires Linux/BlueZ (raw AF_BLUETOOTH sockets).")
    main()
