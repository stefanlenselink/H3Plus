#!/usr/bin/env python3
"""
RFCOMM channel-map prober — enumerate EVERY open channel on a peer and see
which ones actually carry PTT events, holding them all open at once.

WHY THIS EXISTS
---------------
`bt_ag_capture.py --connect` brute-forces channels 1-30 but STOPS at the first
opener, so the TID-PTT button's full channel map was never enumerated. Card
P0.2 Run A (ch. 39 §39.4) found the button opens **channel 10 while in
pairing-blink** and **channel 2 when bonded/idle** — other channels may exist
too, and "open" does not mean "talks". This prober:

    1. tries every channel in range, KEEPING every socket that opens;
    2. holds them all connected for N seconds while you press the button;
    3. reports per channel: open? bytes seen? +SPP events decoded?;
    4. closes everything at once at the end (a single early close could trip
       the button's drop-ACL-on-SPP-close quirk, §38.1, mid-test).

LINUX/BlueZ ONLY (part of the bt_* rig). Run as root.

USAGE
-----
    sudo python3 tools/bt_ptt_channel_probe.py 6F:E5:E7:FB:12:4F
    sudo python3 tools/bt_ptt_channel_probe.py <mac> --channels 1-12 --hold 15
    sudo python3 tools/bt_ptt_channel_probe.py <mac> --only 2,10 --hold 10

Tip: run once bonded/idle and once right after a button blink to compare the
channel maps of the two states (P0.2 follow-up, ch. 39 §39.4).
"""
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Stefan Lenselink

import argparse
import select
import socket
import sys
import time

TIMEOUT = 3.0  # per-channel connect timeout


def fmt_status(err):
    """Human label for a failed connect."""
    if isinstance(err, socket.timeout):
        return "TIMEOUT"
    if isinstance(err, OSError):
        return {111: "REFUSED", 112: "HOST-DOWN", 16: "BUSY", 110: "TIMEOUT"}.get(
            err.errno, f"ERRNO-{err.errno}"
        )
    return str(err)


def open_channels(mac, channels, log):
    """Probe every channel; return {ch: socket} for the openers."""
    live = {}
    for ch in channels:
        s = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
        )
        s.settimeout(TIMEOUT)
        try:
            s.connect((mac, ch))
            s.setblocking(False)
            live[ch] = s
            log(f"  ch {ch:>2}: OPEN (kept connected)")
        except (socket.timeout, OSError) as e:
            s.close()
            log(f"  ch {ch:>2}: {fmt_status(e)}")
    return live


def drain(socks, bufs, log):
    """Non-blocking read pass over all live sockets; decode NUL-terminated frames."""
    if not socks:
        return []
    readable, _, _ = select.select(list(socks.values()), [], [], 0.2)
    events = []
    for s in readable:
        try:
            data = s.recv(1024)
        except (BlockingIOError, OSError):
            continue
        if not data:  # peer closed this channel
            ch = next(k for k, v in socks.items() if v is s)
            log(f"  ch {ch:>2}: CLOSED by peer")
            s.close()
            del socks[ch]
            continue
        ch = next(k for k, v in socks.items() if v is s)
        raw = " ".join(f"{b:02x}" for b in data)
        log(f"  ch {ch:>2}  raw {raw}")
        bufs[ch] += data
        *frames, bufs[ch] = bufs[ch].split(b"\x00")
        for f in frames:
            try:
                text = f.decode("ascii", "replace")
            except Exception:
                text = repr(f)
            if text:
                events.append((ch, text))
                log(f"  ch {ch:>2}  event {text!r}")
    return events


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("mac", help="peer BD_ADDR, e.g. 6F:E5:E7:FB:12:4F")
    ap.add_argument("--channels", default="1-30", help="range, default 1-30")
    ap.add_argument("--only", help="comma/range list overrides --channels, e.g. 2,10 or 1-12")
    ap.add_argument("--hold", type=float, default=10.0, help="watch seconds, default 10")
    args = ap.parse_args()

    def parse(spec):
        """'1-12,20,25-27' -> [1..12, 20, 25, 26, 27] (accepts ranges and lists)."""
        out = []
        for part in spec.split(","):
            part = part.strip()
            if "-" in part:
                lo, hi = part.split("-", 1)
                out.extend(range(int(lo), int(hi) + 1))
            else:
                out.append(int(part))
        return sorted(set(out))

    channels = parse(args.only if args.only else args.channels)

    def log(msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    log(f"probing {len(channels)} channel(s) on {args.mac} (openers stay connected)")
    socks = open_channels(args.mac, channels, log)
    if not socks:
        log("no channel opened — peer may need bonding or a pairing blink")
        sys.exit(1)

    bufs = {ch: b"" for ch in socks}
    tally = {ch: 0 for ch in socks}
    log(f"{len(socks)} channel(s) open: {sorted(socks)}")
    log(f"PRESS THE BUTTON NOW for the next {args.hold:.0f} seconds ...")

    end = time.monotonic() + args.hold
    while time.monotonic() < end and socks:
        for ch, text in drain(socks, bufs, log):
            tally[ch] += 1

    log("---- summary ----")
    for ch in channels:
        if ch in tally:
            state = "OPEN" if ch in socks else "closed-mid-test"
            log(f"  ch {ch:>2}: {state}, {tally[ch]} event(s)")
        # failed probes were already logged
    log(f"{len(socks)} channel(s) still open — closing ALL at once")
    for s in socks.values():
        s.close()


if __name__ == "__main__":
    main()
