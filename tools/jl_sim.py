#!/usr/bin/env python3
"""
Pre-flash simulator for H3+ patch/cave logic on the decrypted app image.

Wraps the upstream pi32v2-isa CPU model (tools/llvm/sim.py in
https://github.com/jvitkauskas/pi32v2-isa), whose per-instruction models are
FITTED TO REAL AC791N HARDWARE runs (hw/fm1-* result sets, docs/ORACLE.md
methodology).  This runs the ACTUAL bytes of our patched firmware in software:

  * the decrypted app is flat-loaded at its load VA (0x01E00000),
  * --patch VA:HEXBYTES overlays patch/cave bytes exactly as they would be
    flashed, so a cave's branch decisions, register math and returns can be
    exercised BEFORE any hardware test,
  * --seed VA:HEXBYTES initialises RAM structures the code reads (conn-record
    pool 0x1A5B8 stride 0x1C, routing byte 0xB464, dispatcher base 0x1A520 ...),
  * --stop-va / the RETURN sentinel end the run; --trace prints every step
    with the upstream objdump text; --expect / --expect-mem assert outcomes
    (nonzero exit on failure, so it composes in scripts).

CAVEATS (documented, not hidden):
  * instruction models were fitted on the AC791N, NOT our BR23/AC635N die
    (findings ch. 34 SS 34.10): chip-divergent forms (popcnt=nop, resets,
    FPU revision) are unmeasured on BR23;
  * SFR/special-register reads return 0 (no peripheral model);
  * interrupts never fire; the stack is zero-filled RAM.
A sim PASS is evidence the LOGIC is right; a flash is still required for
chip behaviour and BT side effects.  A sim FAIL at a form with no model is a
coverage report, not a bug in the patch.

Usage:
    python tools/jl_sim.py --start=0x01E5B22A --patch=0x01E5B22A:40238000 \
        --expect=r0=3 --trace
    python tools/jl_sim.py --call=0x01E173D0 --seed=0x0001A5B8:0000... \
        --max-steps=50000
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
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOAD_BASE = 0x01E00000


def load_sim(upstream_dir):
    """Put the upstream repo's sim/check/semantics packages on sys.path."""
    for p in (upstream_dir, os.path.join(upstream_dir, "tools", "hwtest"),
              os.path.join(upstream_dir, "tools", "llvm")):
        if not os.path.isdir(p):
            sys.exit("upstream layout not found (%s missing) - clone "
                     "github.com/jvitkauskas/pi32v2-isa or pass --upstream" % p)
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        import sim
        from pi32v2isa import objdump as jobjdump
    except ImportError as e:
        sys.exit("cannot import upstream sim from %s: %s" % (upstream_dir, e))
    return sim, jobjdump


def parse_val(s):
    return int(s, 0)


def parse_seed(s):
    """'VA:HEXBYTES' -> (addr, bytes)."""
    try:
        va, hx = s.split(":", 1)
        return parse_val(va), bytes.fromhex(hx)
    except ValueError:
        sys.exit("bad spec %r (want VA:HEXBYTES)" % s)


def main():
    ap = argparse.ArgumentParser(description="pre-flash pi32v2 simulator "
                                 "(upstream hardware-fitted models)")
    ap.add_argument("--image", default=os.path.join(HERE, "..", "work", "app_dec.bin"),
                    help="decrypted app image (default work/app_dec.bin)")
    ap.add_argument("--base", type=parse_val, default=LOAD_BASE,
                    help="VA the image loads at (default 0x01E00000)")
    ap.add_argument("--upstream", default=os.path.join(HERE, "..", "..", "pi32v2-isa"),
                    help="path to the pi32v2-isa repo (default ../pi32v2-isa)")
    ap.add_argument("--start", type=parse_val, help="entry VA (pc)")
    ap.add_argument("--call", type=parse_val,
                    help="call VA as a function: rets=sentinel, args from --arg")
    ap.add_argument("--arg", type=parse_val, action="append", default=[],
                    help="argument in r0.. (repeatable, with --call)")
    ap.add_argument("--patch", action="append", default=[], metavar="VA:HEX",
                    help="overlay bytes at VA (repeatable) - the patched image")
    ap.add_argument("--seed", action="append", default=[], metavar="VA:HEX",
                    help="initialise RAM at VA (repeatable)")
    ap.add_argument("--regs", action="append", default=[], metavar="rN=VAL",
                    help="set a register before the run (repeatable)")
    ap.add_argument("--sp", type=parse_val, default=None)
    ap.add_argument("--rets", type=parse_val, default=None)
    ap.add_argument("--flags", type=parse_val, default=None)
    ap.add_argument("--stop-va", type=parse_val, action="append", default=[],
                    help="stop when pc reaches VA (repeatable)")
    ap.add_argument("--max-steps", type=int, default=200000)
    ap.add_argument("--trace", action="store_true", help="print every step")
    ap.add_argument("--expect", action="append", default=[], metavar="rN=VAL",
                    help="assert register at stop (repeatable)")
    ap.add_argument("--expect-mem", action="append", default=[], metavar="VA:HEX",
                    help="assert memory bytes at stop (repeatable)")
    args = ap.parse_args()

    sim, jobjdump = load_sim(os.path.abspath(args.upstream))

    # Workaround for an upstream artifact bug (2026-11-10): semantics/m2.py
    # opens a hardcoded dev-only path (/root/.t3/.../ids5-m.txt, not
    # committed) to register its generic ld./st./rmw. models. Replace
    # check.load_models with an equivalent that reconstructs that id list
    # from the table: every ld./st./rmw. form, except the two m2 models by
    # hand and any id another semantics module already models (the curated
    # upstream list excluded those; k2.py models e.g. bare ld.w).
    import builtins
    import importlib
    import io
    import pathlib
    from pi32v2isa import table as jtable
    import check as jcheck

    up = os.path.abspath(args.upstream)

    def jl_load_models():
        sem = pathlib.Path(jcheck.__file__).parent / "semantics"
        models = {}
        for p in sorted(sem.glob("*.py")):
            if p.name.startswith("_") or p.name == "m2.py":
                continue
            mod = importlib.import_module("semantics.%s" % p.stem)
            for k, fn in mod.MODELS.items():
                models.setdefault(k, fn)
        tab = jtable.load(os.path.join(up, "isa", "pi32v2.toml"))
        ids = list(dict.fromkeys(
            e.id for e in tab.insns
            if e.id.startswith(("ld.", "st.", "rmw."))
            and not e.id.startswith(("ld.w.npc", "st.w.modimm"))
            and e.id not in models))
        real_open = builtins.open

        def _open(f, *a, **k):
            if isinstance(f, str) and f.endswith("ids5-m.txt"):
                return io.StringIO(" ".join(ids))
            return real_open(f, *a, **k)

        builtins.open = _open
        try:
            m2 = importlib.import_module("semantics.m2")
        finally:
            builtins.open = real_open
        for k, fn in m2.MODELS.items():
            models.setdefault(k, fn)
        return models

    jcheck.load_models = jl_load_models
    cpu = sim.CPU()
    dec = jobjdump.decoder_for(cpu.tab, mcpu="r3")

    if not os.path.isfile(args.image):
        sys.exit("image not found: %s (decrypt with tools/jl_sfcenc.py)" % args.image)
    image = open(args.image, "rb").read()
    for va, hx in (parse_seed(s) for s in args.patch):
        if va < args.base or va + len(hx) > args.base + len(image):
            sys.exit("patch VA %#x outside image window" % va)
        image = image[:va - args.base] + hx + image[va - args.base + len(hx):]
    cpu.mem.write(args.base, image)
    for va, hx in (parse_seed(s) for s in args.seed):
        cpu.mem.write(va, hx)

    for spec in args.regs:
        name, _, val = spec.partition("=")
        n = int(name.lstrip("rR"))
        cpu.R[n] = parse_val(val) & sim.M
    if args.sp is not None:
        cpu.sp = args.sp
    if args.flags is not None:
        cpu.flags = args.flags & 0xF

    sentinel = sim.RETURN
    if args.call is not None:
        cpu.R[:len(args.arg)] = [a & sim.M for a in args.arg]
        cpu.rets = sentinel
        cpu.pc = args.call
    elif args.start is not None:
        cpu.rets = sentinel if args.rets is None else args.rets
        cpu.pc = args.start
    else:
        ap.error("need --start or --call")
    if args.rets is not None:
        cpu.rets = args.rets

    before = {k: bytes(v) for k, v in cpu.mem.pages.items()}
    stop, reason = None, "step limit"
    for _ in range(args.max_steps):
        if cpu.pc == sentinel:
            stop, reason = cpu.pc, "returned (rets sentinel)"
            break
        if cpu.pc in args.stop_va:
            stop, reason = cpu.pc, "stop-va hit"
            break
        if args.trace:
            got = dec.decode(cpu.mem.read(cpu.pc, 6), 0)
            txt = got[3] if got else "???"
            sys.stderr.write("%08X  %s\n" % (cpu.pc, txt))
        try:
            cpu.step()
        except RuntimeError as e:
            reason = "unsupported form: %s" % e
            break
    sys.stderr.flush()

    # Memory diff: pages changed or created during the run.
    writes = []
    for k, page in sorted(cpu.mem.pages.items()):
        init = before.get(k, bytes(4096))
        if bytes(page) != init:
            a = k << 12
            runs = []
            i = 0
            while i < 4096:
                if page[i] != init[i]:
                    j = i
                    while j < 4096 and page[j] != init[j]:
                        j += 1
                    runs.append((a + i, init[i:j], bytes(page[i:j])))
                    i = j
                else:
                    i += 1
            writes.extend(runs)

    print("stop reason : %s" % reason)
    print("pc          : %#010X  steps: %d" % (cpu.pc, cpu.steps))
    print("registers   : " + " ".join("r%d=%#010X" % (n, v) for n, v in enumerate(cpu.R)))
    print("flags=%#x  sp=%#010X  rets=%#010X" % (cpu.flags, cpu.sp, cpu.rets))
    if writes:
        print("memory writes (%d runs):" % len(writes))
        for addr, old, new in writes[:60]:
            print("  %#010X  %s -> %s" % (addr, old.hex(), new.hex()))
        if len(writes) > 60:
            print("  ... %d more" % (len(writes) - 60))
    else:
        print("memory writes: none")

    ok = True
    for spec in args.expect:
        name, _, val = spec.partition("=")
        n = int(name.lstrip("rR"))
        want = parse_val(val) & sim.M
        got = cpu.R[n]
        mark = "OK " if got == want else "FAIL"
        ok = ok and got == want
        print("expect r%-2d = %#010X  got %#010X  %s" % (n, want, got, mark))
    for spec in args.expect_mem:
        try:
            va, hx = spec.split(":", 1)
            va, want = parse_val(va), bytes.fromhex(hx)
        except ValueError:
            sys.exit("bad --expect-mem %r (want VA:HEX)" % spec)
        got = bytes(cpu.mem.read(va, len(want)))
        mark = "OK " if got == want else "FAIL"
        ok = ok and got == want
        print("expect mem %#010X = %s  got %s  %s" % (va, want.hex(), got.hex(), mark))
    if args.expect or args.expect_mem:
        print("verdict: %s" % ("PASS" if ok else "FAIL"))
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
