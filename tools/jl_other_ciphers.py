"""Try the other known JieLi ciphers (CrcDecode/'MengLi' and RxGp) against the
app region of the H3 Plus image."""
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

import sys, collections, math

try:
    import crcmod
    jl_crc16 = crcmod.mkCrcFun(0x11021, initCrc=0x0000, rev=False)
except ImportError:
    def jl_crc16(data, crc=0x0000):
        for b in data:
            crc ^= b << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        return crc

MAGIC = "孟黎我爱你，玉林".encode('gb2312')


def crc_keystream(n, key=0xFFFFFFFF):
    crc = jl_crc16(int.to_bytes(key >> 16, 2, 'little'), key & 0xFFFF)
    out = bytearray()
    for i in range(n):
        mi = i % len(MAGIC)
        crc = jl_crc16(MAGIC[mi:mi+1], crc)
        out.append(crc & 0xFF)
    return bytes(out)


def rxgp_keystream(n):
    rng = 0x70477852
    out = bytearray()
    for _ in range(n):
        rng = (rng * 16807) + (rng // 127773) * -0x7FFFFFFF
        out.append(rng & 0xFF)
    return bytes(out)


def ent(d):
    c = collections.Counter(d); n = len(d)
    return -sum((v/n)*math.log2(v/n) for v in c.values())


def score(buf):
    return buf.count(0)


def main():
    path = sys.argv[1]
    data = open(path, 'rb').read()
    app_start = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x5000
    app = data[app_start:app_start + 0x10000]
    print(f"app region 0x{app_start:x}, {len(app)} bytes, entropy={ent(app):.4f}, zeros={app.count(0)}")

    for name, ks in (('CrcDecode/MengLi', crc_keystream(len(app))),
                     ('RxGp', rxgp_keystream(len(app)))):
        dec = bytes(a ^ b for a, b in zip(app, ks))
        print(f"  {name:<18} zeros={score(dec):6d}  entropy={ent(dec):.4f}")

    # keystream periodicity of CrcDecode
    ks = crc_keystream(0x4000)
    per = None
    for p in range(1, 0x2000):
        if ks[:0x1000] == ks[p:p+0x1000]:
            per = p; break
    print(f"  CrcDecode keystream period: {per}")

    # Is the app region XOR-periodic at ANY period up to 8192?
    print("\nXOR self-correlation of app region (match rate, random=0.0039):")
    best = []
    for p in range(1, 8192):
        same = sum(1 for i in range(0, len(app) - p, 13) if app[i] == app[i+p])
        tot = len(range(0, len(app) - p, 13))
        best.append((same/tot, p))
    best.sort(reverse=True)
    print("  top:", [(round(s, 4), p) for s, p in best[:10]])


main()
