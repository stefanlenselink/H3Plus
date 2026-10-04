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
