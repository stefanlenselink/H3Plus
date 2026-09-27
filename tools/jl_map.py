"""Map where raw JieLi keystream is exposed (plaintext 0x00 regions) and deduce
the cipher's reset/block structure.

For every 8-byte window in the file we test whether it is a valid subsequence of
the LFSR(0x1021) low-byte cycle. If so we record (file_offset, cycle_index).
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

POLY = 0x1021

def step(k):
    return ((k << 1) ^ (POLY if k & 0x8000 else 0)) & 0xFFFF

def build_cycle(seed=0xFFFF):
    states, seen, k = [], {}, seed
    while k not in seen:
        seen[k] = len(states)
        states.append(k)
        k = step(k)
    return states, bytes(s & 0xFF for s in states)

def main():
    path = sys.argv[1]
    W = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    data = open(path, 'rb').read()
    states, low = build_cycle()
    P = len(states)
    print(f"cycle length={P}, window={W}")

    # index every W-byte window of the (doubled) keystream
    seq = low + low[:W]
    table = {}
    for i in range(P):
        table.setdefault(seq[i:i+W], i)

    hits = []
    for off in range(0, len(data) - W):
        idx = table.get(data[off:off+W])
        if idx is not None:
            hits.append((off, idx))
    print(f"keystream-exposed windows: {len(hits)}")
    if not hits:
        return

    # group contiguous hits into runs
    runs = []
    cur = [hits[0]]
    for h in hits[1:]:
        if h[0] == cur[-1][0] + 1 and h[1] == (cur[-1][1] + 1) % P:
            cur.append(h)
        else:
            runs.append(cur); cur = [h]
    runs.append(cur)
    print(f"contiguous runs: {len(runs)}")
    print("\nfirst 30 runs:  file_off (len)  cycle_idx_at_start   (idx - off) mod P")
    for r in runs[:30]:
        off, idx = r[0]
        print(f"  0x{off:08x} ({len(r)+W-1:6d})  idx={idx:6d}   delta={(idx-off) % P:6d}   off%512={off%512:4d} off%4096={off%4096:5d}")

    # Test candidate reset block sizes
    print("\nTesting reset block sizes (phase must be constant within a block):")
    for B in (0x20, 0x40, 0x80, 0x100, 0x200, 0x400, 0x800, 0x1000, 0x10000, P):
        deltas = collections.Counter(((idx - (off % B)) % P) for off, idx in hits)
        top, n = deltas.most_common(1)[0]
        print(f"  block=0x{B:<6x} distinct_phases={len(deltas):6d}  top_phase={top:6d} covers {n}/{len(hits)} ({100*n/len(hits):.1f}%)")

if __name__ == '__main__':
    main()
