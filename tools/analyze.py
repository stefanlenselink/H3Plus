"""Structural analysis of TIDRADIO H3 Plus firmware images."""
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

import sys, os, math, collections

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def entropy(data):
    if not data:
        return 0.0
    c = collections.Counter(data)
    n = len(data)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def ic(data):
    """Index of coincidence-ish: probability two random bytes match."""
    c = collections.Counter(data)
    n = len(data)
    if n < 2:
        return 0.0
    return sum(v * (v - 1) for v in c.values()) / (n * (n - 1))


def find_xor_period(data, maxp=1024):
    """For repeating-key XOR, data[i] ^ data[i+p] == 0 often when p == keylen
    and plaintext is constant (padding). Score by match rate."""
    scores = []
    n = min(len(data), 200000)
    d = data[:n]
    for p in range(1, maxp + 1):
        same = sum(1 for i in range(0, n - p, 7) if d[i] == d[i + p])
        total = len(range(0, n - p, 7))
        scores.append((same / total, p))
    scores.sort(reverse=True)
    return scores[:15]


def report(path):
    data = open(path, 'rb').read()
    print(f"\n=== {os.path.basename(path)}  ({len(data)} bytes) ===")
    print(f"  whole-file entropy : {entropy(data):.4f} bits/byte")
    print(f"  index of coincid.  : {ic(data):.6f}  (random=0.003906)")
    # byte histogram extremes
    c = collections.Counter(data)
    top = c.most_common(5)
    print(f"  top bytes          : {[(hex(b), n) for b, n in top]}")
    print(f"  distinct bytes     : {len(c)}")
    # blockwise entropy to find plain vs encrypted regions
    bs = 4096
    ents = [entropy(data[i:i + bs]) for i in range(0, len(data), bs)]
    low = [(i, e) for i, e in enumerate(ents) if e < 6.0]
    print(f"  blocks(4k)         : {len(ents)}, low-entropy blocks: {len(low)}")
    if low:
        print(f"    first few low    : {[(hex(i*bs), round(e,2)) for i, e in low[:8]]}")
    print(f"  top XOR periods    : {[(round(s,3), p) for s, p in find_xor_period(data)[:8]]}")


def dup_blocks(path, bs=16):
    data = open(path, 'rb').read()
    seen = collections.Counter()
    for i in range(0, len(data) - bs, bs):
        seen[data[i:i + bs]] += 1
    dups = seen.most_common(5)
    print(f"  repeated {bs}B blocks: {[(b.hex(), n) for b, n in dups if n > 1][:3]}")


if __name__ == '__main__':
    targets = sys.argv[1:]
    if not targets:
        targets = [
            os.path.join(BASE, 'BIN', 'TID-H3-PlusV1.0.45.bin'),
            os.path.join(BASE, 'FW', 'TID-H3-PlusV1.0.45.fw'),
            os.path.join(BASE, 'BIN', 'TD-H3-PlusV1.0.50.bin'),
            os.path.join(BASE, 'FW', 'TD-H3-PlusV1.0.50.fw'),
        ]
    for t in targets:
        report(t)
        dup_blocks(t, 16)
