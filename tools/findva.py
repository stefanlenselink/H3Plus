"""Find every reference to a VA (or any byte pattern) in a decrypted image.

Complements ``xref.py`` (which decodes real pi32v2 call/goto displacements):
this is a raw *byte-pattern* search that additionally tries the two encodings
patch sites use in this firmware —

  * 32-bit little-endian VA, e.g. ``38 5E E7 01`` for 0x01E75E38
    (pointer tables such as the nine PF S Press language lists);
  * the 24-bit ``target/2`` form used inside jump-table entries.

Each hit is reported with both the file offset and the VA of the *referring*
byte, so the result can be fed straight to ``pi32dis.py --off`` /
``xref.py``.

Usage:
    python tools/findva.py <file> <VA> [VA...] [--half] [--raw HEXBYTES]

    file        decrypted app image (offset 0 = VA 0x01E00000), or any file
    VA          address to search for, hex (0x...) or decimal; repeatable
    --half      also search the 24-bit target/2 encoding of each VA
    --raw HEX   search this literal byte string instead of / besides VAs

Examples (Findings.md 9A.47/9A.48 work):
    # who points at the "PTT2" string?  -> the nine PF list entries
    python tools/findva.py work/app_dec.bin 0x01E8E30E
    # find the RU "NET" string bytes
    python tools/findva.py work/app_dec.bin --raw D09DD095D0A200
    # absolute /2 jump-table entries (note: the tbb table at 0x01E75DDC is
    # RELATIVE (target-table)/2 -- use pf78tbl.py to decode that one)
    python tools/findva.py work/app_dec.bin 0x01E75E38 --half
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

import sys

APP_VA_BASE = 0x01E00000


def find_all(data, pat):
    out, off = [], 0
    while True:
        i = data.find(pat, off)
        if i < 0:
            return out
        out.append(i)
        off = i + 1


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    path = args[0]
    args = args[1:]
    half = "--half" in args
    raws = []
    while "--raw" in args:
        k = args.index("--raw")
        raws.append(bytes.fromhex(args[k + 1]))
        del args[k:k + 2]
    args = [a for a in args if not a.startswith("--")]
    vas = [int(a, 0) for a in args]
    if not vas and not raws:
        sys.exit("give at least one VA or --raw HEX")

    data = open(path, "rb").read()
    total = 0
    for va in vas:
        pat = va.to_bytes(4, "little")
        hits = find_all(data, pat)
        print("VA 0x%08X (32-bit LE): %d hit(s)" % (va, len(hits)))
        for i in hits:
            print("  file 0x%06X  ref VA 0x%08X" % (i, i + APP_VA_BASE))
        total += len(hits)
        if half:
            pat = (va // 2).to_bytes(3, "little")
            hits = find_all(data, pat)
            print("VA 0x%08X (24-bit target/2): %d hit(s)" % (va, len(hits)))
            for i in hits:
                print("  file 0x%06X  ref VA 0x%08X" % (i, i + APP_VA_BASE))
            total += len(hits)
    for pat in raws:
        hits = find_all(data, pat)
        print("raw %s: %d hit(s)" % (pat.hex(), len(hits)))
        for i in hits:
            print("  file 0x%06X  VA 0x%08X" % (i, i + APP_VA_BASE))
        total += len(hits)
    sys.exit(0 if total else 1)


if __name__ == "__main__":
    main()
