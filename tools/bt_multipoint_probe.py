#!/usr/bin/env python3
"""
Phase-0 multipoint probe: answer the ONE open question (Findings.md 9A.7).

Does the H3 Plus firmware allow TWO concurrent ACL connections - the SPP
channel held by one host (PTT-button role) while a second host (generic
headset role, HFP AG) attaches?

This tool automates the experiment that was never run:

    1. Connect SPP channel 2 from host A  (acts as the TID-PTT button)
    2. Verify the radio considers itself connected (squelch notifications
       flow, or at least the link stays up)
    3. While SPP is held, attempt an HFP (RFCOMM ch 6) connection from the
       SAME host  -> simulates "headset joins while button is connected"
    4. Report what the radio does:
         - both channels open            => multipoint OK, mic-routing problem
         - HFP refused (busy/refused)    => admission gate exists, find it
         - SPP dropped when HFP opens    => 1-link policy, kick-on-connect
    5. Reverse order: HFP first, then SPP.
    6. Optional: send +SPP=P while HFP is up; does the radio still key?

Run on Linux (BlueZ). The radio must already be paired with this host
(see tools/bt_wait_and_pair.sh). Keep PipeWire/WirePlumber running so HFP
has a local AG responder, or pass --no-hfp-sdp to skip the HFP leg.

USAGE
-----
    sudo python3 tools/bt_multipoint_probe.py AA:BB:CC:DD:EE:FF
    sudo python3 tools/bt_multipoint_probe.py AA:BB:CC:DD:EE:FF --reverse
    sudo python3 tools/bt_multipoint_probe.py AA:BB:CC:DD:EE:FF --ptt-hold 3

The tool prints a VERDICT line at the end; capture the whole output.
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

SPP_CH = 2      # radio's SPP endpoint (Findings.md 9A.18)
HFP_CH = 6      # radio's HFP-AG-role channel (9A.18; EBUSY when owned)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def try_connect(mac, channel, label, timeout=8.0):
    """Open an RFCOMM socket; return socket or None (reason in log)."""
    s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                      socket.BTPROTO_RFCOMM)
    s.settimeout(timeout)
    t0 = time.time()
    try:
        s.connect((mac, channel))
        log(f"{label}: CONNECTED ch{channel} in {time.time()-t0:.2f}s")
        return s
    except OSError as e:
        log(f"{label}: FAILED ch{channel}: {e!r}")
        try:
            s.close()
        except OSError:
            pass
        return None


def drain(s, label, seconds=1.0):
    """Read whatever the radio sends within `seconds`; log it."""
    s.settimeout(seconds)
    try:
        data = s.recv(256)
        if data:
            log(f"{label}: radio sent {data!r}")
            return data
        log(f"{label}: peer closed (0 bytes)")
        return b""
    except socket.timeout:
        return None
    except OSError as e:
        log(f"{label}: recv error {e!r}")
        return b""


def alive(s):
    """Cheap liveness probe: non-blocking recv; None = still open/quiet."""
    try:
        s.settimeout(0.2)
        d = s.recv(256)
        if d == b"":
            return False
        log(f"  (radio sent {d!r})")
        return True
    except socket.timeout:
        return True
    except OSError:
        return False


def probe(mac, hold=2.0, ptt_hold=0.0, no_hfp=False):
    result = {"spp": False, "hfp": False, "spp_survives": None,
              "hfp_after_spp": None, "spp_after_hfp": None,
              "ptt_during_both": None}

    log(f"=== multipoint probe vs {mac} ===")

    # --- leg 1: SPP (button role) ------------------------------------------
    spp = try_connect(mac, SPP_CH, "SPP/button")
    if spp is None:
        log("cannot even hold SPP - is the radio on, paired, and idle?")
        return result
    result["spp"] = True
    drain(spp, "SPP", 1.0)
    time.sleep(hold)
    if not alive(spp):
        log("SPP dropped on its own before the second leg - odd")

    # --- leg 2: HFP while SPP held (headset joins) --------------------------
    if not no_hfp:
        hfp = try_connect(mac, HFP_CH, "HFP/headset-while-SPP")
        result["hfp_after_spp"] = hfp is not None
        if hfp:
            result["hfp"] = True
            drain(hfp, "HFP", 1.0)
            time.sleep(hold)
            # did the radio kick SPP to make room?
            result["spp_survives"] = alive(spp)
            log(f"SPP survived HFP join? {result['spp_survives']}")
            if ptt_hold:
                spp.send(PRESS)
                log(f"PTT pressed while both up; holding {ptt_hold}s")
                time.sleep(ptt_hold)
                spp.send(RELEASE)
                spp.send(RELEASE)
                result["ptt_during_both"] = alive(spp) and alive(hfp)
                log(f"both alive after PTT? {result['ptt_during_both']}")
            hfp.close()
        else:
            # EBUSY/refused: check whether the radio's own HF-role attempt
            # owns ch6 (9A.17: radio initiates). Wait and retry once.
            log("retrying HFP in 5s (radio may own the channel itself)...")
            time.sleep(5)
            hfp = try_connect(mac, HFP_CH, "HFP/retry")
            result["hfp_after_spp"] = hfp is not None
            if hfp:
                result["hfp"] = True
                result["spp_survives"] = alive(spp)
                hfp.close()

    # --- leg 3: reverse order (headset first, then button) ------------------
    spp.close()
    log("SPP closed; 3s pause, then reverse order")
    time.sleep(3)
    if not no_hfp:
        hfp = try_connect(mac, HFP_CH, "HFP/headset-first")
        if hfp:
            time.sleep(hold)
            spp2 = try_connect(mac, SPP_CH, "SPP/while-HFP")
            result["spp_after_hfp"] = spp2 is not None
            if spp2:
                time.sleep(1)
                result["hfp_survives_spp"] = alive(hfp)
                spp2.close()
            hfp.close()
        else:
            log("reverse order: could not establish HFP first - skipping")
    return result


def verdict(r):
    log("=== VERDICT ===")
    if not r["spp"]:
        log("INCONCLUSIVE - SPP never came up")
        return
    if r["hfp_after_spp"] and r.get("spp_survives"):
        log("MULTIPOINT OK: radio holds SPP + HFP concurrently on separate")
        log("links. Feature reduces to mic routing + whitelist policy.")
    elif r["hfp_after_spp"] and r.get("spp_survives") is False:
        log("KICK-ON-CONNECT: second link evicts the first. Firmware caps")
        log("concurrent links at 1; admission gate must be patched.")
    elif r["hfp_after_spp"] is False:
        log("SECOND LINK REFUSED while SPP held (check EBUSY vs refused in")
        log("log above). If EBUSY: radio owns ch6 itself (HF role), not a")
        log("multipoint verdict - rerun with a real headset or --reverse.")
    if r.get("spp_after_hfp"):
        log("Reverse order: SPP joins while HFP up -> multipoint OK")
    elif r.get("spp_after_hfp") is False:
        log("Reverse order: SPP refused while HFP up -> 1-link cap")


def main():
    ap = argparse.ArgumentParser(description="H3 Plus dual-ACL multipoint probe")
    ap.add_argument("mac")
    ap.add_argument("--hold", type=float, default=2.0,
                    help="seconds to hold each leg before probing (def 2)")
    ap.add_argument("--ptt-hold", type=float, default=0.0,
                    help="if >0, send +SPP=P for this many seconds while "
                         "both links are up")
    ap.add_argument("--no-hfp", action="store_true",
                    help="SPP-only smoke run (no HFP leg)")
    args = ap.parse_args()
    r = probe(args.mac, args.hold, args.ptt_hold, args.no_hfp)
    verdict(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
