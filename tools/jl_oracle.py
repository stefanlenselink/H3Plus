#!/usr/bin/env python3
"""SHA-pinned JieLi toolchain oracle for the H3 Plus firmware project.

Thin wrapper over the upstream `pi32v2isa.oracle` module
(https://github.com/jvitkauskas/pi32v2-isa, CC0/MIT-0): it pins the two known
JieLi Linux toolchain releases by SHA-256, downloads/verifies/unpacks them on
demand, and uses the vendor `clang` + `objdump` strictly as a BLACK BOX to
answer three questions we need before every flash:

  status   is a pinned toolchain present, and where?
  fetch    download + SHA-256-verify + unpack a pinned release (user action)
  decode   what does JieLi's objdump make of these bytes?  (each probe is
           padded with two nops so an over-long decode cannot swallow it)
  encode   what bytes does JieLi's assembler make of these asm lines?
  site     MANDATORY SECOND OPINION (copilot-instructions.md): run the bytes
           of a planned patch/cave site, in the context of the image around
           it, through JieLi's objdump and verify (1) the decode matches the
           intended instructions, (2) the decode length equals the patch
           length, (3) the next instruction starts exactly at VA+len
           (re-entry alignment).

Nothing of JieLi's is committed: the toolchain lives under the upstream
repo's gitignored `oracle/` dir (or $PI32V2_TOOLCHAIN) and is referenced
here only by release name + SHA-256, per the project's clean-room rules.

Usage:
    python3 tools/jl_oracle.py status
    python3 tools/jl_oracle.py fetch [--release=20260730.1]
    python3 tools/jl_oracle.py decode 40238000 00238000
    python3 tools/jl_oracle.py encode "r0 = 3" "rts"
    python3 tools/jl_oracle.py site 0x01E5B22A:40238000 --image=work/app_dec.bin

Requires Python >= 3.11 (upstream reads its ISA table with tomllib).
"""
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Stefan Lenselink — TIDRADIO H3 Plus firmware RE

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_UPSTREAM = os.path.normpath(os.path.join(HERE, "..", "..", "pi32v2-isa"))
DEFAULT_IMAGE = os.path.normpath(os.path.join(HERE, "..", "work", "app_dec.bin"))
LOAD_BASE = 0x01E00000


def load_oracle(upstream_dir):
    """Import upstream pi32v2isa.oracle from the cloned repo (never vendored)."""
    if not os.path.isdir(upstream_dir):
        sys.exit("upstream repo not found at %s (clone github.com/jvitkauskas/"
                 "pi32v2-isa or pass --upstream)" % upstream_dir)
    sys.path.insert(0, upstream_dir)
    try:
        from pi32v2isa import oracle as J
    except ImportError as e:
        sys.exit("cannot import pi32v2isa.oracle from %s: %s\n"
                 "(needs Python >= 3.11 for tomllib)" % (upstream_dir, e))
    return J


def parse_val(s):
    return int(s, 0)


def open_oracle(J, args):
    try:
        return J.Oracle(release=args.release)
    except J.OracleError as e:
        sys.exit("%s\n(or point --upstream/env PI32V2_TOOLCHAIN at an unpacked "
                 "release)" % e)


def cmd_status(J, args):
    print("pinned releases (SHA-256 of the vendor tarballs):")
    for rel in sorted(J.RELEASES):
        mark = "  <- default" if rel == J.DEFAULT_RELEASE else ""
        print("  %-12s %s%s" % (rel, J.RELEASES[rel], mark))
    env = os.environ.get("PI32V2_TOOLCHAIN")
    if env:
        present = os.path.isdir(env)
        print("environment PI32V2_TOOLCHAIN: %s (%s)" %
              (env, "present" if present else "MISSING"))
    fetched = [rel for rel in sorted(J.RELEASES)
               if os.path.isdir(os.path.join(J.ORACLE_DIR,
                                             "jieli-linux-toolchains-" + rel))]
    if fetched:
        print("fetched under oracle/: %s" %
              ", ".join(os.path.join(J.ORACLE_DIR, "jieli-linux-toolchains-" + r)
                        for r in fetched))
    try:
        o = J.Oracle(release=args.release)
        print("usable toolchain: release %s at %s" % (args.release, o.path))
        print("  clang:   %s" % o.clang)
        print("  objdump: %s" % o.objdump)
    except J.OracleError as e:
        print("usable toolchain: NONE (%s)" % e)
        print("fetch one with:  python3 tools/jl_oracle.py fetch"
              " [--release=%s]" % J.DEFAULT_RELEASE)


def cmd_fetch(J, args):
    print("fetching %s (expected SHA-256 %s)..." %
          (args.release, J.RELEASES[args.release]))
    path = J.fetch(args.release)
    print("OK: unpacked and SHA-256-verified at %s" % path)


def cmd_decode(J, args):
    if not args.probes:
        sys.exit("give one or more hex byte strings, e.g. 40238000")
    o = open_oracle(J, args)
    probes = []
    for h in args.probes:
        h = h.replace(" ", "")
        if len(h) % 2 or any(c not in "0123456789abcdefABCDEF" for c in h):
            sys.exit("bad hex probe: %r" % h)
        probes.append(bytes.fromhex(h))
    results = o.decode(probes, features=args.feature)
    for h, res in zip(args.probes, results):
        if res is None:
            print("%-20s  <no decode>" % h)
        else:
            ins, text = res
            print("%-20s  %d bytes: %s" % (h, len(ins), text))


def cmd_encode(J, args):
    if not args.lines:
        sys.exit("give one or more asm lines")
    o = open_oracle(J, args)
    results = o.encode(args.lines, features=args.feature)
    bad = 0
    for line, res in zip(args.lines, results):
        if isinstance(res, str):
            print("%-30s  ERROR: %s" % (line, res))
            bad += 1
        else:
            print("%-30s  %s" % (line, res.hex(" ")))
    if bad:
        sys.exit(1)


def cmd_site(J, args):
    """JieLi-objdump second opinion on a patch/cave site in image context."""
    try:
        va_s, hexbytes = args.site.split(":", 1)
    except ValueError:
        sys.exit("site must be VA:HEXBYTES, e.g. 0x01E5B22A:40238000")
    va = parse_val(va_s)
    patch = bytes.fromhex(hexbytes.replace(" ", ""))
    if not patch:
        sys.exit("empty patch bytes")
    if not os.path.isfile(args.image):
        sys.exit("image not found: %s (decrypt with tools/jl_sfcenc.py)" % args.image)
    data = open(args.image, "rb").read()
    off = va - args.base
    if off < 0 or off + len(patch) > len(data):
        sys.exit("VA 0x%08X outside image" % va)

    # Context window: 8 bytes before, 8 after (clamped), so objdump shows
    # the neighbours and we can check re-entry alignment.
    pre, post = 8, 8
    start = max(0, off - pre)
    end = min(len(data), off + len(patch) + post)
    ctx = bytearray(data[start:end])
    ctx[off - start: off - start + len(patch)] = patch   # overlay the patch
    o = open_oracle(J, args)
    listing = o.listing(bytes(ctx), features=args.feature)

    print("image   : %s  (VA base 0x%08X)" % (args.image, args.base))
    print("site    : 0x%08X, patch %d bytes %s" %
          (va, len(patch), patch.hex(" ")))
    print("JieLi objdump reading (context 0x%08X-0x%08X):" %
          (args.base + start, args.base + end))
    ok_len = False
    for addr, ins_bytes, text in listing:
        mark = ""
        if args.base + start <= addr < va:
            mark = "  (before)"
        elif addr == va:
            mark = "  <-- PATCH START"
            ok_len = len(ins_bytes) == len(patch)
        elif va < addr < va + len(patch):
            mark = "  !! patch overrun: decode continues INSIDE the patch"
        elif addr == va + len(patch):
            mark = "  <-- re-entry aligned"
        print("  %08X  %-14s %s%s" % (addr, ins_bytes.hex(" "), text, mark))
    print()
    if not ok_len:
        print("verdict: FAIL - the instruction at the site is not exactly %d "
              "bytes long" % len(patch))
        sys.exit(1)
    reentry = any(addr == va + len(patch) for addr, _, _ in listing)
    if not reentry:
        print("verdict: FAIL - no instruction starts at 0x%08X (re-entry "
              "misaligned)" % (va + len(patch)))
        sys.exit(1)
    print("verdict: PASS - patch decodes as %d bytes and re-entry at "
          "0x%08X is aligned" % (len(patch), va + len(patch)))
    print("(decode text above must still be read by a human to confirm "
          "INTENT - the tool checks length/alignment only)")


def main():
    ap = argparse.ArgumentParser(
        description="SHA-pinned JieLi toolchain oracle (upstream pi32v2-isa)")
    ap.add_argument("--upstream", default=DEFAULT_UPSTREAM,
                    help="path to the cloned pi32v2-isa repo "
                         "(default: ../pi32v2-isa)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="pinned releases + toolchain presence")
    p.add_argument("--release", default=None)

    p = sub.add_parser("fetch", help="download + SHA-256-verify a pinned release")
    p.add_argument("--release", default=None)

    p = sub.add_parser("decode", help="JieLi objdump reading of hex probes")
    p.add_argument("probes", nargs="*")
    p.add_argument("--release", default=None)
    p.add_argument("--feature", action="append", default=[],
                   help="toolchain feature, e.g. fprev1/instrev3 (repeatable)")

    p = sub.add_parser("encode", help="JieLi assembler bytes for asm lines")
    p.add_argument("lines", nargs="*")
    p.add_argument("--release", default=None)
    p.add_argument("--feature", action="append", default=[])

    p = sub.add_parser("site", help="second opinion on a patch site in image")
    p.add_argument("site", help="VA:HEXBYTES e.g. 0x01E5B22A:40238000")
    p.add_argument("--image", default=DEFAULT_IMAGE)
    p.add_argument("--base", type=parse_val, default=LOAD_BASE)
    p.add_argument("--release", default=None)
    p.add_argument("--feature", action="append", default=[])

    args = ap.parse_args()
    J = load_oracle(args.upstream)
    if getattr(args, "release", None) is None:
        args.release = J.DEFAULT_RELEASE
    {"status": cmd_status, "fetch": cmd_fetch, "decode": cmd_decode,
     "encode": cmd_encode, "site": cmd_site}[args.cmd](J, args)


if __name__ == "__main__":
    main()
