"""Decode the PF S Press executor dispatch in the H3 Plus firmware.

Reads the decrypted app image and prints:

  1. the eight-entry ``tbb r0`` press-dispatch table (value 1..8 -> body VA),
  2. the two release-executor ``if (r0 == imm) goto`` compares with their
     decoded immediates.

This is the machinery behind the ``--PTT2=`` / ``--OD-PTT=`` actions of
``patch_h3plus_firmware_bluetooth.py`` (Findings.md 9A.47 / 9A.48): stored menu value 7 runs
the "PTT2" body, value 8 the "OD PTT" body, and the swap patch exchanges both
the tbb entries and the release compare immediates.

Encodings (pi32v2, Findings.md 9A.48):
  * ``tbb r0`` at 0x01E75DDA indexes the 8-entry byte table at 0x01E75DDC;
    each entry is ``(target - table) / 2``.
  * ``if (r0 == N) goto`` is word0 = ``00 f8``, word1 = ``(N << 9) | disp9``,
    so the immediate is ``word1 >> 9``.

Usage:
    python tools/pf78tbl.py [app_dec.bin]

    app_dec.bin  decrypted app image, file offset 0 = VA 0x01E00000
                 (default: work/app_dec.bin; produce it with
                 python tools/jl_sfcenc.py BIN/TD-H3-PlusV1.0.50.bin \\
                     work/app_dec.bin --key=0xF181 --start=0x5000 --end=0xC8FE0)

A stock v1.0.50 image prints value 7 -> 0x01E75E38, value 8 -> 0x01E75E42,
and release compare immediates 8 (at 0x01E75E7A) and 7 (at 0x01E75E7E).
Exit 1 if the image doesn't look right (tbb entries 6/7 too small, or the
`00 f8` compare word0 missing before either release compare address).
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
TBL_VA = 0x01E75DDC          # tbb r0 press-dispatch table, 8 entries
TBL_COUNT = 8
REL_CMP1_VA = 0x01E75E7A     # first release compare (stock imm 8)
REL_CMP2_VA = 0x01E75E7E     # second release compare (stock imm 7)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "work/app_dec.bin"
    data = open(path, "rb").read()

    def at(va):
        return va - APP_VA_BASE

    off = at(TBL_VA)
    entries = data[off:off + TBL_COUNT]
    # Sanity: the two dispatch bodies live well past the table (entries 6/7
    # >= 0x2C) and the release compares must carry the `00 f8` word0. A wrong
    # input file (still encrypted, wrong base) fails this instead of printing
    # plausible-looking garbage.
    if entries[6] < 0x2C or entries[7] < 0x2C:
        sys.exit("%s: table at 0x%08X does not look like the tbb dispatch "
                 "(need a decrypted app image, offset 0 = VA 0x01E00000)"
                 % (path, TBL_VA))
    for va in (REL_CMP1_VA, REL_CMP2_VA):
        if data[at(va) - 2:at(va)] != b"\x00\xf8":
            sys.exit("%s: no `00 f8` compare word before 0x%08X - wrong image?"
                     % (path, va))
    print("%s  tbb press-dispatch table @ 0x%08X" % (path, TBL_VA))
    print("  entries: " + " ".join("%02X" % b for b in entries))
    for i, e in enumerate(entries):
        print("  value %d -> 0x%08X" % (i + 1, TBL_VA + 2 * e))

    print("\nrelease-executor compares (imm = word1 >> 9):")
    for va in (REL_CMP1_VA, REL_CMP2_VA):
        word1 = int.from_bytes(data[at(va):at(va) + 2], "little")
        imm = word1 >> 9
        print("  0x%08X: imm %d" % (va, imm))


if __name__ == "__main__":
    main()
