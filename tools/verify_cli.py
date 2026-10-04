#!/usr/bin/env python3
"""CLI matrix for patch_h3plus_firmware_bluetooth.py (direct-rewrite model, 9A.50).

Platform-independent port of the old tools/verify_cli.ps1 — pure stdlib, runs
identically on Windows, Linux and macOS. Run from the repo root:

    python tools/verify_cli.py

Builds are written to work/cli/ and removed when everything passes.
Covers: every --PTT2/--OD-PTT pair accepted, same-action pairs refused,
--PTT restrictions, alias spellings, option-case insensitivity, --show.
Exits with the number of failed cases (0 = all green).
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

import hashlib
import os
import re
import shutil
import subprocess
import sys

TOOL = "tools/patch_h3plus_firmware_bluetooth.py"
SRC = "Dumps/dump_internal.bin"
OUTDIR = "work/cli"

# name -> (args, expect_exit)
CASES = [
    # the unique combinations, in either option order
    ("c1_ptt_ptt2",     ["--PTT2=PTT", "--OD-PTT=PTT2"], 0),
    ("c2_ptt_odptt",    ["--PTT2=PTT", "--OD-PTT=OD-PTT"], 0),
    ("c3_ptt_btptt",    ["--PTT2=PTT", "--OD-PTT=BT-PTT"], 0),
    ("c3b_ptt_btptt2",  ["--PTT2=PTT", "--OD-PTT=BT-PTT2"], 0),
    ("c4_ptt2_odptt",   ["--PTT2=PTT2", "--OD-PTT=OD-PTT"], 0),
    ("c5_ptt2_btptt",   ["--PTT2=PTT2", "--OD-PTT=BT-PTT"], 0),
    ("c5b_ptt2_btptt2", ["--PTT2=PTT2", "--OD-PTT=BT-PTT2"], 0),
    ("c6_odptt_btptt",  ["--PTT2=OD-PTT", "--OD-PTT=BT-PTT"], 0),
    ("c6_rev",          ["--PTT2=BT-PTT", "--OD-PTT=OD-PTT"], 0),
    ("c7_odptt_btptt2", ["--PTT2=OD-PTT", "--OD-PTT=BT-PTT2"], 0),
    ("c7_rev",          ["--PTT2=BT-PTT2", "--OD-PTT=OD-PTT"], 0),
    ("c8_btptt_btptt2", ["--PTT2=BT-PTT", "--OD-PTT=BT-PTT2"], 0),
    ("c8_rev",          ["--PTT2=BT-PTT2", "--OD-PTT=BT-PTT"], 0),
    # the user's "rewiring" example builds directly - no swap needed
    ("example",         ["--PTT2=OD-PTT", "--OD-PTT=BT-PTT"], 0),
    # alias spellings + lowercase options
    ("alias_od",        ["--ptt2=od_ptt", "--OD-PTT=PTT2"], 0),
    ("alias_bt",        ["--PTT2=BTPTT", "--od-ptt=PTT"], 0),
    ("alias_bt2",       ["--PTT2=BTPTT2", "--OD-PTT=PTT"], 0),
    ("space_bt",        ["--PTT2=BT PTT", "--OD-PTT=PTT2"], 0),
    # ("BT PTT2"/PTT pair — the original .ps1 had --OD-PTT=PTT2 here, a typo
    #  that made the BT-PTT2/PTT identity comparison below always fail)
    ("space_bt2",       ["--PTT2=BT PTT2", "--OD-PTT=PTT"], 0),
    # main PTT key: only PTT / BT-PTT exist
    ("ptt_stock",       ["--PTT=PTT"], 0),
    ("ptt_bt",          ["--PTT=BT-PTT"], 0),
    ("ref_ptt2",        ["--PTT=PTT2"], 1),
    ("ref_od",          ["--PTT=OD-PTT"], 1),
    ("ref_bt2",         ["--PTT=BT-PTT2"], 1),
    # same-action pairs are the only refused PF pairs
    ("ref_pp",          ["--PTT2=PTT", "--OD-PTT=PTT"], 1),
    ("ref_22",          ["--PTT2=PTT2", "--OD-PTT=PTT2"], 1),
    ("ref_bb",          ["--PTT2=BT-PTT", "--OD-PTT=BT-PTT"], 1),
    ("ref_b2b2",        ["--PTT2=BT-PTT2", "--OD-PTT=BT-PTT2"], 1),
    ("ref_oo",          ["--PTT2=OD-PTT", "--OD-PTT=OD-PTT"], 1),
    ("ref_badspec",     ["--PTT2=NOPE"], 1),
    # bluetooth-mode aliases
    ("bt_alias",        ["--bt", "2"], 0),
    ("bt_alias2",       ["--bluetooth-mode=5"], 0),
    # multipoint Option A: kick-NOP, alone and combined with conn-num
    ("nokick",          ["--no-kick"], 0),
    ("nokick_cn",       ["--no-kick", "--conn-num=2"], 0),
    ("nk_alias",        ["--NO-KICK"], 0),
]

RE_BYTES = re.compile(r"plaintext bytes changed: (\d+)")
RE_MSG = re.compile(r"not possible|invalid|must be|Traceback", re.IGNORECASE)


def run(args, dst=None):
    """Run the patch tool; return (exitcode, combined output)."""
    cmd = [sys.executable, TOOL] + list(args)
    if dst is not None:
        cmd += [SRC, dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    if not os.path.isfile(SRC):
        print("ERROR: source dump not found: %s (see ARTIFACTS.md)" % SRC)
        return 2
    os.makedirs(OUTDIR, exist_ok=True)

    fail = 0
    for name, args, want in CASES:
        dst = os.path.join(OUTDIR, name + ".bin")
        exitcode, out = run(args, dst)
        bc = ",".join(RE_BYTES.findall(out))
        ok = exitcode == want
        if not ok:
            fail += 1
        m = RE_MSG.search(out)
        msg = m.group(0) if m else ""
        line = "%-15s exit=%d (want %d) bytes=%s %s" % (
            name, exitcode, want, bc, "OK" if ok else "FAIL")
        if msg:
            line += " | %s" % msg
        print(line)

    def identical(name_a, name_b, label_a, label_b):
        """Compare two generated images; count a failure when they differ."""
        nonlocal fail
        ha, hb = sha256(name_a), sha256(name_b)
        if ha != hb:
            print("%s DIFFERS from %s -> FAIL" % (label_a, label_b))
            fail += 1
        else:
            print("%s == %s IDENTICAL OK" % (label_a, label_b))

    # alias builds must equal the canonical spelling of the same pair.
    # alias_od is OD-PTT/PTT2 (the reverse of c1), so build that pair to compare.
    run(["--PTT2=OD-PTT", "--OD-PTT=PTT2"], os.path.join(OUTDIR, "c1_rev.bin"))
    identical(os.path.join(OUTDIR, "alias_od.bin"),
              os.path.join(OUTDIR, "c1_rev.bin"), "alias_od", "OD-PTT/PTT2")
    # space_bt is BT-PTT/PTT2 ("BT PTT" spelling); compare against the canonical one
    run(["--PTT2=BT-PTT", "--OD-PTT=PTT2"], os.path.join(OUTDIR, "btptt_ptt2.bin"))
    identical(os.path.join(OUTDIR, "space_bt.bin"),
              os.path.join(OUTDIR, "btptt_ptt2.bin"), "space_bt", "BT-PTT/PTT2")
    # alias_bt2 / space_bt2 are BT-PTT2/PTT; compare against the canonical one
    run(["--PTT2=BT-PTT2", "--OD-PTT=PTT"], os.path.join(OUTDIR, "btptt2_ptt.bin"))
    identical(os.path.join(OUTDIR, "alias_bt2.bin"),
              os.path.join(OUTDIR, "btptt2_ptt.bin"), "alias_bt2", "BT-PTT2/PTT")
    identical(os.path.join(OUTDIR, "space_bt2.bin"),
              os.path.join(OUTDIR, "btptt2_ptt.bin"), "space_bt2", "BT-PTT2/PTT")
    # example must equal c6 (same pair, same order)
    identical(os.path.join(OUTDIR, "example.bin"),
              os.path.join(OUTDIR, "c6_odptt_btptt.bin"), "example", "c6")
    # --bt 2 must equal an explicit mode-2 build
    run(["--bluetooth-mode", "2"], os.path.join(OUTDIR, "bt_alias_x.bin"))
    identical(os.path.join(OUTDIR, "bt_alias.bin"),
              os.path.join(OUTDIR, "bt_alias_x.bin"), "bt_alias", "bluetooth-mode 2")
    # --NO-KICK must equal the canonical --no-kick build
    identical(os.path.join(OUTDIR, "nk_alias.bin"),
              os.path.join(OUTDIR, "nokick.bin"), "--NO-KICK", "--no-kick")
    # --show must run clean on a kick-NOP'd image
    exitcode, out = run([os.path.join(OUTDIR, "nokick.bin"), "--show",
                         "--no-kick"])
    if exitcode == 0 and "UNKNOWN" not in out.upper():
        print("--show on nokick clean OK")
    else:
        print("--show on nokick -> FAIL")
        fail += 1
    # --show must run clean on a patched image
    exitcode, out = run([os.path.join(OUTDIR, "c6_odptt_btptt.bin"), "--show",
                         "--PTT2=OD-PTT", "--OD-PTT=BT-PTT"])
    if exitcode == 0 and "UNKNOWN" not in out.upper():
        print("--show on c6 clean OK")
    else:
        print("--show on c6 -> FAIL")
        fail += 1

    if fail == 0:
        shutil.rmtree(OUTDIR, ignore_errors=True)
    print("FAILURES: %d" % fail)
    return fail


if __name__ == "__main__":
    sys.exit(main())
