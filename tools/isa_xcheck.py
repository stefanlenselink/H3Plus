#!/usr/bin/env python3
"""
Cross-check tools/isa/pi32v2.md (our hand-built spec, parsed by pi32dis.py)
against the open, oracle-validated pi32v2-isa reference table
(https://github.com/jvitkauskas/pi32v2-isa).

Both decoders are run over the same decrypted app image at every 2-byte
aligned offset and compared on:

  * instruction LENGTH (the structural invariant: both must agree on how many
    bytes each first word consumes),
  * decode STATUS (known to ours only / theirs only / both / neither),
  * optionally TEXT for sampled addresses (mnemonic spellings differ; the
    tool prints pairs side by side for eyeball verification).

The upstream repo is used as a Python package (no subprocesses): pass
--upstream DIR (default: ../pi32v2-isa relative to this tool). Upstream's
table is confirmed against JieLi's closed clang+objdump in BOTH directions
(see pi32v2-isa docs/ORACLE.md), so it is the stronger authority; mismatches
here are candidates for fixing OUR spec, not theirs.

Usage:
    python tools/isa_xcheck.py work/app_dec.bin
    python tools/isa_xcheck.py work/app_dec.bin --upstream ../pi32v2-isa --mcpu r3
    python tools/isa_xcheck.py work/app_dec.bin --sample 16 --show 20
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

import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pi32dis  # noqa: E402


def load_upstream(upstream_dir, mcpu):
    if not os.path.isdir(upstream_dir):
        sys.exit("upstream repo not found at %s (clone github.com/jvitkauskas/pi32v2-isa "
                 "or pass --upstream)" % upstream_dir)
    sys.path.insert(0, upstream_dir)
    try:
        from pi32v2isa import table as jtable
        from pi32v2isa import objdump as jobjdump
    except ImportError as e:
        sys.exit("cannot import pi32v2isa from %s: %s" % (upstream_dir, e))
    tab = jtable.load(os.path.join(upstream_dir, "isa", "pi32v2.toml"))
    return jobjdump.decoder_for(tab, mcpu=mcpu)


def main():
    ap = argparse.ArgumentParser(description="cross-check our ISA spec vs pi32v2-isa upstream")
    ap.add_argument("image", help="decrypted app image (e.g. work/app_dec.bin)")
    ap.add_argument("--upstream", default=os.path.join(HERE, "..", "..", "pi32v2-isa"),
                    help="path to the pi32v2-isa repo (default: ../pi32v2-isa)")
    ap.add_argument("--mcpu", default="r3", help="upstream -mcpu model (default r3, our BR23 model)")
    ap.add_argument("--base", type=lambda s: int(s, 0), default=pi32dis.LOAD_BASE,
                    help="virtual address of image offset 0 (default 0x01E00000)")
    ap.add_argument("--sample", type=int, default=1,
                    help="probe every Nth 2-byte-aligned offset (default 1 = every word)")
    ap.add_argument("--show", type=int, default=12,
                    help="print up to N mismatch examples / text-diff pairs")
    args = ap.parse_args()

    data = open(args.image, "rb").read()
    ours = pi32dis.Disassembler(data, base=args.base)
    theirs = load_upstream(os.path.abspath(args.upstream), args.mcpu)

    n = len(data) - 1
    stats = collections.Counter()
    len_mismatch = collections.Counter()   # (our_len, their_len) -> count
    len_examples = {}                      # (our_len, their_len) -> [addrs]
    status_examples = {"ours_only": [], "theirs_only": [], "neither": []}
    gap_ids = collections.Counter()        # upstream insn.id our spec misses -> count
    text_pairs = []

    for off in range(0, n, max(1, args.sample) * 2):
        addr = args.base + off
        otext, _raw, olen, _tgt = ours.decode(addr)
        j = theirs.decode(data, off)
        word = data[off] | (data[off + 1] << 8)

        if otext is not None and j is not None:
            stats["both"] += 1
            if olen != j[2]:
                key = (olen, j[2])
                len_mismatch[key] += 1
                len_examples.setdefault(key, []).append(addr)
            elif len(text_pairs) < args.show and off % 0x4000 == 0:
                text_pairs.append((addr, word, otext, j[3]))
        elif otext is not None:
            stats["ours_only"] += 1
            if len(status_examples["ours_only"]) < args.show:
                status_examples["ours_only"].append((addr, word, olen, otext))
        elif j is not None:
            stats["theirs_only"] += 1
            gap_ids[j[0].id] += 1
            if len(status_examples["theirs_only"]) < args.show:
                status_examples["theirs_only"].append((addr, word, j[2], j[3]))
        else:
            stats["neither"] += 1
            if len(status_examples["neither"]) < args.show:
                status_examples["neither"].append((addr, word, None, None))

    total = sum(stats.values())
    print("image      : %s (%d bytes, base 0x%08X)" % (args.image, len(data), args.base))
    print("upstream   : %s  (-mcpu=%s, %d forms)" % (os.path.abspath(args.upstream), args.mcpu,
                                                     len(theirs.tab.insns)))
    print("probed     : %d aligned offsets" % total)
    print("  both decode      : %d (%.2f%%)" % (stats["both"], 100.0 * stats["both"] / total))
    print("  ours only        : %d" % stats["ours_only"])
    print("  theirs only      : %d  <- our spec gaps (upstream confirms these vs JieLi tools)"
          % stats["theirs_only"])
    print("  neither          : %d  (data / undefined words)" % stats["neither"])
    print("length mismatches where both decode: %d" % sum(len_mismatch.values()))
    for key, cnt in len_mismatch.most_common(10):
        ex = ", ".join("0x%08X" % a for a in len_examples[key][:3])
        print("  ours=%dB theirs=%dB : %6d  e.g. %s" % (key[0], key[1], cnt, ex))
    for cat in ("theirs_only", "ours_only"):
        if status_examples[cat]:
            print("\n%s examples:" % cat)
            for addr, word, ln, text in status_examples[cat]:
                print("  %08X  %04X  len=%s  %s" % (addr, word, ln, text if text else ""))
    if gap_ids:
        print("\nupstream forms our spec misses (insn.id -> occurrences in this image):")
        for iid, cnt in gap_ids.most_common(40):
            print("  %-40s %6d" % (iid, cnt))
    if text_pairs:
        print("\nsampled text pairs (both decode, same length; spellings differ by design):")
        for addr, word, o, t in text_pairs:
            print("  %08X  %04X\n      ours  : %s\n      theirs: %s" % (addr, word, o, t))
    print("\nverdict: %s" % ("IDENTICAL structure (lengths agree everywhere both decode)"
                             if not len_mismatch else
                             "STRUCTURAL MISMATCHES - see table above"))


if __name__ == "__main__":
    main()
