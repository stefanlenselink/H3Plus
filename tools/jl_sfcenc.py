"""
JieLi SFC/ENC hardware-scrambler decryptor for BR23 (AC635N/AC695N).

The app region of the H3 Plus image is NOT encrypted by the continuous
"ENC" LFSR stream used for UBOOT. Instead it is descrambled on the fly by
the SFC ENC hardware block that sits between the SPI flash controller and
the instruction cache.

Per kagaimiq/jielie (periph/sfc.md):

    "Due to the cache line size, the data is scrambled in 32-byte blocks,
     additionally the key used for scrambling is the actual key set up in
     the ENC/SFCENC XORed with the absolute memory address shifted right
     by 2, i.e. key = key ^ (addr >> 2)."

So for every 32-byte cache line:

    seed = chipkey ^ (addr >> 2)          # 16-bit
    then run the ordinary JieLi ENC LFSR (poly 0x1021) over those 32 bytes,
    reseeding at the start of every line.

For the H3 Plus:
    chipkey   = 0xF181   (read from hardware with jl-uboot-tool)
    app start = 0x5000   (flash offset)
    addresses are counted RELATIVE to the app start, i.e. the SFC base
    address offset is programmed so the app begins at mapped address 0.

Usage:
    python tools/jl_sfcenc.py <file> [outfile] [--key 0xF181]
                              [--start 0x5000] [--end 0xC8FE0] [--base 0]
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

POLY = 0x1021
LINE = 32


def sfc_enc_decrypt(data, base=0, chipkey=0xF181):
    """Descramble `data` as if read through the SFC ENC block.

    `base` is the mapped address of data[0] (relative to the SFC base offset).
    """
    out = bytearray(data)
    for off in range(0, len(data), LINE):
        k = (chipkey ^ ((base + off) >> 2)) & 0xFFFF
        for i in range(off, min(off + LINE, len(data))):
            out[i] ^= k & 0xFF
            k = ((k << 1) ^ (POLY if k & 0x8000 else 0)) & 0xFFFF
    return bytes(out)


def _stats(b):
    import collections
    import math

    c = collections.Counter(b)
    n = len(b)
    ent = -sum(v / n * math.log2(v / n) for v in c.values()) if n else 0
    return ent, b.count(0), b.count(0xFF)


def find_base(data, chipkey=0xF181, limit=0x20000):
    """Brute-force the mapped base address by maximising the zero count."""
    best = []
    for base in range(0, limit, LINE):
        best.append((sfc_enc_decrypt(data, base, chipkey).count(0), base))
    best.sort(reverse=True)
    return best[:10]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {}
    for a in sys.argv[1:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("=")
            opts[k] = v

    if not args:
        print(__doc__)
        return 1

    path = args[0]
    outp = args[1] if len(args) > 1 else path + ".sfcdec"

    key = int(opts.get("key", "0xF181"), 0)
    start = int(opts.get("start", "0x5000"), 0)
    end = int(opts.get("end", "0"), 0)
    base = int(opts.get("base", "0"), 0)

    with open(path, "rb") as f:
        raw = f.read()

    seg = raw[start:end] if end else raw[start:]

    ent, z, ff = _stats(seg)
    print(f"in : {len(seg)} bytes  entropy={ent:.4f} zeros={z} ff={ff}")

    dec = sfc_enc_decrypt(seg, base, key)

    ent, z, ff = _stats(dec)
    print(f"out: {len(dec)} bytes  entropy={ent:.4f} zeros={z} ff={ff}")
    print(f"key=0x{key:04X} start=0x{start:X} base=0x{base:X}")

    with open(outp, "wb") as f:
        f.write(dec)
    print("wrote", outp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
