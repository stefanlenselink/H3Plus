#!/usr/bin/env python3
"""jl_jlfs.py — walk + extract the JLFS resource chain in the H3 Plus app image,
parse the JCRT TLV container inside config.dat, and list the in-app tone table.

Usage (platform-independent, stdlib-only):

    python tools/jl_jlfs.py <app_dec.bin> [outdir] [--list] [--tones]

Input is the DECRYPTED app plaintext (work/app_dec.bin: VA 0x01E00000 == file
offset 0 == flash 0x5000; findings/24 §24.6). The raw full-chip dump is
scrambled — run tools/jl_sfcenc.py first.

JLFS entry header (32 B, little-endian) — the 16-byte-name variant our image
uses (the community fwunpack_newfw.py 32-byte-name layout does NOT apply):

    +0x00 u32  data_crc
    +0x04 u32  data_off   (32 — data follows header+name)
    +0x08 u32  block_size (includes the 32 B header; blocks are contiguous)
    +0x0C u8   flags      (0x82 on our resources)
    +0x0D u8   reserved
    +0x0E u16  index
    +0x10 char name[16]   (NUL-padded ASCII)

data = file[hdr+data_off : hdr+block_size]; the chain walks p += block_size
while the next header validates. On the H3+ the chain is cfg_tool.bin,
eq_cfg_hw.bin, config.dat, md5.bin (findings/40).

config.dat is a JCRT TLV container (findings/40 §40.3):

    +0x00 char[4] magic 'JCRT'; +0x04 u32 hash; +0x08 u32 total_size;
    +0x0C u32 count; 32 B header block, then count x 32 B entries:
    +0x00 u16 idx; +0x02 u16 type (1=raw bytes, 2=NUL-terminated string);
    +0x04 u32 val_off; +0x08 u32 val_len; +0x0C u16 crc16; +0x0E u16 0xFFFF;
    +0x10 char name[16] — values at file[val_off].

The tone table (§40.7) is a list of `storage/res_nor/C/tone/<name>.*` strings
inside the app code region; --tones lists the names. The audio itself is NOT
in the 1 MiB dump (open question, §40.7).
"""
# SPDX-License-Identifier: MIT
# Copyright 2026 Stefan Lenselink.

import hashlib
import os
import re
import struct
import sys

HDR = 32


def valid_header(buf, p):
    """Return (name, data_off, block_size, flags, index) if p is a plausible
    JLFS entry header, else None."""
    if p + HDR > len(buf):
        return None
    _crc, data_off, block_size = struct.unpack_from("<III", buf, p)
    flags, _resvd, index = struct.unpack_from("<BBH", buf, p + 12)
    raw = buf[p + 16 : p + 32]
    end = raw.find(b"\x00")
    if end == 0:
        return None
    name = raw[: end if end >= 0 else 16]
    if not name or not all(0x20 <= c < 0x7F for c in name):
        return None
    if not (16 <= data_off <= 0x100) or not (data_off < block_size <= 0x100000):
        return None
    if p + block_size > len(buf):
        return None
    if index > 0x1000:
        return None
    return name.decode("ascii"), data_off, block_size, flags, index


def walk_chain(buf, start):
    """Walk contiguous JLFS entries from `start`; return list of entries."""
    entries, p = [], start
    while True:
        h = valid_header(buf, p)
        if h is None:
            break
        name, data_off, block_size, flags, index = h
        entries.append(
            {
                "off": p,
                "name": name,
                "data_off": data_off,
                "size": block_size - data_off,
                "block": block_size,
                "flags": flags,
                "index": index,
                "crc": struct.unpack_from("<I", buf, p)[0],
            }
        )
        p += block_size
    return entries


def find_chains(buf):
    """Find every maximal contiguous chain of valid entries; longest first."""
    heads = {}  # offset -> header tuple, for all valid entry headers
    for p in range(len(buf) - HDR):
        h = valid_header(buf, p)
        if h is not None:
            heads[p] = h
    covered = {p + h[2] for p, h in heads.items()}  # offsets reached by a block walk
    chains = []
    for s in sorted(heads):
        if s in covered:
            continue  # not a chain head — some entry's block ends here
        chains.append(walk_chain(buf, s))
    return sorted(chains, key=len, reverse=True)


def parse_jcrt(buf, base):
    """Parse a JCRT TLV container at buf[base:]; return list of (name, type,
    value) with value bytes."""
    magic = buf[base : base + 4]
    if magic != b"JCRT":
        return None
    _hash, total = struct.unpack_from("<II", buf, base + 4)
    (count,) = struct.unpack_from("<H", buf, base + 12)
    out = []
    for i in range(count):
        e = base + 32 + 32 * i
        idx, typ, voff, vlen, crc, _ff = struct.unpack_from("<HHIIHH", buf, e)
        raw = buf[e + 16 : e + 32].rstrip(b"\x00\xff")
        end = raw.find(b"\x00")
        name = raw[: end if end >= 0 else 16].decode("latin-1")
        value = buf[base + voff : base + voff + vlen]
        out.append((name, typ, value, idx, crc))
    return out


def show_jcrt(buf, base, name):
    recs = parse_jcrt(buf, base)
    if recs is None:
        print(f"  {name}: no JCRT magic — raw file")
        return
    print(f"  {name}: JCRT container, {len(recs)} records")
    for rname, typ, value, idx, crc in recs:
        if typ == 2:
            txt = value.rstrip(b"\x00").decode("latin-1")
            print(f"    [{idx}] {rname:<14} str  = {txt!r}")
        else:
            print(f"    [{idx}] {rname:<14} bytes= {value.hex(' ')}  (crc16 {crc:#06x})")


def find_tones(buf):
    """Tone resource names from the `storage/res_nor/C/tone/<name>.*` table."""
    return sorted(
        {m.decode("ascii") for m in re.findall(rb"tone/([A-Za-z0-9_]+)\.\*", buf)}
    )


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    outdir = args[1] if len(args) > 1 else None
    with open(path, "rb") as f:
        buf = f.read()
    print(f"{path}: {len(buf)} bytes ({len(buf):#x})")

    chains = find_chains(buf)
    if not chains:
        print("no JLFS chain found")
        return 1
    for ch in chains[:1]:
        print(f"JLFS chain: {len(ch)} entries, {ch[0]['off']:#x} .. "
              f"{ch[-1]['off'] + ch[-1]['block']:#x}")
        for e in ch:
            print(f"  {e['name']:<16} hdr {e['off']:#08x} data {e['off'] + e['data_off']:#08x} "
                  f"{e['size']:>6} B  flags {e['flags']:#04x} idx {e['index']} crc {e['crc']:#010x}")
            if outdir:
                os.makedirs(outdir, exist_ok=True)
                dst = os.path.join(outdir, e["name"])
                with open(dst, "wb") as g:
                    g.write(buf[e["off"] + e["data_off"] : e["off"] + e["block"]])
            if e["name"] == "config.dat":
                show_jcrt(buf, e["off"] + e["data_off"], "config.dat")
        md5 = hashlib.md5(
            b"".join(buf[e["off"] + e["data_off"] : e["off"] + e["block"]] for e in ch[:-1])
        ).hexdigest()
        print(f"  md5 of preceding entry data = {md5}")

    if "--tones" in flags:
        tones = find_tones(buf)
        print(f"tone table: {len(tones)} names")
        print("  " + " ".join(tones))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
