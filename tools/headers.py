"""Compare headers/footers of all firmware images."""
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

import os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def show(path, n=64):
    d = open(path, 'rb').read()
    head = d[:n]
    tail = d[-n:]
    def fmt(b):
        h = b.hex(' ')
        a = ''.join(chr(c) if 32 <= c < 127 else '.' for c in b)
        return h, a
    print(f"\n--- {os.path.basename(path):<32} size={len(d)} (0x{len(d):x})")
    h, a = fmt(head)
    print(f"  HEAD hex: {h}")
    print(f"  HEAD asc: {a}")
    h, a = fmt(tail)
    print(f"  TAIL hex: {h}")
    print(f"  TAIL asc: {a}")

for folder in ('BIN', 'FW'):
    p = os.path.join(BASE, folder)
    print(f"\n================ {folder} ================")
    for f in sorted(os.listdir(p)):
        show(os.path.join(p, f))
