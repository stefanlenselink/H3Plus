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
    # multipoint experiment E4: role-keep accept, alone and in the full recipe
    ("rolekeep",        ["--force-role-keep"], 0),
    ("rolekeep_a2",     ["--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep"], 0),
    ("rk_alias",        ["--FORCE-ROLE-KEEP"], 0),
    # multipoint experiment E6: app 0x13 disconnect NOP, alone and full recipe
    ("disc13",          ["--no-disconnect-13"], 0),
    ("disc13_e6",       ["--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep", "--no-disconnect-13"], 0),
    ("d13_alias",       ["--NO-DISCONNECT-13"], 0),
    # multipoint experiment E7: app 0x16 pairing-kick NOP, alone and full recipe
    ("pairkick",        ["--no-pairing-kick"], 0),
    ("pairkick_e7",     ["--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep", "--no-disconnect-13",
                         "--no-pairing-kick"], 0),
    ("pk_alias",        ["--NO-PAIRING-KICK"], 0),
    # multipoint experiment E8: app 0x13 cleanup-kick NOPs, alone and full recipe
    ("cleanupkick",     ["--no-cleanup-kick"], 0),
    ("cleanupkick_e8",  ["--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep", "--no-disconnect-13",
                         "--no-pairing-kick", "--no-cleanup-kick"], 0),
    ("ck_alias",        ["--NO-CLEANUP-KICK"], 0),
    # multipoint experiment E9: app L2CAP-teardown NOPs, alone and full recipe
    ("l2capteardown",   ["--no-l2cap-teardown"], 0),
    ("l2capteardown_e9", ["--no-kick", "--conn-num=2", "--force-page-scan",
                          "--force-role-keep", "--no-disconnect-13",
                          "--no-pairing-kick", "--no-cleanup-kick",
                          "--no-l2cap-teardown"], 0),
    ("ltd_alias",       ["--NO-L2CAP-TEARDOWN"], 0),
    # multipoint experiment E10: app spp_channel_disconnect() no-op, alone and full recipe
    ("sppclose",        ["--no-spp-close"], 0),
    ("sppclose_e10",    ["--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep", "--no-disconnect-13",
                         "--no-pairing-kick", "--no-cleanup-kick",
                         "--no-l2cap-teardown", "--no-spp-close"], 0),
    ("sc_alias",        ["--NO-SPP-CLOSE"], 0),
    # multipoint experiment E11: app L2CAP-level kill, alone and full recipe
    ("l2capdisc",       ["--no-l2cap-disconnect"], 0),
    ("l2capdisc_e11",   ["--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep", "--no-disconnect-13",
                         "--no-pairing-kick", "--no-cleanup-kick",
                         "--no-l2cap-teardown", "--no-spp-close",
                         "--no-l2cap-disconnect"], 0),
    ("ld_alias",        ["--NO-L2CAP-DISCONNECT"], 0),
    # ch.30 F3: conditional close gate, alone and full M3 recipe
    ("gateclose",       ["--gate-close"], 0),
    ("gateclose_f3",    ["--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep", "--no-disconnect-13",
                         "--no-pairing-kick", "--no-cleanup-kick",
                         "--no-l2cap-teardown", "--gate-close"], 0),
    ("gc_alias",        ["--GATE-CLOSE"], 0),
    # gate trampolines share the entry bytes of the E10/E11 no-ops -> refused
    ("gc_conf_spp",     ["--gate-close", "--no-spp-close"], 1),
    ("gc_conf_l2cap",   ["--gate-close", "--no-l2cap-disconnect"], 1),
    # ch.30 R1-e: targeted cmd-5 kill + press store, alone and full F3-v3 recipe
    ("cmd5target",      ["--cmd5-target"], 0),
    ("cmd5target_f3",   ["--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT",
                         "--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep", "--no-disconnect-13",
                         "--no-pairing-kick", "--no-cleanup-kick",
                         "--no-l2cap-teardown", "--gate-close",
                         "--cmd5-target"], 0),
    ("ct_alias",        ["--CMD5-TARGET"], 0),
    ("ct_conf_nok",     ["--cmd5-target", "--no-cmd5-kill"], 1),
    ("ct_conf_r1a",     ["--cmd5-target", "--r1-conditional-kill"], 1),
    ("ct_conf_r1b",     ["--cmd5-target", "--r1-walker-kill"], 1),
    ("ct_conf_r1c",     ["--cmd5-target", "--cmd5-handle"], 1),
    # ch.31 D1 target-specific page waits (R1-e3)
    ("d1wait",          ["--d1-target-wait"], 0),
    ("d1wait_e3",       ["--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT",
                         "--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep", "--no-disconnect-13",
                         "--no-pairing-kick", "--no-cleanup-kick",
                         "--no-l2cap-teardown", "--gate-close",
                         "--cmd5-target", "--d1-target-wait"], 0),
    ("dt_alias",        ["--D1-TARGET-WAIT"], 0),
    # ch.30 R3 incoming-mode3 tbh hook (2026-11-02)
    ("r3",              ["--incoming-mode3"], 0),
    ("r3_e7",           ["--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT",
                         "--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep", "--no-disconnect-13",
                         "--no-pairing-kick", "--incoming-mode3"], 0),
    ("im3_alias",       ["--INCOMING-MODE3"], 0),
    # ch.30 R4 incoming-hfp tbh hook + cmd-1 bail (2026-11-03)
    ("r4",              ["--incoming-hfp"], 0),
    ("r4_e7",           ["--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT",
                         "--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep", "--no-disconnect-13",
                         "--no-pairing-kick", "--incoming-hfp"], 0),
    ("ihfp_alias",      ["--INCOMING-HFP"], 0),
    ("ihfp_conf_im3",   ["--incoming-mode3", "--incoming-hfp"], 1),
    # ch.30 R5 incoming-redial kick+redial at the tbh hook (2026-11-03)
    ("r5",              ["--incoming-redial"], 0),
    ("r5_e7",           ["--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT",
                         "--no-kick", "--conn-num=2", "--force-page-scan",
                         "--force-role-keep", "--no-disconnect-13",
                         "--no-pairing-kick", "--incoming-redial"], 0),
    ("irdl_alias",      ["--INCOMING-REDIAL"], 0),
    ("irdl_conf_im3",   ["--incoming-mode3", "--incoming-redial"], 1),
    ("irdl_conf_ihfp",  ["--incoming-hfp", "--incoming-redial"], 1),
    ("irdl_conf_gate",  ["--gate-close", "--incoming-redial"], 1),
    ("irdl_conf_c5t",   ["--cmd5-target", "--incoming-redial"], 1),
    ("irdl_conf_r1b",   ["--r1-walker-kill", "--incoming-redial"], 1),
    # ch.30 R6a redial-bind (loop-guard stamps byte 3) (2026-11-04)
    ("r6a",             ["--incoming-redial", "--redial-bind"], 0),
    ("r6a_alias",       ["--REDIAL-BIND", "--incoming-redial"], 0),
    ("r6a_alone",       ["--redial-bind"], 1),
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
    # --FORCE-ROLE-KEEP must equal the canonical --force-role-keep build
    identical(os.path.join(OUTDIR, "rk_alias.bin"),
              os.path.join(OUTDIR, "rolekeep.bin"),
              "--FORCE-ROLE-KEEP", "--force-role-keep")
    # --NO-DISCONNECT-13 must equal the canonical --no-disconnect-13 build
    identical(os.path.join(OUTDIR, "d13_alias.bin"),
              os.path.join(OUTDIR, "disc13.bin"),
              "--NO-DISCONNECT-13", "--no-disconnect-13")
    # --NO-PAIRING-KICK must equal the canonical --no-pairing-kick build
    identical(os.path.join(OUTDIR, "pk_alias.bin"),
              os.path.join(OUTDIR, "pairkick.bin"),
              "--NO-PAIRING-KICK", "--no-pairing-kick")
    # --NO-CLEANUP-KICK must equal the canonical --no-cleanup-kick build
    identical(os.path.join(OUTDIR, "ck_alias.bin"),
              os.path.join(OUTDIR, "cleanupkick.bin"),
              "--NO-CLEANUP-KICK", "--no-cleanup-kick")
    # --NO-L2CAP-TEARDOWN must equal the canonical --no-l2cap-teardown build
    identical(os.path.join(OUTDIR, "ltd_alias.bin"),
              os.path.join(OUTDIR, "l2capteardown.bin"),
              "--NO-L2CAP-TEARDOWN", "--no-l2cap-teardown")
    # --NO-SPP-CLOSE must equal the canonical --no-spp-close build
    identical(os.path.join(OUTDIR, "sc_alias.bin"),
              os.path.join(OUTDIR, "sppclose.bin"),
              "--NO-SPP-CLOSE", "--no-spp-close")
    # --NO-L2CAP-DISCONNECT must equal the canonical --no-l2cap-disconnect build
    identical(os.path.join(OUTDIR, "ld_alias.bin"),
              os.path.join(OUTDIR, "l2capdisc.bin"),
              "--NO-L2CAP-DISCONNECT", "--no-l2cap-disconnect")
    # --GATE-CLOSE must equal the canonical --gate-close build
    identical(os.path.join(OUTDIR, "gc_alias.bin"),
              os.path.join(OUTDIR, "gateclose.bin"),
              "--GATE-CLOSE", "--gate-close")
    # --show must run clean on a gated image
    exitcode, out = run([os.path.join(OUTDIR, "gateclose.bin"), "--show",
                         "--gate-close"])
    if exitcode == 0 and "UNKNOWN" not in out.upper():
        print("--show on gateclose clean OK")
    else:
        print("--show on gateclose -> FAIL")
        fail += 1
    # --show must run clean on a kick-NOP'd image
    exitcode, out = run([os.path.join(OUTDIR, "nokick.bin"), "--show",
                         "--no-kick"])
    if exitcode == 0 and "UNKNOWN" not in out.upper():
        print("--show on nokick clean OK")
    else:
        print("--show on nokick -> FAIL")
        fail += 1
    # --show must run clean on a role-keep image
    exitcode, out = run([os.path.join(OUTDIR, "rolekeep.bin"), "--show",
                         "--force-role-keep"])
    if exitcode == 0 and "UNKNOWN" not in out.upper():
        print("--show on rolekeep clean OK")
    else:
        print("--show on rolekeep -> FAIL")
        fail += 1
    # --show must run clean on a disc13 image
    exitcode, out = run([os.path.join(OUTDIR, "disc13.bin"), "--show",
                         "--no-disconnect-13"])
    if exitcode == 0 and "UNKNOWN" not in out.upper():
        print("--show on disc13 clean OK")
    else:
        print("--show on disc13 -> FAIL")
        fail += 1
    # --show must run clean on a pairkick image
    exitcode, out = run([os.path.join(OUTDIR, "pairkick.bin"), "--show",
                         "--no-pairing-kick"])
    if exitcode == 0 and "UNKNOWN" not in out.upper():
        print("--show on pairkick clean OK")
    else:
        print("--show on pairkick -> FAIL")
        fail += 1
    # --show must run clean on a cleanupkick image
    exitcode, out = run([os.path.join(OUTDIR, "cleanupkick.bin"), "--show",
                         "--no-cleanup-kick"])
    if exitcode == 0 and "UNKNOWN" not in out.upper():
        print("--show on cleanupkick clean OK")
    else:
        print("--show on cleanupkick -> FAIL")
        fail += 1
    # --show must run clean on an l2capteardown image
    exitcode, out = run([os.path.join(OUTDIR, "l2capteardown.bin"), "--show",
                         "--no-l2cap-teardown"])
    if exitcode == 0 and "UNKNOWN" not in out.upper():
        print("--show on l2capteardown clean OK")
    else:
        print("--show on l2capteardown -> FAIL")
        fail += 1
    # --show must run clean on a sppclose image
    exitcode, out = run([os.path.join(OUTDIR, "sppclose.bin"), "--show",
                         "--no-spp-close"])
    if exitcode == 0 and "UNKNOWN" not in out.upper():
        print("--show on sppclose clean OK")
    else:
        print("--show on sppclose -> FAIL")
        fail += 1
    # --show must run clean on a l2capdisc image
    exitcode, out = run([os.path.join(OUTDIR, "l2capdisc.bin"), "--show",
                         "--no-l2cap-disconnect"])
    if exitcode == 0 and "UNKNOWN" not in out.upper():
        print("--show on l2capdisc clean OK")
    else:
        print("--show on l2capdisc -> FAIL")
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
