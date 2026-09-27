"""Brute-force the JieLi 16-bit ENC cipher key against H3 Plus firmware images.

JieLi 'ENC' cipher: a 16-bit LFSR (poly 0x1021) seeded with the chipkey.
In the flash-image variant the keystream is materialised as a 32-byte table
which is then XORed cyclically over the data.
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

import sys, os, re, collections, math

def keytable(key, n=32):
    t = bytearray()
    for _ in range(n):
        t.append(key & 0xFF)
        key = ((key << 1) ^ (0x1021 if key & 0x8000 else 0)) & 0xFFFF
    return bytes(t)


def xor_table(data, tbl, phase=0):
    out = bytearray(len(data))
    n = len(tbl)
    for i, b in enumerate(data):
        out[i] = b ^ tbl[(i + phase) % n]
    return bytes(out)


# markers we'd expect inside a decrypted JieLi flash image
MARKERS = [b'JL', b'jl_', b'app.bin', b'uboot', b'AC69', b'AD69', b'bank',
           b'SDFILE', b'CONFIG', b'cfg_tool', b'.bin', b'.res', b'.TAB',
           b'tone', b'btstack', b'sdk', b'VERSION', b'Ver', b'spi', b'flash']


def score(buf):
    """Heuristic: real code/data has many zero bytes and long ASCII runs."""
    s = 0
    s += buf.count(0) * 1.0
    for m in re.finditer(rb'[\x20-\x7e]{8,}', buf):
        s += len(m.group()) * 4
    for mk in MARKERS:
        s += buf.count(mk) * 200
    return s


def entropy(d):
    if not d:
        return 0.0
    c = collections.Counter(d); n = len(d)
    return -sum((v/n)*math.log2(v/n) for v in c.values())


def main():
    path = sys.argv[1]
    data = open(path, 'rb').read()
    # sample a few chunks from the middle of the image, skipping 0xFF padding
    samples = []
    for off in range(0x1000, len(data) - 0x2000, 0x8000):
        chunk = data[off:off + 0x2000]
        if chunk.count(0xFF) > len(chunk) * 0.5:
            continue
        samples.append((off, chunk))
        if len(samples) >= 12:
            break
    print(f"{os.path.basename(path)}: {len(samples)} sample chunks")

    results = []
    for key in range(0x10000):
        tbl = keytable(key)
        tot = 0
        for off, chunk in samples:
            tot += score(xor_table(chunk, tbl, off % 32))
        results.append((tot, key))
    results.sort(reverse=True)
    print("\nTop 15 candidate keys:")
    for sc, key in results[:15]:
        print(f"  key=0x{key:04X}  score={sc:,.0f}  table={keytable(key)[:8].hex(' ')}")
    return results


if __name__ == '__main__':
    main()
