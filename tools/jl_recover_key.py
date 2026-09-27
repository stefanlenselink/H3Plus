"""Recover the JieLi 32-byte XOR keystream statistically, then identify the
16-bit LFSR chipkey that generates it.

Idea: plaintext firmware is dominated by 0x00 bytes. If ciphertext = plaintext
XOR keytable[i % 32], then for each phase p the most frequent ciphertext byte
should be keytable[p] ^ 0x00 = keytable[p].
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

import sys, os, collections


def keytable(key, n=32):
    t = bytearray()
    for _ in range(n):
        t.append(key & 0xFF)
        key = ((key << 1) ^ (0x1021 if key & 0x8000 else 0)) & 0xFFFF
    return bytes(t)


def recover(data, period=32, skip_ff=True, blocksize=64):
    """Return per-phase byte frequency ranking."""
    hist = [collections.Counter() for _ in range(period)]
    for base in range(0, len(data) - blocksize, blocksize):
        blk = data[base:base + blocksize]
        if skip_ff and blk.count(0xFF) > blocksize * 0.5:
            continue          # erased flash region
        for i, b in enumerate(blk):
            hist[(base + i) % period][b] += 1
    return hist


def main():
    path = sys.argv[1]
    period = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    data = open(path, 'rb').read()
    hist = recover(data, period)

    print(f"=== {os.path.basename(path)}  period={period} ===")
    top1 = bytes(h.most_common(1)[0][0] if h else 0 for h in hist)
    print(f"most-common-per-phase : {top1.hex(' ')}")
    # show confidence
    conf = []
    for h in hist:
        mc = h.most_common(2)
        tot = sum(h.values()) or 1
        conf.append(mc[0][1] / tot)
    print(f"confidence            : min={min(conf):.3f} avg={sum(conf)/len(conf):.3f}")

    # Does top1 correspond to an LFSR sequence? Try every 16-bit seed.
    print("\nMatching against LFSR(poly=0x1021) sequences:")
    best = []
    for key in range(0x10000):
        t = keytable(key, period)
        match = sum(1 for a, b in zip(t, top1) if a == b)
        best.append((match, key))
    best.sort(reverse=True)
    for match, key in best[:5]:
        print(f"  key=0x{key:04X}  matches {match}/{period}  {keytable(key, period).hex(' ')}")

    # also try phase-rotated versions of the recovered stream
    print("\nBest match allowing keystream rotation:")
    found = []
    for key in range(0x10000):
        t = keytable(key, period)
        for rot in range(period):
            r = bytes(t[(i + rot) % period] for i in range(period))
            match = sum(1 for a, b in zip(r, top1) if a == b)
            if match >= period - 2:
                found.append((match, key, rot))
    found.sort(reverse=True)
    for match, key, rot in found[:10]:
        print(f"  key=0x{key:04X} rot={rot} matches {match}/{period}")
    if not found:
        print("  (none >= period-2)")


if __name__ == '__main__':
    main()
