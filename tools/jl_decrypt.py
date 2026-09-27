"""Decrypt a JieLi image with a given LFSR phase and inspect the result."""
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

import sys, os, re, collections, math

POLY = 0x1021

def step(k):
    return ((k << 1) ^ (POLY if k & 0x8000 else 0)) & 0xFFFF

def build_cycle(seed=0xFFFF):
    states, seen, k = [], {}, seed
    while k not in seen:
        seen[k] = len(states); states.append(k); k = step(k)
    return states, bytes(s & 0xFF for s in states)

def ent(d):
    if not d: return 0.0
    c = collections.Counter(d); n = len(d)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def hexdump(b, base=0, n=512):
    for i in range(0, min(len(b), n), 16):
        row = b[i:i+16]
        print(f"  {base+i:08x}  {row.hex(' '):<47}  "
              f"{''.join(chr(c) if 32 <= c < 127 else '.' for c in row)}")

def main():
    path, phase = sys.argv[1], int(sys.argv[2])
    data = open(path, 'rb').read()
    states, low = build_cycle()
    P = len(states)
    ks = bytes(low[(phase + i) % P] for i in range(len(data)))
    dec = bytes(a ^ b for a, b in zip(data, ks))

    out = os.path.splitext(path)[0] + f'.p{phase}.dec'
    open(out, 'wb').write(dec)
    print(f"phase={phase} key0=0x{states[phase % P]:04X} -> {out}")
    print(f"entropy whole={ent(dec):.4f}  zeros={dec.count(0):,}  ff={dec.count(0xFF):,}")

    print("\nper-4K-block entropy histogram (decrypted):")
    hist = collections.Counter()
    for i in range(0, len(dec), 4096):
        hist[round(ent(dec[i:i+4096]))] += 1
    for k in sorted(hist):
        print(f"   ~{k} bits: {'#'*hist[k]} ({hist[k]})")

    print("\n--- region 0x3d00 ---")
    hexdump(dec[0x3d00:0x4600], 0x3d00, 0x200)
    print("\n--- start ---")
    hexdump(dec[:0x100], 0, 0x100)

    strs = [(m.start(), m.group()) for m in re.finditer(rb'[\x20-\x7e]{6,}', dec)]
    print(f"\nprintable strings: {len(strs)}")
    for o, s in strs[:60]:
        print(f"  {o:08x}  {s.decode('latin1')}")

main()
