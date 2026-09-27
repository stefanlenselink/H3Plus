"""Minimal PE section/import dumper - no external deps."""
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

import sys, struct, math, collections, os

def ent(d):
    if not d: return 0.0
    c = collections.Counter(d); n = len(d)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def main(path):
    d = open(path,'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    assert d[pe:pe+4] == b'PE\0\0', 'not PE'
    machine, nsec, tds, _, _, optsz, chars = struct.unpack_from('<HHIIIHH', d, pe+4)
    opt = pe + 24
    magic = struct.unpack_from('<H', d, opt)[0]
    pe32p = magic == 0x20b
    print(f"# {os.path.basename(path)}  size={len(d)}")
    print(f"  machine={machine:#06x} ({'x64' if machine==0x8664 else 'x86' if machine==0x14c else '?'})  "
          f"{'PE32+' if pe32p else 'PE32'}  sections={nsec}  timestamp={tds}")
    ep = struct.unpack_from('<I', d, opt+16)[0]
    print(f"  entrypoint RVA={ep:#x}  subsystem={struct.unpack_from('<H', d, opt+(0x44 if pe32p else 0x44))[0]}")
    # data directories
    ddoff = opt + (0x70 if pe32p else 0x60)
    nrva = struct.unpack_from('<I', d, opt + (0x6c if pe32p else 0x5c))[0]
    names = ['Export','Import','Resource','Exception','Security','Reloc','Debug','Arch',
             'GlobalPtr','TLS','LoadConfig','BoundImport','IAT','DelayImport','CLR','Reserved']
    print("  data directories:")
    for i in range(min(nrva, 16)):
        rva, sz = struct.unpack_from('<II', d, ddoff + i*8)
        if rva: print(f"    {names[i]:<12} rva={rva:#010x} size={sz:#x}")
    sec = pe + 24 + optsz
    print("  sections:")
    secs = []
    for i in range(nsec):
        off = sec + i*40
        nm = d[off:off+8].rstrip(b'\0').decode('latin1')
        vsz, vaddr, rsz, raddr = struct.unpack_from('<IIII', d, off+8)
        ch = struct.unpack_from('<I', d, off+36)[0]
        e = ent(d[raddr:raddr+min(rsz, 1<<20)])
        secs.append((nm, vaddr, vsz, raddr, rsz, ch, e))
        print(f"    {nm:<10} va={vaddr:#010x} vsz={vsz:#010x} raw={raddr:#010x} rsz={rsz:#010x} "
              f"flags={ch:#010x} entropy={e:.3f}")
    return secs

for p in sys.argv[1:]:
    main(p); print()
