#!/usr/bin/env python3
"""
Find call/goto sites targeting a given VA in a decrypted JieLi app image.

Scans the 32-bit call/goto form documented in tools/isa/pi32v2.md lines
578/579:

    1110101010 Aaaaaa Bbbbbbbbbbbbbbbb    call `AaaaaaBbbbbbbbbbbbbbbb0`
    1110101011 Aaaaaa Bbbbbbbbbbbbbbbb    goto `AaaaaaBbbbbbbbbbbbbbbb0`

The displacement is signed and PC-relative to the *next* instruction
(see Findings.md 9A.26):

    target = addr + 4 + (sign_extend_23(A:B << 1))

Usage:
    python tools/xref.py work/app_dec.bin 0x01E50398
    python tools/xref.py work/app_dec.bin 0x01E50398 --goto
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
import struct

LOAD_BASE = 0x01E00000


def sign_extend(v, nbits):
    if v >> (nbits - 1):
        v -= 1 << nbits
    return v


def scan(data, base=LOAD_BASE, want_goto=False):
    """Yield (site_va, target_va, kind) for every 32-bit call/goto."""
    opc = 0b1110101011 if want_goto else 0b1110101010
    kind = "goto" if want_goto else "call"
    for off in range(0, len(data) - 4, 2):
        w0 = struct.unpack_from("<H", data, off)[0]
        if (w0 >> 6) != opc:
            continue
        a = w0 & 0x3F
        b = struct.unpack_from("<H", data, off + 2)[0]
        disp = sign_extend(((a << 16) | b) << 1, 23)
        yield base + off, (base + off + 4 + disp) & 0xFFFFFFFF, kind


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("target", help="target VA, e.g. 0x01E50398")
    ap.add_argument("--base", type=lambda x: int(x, 0), default=LOAD_BASE)
    ap.add_argument("--goto", action="store_true", help="scan goto instead of call")
    ap.add_argument("--both", action="store_true", help="scan call and goto")
    args = ap.parse_args()

    data = open(args.file, "rb").read()
    target = int(args.target, 0)

    kinds = [False, True] if args.both else [args.goto]
    hits = 0
    for g in kinds:
        for site, tgt, kind in scan(data, args.base, g):
            if tgt == target:
                off = site - args.base
                print("  %s from va 0x%08X  (off 0x%05X)" % (kind, site, off))
                hits += 1
    print("%d site(s) target 0x%08X" % (hits, target))


if __name__ == "__main__":
    main()
