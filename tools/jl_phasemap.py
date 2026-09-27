"""Find the best JieLi LFSR phase for each block of an image.

Scoring = number of resulting 0x00 bytes (firmware plaintext is zero-rich).
Uses a histogram trick: for each byte value v, the phases that would decrypt
position i to zero are (index_of_v - i) mod P.
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

import sys, os, numpy as np, collections

POLY = 0x1021

def build_cycle(seed=0xFFFF):
    states, seen, k = [], {}, seed
    while k not in seen:
        seen[k] = len(states); states.append(k)
        k = ((k << 1) ^ (POLY if k & 0x8000 else 0)) & 0xFFFF
    return np.array([s & 0xFF for s in states], dtype=np.uint8)


def best_phases(block, ks, pos_by_val, P, topn=3):
    votes = np.zeros(P, dtype=np.int32)
    idx = np.arange(len(block))
    for v in np.unique(block):
        positions = idx[block == v]
        kpos = pos_by_val[v]
        if len(kpos) == 0 or len(positions) == 0:
            continue
        ph = (kpos[None, :] - positions[:, None]) % P
        np.add.at(votes, ph.ravel(), 1)
    order = np.argsort(votes)[::-1][:topn]
    return [(int(p), int(votes[p])) for p in order]


def main():
    path = sys.argv[1]
    bs = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x1000
    data = np.frombuffer(open(path, 'rb').read(), dtype=np.uint8)
    ks = build_cycle()
    P = len(ks)
    pos_by_val = [np.where(ks == v)[0] for v in range(256)]

    print(f"{os.path.basename(path)}  blocksize=0x{bs:x}  cycle={P}")
    print(f"{'offset':>10} {'best phase':>11} {'zeros':>7} {'expect':>7} {'delta=(ph-off)%P':>18}")
    rows = []
    for off in range(0, len(data), bs):
        blk = data[off:off + bs]
        if len(blk) < 64:
            continue
        if int((blk == 0xFF).sum()) > 0.9 * len(blk):
            print(f"{off:#010x}  {'(erased 0xFF)':>11}")
            continue
        res = best_phases(blk, ks, pos_by_val, P)
        p, n = res[0]
        exp = len(blk) / 256
        rows.append((off, p, n))
        print(f"{off:#010x} {p:11d} {n:7d} {exp:7.1f} {(p - off) % P:18d}")
    # summarise deltas
    print("\nmost common (phase-offset) deltas:")
    c = collections.Counter((p - off) % P for off, p, n in rows)
    for d, n in c.most_common(10):
        print(f"   delta={d:6d}  blocks={n}")

main()
