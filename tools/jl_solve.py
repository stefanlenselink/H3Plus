"""Solve the JieLi ENC cipher for the H3 Plus images.

The cipher is:
    for each byte:  out[i] = in[i] ^ (key & 0xFF)
                    key = ((key << 1) ^ (0x1021 if key & 0x8000 else 0)) & 0xFFFF

Wherever the plaintext is 0x00 the ciphertext *is* the raw keystream, so we can
locate such a run, match it against the LFSR cycle, and recover the phase.
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


def step(key):
    return ((key << 1) ^ (POLY if key & 0x8000 else 0)) & 0xFFFF


def cycles():
    """Enumerate all LFSR cycles; return list of (states, lowbytes)."""
    seen = set()
    out = []
    for start in range(1, 0x10000):
        if start in seen:
            continue
        states = []
        k = start
        while k not in seen:
            seen.add(k)
            states.append(k)
            k = step(k)
        if k == start:                       # a real cycle
            out.append(states)
        else:                                # tail leading into known cycle
            for s in states:
                pass
    return out


def build_cycle():
    """Return (states, lowbytes) for the main cycle containing 0xFFFF."""
    k0 = 0xFFFF
    states = []
    seen = {}
    k = k0
    while k not in seen:
        seen[k] = len(states)
        states.append(k)
        k = step(k)
    return states, bytes(s & 0xFF for s in states), seen


def find_zero_runs(data, minlen=32):
    """Find repeated byte-runs likely to be encrypted 0x00 padding."""
    counts = collections.Counter()
    for i in range(0, len(data) - 16, 16):
        counts[data[i:i+16]] += 1
    return [b for b, n in counts.most_common(40) if n > 1 and b != b'\xff'*16]


def main():
    path = sys.argv[1]
    data = open(path, 'rb').read()
    states, low, index_of = build_cycle()
    P = len(states)
    print(f"LFSR cycle length (from 0xFFFF): {P}")

    seq = low + low          # doubled for easy substring search
    cands = find_zero_runs(data)
    print(f"candidate keystream runs: {len(cands)}")

    phases = collections.Counter()
    for pat in cands:
        idx = seq.find(pat)
        if idx < 0 or idx >= P:
            continue
        off = data.find(pat)
        while off >= 0:
            phases[(idx - off) % P] += 1
            off = data.find(pat, off + 1)

    if not phases:
        print("No keystream run matched the LFSR cycle.")
        return
    print("\nPhase votes (phase = cycle index at file offset 0):")
    for ph, n in phases.most_common(5):
        print(f"  phase={ph}  votes={n}  -> key at offset 0 = 0x{states[ph]:04X}")

    phase = phases.most_common(1)[0][0]
    key0 = states[phase]
    print(f"\n>>> Recovered initial key = 0x{key0:04X} (phase {phase}) <<<")

    # decrypt
    ks = bytes(low[(phase + i) % P] for i in range(len(data)))
    dec = bytes(a ^ b for a, b in zip(data, ks))
    outp = os.path.splitext(path)[0] + '.dec.bin'
    open(outp, 'wb').write(dec)
    print(f"wrote {outp}")

    import re, math
    print(f"decrypted zero bytes: {dec.count(0):,} / {len(dec):,}")
    print(f"decrypted 0xFF bytes: {dec.count(0xFF):,}")
    c = collections.Counter(dec); n = len(dec)
    ent = -sum((v/n)*math.log2(v/n) for v in c.values())
    print(f"decrypted entropy   : {ent:.4f}")
    strs = [m.group() for m in re.finditer(rb'[\x20-\x7e]{6,}', dec)]
    print(f"printable strings   : {len(strs)}")
    for s in strs[:40]:
        print('   ', s.decode('latin1'))


if __name__ == '__main__':
    main()
