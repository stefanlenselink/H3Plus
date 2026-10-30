"""Verify every (--PTT2, --OD-PTT) action pair of patch_h3plus_firmware_bluetooth.py.

Self-contained regression suite for the DIRECT-REWRITE model (Findings.md
9A.50): it builds all 20 ordered pairs of distinct actions itself, then
checks the patched images byte-for-byte. Run from the repo root:

    python tools/verify_actions.py [--keep]

--keep  leave the generated images in work/verify/ (they are deleted when
        every check passes; a failing build is always kept).

What each pair build is checked for:
  * press body A (stored value 7) == _pf_body7(--PTT2 action)
  * press body B (stored value 8) == _pf_body8(--OD-PTT action)
  * release dispatch window      == _pf_release(pair)
  * press tbb table entries 7/8 stay native (the model never swaps them)
  * main PTT key -> BT-PTT (tool default): pttdown 0x2A / pttup 0x2B
  * duplex mode 4 applied (tool default)
  * the stock pair (--PTT2=PTT2 --OD-PTT=OD-PTT) leaves the whole PF
    executor region untouched
  * BT-PTT2 (when in the pair): the key-0x2A TX-start trampoline and the
    code cave hold the expected bytes, and the cave handler reproduces
    the stock tail with the force-VFO-B branch
  * menu labels: all nine language lists read the right string for value
    7 and value 8; shared strings ('OD PTT', RU 'Net') stay intact
  * the changed-byte set equals exactly what build_patches() describes
  * idempotency: rebuilding from the patched image writes nothing
  * --show on the patched image reports no UNKNOWN state
Plus the refusal cases: same-action pairs, --PTT=PTT2/OD-PTT, and images
carrying the obsolete swap model (swapped tbb table).
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

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_h3plus_firmware_bluetooth as P
from jl_sfcenc import sfc_enc_decrypt

SRC = "Dumps/dump_internal.bin"
START = 0x5000            # app offset inside a raw internal dump
OUTDIR = "work/verify"
PTT_DOWN, PTT_UP = 0x01E52400, 0x01E524BE

LABEL = {"PTT": b"PTT", "PTT2": b"PTT2", "OD-PTT": b"OD PTT", "BT-PTT": b"BT PTT",
         "BT-PTT2": b"BT PTT2"}
NET = "\u041d\u0415\u0422\0".encode()
NO = "\u041d\u0435\u0442\0".encode()


def expected_label(action, a7, a8):
    """The menu string a list entry must read for `action` in this pair.

    BT-PTT2 shows "BT PTT2" when it can overwrite "PTT2"+NET in full, but
    the shorter "BT2" whenever "PTT2" must stay readable or the other BT
    action already occupies the "BT PTT" placement.
    """
    if action != "BT-PTT2":
        return LABEL[action]
    if "BT-PTT" in (a7, a8) or "PTT2" in (a7, a8):
        return b"BT2"
    return b"BT PTT2"

KEEP = "--keep" in sys.argv


def dec(path):
    r = open(path, "rb").read()
    return sfc_enc_decrypt(r[START:START + P.APP_LEN], 0, P.CHIPKEY)


def g(app, va, n):
    return bytes(app[P.va_to_off(va):P.va_to_off(va) + n])


def ptr_at(app, va):
    return int.from_bytes(g(app, va, 4), "little")


def run(*args):
    return subprocess.run(
        [sys.executable, "tools/patch_h3plus_firmware_bluetooth.py"] + list(args),
        capture_output=True, text=True)


stock = dec(SRC)
fail = []


def ck(cond, what):
    print(("OK   " if cond else "FAIL ") + what)
    if not cond:
        fail.append(what)


def expected_changed_set(a7, a8, ptt_action):
    """Every flash offset the tool is supposed to touch for this config."""
    patches = P.build_patches(4, a7, a8)
    names = list(P.DEFAULT_PATCHES) + P.PTT_KEY_PATCHES[ptt_action] \
        + P.pf_combo_patches(a7, a8)
    exp = set()

    def add_site(va, nat, new):
        o = P.va_to_off(va)
        exp.update(o + i for i in range(len(new)) if nat[i] != new[i])

    native = {"pfbody7": P.PF_BODY7_NATIVE,
              "pfbody8": P.PF_BODY8_NATIVE,
              "pfrelease": P.PF_REL_NATIVE,
              "pfhandler": P.H2A_TRAMP_NATIVE}
    for name in dict.fromkeys(names):
        pp = patches[name]
        if pp.get("kind") == "multi":
            for va, nat, new in pp["sites"]:
                add_site(va, nat, new)
        elif name == "duplex":
            add_site(pp["va"], P.DUPLEX_STATES[3], pp["new"])
        else:
            nat = native[name] if name in native else pp["states"]["native"]
            add_site(pp["va"], nat, pp["new"])
    return exp


# --- the 20 ordered pairs ---------------------------------------------------
pairs = sorted(P.PF_COMBO_PATCHES)
print("building %d (--PTT2, --OD-PTT) pairs from %s" % (len(pairs), SRC))
os.makedirs(OUTDIR, exist_ok=True)

for a7, a8 in pairs:
    out = os.path.join(OUTDIR, "v_%s_%s.bin"
                       % (a7.replace("-", ""), a8.replace("-", "")))
    cp = run(SRC, out, "--PTT2=%s" % a7, "--OD-PTT=%s" % a8)
    tag = "%-7s/%-7s" % (a7, a8)
    if cp.returncode != 0:
        ck(False, "%s build failed: %s" % (tag, (cp.stdout + cp.stderr)[-400:]))
        continue
    a = dec(out)

    # executor bodies + release dispatch + untouched tbb table
    ck(g(a, P.PF_BODY7_VA, 10) == P._pf_body7(a7), "%s body7" % tag)
    ck(g(a, P.PF_BODY8_VA, 8) == P._pf_body8(a8), "%s body8" % tag)
    ck(g(a, P.PF_REL_VA, P.PF_REL_LEN) == P._pf_release(a7, a8), "%s release" % tag)
    ck(g(a, P.PF_TBB_78_VA, 2) == P.PF_TBB_78_NATIVE, "%s tbb native" % tag)

    # defaults: main PTT -> BT-PTT, duplex mode 4
    ck(g(a, PTT_DOWN, 2) == b"\x48\x2a", "%s pttdown 0x2A" % tag)
    ck(g(a, PTT_UP, 2) == b"\x48\x2b", "%s pttup 0x2B" % tag)
    ck(g(a, P.DUPLEX_VA, 2) == bytes([0x41, 0x24]), "%s duplex mode 4" % tag)

    # the stock pair must leave the executor region byte-identical
    if (a7, a8) == ("PTT2", "OD-PTT"):
        lo = P.va_to_off(P.PF_BODY7_VA)
        hi = P.va_to_off(P.PF_REL_VA) + P.PF_REL_LEN
        ck(a[lo:hi] == stock[lo:hi], "%s stock pair leaves executor untouched" % tag)

    # --- strings -------------------------------------------------------------
    ck(g(a, P.STR_OD_PTT_VA, 7) == b"OD PTT\0", "%s: 'OD PTT' intact" % tag)
    ck(g(a, P.STR_PTT_VA, 4) == b"PTT\0", "%s: 'PTT' tail intact" % tag)
    ck(g(a, P.STR_RU_NO_VA, 7) == NO, "%s: RU 'Net' intact" % tag)
    bt_needed = "BT-PTT" in (a7, a8)
    bt2_needed = "BT-PTT2" in (a7, a8)
    keep_ptt2 = "PTT2" in (a7, a8)
    if bt_needed:
        bt_at = P._BT_PTT_AT_NET if (keep_ptt2 or bt2_needed) else P._BT_PTT_AT_PTT2
        ck(g(a, bt_at, 7) == b"BT PTT\0", "%s: 'BT PTT' at 0x%08X" % (tag, bt_at))
    if bt2_needed:
        if bt_needed:
            ck(g(a, P.STR_PTT2_VA, 4) == b"BT2\0", "%s: 'BT2' over PTT2" % tag)
        elif keep_ptt2:
            ck(g(a, P._RU_NET_AT, 4) == b"BT2\0", "%s: 'BT2' over RU NET" % tag)
        else:
            ck(g(a, P.STR_PTT2_VA, 8) == b"BT PTT2\0",
               "%s: 'BT PTT2' over PTT2+NET" % tag)
    if bt_needed or bt2_needed:
        for p in P.RU_NONE_PTRS:
            ck(ptr_at(a, p) == P.STR_RU_NO_VA, "%s: RU NET ptr -> 'Net'" % tag)
    else:
        ck(g(a, P._RU_NET_AT, 7) == NET, "%s: RU NET intact" % tag)
        for p in P.RU_NONE_PTRS:
            ck(ptr_at(a, p) == P.STR_RU_NONE_VA, "%s: RU NET ptr untouched" % tag)
    if keep_ptt2 and not (bt2_needed and bt_needed):
        ck(g(a, P.STR_PTT2_VA, 5) == b"PTT2\0", "%s: 'PTT2' string intact" % tag)

    # --- BT-PTT2 trampoline + code cave -------------------------------------
    if bt2_needed:
        ck(g(a, P.H2A_TRAMP_VA, P.H2A_TRAMP_LEN)
           == P.encode_goto32(P.H2A_TRAMP_VA, P.CAVE_VA)
           + b"\x00" * (P.H2A_TRAMP_LEN - 4),
           "%s: key-0x2A TX-start trampoline -> cave" % tag)
        ck(g(a, P.CAVE_VA, P.CAVE_LEN) == P._cave_images(),
           "%s: cave holds BT-PTT2 helper code" % tag)
        # the cave handler must reproduce the stock tail it replaces:
        # load/shift/store of the current-VFO byte, then the TX-start call
        h = g(a, P.CAVE_VA, 36)
        ck(h[18:28] == bytes.fromhex("50ee7707 80a7 52ee7604".replace(" ", "")),
           "%s: cave handler keeps the stock current-VFO tail" % tag)
        ck(g(a, P.CAVE_VA + 28, 4) == P.encode_call(P.CAVE_VA + 28, P.TXSTART2_VA),
           "%s: cave handler calls the TX start" % tag)
        ck(g(a, P.CAVE_VA + 32, 4)
           == P.encode_goto32(P.CAVE_VA + 32, P.H2A_RESUME_VA),
           "%s: cave handler resumes after the native call" % tag)
    else:
        ck(g(a, P.H2A_TRAMP_VA, P.H2A_TRAMP_LEN) == P.H2A_TRAMP_NATIVE,
           "%s: key-0x2A TX-start tail untouched" % tag)
        ck(g(a, P.CAVE_VA, P.CAVE_LEN) == b"\x00" * P.CAVE_LEN,
           "%s: code cave stays erased" % tag)

    # --- menu labels resolve ------------------------------------------------
    for p in P.PF_LIST_PTT2_PTRS:
        for val, act in ((7, a7), (8, a8)):
            va = ptr_at(a, p + (0 if val == 7 else 4))
            s = g(a, va, 16).split(b"\0")[0]
            want = expected_label(act, a7, a8)
            ck(s == want, "%s: list 0x%08X value %d reads %r" % (tag, p, val, want))

    # --- nothing else changed -----------------------------------------------
    exp = expected_changed_set(a7, a8, "BT-PTT")
    got = {i for i in range(len(stock)) if stock[i] != a[i]}
    ck(got == exp, "%s: changed set == expected (%d vs %d bytes)"
       % (tag, len(got), len(exp)))
    if got != exp:
        print("     unexpected:", ["%X" % i for i in sorted(got - exp)[:10]])
        print("     missing:", ["%X" % i for i in sorted(exp - got)[:10]])

    # --- idempotency + --show ------------------------------------------------
    cp2 = run(out, out + ".2", "--PTT2=%s" % a7, "--OD-PTT=%s" % a8)
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout
       and not os.path.exists(out + ".2"), "%s idempotent" % tag)
    cp3 = run(out, "--show", "--PTT2=%s" % a7, "--OD-PTT=%s" % a8)
    ck(cp3.returncode == 0 and "UNKNOWN" not in cp3.stdout, "%s --show clean" % tag)

# --- refusal cases ----------------------------------------------------------
# SystemExit messages go to stderr, so check both streams.
for act in P.ACTIONS:
    cp = run(SRC, os.path.join(OUTDIR, "v_no.bin"),
             "--PTT2=%s" % act, "--OD-PTT=%s" % act)
    ck(cp.returncode != 0 and "cannot run the same action" in cp.stdout + cp.stderr,
       "refuse same-action %s/%s" % (act, act))
for act in ("PTT2", "OD-PTT", "BT-PTT2"):
    cp = run(SRC, os.path.join(OUTDIR, "v_no.bin"), "--PTT=%s" % act)
    ck(cp.returncode != 0 and "--PTT=%s is not possible" % act in cp.stdout + cp.stderr,
       "refuse --PTT=%s" % act)

# an image carrying the obsolete swap model (swapped press tbb table) must
# be detected and refused instead of being mislabelled by the new model
sw = os.path.join(OUTDIR, "v_swap_legacy.bin")
a = bytearray(stock)
o = P.va_to_off(P.PF_TBB_78_VA)
a[o:o + 2] = P.PF_TBB_78_SWAPPED
raw = bytearray(open(SRC, "rb").read())
raw[START:START + P.APP_LEN] = sfc_enc_decrypt(bytes(a), 0, P.CHIPKEY)
open(sw, "wb").write(raw)
cp = run(sw, os.path.join(OUTDIR, "v_swap_out.bin"),
         "--PTT2=BT-PTT", "--OD-PTT=PTT")
ck(cp.returncode != 0 and "obsolete swap model" in cp.stdout + cp.stderr,
   "refuse image with swapped tbb table")

# --- --conn-num (EXPERIMENTAL multipoint gate, ch.22 §9B.10.1) --------------
cn = os.path.join(OUTDIR, "v_connum2.bin")
cp = run(SRC, cn, "--only", "connum", "--conn-num=2")
ck(cp.returncode == 0, "--conn-num=2 build")
if cp.returncode == 0:
    a = dec(cn)
    ck(g(a, P.CONN_NUM_VA, 2) == b"\x31\x25", "connum byte -> 31 25")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    ck(d == [P.va_to_off(P.CONN_NUM_VA) + 1],
       "connum patch touches exactly one byte (%s)" % [hex(x) for x in d])
    cp = run(cn, "--show")
    cnline = [l for l in cp.stdout.splitlines() if l.startswith("connum")]
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and len(cnline) == 1 and "current" in cnline[0],
       "--show on patched connum clean")
    cp2 = run(cn, cn + ".2", "--only", "connum", "--conn-num=2")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "connum idempotent")
    cp3 = run(cn, os.path.join(OUTDIR, "v_connum1.bin"),
              "--only", "connum", "--conn-num=1")
    ck(cp3.returncode == 0 and dec(os.path.join(OUTDIR, "v_connum1.bin"))
       [P.va_to_off(P.CONN_NUM_VA) + 1] == 0x24, "conn-num=1 reverts")
cp = run(SRC, os.path.join(OUTDIR, "v_no.bin"), "--conn-num=3")
ck(cp.returncode != 0, "refuse --conn-num=3")

# --- --no-kick (multipoint Option A, ch.26 SS26.4/SS26.7) -------------------
nk = os.path.join(OUTDIR, "v_nokick.bin")
cp = run(SRC, nk, "--only", "nokick", "--no-kick")
ck(cp.returncode == 0, "--no-kick build")
if cp.returncode == 0:
    a = dec(nk)
    ck(g(a, P.NOKICK_VA, 4) == b"\x40\x23\x80\x00",
       "kick entry -> r0 = 3; rts")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    ck(d == list(range(P.va_to_off(P.NOKICK_VA),
                       P.va_to_off(P.NOKICK_VA) + 4)),
       "nokick patch touches exactly 4 bytes (%s)" % [hex(x) for x in d])
    cp = run(nk, "--show", "--no-kick")
    nkline = [l for l in cp.stdout.splitlines() if l.startswith("nokick")]
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and len(nkline) == 1 and "TARGET" in nkline[0],
       "--show on patched nokick clean")
    cp2 = run(nk, nk + ".2", "--only", "nokick", "--no-kick")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "nokick idempotent")
    cp3 = run(nk, os.path.join(OUTDIR, "v_kickback.bin"),
              "--only", "nokick")
    ck(cp3.returncode == 0 and dec(os.path.join(OUTDIR, "v_kickback.bin"))
       [P.va_to_off(P.NOKICK_VA):P.va_to_off(P.NOKICK_VA) + 4]
       == b"\x75\x04\xc5\xff", "nokick reverts to stock")
# Option A combo: kick-NOP + conn-num=2 in one build
ca = os.path.join(OUTDIR, "v_optiona.bin")
cp = run(SRC, ca, "--no-kick", "--conn-num=2", "--PTT=BT-PTT",
         "--PTT2=BT-PTT2", "--OD-PTT=PTT")
ck(cp.returncode == 0, "Option A combo build (--no-kick --conn-num=2)")
if cp.returncode == 0:
    a = dec(ca)
    ck(g(a, P.NOKICK_VA, 4) == b"\x40\x23\x80\x00"
       and g(a, P.CONN_NUM_VA, 2) == b"\x31\x25",
       "Option A carries both kick-NOP and conn_num=2")

# --- --force-page-scan (multipoint Option A2, ch.26 SS26.9) -----------------
fp = os.path.join(OUTDIR, "v_pagescan.bin")
cp = run(SRC, fp, "--only", "pagescan", "--force-page-scan")
ck(cp.returncode == 0, "--force-page-scan build")
if cp.returncode == 0:
    a = dec(fp)
    ck(g(a, P.PAGESCAN_VA, 4) == b"\x00\x00\x00\x00",
       "page-scan disable branch -> nop; nop")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    ck(d == list(range(P.va_to_off(P.PAGESCAN_VA),
                       P.va_to_off(P.PAGESCAN_VA) + 4)),
       "pagescan patch touches exactly 4 bytes (%s)" % [hex(x) for x in d])
    cp = run(fp, "--show", "--force-page-scan")
    psline = [l for l in cp.stdout.splitlines() if l.startswith("pagescan")]
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and len(psline) == 1 and "TARGET" in psline[0],
       "--show on patched pagescan clean")
    cp2 = run(fp, fp + ".2", "--only", "pagescan", "--force-page-scan")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "pagescan idempotent")
    cp3 = run(fp, os.path.join(OUTDIR, "v_psback.bin"), "--only", "pagescan")
    ck(cp3.returncode == 0 and dec(os.path.join(OUTDIR, "v_psback.bin"))
       [P.va_to_off(P.PAGESCAN_VA):P.va_to_off(P.PAGESCAN_VA) + 4]
       == b"\x80\x41\x24\x16", "pagescan reverts to stock")
# Option A2 combo: kick-NOP + conn-num=2 + force-page-scan
ca2 = os.path.join(OUTDIR, "v_optiona2.bin")
cp = run(SRC, ca2, "--no-kick", "--conn-num=2", "--force-page-scan",
         "--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT")
ck(cp.returncode == 0, "Option A2 combo build (+--force-page-scan)")
if cp.returncode == 0:
    a = dec(ca2)
    ck(g(a, P.NOKICK_VA, 4) == b"\x40\x23\x80\x00"
       and g(a, P.CONN_NUM_VA, 2) == b"\x31\x25"
       and g(a, P.PAGESCAN_VA, 4) == b"\x00\x00\x00\x00",
       "Option A2 carries kick-NOP + conn_num=2 + page-scan NOP")

# --- --force-role-keep (multipoint experiment E4, ch.27 SS27.8) -------------
rk = os.path.join(OUTDIR, "v_rolekeep.bin")
cp = run(SRC, rk, "--only", "rolekeep", "--force-role-keep")
ck(cp.returncode == 0, "--force-role-keep build")
if cp.returncode == 0:
    a = dec(rk)
    ck(g(a, P.ROLEKEEP_VA, 10) == bytes.fromhex("c0ea4502000000000000"),
       "ACL role test -> goto 0x01E1A4C8 (accept with role 0xAA)")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    roff = P.va_to_off(P.ROLEKEEP_VA)
    ck(len(d) == 9 and all(roff <= i < roff + 10 for i in d),
       "rolekeep patch touches only its site, 9 differing bytes (%s)"
       % [hex(x) for x in d])
    cp = run(rk, "--show", "--force-role-keep")
    rkline = [l for l in cp.stdout.splitlines() if l.startswith("rolekeep")]
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and len(rkline) == 1 and "TARGET" in rkline[0],
       "--show on patched rolekeep clean")
    cp2 = run(rk, rk + ".2", "--only", "rolekeep", "--force-role-keep")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "rolekeep idempotent")
    cp3 = run(rk, os.path.join(OUTDIR, "v_rkback.bin"), "--only", "rolekeep")
    ck(cp3.returncode == 0 and dec(os.path.join(OUTDIR, "v_rkback.bin"))
       [roff:roff + 10] == bytes.fromhex("50ee970161ff08004202"),
       "rolekeep reverts to stock")
# E4 combo: Option A2 trio + role-keep
ce4 = os.path.join(OUTDIR, "v_e4.bin")
cp = run(SRC, ce4, "--no-kick", "--conn-num=2", "--force-page-scan",
         "--force-role-keep", "--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT")
ck(cp.returncode == 0, "E4 combo build (Option A2 + --force-role-keep)")
if cp.returncode == 0:
    a = dec(ce4)
    ck(g(a, P.NOKICK_VA, 4) == b"\x40\x23\x80\x00"
       and g(a, P.CONN_NUM_VA, 2) == b"\x31\x25"
       and g(a, P.PAGESCAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.ROLEKEEP_VA, 10) == bytes.fromhex("c0ea4502000000000000"),
       "E4 combo carries kick-NOP + conn_num=2 + page-scan NOP + role-keep")

# --- --no-disconnect-13 (multipoint experiment E6, ch.27 SS27.9) ------------
d13 = os.path.join(OUTDIR, "v_disc13.bin")
cp = run(SRC, d13, "--only", "disc13", "--no-disconnect-13")
ck(cp.returncode == 0, "--no-disconnect-13 build")
if cp.returncode == 0:
    a = dec(d13)
    ck(g(a, P.DISC13_VA, 8) == bytes.fromhex("0000000040165504"),
       "disconnect(handle,0x13) call -> nop;nop, falls through to mov r0,r4")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    doff = P.va_to_off(P.DISC13_VA)
    ck(len(d) == 4 and all(doff <= i < doff + 4 for i in d),
       "disc13 patch touches exactly 4 bytes (%s)" % [hex(x) for x in d])
    cp = run(d13, "--show", "--no-disconnect-13")
    d13line = [l for l in cp.stdout.splitlines() if l.startswith("disc13")]
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and len(d13line) == 1 and "TARGET" in d13line[0],
       "--show on patched disc13 clean")
    cp2 = run(d13, d13 + ".2", "--only", "disc13", "--no-disconnect-13")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "disc13 idempotent")
    cp3 = run(d13, os.path.join(OUTDIR, "v_d13back.bin"), "--only", "disc13")
    ck(cp3.returncode == 0 and dec(os.path.join(OUTDIR, "v_d13back.bin"))
       [doff:doff + 4] == bytes.fromhex("bfea1b81"),
       "disc13 reverts to stock")
# E6 combo: full multipoint recipe + disc13 NOP
ce6 = os.path.join(OUTDIR, "v_e6.bin")
cp = run(SRC, ce6, "--no-kick", "--conn-num=2", "--force-page-scan",
         "--force-role-keep", "--no-disconnect-13", "--PTT=BT-PTT",
         "--PTT2=BT-PTT2", "--OD-PTT=PTT")
ck(cp.returncode == 0, "E6 combo build (E4 + --no-disconnect-13)")
if cp.returncode == 0:
    a = dec(ce6)
    ck(g(a, P.NOKICK_VA, 4) == b"\x40\x23\x80\x00"
       and g(a, P.CONN_NUM_VA, 2) == b"\x31\x25"
       and g(a, P.PAGESCAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.ROLEKEEP_VA, 10) == bytes.fromhex("c0ea4502000000000000")
       and g(a, P.DISC13_VA, 4) == b"\x00\x00\x00\x00",
       "E6 combo carries all five multipoint patches")

# --- --no-pairing-kick (multipoint experiment E7, ch.27 SS27.12) -------------
pk = os.path.join(OUTDIR, "v_pairkick.bin")
cp = run(SRC, pk, "--only", "pairkickall", "--only", "pairkickone",
         "--no-pairing-kick")
ck(cp.returncode == 0, "--no-pairing-kick build")
if cp.returncode == 0:
    a = dec(pk)
    ck(g(a, P.PAIRKICK_ALL_VA, 8) == bytes.fromhex("000000004521c63c"),
       "disconnect-all 0x16 call -> nop;nop, loop + scan-reset intact")
    ck(g(a, P.PAIRKICK_ONE_VA, 8) == bytes.fromhex("00000000059400e1"),
       "single 0x16 call -> nop;nop, falls through to return")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    o1 = P.va_to_off(P.PAIRKICK_ALL_VA)
    o2 = P.va_to_off(P.PAIRKICK_ONE_VA)
    ck(len(d) == 8 and all(o1 <= i < o1 + 4 or o2 <= i < o2 + 4 for i in d),
       "pairkick patch touches exactly 8 bytes (%s)" % [hex(x) for x in d])
    cp = run(pk, "--show", "--no-pairing-kick")
    pklines = [l for l in cp.stdout.splitlines() if l.startswith("pairkick")]
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and len(pklines) == 2 and all("TARGET" in l for l in pklines),
       "--show on patched pairkick clean")
    cp2 = run(pk, pk + ".2", "--only", "pairkickall", "--only", "pairkickone",
              "--no-pairing-kick")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "pairkick idempotent")
    cp3 = run(pk, os.path.join(OUTDIR, "v_pkback.bin"),
              "--only", "pairkickall", "--only", "pairkickone")
    b3 = dec(os.path.join(OUTDIR, "v_pkback.bin")) if cp3.returncode == 0 else b""
    ck(cp3.returncode == 0 and b3[o1:o1 + 4] == bytes.fromhex("bfea55bb")
       and b3[o2:o2 + 4] == bytes.fromhex("bfeae5ba"),
       "pairkick reverts to stock")
# E7 combo: full multipoint recipe + pairing-kick NOPs
ce7 = os.path.join(OUTDIR, "v_e7.bin")
cp = run(SRC, ce7, "--no-kick", "--conn-num=2", "--force-page-scan",
         "--force-role-keep", "--no-disconnect-13", "--no-pairing-kick",
         "--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT")
ck(cp.returncode == 0, "E7 combo build (E6 + --no-pairing-kick)")
if cp.returncode == 0:
    a = dec(ce7)
    ck(g(a, P.NOKICK_VA, 4) == b"\x40\x23\x80\x00"
       and g(a, P.CONN_NUM_VA, 2) == b"\x31\x25"
       and g(a, P.PAGESCAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.ROLEKEEP_VA, 10) == bytes.fromhex("c0ea4502000000000000")
       and g(a, P.DISC13_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ALL_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ONE_VA, 4) == b"\x00\x00\x00\x00",
       "E7 combo carries all seven multipoint patches")

# --- --no-cleanup-kick (multipoint experiment E8, ch.27 SS27.13/27.14) -------
ckk = os.path.join(OUTDIR, "v_cleanupkick.bin")
cp = run(SRC, ckk, "--only", "cleanupkickvar", "--only", "cleanupkickorphan",
         "--only", "cleanupkickprof", "--no-cleanup-kick")
ck(cp.returncode == 0, "--no-cleanup-kick build")
if cp.returncode == 0:
    a = dec(ckk)
    ck(g(a, P.CLEANUPKICK_VAR_VA, 8) == bytes.fromhex("00000000649d5016"),
       "variable-reason event call -> nop;nop, msg path intact")
    ck(g(a, P.CLEANUPKICK_ORPHAN_VA, 8) == bytes.fromhex("00000000549d84f9"),
       "orphan-ACL cleanup call -> nop;nop, falls through to return")
    ck(g(a, P.CLEANUPKICK_PROF_VA, 8) == bytes.fromhex("00000000486261ff"),
       "profile-record cleanup call -> nop;nop, record still cleared")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    o1 = P.va_to_off(P.CLEANUPKICK_VAR_VA)
    o2 = P.va_to_off(P.CLEANUPKICK_ORPHAN_VA)
    o3 = P.va_to_off(P.CLEANUPKICK_PROF_VA)
    ck(len(d) == 12 and all(o1 <= i < o1 + 4 or o2 <= i < o2 + 4
       or o3 <= i < o3 + 4 for i in d),
       "cleanupkick patch touches exactly 12 bytes (%s)" % [hex(x) for x in d])
    cp = run(ckk, "--show", "--no-cleanup-kick")
    cklines = [l for l in cp.stdout.splitlines() if l.startswith("cleanupkick")]
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and len(cklines) == 3 and all("TARGET" in l for l in cklines),
       "--show on patched cleanupkick clean")
    cp2 = run(ckk, ckk + ".2", "--only", "cleanupkickvar",
              "--only", "cleanupkickorphan", "--only", "cleanupkickprof",
              "--no-cleanup-kick")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "cleanupkick idempotent")
    cp3 = run(ckk, os.path.join(OUTDIR, "v_ckback.bin"),
              "--only", "cleanupkickvar", "--only", "cleanupkickorphan",
              "--only", "cleanupkickprof")
    b3 = dec(os.path.join(OUTDIR, "v_ckback.bin")) if cp3.returncode == 0 else b""
    ck(cp3.returncode == 0 and b3[o1:o1 + 4] == bytes.fromhex("bfeadffc")
       and b3[o2:o2 + 4] == bytes.fromhex("bfeabdfc")
       and b3[o3:o3 + 4] == bytes.fromhex("bfeaeec4"),
       "cleanupkick reverts to stock")
# E8 combo: full multipoint recipe + cleanup-kick NOPs
ce8 = os.path.join(OUTDIR, "v_e8.bin")
cp = run(SRC, ce8, "--no-kick", "--conn-num=2", "--force-page-scan",
         "--force-role-keep", "--no-disconnect-13", "--no-pairing-kick",
         "--no-cleanup-kick",
         "--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT")
ck(cp.returncode == 0, "E8 combo build (E7 + --no-cleanup-kick)")
if cp.returncode == 0:
    a = dec(ce8)
    ck(g(a, P.NOKICK_VA, 4) == b"\x40\x23\x80\x00"
       and g(a, P.CONN_NUM_VA, 2) == b"\x31\x25"
       and g(a, P.PAGESCAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.ROLEKEEP_VA, 10) == bytes.fromhex("c0ea4502000000000000")
       and g(a, P.DISC13_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ALL_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ONE_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_VAR_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_ORPHAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_PROF_VA, 4) == b"\x00\x00\x00\x00",
       "E8 combo carries all ten multipoint patches")

# --- --no-l2cap-teardown (multipoint experiment E9, ch.27 SS27.15) -----------
ltd = os.path.join(OUTDIR, "v_l2capteardown.bin")
cp = run(SRC, ltd, "--only", "l2capteardownui", "--only", "l2capteardownmode",
         "--no-l2cap-teardown")
ck(cp.returncode == 0, "--no-l2cap-teardown build")
if cp.returncode == 0:
    a = dec(ltd)
    ck(g(a, P.L2CAPTEARDOWN_UI_VA, 8) == bytes.fromhex("00000000506b804b"),
       "connect-UI 0x4a post -> nop;nop, connect flow continues")
    ck(g(a, P.L2CAPTEARDOWN_MODE_VA, 8) == bytes.fromhex("00000000048dbdea"),
       "mode-setter 0x4a post -> nop;nop, mode switch continues")
    ck(g(a, P.L2CAPTEARDOWN_APP_VA, 4) == bytes.fromhex("00000000"),
       "app (AT/SPP-dispatcher) 0x4a post -> nop;nop (F3-B third poster)")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    o1 = P.va_to_off(P.L2CAPTEARDOWN_UI_VA)
    o2 = P.va_to_off(P.L2CAPTEARDOWN_MODE_VA)
    o3 = P.va_to_off(P.L2CAPTEARDOWN_APP_VA)
    ck(len(d) == 12 and all(o1 <= i < o1 + 4 or o2 <= i < o2 + 4 or o3 <= i < o3 + 4
                            for i in d),
       "l2capteardown patch touches exactly 12 bytes (%s)" % [hex(x) for x in d])
    cp = run(ltd, "--show", "--no-l2cap-teardown")
    ltdlines = [l for l in cp.stdout.splitlines() if l.startswith("l2capteardown")]
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and len(ltdlines) == 3 and all("TARGET" in l for l in ltdlines),
       "--show on patched l2capteardown clean")
    cp2 = run(ltd, ltd + ".2", "--only", "l2capteardownui",
              "--only", "l2capteardownmode", "--no-l2cap-teardown")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "l2capteardown idempotent")
    cp3 = run(ltd, os.path.join(OUTDIR, "v_ltdback.bin"),
              "--only", "l2capteardownui", "--only", "l2capteardownmode",
              "--only", "l2capteardownapp")
    b3 = dec(os.path.join(OUTDIR, "v_ltdback.bin")) if cp3.returncode == 0 else b""
    ck(cp3.returncode == 0 and b3[o1:o1 + 4] == bytes.fromhex("bdea84ad")
       and b3[o2:o2 + 4] == bytes.fromhex("bdead1bb")
       and b3[o3:o3 + 4] == bytes.fromhex("beea9340"),
       "l2capteardown reverts to stock")
# E9 combo: full multipoint recipe + L2CAP-teardown NOPs
ce9 = os.path.join(OUTDIR, "v_e9.bin")
cp = run(SRC, ce9, "--no-kick", "--conn-num=2", "--force-page-scan",
         "--force-role-keep", "--no-disconnect-13", "--no-pairing-kick",
         "--no-cleanup-kick", "--no-l2cap-teardown",
         "--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT")
ck(cp.returncode == 0, "E9 combo build (E8 + --no-l2cap-teardown)")
if cp.returncode == 0:
    a = dec(ce9)
    ck(g(a, P.NOKICK_VA, 4) == b"\x40\x23\x80\x00"
       and g(a, P.CONN_NUM_VA, 2) == b"\x31\x25"
       and g(a, P.PAGESCAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.ROLEKEEP_VA, 10) == bytes.fromhex("c0ea4502000000000000")
       and g(a, P.DISC13_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ALL_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ONE_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_VAR_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_ORPHAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_PROF_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.L2CAPTEARDOWN_UI_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.L2CAPTEARDOWN_MODE_VA, 4) == b"\x00\x00\x00\x00",
       "E9 combo carries all twelve multipoint patches")

# --- --no-spp-close (multipoint experiment E10, ch.27 SS27.16) ---------------
spc = os.path.join(OUTDIR, "v_sppclose.bin")
cp = run(SRC, spc, "--only", "sppclose", "--no-spp-close")
ck(cp.returncode == 0, "--no-spp-close build")
if cp.returncode == 0:
    a = dec(spc)
    ck(g(a, P.SPPCLOSE_VA, 8) == bytes.fromhex("4020000401000060"),
       "spp_channel_disconnect entry -> mov r0,#0; rts, push rets intact")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    o1 = P.va_to_off(P.SPPCLOSE_VA)
    ck(len(d) == 4 and all(o1 <= i < o1 + 4 for i in d),
       "sppclose patch touches exactly 4 bytes (%s)" % [hex(x) for x in d])
    cp = run(spc, "--show", "--no-spp-close")
    splines = [l for l in cp.stdout.splitlines() if l.startswith("sppclose")]
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and len(splines) == 1 and "TARGET" in splines[0],
       "--show on patched sppclose clean")
    cp2 = run(spc, spc + ".2", "--only", "sppclose", "--no-spp-close")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "sppclose idempotent")
    cp3 = run(spc, os.path.join(OUTDIR, "v_spcback.bin"), "--only", "sppclose")
    b3 = dec(os.path.join(OUTDIR, "v_spcback.bin")) if cp3.returncode == 0 else b""
    ck(cp3.returncode == 0 and b3[o1:o1 + 4] == bytes.fromhex("c0ff40a7"),
       "sppclose reverts to stock")
# E10 combo: full multipoint recipe + spp_channel_disconnect no-op
ce10 = os.path.join(OUTDIR, "v_e10.bin")
cp = run(SRC, ce10, "--no-kick", "--conn-num=2", "--force-page-scan",
         "--force-role-keep", "--no-disconnect-13", "--no-pairing-kick",
         "--no-cleanup-kick", "--no-l2cap-teardown", "--no-spp-close",
         "--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT")
ck(cp.returncode == 0, "E10 combo build (E9 + --no-spp-close)")
if cp.returncode == 0:
    a = dec(ce10)
    ck(g(a, P.NOKICK_VA, 4) == b"\x40\x23\x80\x00"
       and g(a, P.CONN_NUM_VA, 2) == b"\x31\x25"
       and g(a, P.PAGESCAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.ROLEKEEP_VA, 10) == bytes.fromhex("c0ea4502000000000000")
       and g(a, P.DISC13_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ALL_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ONE_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_VAR_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_ORPHAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_PROF_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.L2CAPTEARDOWN_UI_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.L2CAPTEARDOWN_MODE_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.SPPCLOSE_VA, 4) == bytes.fromhex("40200004"),
       "E10 combo carries all thirteen multipoint patches")

# --- --no-l2cap-disconnect (multipoint experiment E11, ch.27 SS27.17) -------
ld = os.path.join(OUTDIR, "v_l2capdisc.bin")
cp = run(SRC, ld, "--only", "l2capdiscbranch", "--only", "l2capdiscentry",
         "--no-l2cap-disconnect")
ck(cp.returncode == 0, "--no-l2cap-disconnect build")
if cp.returncode == 0:
    a = dec(ld)
    ck(g(a, P.L2CAPDISC_BRANCH_VA, 8) == bytes.fromhex("0000000000ff58b0"),
       "0x4a dispatch branch -> nop;nop, falls through to default")
    ck(g(a, P.L2CAPDISC_ENTRY_VA, 8) == bytes.fromhex("00238000b1fa0049"),
       "l2cap_disconnect entry -> mov r0,#0; rts")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    o1 = P.va_to_off(P.L2CAPDISC_BRANCH_VA)
    o2 = P.va_to_off(P.L2CAPDISC_ENTRY_VA)
    ck(len(d) == 8 and all(o1 <= i < o1 + 4 or o2 <= i < o2 + 4 for i in d),
       "l2capdisc patch touches exactly 8 bytes (%s)" % [hex(x) for x in d])
    cp = run(ld, "--show", "--no-l2cap-disconnect")
    ldlines = [l for l in cp.stdout.splitlines() if l.startswith("l2capdisc")]
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and len(ldlines) == 2 and all("TARGET" in l for l in ldlines),
       "--show on patched l2capdisc clean")
    cp2 = run(ld, ld + ".2", "--only", "l2capdiscbranch",
              "--only", "l2capdiscentry", "--no-l2cap-disconnect")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "l2capdisc idempotent")
    cp3 = run(ld, os.path.join(OUTDIR, "v_ldback.bin"),
              "--only", "l2capdiscbranch", "--only", "l2capdiscentry")
    b3 = dec(os.path.join(OUTDIR, "v_ldback.bin")) if cp3.returncode == 0 else b""
    ck(cp3.returncode == 0 and b3[o1:o1 + 4] == bytes.fromhex("0bf8d494")
       and b3[o2:o2 + 4] == bytes.fromhex("1004bfea"),
       "l2capdisc reverts to stock")
# E11 combo: full multipoint recipe + L2CAP-level kill
ce11 = os.path.join(OUTDIR, "v_e11.bin")
cp = run(SRC, ce11, "--no-kick", "--conn-num=2", "--force-page-scan",
         "--force-role-keep", "--no-disconnect-13", "--no-pairing-kick",
         "--no-cleanup-kick", "--no-l2cap-teardown", "--no-spp-close",
         "--no-l2cap-disconnect",
         "--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT")
ck(cp.returncode == 0, "E11 combo build (E10 + --no-l2cap-disconnect)")
if cp.returncode == 0:
    a = dec(ce11)
    ck(g(a, P.NOKICK_VA, 4) == b"\x40\x23\x80\x00"
       and g(a, P.CONN_NUM_VA, 2) == b"\x31\x25"
       and g(a, P.PAGESCAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.ROLEKEEP_VA, 10) == bytes.fromhex("c0ea4502000000000000")
       and g(a, P.DISC13_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ALL_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ONE_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_VAR_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_ORPHAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_PROF_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.L2CAPTEARDOWN_UI_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.L2CAPTEARDOWN_MODE_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.SPPCLOSE_VA, 4) == bytes.fromhex("40200004")
       and g(a, P.L2CAPDISC_BRANCH_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.L2CAPDISC_ENTRY_VA, 4) == bytes.fromhex("00238000"),
       "E11 combo carries all fifteen multipoint patches")

# --- --gate-close (ch.30 F3 conditional close gate, findings/30 SS30.11) ----
gc = os.path.join(OUTDIR, "v_gateclose.bin")
cp = run(SRC, gc, "--only", "gatespptramp", "--only", "gatel2captramp",
         "--only", "gatecave", "--gate-close")
ck(cp.returncode == 0, "--gate-close build")
if cp.returncode == 0:
    a = dec(gc)
    ck(g(a, P.GATE_SPP_TRAMP_VA, 4) == P.GATE_SPP_TRAMP
       and g(a, P.GATE_L2CAP_TRAMP_VA, 4) == P.GATE_L2CAP_TRAMP
       and g(a, P.GATE_CAVE2_VA, P.GATE_CAVE2_LEN) == P.GATE_CAVE2_IMG,
       "gate trampolines + cave stubs written")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    o1 = P.va_to_off(P.GATE_SPP_TRAMP_VA)
    o2 = P.va_to_off(P.GATE_L2CAP_TRAMP_VA)
    o3 = P.va_to_off(P.GATE_CAVE2_VA)
    ck(len(d) == 56 and all(o1 <= i < o1 + 4 or o2 <= i < o2 + 4
                            or o3 <= i < o3 + P.GATE_CAVE2_LEN for i in d),
       "gate-close patch touches exactly 56 bytes (%d)" % len(d))
    cp = run(gc, "--show", "--gate-close")
    gclines = [l for l in cp.stdout.splitlines() if l.startswith("gate")]
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and len(gclines) == 3 and all("TARGET" in l for l in gclines),
       "--show on gated image clean")
    cp2 = run(gc, gc + ".2", "--only", "gatespptramp", "--only",
              "gatel2captramp", "--only", "gatecave", "--gate-close")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "gate-close idempotent")
    cp3 = run(gc, os.path.join(OUTDIR, "v_gcback.bin"),
              "--only", "gatespptramp", "--only", "gatel2captramp",
              "--only", "gatecave")
    b3 = dec(os.path.join(OUTDIR, "v_gcback.bin")) if cp3.returncode == 0 else b""
    ck(cp3.returncode == 0 and b3[o1:o1 + 4] == bytes.fromhex("1004c0ff")
       and b3[o2:o2 + 4] == bytes.fromhex("1004bfea")
       and b3[o3:o3 + P.GATE_CAVE2_LEN] == b"\x00" * P.GATE_CAVE2_LEN,
       "gate-close reverts to stock")
    cp4 = run(SRC, os.path.join(OUTDIR, "v_gcbad.bin"), "--gate-close",
              "--no-spp-close")
    ck(cp4.returncode != 0, "--gate-close refuses --no-spp-close")
    cp5 = run(SRC, os.path.join(OUTDIR, "v_gcbad.bin"), "--gate-close",
              "--no-l2cap-disconnect")
    ck(cp5.returncode != 0, "--gate-close refuses --no-l2cap-disconnect")
    # sibling no-op states on an E10/E11 image must stay classified, not UNKNOWN
    cp = run(spc, "--show", "--gate-close")
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout,
       "--show on E10 image with gate flag clean")
    cp = run(ld, "--show", "--gate-close")
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout,
       "--show on E11 image with gate flag clean")
# F3 combo: full M3 recipe + conditional gate (the field-test image)
cf3 = os.path.join(OUTDIR, "v_f3.bin")
cp = run(SRC, cf3, "--no-kick", "--conn-num=2", "--force-page-scan",
         "--force-role-keep", "--no-disconnect-13", "--no-pairing-kick",
         "--no-cleanup-kick", "--no-l2cap-teardown", "--gate-close",
         "--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT")
ck(cp.returncode == 0, "F3 combo build (M3 recipe + --gate-close)")
if cp.returncode == 0:
    a = dec(cf3)
    ck(g(a, P.NOKICK_VA, 4) == b"\x40\x23\x80\x00"
       and g(a, P.CONN_NUM_VA, 2) == b"\x31\x25"
       and g(a, P.PAGESCAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.ROLEKEEP_VA, 10) == bytes.fromhex("c0ea4502000000000000")
       and g(a, P.DISC13_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ALL_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.PAIRKICK_ONE_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_VAR_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_ORPHAN_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.CLEANUPKICK_PROF_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.L2CAPTEARDOWN_UI_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.L2CAPTEARDOWN_MODE_VA, 4) == b"\x00\x00\x00\x00"
       and g(a, P.GATE_SPP_TRAMP_VA, 4) == P.GATE_SPP_TRAMP
       and g(a, P.GATE_L2CAP_TRAMP_VA, 4) == P.GATE_L2CAP_TRAMP
       and g(a, P.GATE_CAVE2_VA, P.GATE_CAVE2_LEN) == P.GATE_CAVE2_IMG,
       "F3 combo carries all M3 patches plus the gate trio")

# --- --cmd5-target (ch.30 R1-e, findings/30 SS30.14.11 + ch. 31) ------------
c5t = os.path.join(OUTDIR, "v_cmd5target.bin")
cp = run(SRC, c5t, "--only", "presstore", "--only", "presstcave",
         "--only", "cmd5target", "--only", "cmd5tcave", "--cmd5-target")
ck(cp.returncode == 0, "--cmd5-target build")
if cp.returncode == 0:
    a = dec(c5t)
    ck(g(a, P.CMD5T_HOOK_VA, 4) == P.CMD5T_HOOK
       and g(a, P.CMD5T_CAVE_VA, len(P.CMD5T_CAVE_BYTES)) == P.CMD5T_CAVE_BYTES
       and g(a, P.PRESST_HOOK_VA, 4) == P.PRESST_HOOK
       and g(a, P.PRESST_CAVE_VA, len(P.PRESST_CAVE_BYTES))
       == P.PRESST_CAVE_BYTES,
       "R1-e hooks + caves written")
    d = [i for i in range(len(stock)) if stock[i] != a[i]]
    wins = [(P.CMD5T_HOOK_VA, 4), (P.CMD5T_CAVE_VA, len(P.CMD5T_CAVE_BYTES)),
            (P.PRESST_HOOK_VA, 4), (P.PRESST_CAVE_VA,
                                    len(P.PRESST_CAVE_BYTES))]
    offs = [P.va_to_off(v) for v, _ in wins]
    ck(all(any(o <= i < o + n for o, n in zip(offs, [w for _, w in wins]))
           for i in d),
       "R1-e patch touches only its four windows (%d bytes)" % len(d))
    cp = run(c5t, "--show", "--cmd5-target")
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and "MIXED" not in cp.stdout,
       "--show on R1-e image clean")
    cp2 = run(c5t, c5t + ".2", "--only", "presstore", "--only", "presstcave",
              "--only", "cmd5target", "--only", "cmd5tcave", "--cmd5-target")
    ck(cp2.returncode == 0 and "Nothing to do" in cp2.stdout,
       "--cmd5-target idempotent")
    # R1-c image underneath must still be recognised (handle state)
    c5h_img = os.path.join(OUTDIR, "v_cmd5handle_then_show.bin")
    cph = run(SRC, c5h_img, "--cmd5-handle")
    cpv = run(c5h_img, "--show", "--cmd5-handle") if cph.returncode == 0 else cp
    ck(cph.returncode == 0 and cpv.returncode == 0
       and "UNKNOWN" not in cpv.stdout,
       "--cmd5-handle image still recognised")

# R1-e on the full F3-v3 recipe: coexistence + clean --show
c5tf = os.path.join(OUTDIR, "v_cmd5target_f3.bin")
cp = run(SRC, c5tf, "--PTT=BT-PTT", "--PTT2=BT-PTT2", "--OD-PTT=PTT",
         "--no-kick", "--conn-num=2", "--force-page-scan",
         "--force-role-keep", "--no-disconnect-13", "--no-pairing-kick",
         "--no-cleanup-kick", "--no-l2cap-teardown", "--gate-close",
         "--cmd5-target")
ck(cp.returncode == 0, "R1-e combo build (F3-v3 recipe + --cmd5-target)")
if cp.returncode == 0:
    a = dec(c5tf)
    ck(g(a, P.CMD5T_HOOK_VA, 4) == P.CMD5T_HOOK
       and g(a, P.CMD5T_CAVE_VA, len(P.CMD5T_CAVE_BYTES)) == P.CMD5T_CAVE_BYTES
       and g(a, P.PRESST_HOOK_VA, 4) == P.PRESST_HOOK
       and g(a, P.PRESST_CAVE_VA, len(P.PRESST_CAVE_BYTES))
       == P.PRESST_CAVE_BYTES
       and g(a, P.GATE_SPP_TRAMP_VA, 4) == P.GATE_SPP_TRAMP
       and g(a, 0x01E21EF4, 4) == bytes.fromhex("bfeace35"),
       "R1-e combo carries its four sites, gate armed, cmd-5 kill stock")
    cp = run(c5tf, "--show", "--PTT=BT-PTT", "--PTT2=BT-PTT2",
             "--OD-PTT=PTT", "--no-kick", "--conn-num=2",
             "--force-page-scan", "--force-role-keep", "--no-disconnect-13",
             "--no-pairing-kick", "--no-cleanup-kick", "--no-l2cap-teardown",
             "--gate-close", "--cmd5-target")
    ck(cp.returncode == 0 and "UNKNOWN" not in cp.stdout
       and "MIXED" not in cp.stdout,
       "--show on R1-e combo image clean")

# --- cleanup ----------------------------------------------------------------
if not fail and not KEEP:
    shutil.rmtree(OUTDIR)
    print("(generated images removed; --keep to inspect them)")
elif fail:
    print("generated images kept in %s" % OUTDIR)

print("\nFAILURES: %d" % len(fail))
for f in fail:
    print("  -", f)
sys.exit(1 if fail else 0)
