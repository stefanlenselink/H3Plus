#!/usr/bin/env python3
"""
Verify candidate free-space blocks in a decrypted JieLi app image.

A block of 0x00 bytes in flash is only usable for code if (a) the disassembler
treats it as data (not live code), (b) nothing points at it, and (c) it is
stable padding across firmware versions (not a runtime-initialized data area).

This tool checks (a) statically against a toolchain-style listing (full.lst,
format: "VA BYTES [flashoff] mnemonic") and (c) against one or more decrypted
app images of other firmware versions (same app layout assumed: app starts at
--base in each image).

Usage:
    python tools/freespace.py work/app_dec.bin --min 64
    python tools/freespace.py work/app_dec.bin --min 64 \
        --lst work/full.lst \
        --other 45=work/decrypted/TID-H3-PlusV1.0.45.p32591.dec \
        --appoff 0x5000
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
import sys

LOAD_BASE = 0x01E00000


def zero_runs(data, minlen):
    """Yield (offset, length) of every run of >= minlen zero bytes."""
    run = 0
    for i, b in enumerate(data):
        if b == 0:
            run += 1
        else:
            if run >= minlen:
                yield i - run, run
            run = 0
    if run >= minlen:
        yield len(data) - run, run


def load_lst_flags(lst_path, lo, hi):
    """For [lo,hi) app offsets, classify listing coverage.

    Returns dict offset -> 'code' | 'data' for offsets present in the listing.
    A line counts as code unless the mnemonic is '.word' (unknown encoding)
    or the line is a raw-data dump.
    """
    flags = {}
    pat = re.compile(r"^([0-9A-Fa-f]{6,8})\s+([0-9A-Fa-f ]+)\s+\[([0-9A-Fa-f]+)\]\s+(.*)$")
    with open(lst_path, "r", encoding="ascii", errors="replace") as f:
        for line in f:
            m = pat.match(line.rstrip("\n"))
            if not m:
                continue
            foff = int(m.group(3), 16)
            if not (lo <= foff < hi):
                continue
            nbytes = len(m.group(2).split())
            mnem = m.group(4).strip()
            kind = "data" if mnem.startswith(".word") else "code"
            for k in range(nbytes):
                flags[foff + k] = kind
    return flags


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("image", help="decrypted app image (app region only)")
    ap.add_argument("--min", type=lambda x: int(x, 0), default=64,
                    help="minimum zero-run length (default 64)")
    ap.add_argument("--lst", help="full.lst to classify runs (code vs data)")
    ap.add_argument("--other", action="append", default=[],
                    help="NAME=path of another whole-bin decrypted image, "
                         "repeated. Compared at the same app offset.")
    ap.add_argument("--appoff", type=lambda x: int(x, 0), default=0,
                    help="offset of the app region inside --other images "
                         "(e.g. 0x5000 for whole-flash decrypts)")
    args = ap.parse_args()

    data = open(args.image, "rb").read()
    runs = list(zero_runs(data, args.min))
    if not runs:
        print(f"no zero runs >= {args.min} bytes found")
        return

    flags = {}
    if args.lst:
        lo, hi = 0, len(data)
        flags = load_lst_flags(args.lst, lo, hi)

    others = []
    for spec in args.other:
        name, path = spec.split("=", 1)
        others.append((name, open(path, "rb").read()))

    print(f"{'VA':>10} {'off':>9} {'len':>6}  {'lst':16} {'others'}")
    for off, ln in runs:
        va = LOAD_BASE + off
        # listing classification for the run
        kinds = {flags.get(off + k) for k in range(ln)}
        if not flags:
            lstinfo = "n/a"
        else:
            ncode = sum(1 for k in range(ln) if flags.get(off + k) == "code")
            cov = len(kinds - {None})
            lstinfo = f"code={ncode}/{ln}"
            if kinds == {"data"}:
                lstinfo += " DATA-only"
            elif kinds == {None}:
                lstinfo += " not-in-lst"
        # cross-version comparison
        oinfo = []
        for name, odata in others:
            oo = args.appoff + off
            chunk = odata[oo:oo + ln]
            if len(chunk) < ln:
                oinfo.append(f"{name}:short")
                continue
            nz = sum(1 for b in chunk if b != 0)
            same = sum(1 for b in chunk if b == 0)
            oinfo.append(f"{name}:zero={nz}/{ln}" if nz else f"{name}:ALLZERO")
        print(f"{va:#010x} {off:#09x} {ln:6d}  {lstinfo:16} {' '.join(oinfo)}")


if __name__ == "__main__":
    sys.exit(main())
