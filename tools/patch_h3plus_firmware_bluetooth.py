"""
Patch the TIDRADIO H3 Plus firmware so that:

  A) ANY Bluetooth headset name is treated as a duplex speaker-mic, and
  B) the radio's PHYSICAL PTT button acts as a virtual "+SPP=P" / "+SPP=R".

Together these give the desired end state: connect any named headset, press
the radio's own PTT key, and transmit the microphone audio received over
Bluetooth.


WHY THESE TWO PATCHES
---------------------

Patch A - "duplex for any name"  (VA 0x01E7EC86, flash 0x083C86)

    The accessory classifier at 0x01E7EC28 classifies the peer and stores a
    routing mode at base+0xD4 (Findings.md 9A.28 / 9A.29 / 9A.34):

        mode 1  "TID-PTT"      TX from BT mic, RX to the radio's speaker
        mode 2  "TID-MIC"      TX from BT mic, RX to BT          <- duplex
        mode 4  "TID-MIC-EAR"  identical to mode 2 at the point of use
        mode 3  anything else  TX from the RADIO's mic, RX to BT
        mode 6  link class 0x80 (NOT name-matched; see below)

    Modes 5 and 6 are NOT reachable by name. They come from a separate
    branch taken before the name table is consulted at all:

        01E7EC36  r3 = b[gp + 0xB10]
        01E7EC40  r0 = r3 & ~0x3f         ; link/device class
        01E7EC4A  if (r0 != 0x80) goto <name matching>
        01E7EC4E  r0 = 0x5 ; b[r5+0xD4] = r0
        01E7EC54  r1 = 0x6 ; goto 01E7EC90 -> b[r5+0xD4] = r1

    Note the mode-5 store is immediately overwritten by the mode-6 store at
    the common tail, so mode 5 is almost certainly dead in practice.

    Modes 5/6 matter because they are the ONLY modes that reach the audio
    routing code. The routing-mode byte has exactly six readers, and the two
    that actually switch the audio path and emit "+SPP=R" are gated on 5/6:

        01E72C3C  if (mode - 5) > 1: skip   -> calls 0x01E50398 / 0x01E503CA
                                                (the audio-path GPIO setters)
        01E72DCC  if (mode - 1) < 4: skip   -> sends "+SPP=R" via 0x01E5B28E

    Modes 1-4 never touch either. That is why --bluetooth-mode=5/6 is worth
    testing: it is the only value that puts an ordinary named headset into
    the class whose code path drives the audio routing GPIOs.

    Mode 3 is the fall-through for unrecognised names:

        01E7EC82  r1 = 0x2                    ; "TID-MIC" matched
        01E7EC84  if (r0 == 0) goto 0x01E7EC90
        01E7EC86  r1 = 0x3                    ; <-- default, unrecognised
        01E7EC88  goto 0x01E7EC90

    Changing that single immediate makes the default something other than
    mode 3, so every unrecognised headset is treated as though its name had
    matched one of the table entries. This is smaller and safer than
    rewriting the string table, and it leaves the real "TID-PTT", "TID-MIC"
    and "TID-MIC-EAR" entries intact, so a genuine TIDRADIO PTT button keeps
    working exactly as before.

        41 23   ->   41 22   (--bluetooth-mode=2: same as "TID-MIC")
        41 23   ->   41 24   (--bluetooth-mode=4, default: same as "TID-MIC-EAR")
        41 23   ->   41 21   (--bluetooth-mode=1: same as "TID-PTT")
        41 23   ->   41 26   (--bluetooth-mode=6: the audio-routing class)

    The target mode is selectable with --bluetooth-mode (1-6, default 4).
    Modes 2 and 4 are known to behave identically at the point of use
    (Findings.md 9A.31); both are confirmed working on hardware. Modes 5 and
    6 are UNTESTED and are the current experiment - see above.


Patch B - "physical button -> virtual +SPP=P"  (VA 0x01E60A7E, flash 0x065A7E)

    *** THIS PATCH IS KNOWN-BAD. DO NOT USE IT. ***
    *** It is retained only so the site stays documented and so the tool
    *** can still RECOGNISE and report an already-patched image.

    Tested on hardware: it does not change mic routing. The front-panel PTT
    still transmits the radio's internal mic. Worse, it is unsafe - see
    below. If it has been flashed, restore the 0x065000 sector.

    The original rationale was that 0x01E60A7E sat in the front-panel key
    handler, so retargeting its call to the SPP ring enqueue would turn the
    button into a virtual "+SPP=P" / "+SPP=R":

        01E60A70  if (r0 == 0x80) goto 0x01E60A7C
        01E60A74  if (r0 != 0x20) goto 0x01E60A82
        01E60A78  r0 = 0x2A               ; press
        01E60A7A  goto 0x01E60A7E
        01E60A7C  r0 = 0x2B               ; release
        01E60A7E  call 0x01E4BAEA         ; <-- retargeted

    That rationale was WRONG on two counts (Findings.md 9A.34):

    1. This is not a key handler. The enclosing function starts at
       0x01E609FE and is a TEARDOWN routine - it withdraws a batch of key
       codes (0xE, 0xF, 0x10, 0x11) from the pressed-key set, then unlinks
       a list node, frees it and cancels timers. It has only two callers
       (0x01E60C4C, 0x01E7FD8C). The 0x2A / 0x2B here are being REMOVED
       during cleanup, not generated on a press. So the patch injected a
       ring event during connection teardown, which is why the button's
       behaviour never changed.

    2. The pressed-key set at 0xFF59 has NO READER anywhere in the image.
       Searching every 6-byte constant load of 0xFF59 finds exactly two
       sites - an add at 0x01E4A9DA and the remove at 0x01E4BACA. It is
       write-only bookkeeping and cannot be what keys the transmitter.

    It is also unsafe. The genuine SPP arm always calls 0x01E5B2B4
    (pop-front) BEFORE the enqueue at 0x01E52362. The enqueue only pushes:
    it increments b[gp+0x76] and writes b[gp+0x566+count]. Patch B pushes
    without popping, so every press/release leaks a ring slot and the writes
    can eventually walk past the ring into adjacent RAM.

    The 32-bit call encoding (tools/isa/pi32v2.md line 578, displacement
    rules per Findings.md 9A.26) is recomputed here rather than hardcoded:

        1110101010 Aaaaaa  Bbbbbbbbbbbbbbbb
        target = site + 4 + sign_extend_23((A:B) << 1)


KEY ACTIONS  (--PTT / --PTT2 / --OD-PTT, Findings.md 9A.41-9A.48)
-----------------------------------------------------------------

    Every PTT-like control of the radio can be assigned one of four actions.
    Option names and action values are matched case-insensitively, and
    BT-PTT / OD-PTT may also be spelled BTPTT / ODPTT / BT_PTT / OD_PTT.

      PTT      normal transmit: TX on the CURRENT VFO with the radio's own
               mic (what the main PTT key always does)
      PTT2     stock menu option: TX forced to VFO B
      BT-PTT   transmit the BLUETOOTH headset's mic (the virtual +SPP=P /
               +SPP=R command); the radio's own mic is used when no headset
               is linked
      OD-PTT   stock menu option: "OD PTT" one-key duplex

    --PTT=A      what the radio's MAIN PTT key does.
                 Default: BT-PTT.  [HARDWARE-CONFIRMED]
                 PTT = stock behaviour (no patch). A wired headset's PTT
                 also transmits the BT mic while BT is linked (same path).
    --PTT2=A     what the PF menu option "PTT2" (stored value 7) does, on
                 every PF key it is assigned to.  Default: PTT2 (stock).
    --OD-PTT=A   what the PF menu option "OD PTT" (stored value 8) does, on
                 every PF key it is assigned to.  Default: OD-PTT (stock).

    So the default build is exactly:

        --bluetooth-mode 4 --PTT=BT-PTT --PTT2=PTT2 --OD-PTT=OD-PTT

    and "--PTT=PTT", "--PTT2=PTT2", "--OD-PTT=OD-PTT" are each a no-op on
    their control.

    HOW THE ACTIONS ARE WIRED (Findings.md 9A.47 / 9A.50). Physical keys
    and "+SPP=P"/"+SPP=R" share one virtual key queue; only the standby
    handler for key code 0x2A (0x01E794A2) switches the mic mux to the BT
    codec (routing modes 1/2/4), so a BT-PTT action is a key that pushes
    0x2A on press and 0x2B on release (patches pttdown/pttup on the main
    PTT, the pfbody7/pfbody8/pfrelease patches in the PF executor).

    The two PF menu options are stored values 7 and 8. The press dispatch
    is a `tbb r0` at 0x01E75DDA over an 8-entry table at 0x01E75DDC (entry
    = byte offset / 2 from the table); entry 7 -> body A at 0x01E75E38
    (10 bytes, stock PTT2 code), entry 8 -> body B at 0x01E75E42 (8 bytes,
    stock OD PTT code). The release executor at 0x01E75E76 has no table:
    two `if (r0 == imm) goto` compares at 0x01E75E78 select the OD
    teardown body (0x01E75E82) or the TX-stop body (0x01E75E92).

    THE MODEL (since v1.0 of this tool, Findings.md 9A.50): each body is
    REWRITTEN in place to whatever action its option must perform - body A
    and body B can each do any of the four actions, and the 32-byte
    release-dispatch window is rewritten to send each value to the release
    code its action needs. The tbb table is never touched. This replaces
    the obsolete "swap" model (exchanging the two tbb entries), which could
    only produce 8 of the 16 pairs; images carrying that old swap are
    detected and refused.

    WHICH COMBINATIONS ARE POSSIBLE. Every ordered pair of DISTINCT
    actions - all 12 - works in either order. The six unordered combos:

      1. PTT     + PTT2
      2. PTT     + OD-PTT
      3. PTT     + BT-PTT
      4. PTT2    + OD-PTT     stock (no-op)
      5. PTT2    + BT-PTT
      6. OD-PTT  + BT-PTT

    ... each in both orientations, e.g. --PTT2=OD-PTT --OD-PTT=BT-PTT is
    served directly: option 7 runs the OD setup, option 8 the BT push, and
    the release dispatch is built to match. No rewiring by the user is
    needed or possible - just choose the action each option should have.

    The only refused pairs are the four where both options would run the
    SAME action (PTT/PTT, PTT2/PTT2, BT-PTT/BT-PTT, OD-PTT/OD-PTT): one
    code body performs one action, so choose which option to sacrifice.

      --PTT=PTT2 / --PTT=OD-PTT   still not possible: the main PTT key
              cannot run the PF-menu executor; only its stock action or
              the BT push exist.

    MENU LABELS. The menu shows the action: an option set to PTT is
    labelled "PTT", to BT-PTT "BT PTT", and stock options keep "PTT2" /
    "OD PTT". "PTT" is the tail of the "OD PTT" string, so that string is
    never modified and the Bluetooth menu's own "OD PTT" item keeps its
    name. "BT PTT" (6 chars + NUL) does not fit over the 5-byte "PTT2"
    string, so it overwrites 7 bytes starting at one of two places:

      0x01E8E30E  over "PTT2\0" + the first 2 bytes of Russian "NET"
                  (used when no option is still labelled "PTT2")
      0x01E8E313  over Russian "NET\0" exactly
                  (used when "PTT2" must stay readable)

    In both cases the three pointers to Russian "NET" move to the existing
    Russian "Net" string at 0x01E92010 (same word, different
    capitalisation). Labels are changed in all nine language lists.
    [UNTESTED]

    New menu entries cannot be ADDED, and other options (Weather, Alarm,
    ...) cannot be taken over as a PTT: only values 7/8 are hold keys in
    the scanner and have a release action, the settings validator resets
    values > 8 to 7, and the option arrays are packed back to back.

    An image already carrying a DIFFERENT action combination's labels is
    detected and refused, with a hint naming the combination. The legacy
    per-key scanner patches (pf1down/pf1up/pf2down/pf2up, which take over
    BOTH menu options on one key) are no longer offered as options; they
    remain available through --only for inspection, and combining them
    with the label patch is refused.


CAVEATS - read before flashing
------------------------------
  * Patch B is known-bad and unsafe; see above. It is excluded from the
    default patch set and must be requested explicitly with --only=ptt.
  * Repeated press/release transmitting only the FIRST time (Findings.md
    9A.22) was seen with a PC-emulated headset; it did not reproduce with
    a real headset (9A.44).
  * Modes 5 and 6 are untested. Mode 6 is the more likely of the two to do
    anything, since the mode-5 store is overwritten at the classifier's
    common tail.

Always keep the original .fw. Flashing is at your own risk.


USAGE
-----
    # inspect the current state of every site
    python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin --show

    # default: --bluetooth-mode 4 --PTT=BT-PTT
    # (any headset = duplex; main PTT = BT mic when linked, else radio mic)
    python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin

    # main PTT stays stock
    python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --PTT=PTT

    # menu option PTT2 becomes "PTT" (TX on current VFO), OD PTT kept
    python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --PTT2=PTT

    # menu option OD PTT becomes "BT PTT", PTT2 kept
    python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --OD-PTT=BT-PTT

    # both menu options replaced (the classic combo)
    python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin ^
        --PTT2=PTT --OD-PTT=BT-PTT

    # any other pair of distinct actions, in either order:
    python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin ^
        --PTT2=BT-PTT --OD-PTT=PTT      # BT mic on one, radio TX on the other
    python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin ^
        --PTT2=OD-PTT --OD-PTT=BT-PTT   # OD on the first, BT mic on the second

    # another bluetooth routing mode (see --help for the mode list)
    python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin -b 2

    # duplex patch only, no key patches at all
    python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --PTT=PTT --only=duplex

    # minimal in-place flashing: export just the 4 KiB sectors that change,
    # plus the jl-uboot-tool commands to write them
    python tools/patch_h3plus_firmware_bluetooth.py BIN/TD-H3-PlusV1.0.50.bin --sectors=work/sect

Option names and action values are case-insensitive (--ptt=bt-ptt works),
and BT-PTT / OD-PTT may be written BTPTT / ODPTT.


FLASHING GRANULARITY
--------------------
A raw flash .bin holds the app at container offset 0x5000, which equals its
flash address, so container offset == flash address throughout (proven in
Findings.md 12A.4: flash content is byte-identical to the distributed .bin).
That makes --sectors safe to use only on a .bin or a full dump, never on a
.fw, where the 0x200 container shift breaks the identity.

The default build (duplex + main PTT = BT-PTT) changes three bytes in two
4 KiB erase sectors (0x057000, 0x083000). Menu-option changes add sites in
0x07A000 (executor bodies / release dispatch), 0x093000 / 0x0C2000 (labels)
and 0x0C4000 (Russian pointers). --sectors lists exactly the sectors that
differ for the chosen pair.
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

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jl_sfcenc import sfc_enc_decrypt

# The app region is 0xC3FE0 bytes of SFC/ENC-scrambled code. Its *flash*
# address is 0x5000, but its offset inside a container varies: a raw flash
# dump holds it at 0x5000, while a .fw update file holds it at 0x5200. The
# offset is therefore detected, not assumed.
APP_LEN = 0xC3FE0
FLASH_BASE = 0x5000
CANDIDATE_STARTS = (0x5200, 0x5000)
CHIPKEY = 0xF181
LOAD_BASE = 0x01E00000
LINE = 32

CALL_OPC = 0b1110101010

SECTOR = 0x1000  # SPI NOR erase granularity


# --------------------------------------------------------------------------
# address helpers.  app offset 0 == flash 0x5000 == VA 0x01E00000
# --------------------------------------------------------------------------
def va_to_off(va):
    return va - LOAD_BASE


def off_to_flash(off):
    return off + FLASH_BASE


def encode_call(site_va, target_va):
    """Encode the 32-bit `call target` that lives at `site_va`."""
    disp = target_va - (site_va + 4)
    if disp & 1:
        raise ValueError("odd call displacement")
    v = disp >> 1
    if not (-(1 << 21) <= v < (1 << 21)):
        raise ValueError("call displacement out of range")
    v &= (1 << 22) - 1
    w0 = (CALL_OPC << 6) | (v >> 16)
    w1 = v & 0xFFFF
    return bytes([w0 & 0xFF, w0 >> 8, w1 & 0xFF, w1 >> 8])


def decode_call(site_va, blob):
    """Inverse of encode_call; returns the target VA or None."""
    w0 = blob[0] | (blob[1] << 8)
    if (w0 >> 6) != CALL_OPC:
        return None
    w1 = blob[2] | (blob[3] << 8)
    v = (((w0 & 0x3F) << 16) | w1) << 1
    if v >> 22:
        v -= 1 << 23
    return (site_va + 4 + v) & 0xFFFFFFFF


def encode_goto2(site_va, target_va):
    """Encode the 2-byte forward `goto` (target = site + 2 + 2*d).

    Empirical layout w = 0x8004 | (d << 8), valid for 0 <= d <= 0xF;
    verified against four stock encodings (0x01E75E3E/40/42/44).
    """
    d = (target_va - site_va - 2) // 2
    if not 0 <= d <= 0xF:
        raise ValueError("2-byte goto displacement out of range: %d" % d)
    w = 0x8004 | (d << 8)
    return bytes([w & 0xFF, w >> 8])


def encode_cmp_eq_imm(site_va, imm, target_va):
    """Encode `if (r0 == imm) goto target` (4 bytes, `00 f8 lo hi`),
    target = site + 4 + 2*d. Verified against the two stock release
    compares at 0x01E75E78 / 0x01E75E7C."""
    d = (target_va - site_va - 4) // 2
    if not 0 < d <= 0xFF:
        raise ValueError("compare displacement out of range: %d" % d)
    w1 = (imm << 9) | d
    return bytes([0x00, 0xF8, w1 & 0xFF, w1 >> 8])


# --------------------------------------------------------------------------
# patch definitions
#
# Each patch site has a set of KNOWN STATES: every byte pattern the tool is
# prepared to find there, whether that is the untouched factory bytes or a
# value this tool itself can write. `ctx_base` is a longer signature checked
# around the site - one variant is built per known state - so the tool
# refuses to run against a firmware version it does not recognise, instead
# of silently corrupting an unrelated instruction.
# --------------------------------------------------------------------------
DUPLEX_VA = 0x01E7EC86
DUPLEX_CTX_VA = 0x01E7EC82
DUPLEX_CTX_BASE = bytes.fromhex("4122 0045 4123 0483 4121 0481 4124".replace(" ", ""))

# Every value the routing-mode byte at base+0xD4 is known to take. Modes 1-4
# come from the name table; modes 5/6 come from the link-class branch taken
# before it (Findings.md 9A.28 / 9A.29 / 9A.31 / 9A.34).
DUPLEX_LABELS = {
    1: 'mode 1 ("TID-PTT": BT mic -> TX, radio\'s own speaker <- RX)',
    2: 'mode 2 ("TID-MIC": BT mic -> TX, BT <- RX)  [duplex, hardware-confirmed]',
    3: "mode 3 (factory default for unrecognised names: radio's own mic -> TX, BT <- RX)",
    4: 'mode 4 ("TID-MIC-EAR": identical to mode 2 at the point of use)  [hardware-confirmed]',
    5: "mode 5 (link-class branch; store is overwritten by mode 6 at the classifier tail)  [UNTESTED; excluded from the 0x2A mic-mux mask 0x16]",
    6: "mode 6 (link class 0x80)  [TESTED: no BT mic on PTT; excluded from the 0x2A mic-mux mask 0x16]",
}


def encode_mode_imm(m):
    """Encode the `r1 = m` immediate-load instruction used for each of the
    classifier's four routing-mode literals (m must fit in a nibble)."""
    if not 0 <= m <= 15:
        raise ValueError("mode immediate out of range: %d" % m)
    return bytes([0x41, 0x20 | m])


DUPLEX_STATES = {m: encode_mode_imm(m) for m in DUPLEX_LABELS}

# Patches applied when --only is not given. 'ptt' is deliberately excluded:
# it is known-bad and unsafe (see the module docstring), so it must be asked
# for explicitly.
DEFAULT_PATCHES = ["duplex"]

KEY_EVENT_CALL_VA = 0x01E60A7E
PTT_CTX_VA = 0x01E60A74
SET_REMOVE_VA = 0x01E4BAEA  # original: pressed-key set remove
RING_ENQUEUE_VA = 0x01E52362  # replacement: SPP message ring enqueue

PTT_STATES = {
    "native": encode_call(KEY_EVENT_CALL_VA, SET_REMOVE_VA),
    "virtual-spp": encode_call(KEY_EVENT_CALL_VA, RING_ENQUEUE_VA),
}
PTT_LABELS = {
    "native": "native teardown call (call 0x%08X, pressed-key set remove)" % SET_REMOVE_VA,
    "virtual-spp": "KNOWN-BAD redirect to ring enqueue (call 0x%08X)" % RING_ENQUEUE_VA,
}
PTT_CTX_BASE = bytes.fromhex("80f80540 482a 0481 482b".replace(" ", "")) + PTT_STATES["native"]


# Key scanner 0x01E5237E pushes virtual key codes into the queue at
# 0x102F0+0x566 via 0x01E52362; +SPP=P / +SPP=R push 0x2A / 0x2B into the
# same queue (0x01E5B37A). Only the standby handler for 0x2A (0x01E794A2)
# switches the mic mux GPIOs to the BT codec (routing modes 1/2/4), so
# making a key push 0x2A/0x2B makes it identical to the SPP commands
# (Findings.md 9A.40). Each entry swaps one `r0 = imm` literal (`48 xx`).
#
#   name: (site VA, ctx VA, ctx hex, native code, spp code, description)
KEYCODE_PATCHES = {
    # main PTT (ADC key A, state 0x102D6)
    "pttdown": (0x01E52400, 0x01E523FE, "518b 4828 518f", 0x28, 0x2A,
                "main PTT press"),
    "pttup": (0x01E524BE, 0x01E524BA, "d8eeb140 4829 bfea4fff", 0x29, 0x2B,
              "main PTT release"),
    # PF1 (ADC key B, state 0x102DC, setting +0x1058). These literals are
    # only reached when PF1 S Press = PTT2 (7) or OD PTT (8).
    "pf1down": (0x01E5253C, 0x01E52538, "b0ec4f40 482c bfea10ff", 0x2C, 0x2A,
                "PF1 press (PF1 S Press = PTT2/OD PTT only)"),
    "pf1up": (0x01E52578, 0x01E52572, "50eeb602 8050 482d 0493", 0x2D, 0x2B,
              "PF1 release (PF1 S Press = PTT2/OD PTT only)"),
    # PF2 (ADC key C, state 0x102DE, setting +0x105A), same structure.
    "pf2down": (0x01E52678, 0x01E52674, "b0ec4f40 4830 bfea72fe", 0x30, 0x2A,
                "PF2 press (PF2 S Press = PTT2/OD PTT only)"),
    "pf2up": (0x01E526AE, 0x01E526A8, "50eeba02 8044 4831 bfea57fe", 0x31, 0x2B,
              "PF2 release (PF2 S Press = PTT2/OD PTT only)"),
}


# --------------------------------------------------------------------------
# PF S Press executor: direct body rewrite model (Findings.md 9A.50)
#
# The two PF menu options are stored values 7 ("PTT2") and 8 ("OD PTT").
# The press dispatch is a `tbb r0` at 0x01E75DDA over an 8-entry table at
# 0x01E75DDC; entry 7 -> body A at 0x01E75E38 (10 bytes), entry 8 -> body B
# at 0x01E75E42 (8 bytes). The release executor at 0x01E75E76 has no table:
# two `if (r0 == imm) goto` compares at 0x01E75E78 / 0x01E75E7C select a
# body at 0x01E75E82 (OD teardown) or 0x01E75E92 (TX stop).
#
# Instead of the old tbb-swap trick, each body is REWRITTEN directly to the
# action it must perform, so every ordered pair of distinct actions is
# reachable and the tbb table is never touched:
#
#   body A (10 B) can do PTT2 / PTT / BT-PTT / OD-PTT
#   body B (8 B)  can do OD-PTT / BT-PTT / PTT / PTT2
#
# Shared tails (never patched): 0x01E75E50 current-VFO (`r0 = b[r4+0x77]>>7`),
# 0x01E75E56 TX start (`b[r4+0x46] = r0 ...`), 0x01E75E4A OD tail
# (`b[r5+0xEA]` test), 0x01E75E74 plain return `5504`.
#
# The release dispatch is rewritten as a whole 32-byte window (0x01E75E78):
# the two compares are re-encoded to the body each value needs. A BT-PTT
# release body (8 B, `r0 = 0x2B; call push; ret`) replaces the OD body at
# 0x01E75E82 when that slot is free. The one tight case is the {OD-PTT,
# BT-PTT} combo: both an OD release and a BT release must coexist, so the
# OD release shrinks to `call teardown; call TXstop; ret` (10 B at
# 0x01E75E82) and the BT release goes to 0x01E75E8C. Dropping the native
# `b[r5+0xEA]` test is safe because TXstop (0x01E5A138) self-guards on
# b[0x102F0+0x24C] - it returns immediately when no TX is pending.
# [UNTESTED on hardware]
#
# None of the release sub-addresses (E80/E82/E8C/E92/E96) is referenced
# from anywhere else in the image (checked 32-bit and /2 forms), and the
# release executor has a single caller (0x01E79658), so the window is free
# to restructure.
OD_SETUP_VA    = 0x01E72C38  # OD PTT press: one-key-duplex setup
OD_REFRESH_VA  = 0x01E56D3C  # OD PTT press: refresh
OD_TEARDOWN_VA = 0x01E72DC4  # OD PTT release: teardown
TXSTOP_VA      = 0x01E5A138  # TX stop (self-guards on b[+0x24C])
PF_BODY7_VA    = 0x01E75E38  # press body of stored value 7 (10 bytes)
PF_BODY8_VA    = 0x01E75E42  # press body of stored value 8 (8 bytes)
OD_TAIL_VA     = 0x01E75E4A
TAIL_VFO_VA    = 0x01E75E50  # r0 = current VFO
TAIL_B_VA      = 0x01E75E56  # b[+0x46] = r0 ; TX start
PF_REL_VA      = 0x01E75E78  # release dispatch window (32 bytes)
PF_REL_LEN     = 32
REL_OD_BODY_VA = 0x01E75E82  # native OD-release body / free BT slot
REL_TX_BODY_VA = 0x01E75E92  # native TX-stop release body
REL_BT_ALT_VA  = 0x01E75E8C  # BT release body slot in the {OD,BT} combo

PF_BODY7_NATIVE = bytes.fromhex("50ee4602 805b 4021 048a".replace(" ", ""))
PF_BODY8_NATIVE = bytes.fromhex("bfeaf9e6 bfea7907".replace(" ", ""))
PF_REL_NATIVE = bytes.fromhex(
    "00f80310 00f8090e 0004"
    "bfea9fe7 c0ff90b3 0000 50ee0a0e 0042"
    "bfea5121 0004".replace(" ", ""))
assert len(PF_REL_NATIVE) == PF_REL_LEN

# action -> release behaviour class
_PF_BEHAV = {"PTT": "TX", "PTT2": "TX", "OD-PTT": "OD", "BT-PTT": "BT"}

# key-queue push (same target the +SPP=P / +SPP=R handlers use)
PUSH_KEY_VA = 0x01E52362


def _pf_body7(action):
    """10-byte press body for stored value 7 running `action`."""
    if action == "PTT2":
        return PF_BODY7_NATIVE
    if action == "PTT":
        # keep the b[+0x26] guard, enter the current-VFO tail instead of r0=1
        return (PF_BODY7_NATIVE[:6]
                + encode_goto2(PF_BODY7_VA + 6, TAIL_VFO_VA)
                + bytes.fromhex("048a"))
    if action == "BT-PTT":
        return (bytes([0x48, 0x2A])
                + encode_call(PF_BODY7_VA + 2, PUSH_KEY_VA)
                + bytes.fromhex("5504 048a"))
    if action == "OD-PTT":
        return (encode_call(PF_BODY7_VA, OD_SETUP_VA)
                + encode_call(PF_BODY7_VA + 4, OD_REFRESH_VA)
                + encode_goto2(PF_BODY7_VA + 8, OD_TAIL_VA))
    raise ValueError(action)


def _pf_body8(action):
    """8-byte press body for stored value 8 running `action`."""
    if action == "OD-PTT":
        return PF_BODY8_NATIVE
    if action == "BT-PTT":
        return (bytes([0x48, 0x2A])
                + encode_call(PF_BODY8_VA + 2, PUSH_KEY_VA)
                + bytes.fromhex("5504"))
    if action == "PTT":
        # four redundant gotos into the current-VFO tail (only the first runs)
        return b"".join(encode_goto2(PF_BODY8_VA + 2 * i, TAIL_VFO_VA)
                        for i in range(4))
    if action == "PTT2":
        return (bytes([0x40, 0x21])
                + encode_goto2(PF_BODY8_VA + 2, TAIL_B_VA)
                + bytes.fromhex("0004 0004"))
    raise ValueError(action)


def _pf_bt_release(site_va):
    """8-byte release body pushing 0x2B (+SPP=R) and returning."""
    return (bytes([0x48, 0x2B])
            + encode_call(site_va + 2, PUSH_KEY_VA)
            + bytes.fromhex("0004"))


def _pf_release(a7, a8):
    """32-byte release dispatch for the (value 7, value 8) action pair.

    The native compare ORDER is kept (imm 8 first at 0x01E75E78, imm 7
    second at 0x01E75E7C) and only the targets are re-encoded, so every
    pair whose targets are the native ones keeps the window byte-identical
    to the factory bytes.
    """
    b7, b8 = _PF_BEHAV[a7], _PF_BEHAV[a8]
    out = bytearray(PF_REL_NATIVE)

    def put(off, data):
        out[off:off + len(data)] = data

    if {b7, b8} == {"OD", "BT"}:
        # tight combo: OD release = teardown + unconditional TXstop (10 B),
        # BT release at the slot freed after it.
        put(0x0A, encode_call(REL_OD_BODY_VA, OD_TEARDOWN_VA)
            + encode_call(REL_OD_BODY_VA + 4, TXSTOP_VA)
            + bytes.fromhex("0004"))
        put(0x14, _pf_bt_release(REL_BT_ALT_VA))
        t7 = REL_OD_BODY_VA if b7 == "OD" else REL_BT_ALT_VA
        t8 = REL_OD_BODY_VA if b8 == "OD" else REL_BT_ALT_VA
    else:
        if "BT" in (b7, b8):
            put(0x0A, _pf_bt_release(REL_OD_BODY_VA))
        tgt = {"TX": REL_TX_BODY_VA, "OD": REL_OD_BODY_VA,
               "BT": REL_OD_BODY_VA}
        t7, t8 = tgt[b7], tgt[b8]
    put(0x00, encode_cmp_eq_imm(PF_REL_VA, 8, t8))
    put(0x04, encode_cmp_eq_imm(PF_REL_VA + 4, 7, t7))
    return bytes(out)


# Release-dispatch images produced by the OBSOLETE pre-1.0 model
# (tbb-swap + odpttup), kept so already-flashed images stay recognised.
_PF_REL_LEGACY = {
    "legacy odpttup": (PF_REL_NATIVE[:0x0A]
                       + _pf_bt_release(REL_OD_BODY_VA)
                       + PF_REL_NATIVE[0x12:]),
    "legacy swap": (bytes.fromhex("00f8030e 00f80910".replace(" ", ""))
                    + PF_REL_NATIVE[8:]),
    "legacy swap+odpttup": (bytes.fromhex("00f8030e 00f80910".replace(" ", ""))
                            + PF_REL_NATIVE[8:0x0A]
                            + _pf_bt_release(REL_OD_BODY_VA)
                            + PF_REL_NATIVE[0x12:]),
}

# tbb table entries of values 7/8 (offset /2 from the table). The new model
# never touches them; an image whose table IS swapped comes from the old
# model and must not be re-patched by this one.
PF_TBB_78_VA = 0x01E75DE2
PF_TBB_78_NATIVE = bytes.fromhex("2e33")
PF_TBB_78_SWAPPED = bytes.fromhex("332e")

# Kept for tools/verify_actions.py: the native body addresses.
ODPTT_PRESS_VA = PF_BODY8_VA
ODPTT_RELEASE_VA = REL_OD_BODY_VA

# --------------------------------------------------------------------------
# key actions (--PTT / --PTT2 / --OD-PTT, see the module docstring)
#
# Actions are matched case-insensitively; BT-PTT / OD-PTT also accept the
# spellings BTPTT / ODPTT / BT_PTT / OD_PTT and "BT PTT" / "OD PTT".
# --------------------------------------------------------------------------
ACTIONS = ("PTT", "PTT2", "BT-PTT", "OD-PTT")
_ACTION_ALIASES = {
    "PTT": "PTT", "PTT2": "PTT2",
    "BT-PTT": "BT-PTT", "BTPTT": "BT-PTT", "BT_PTT": "BT-PTT",
    "OD-PTT": "OD-PTT", "ODPTT": "OD-PTT", "OD_PTT": "OD-PTT",
}


def normalize_action(value, opt):
    key = value.strip().upper().replace(" ", "-").replace("_", "-")
    action = _ACTION_ALIASES.get(key)
    if action is None:
        raise SystemExit(
            "%s: unknown action %r. Choose from: %s"
            % (opt, value, ", ".join(ACTIONS))
        )
    return action


# Default configuration when the option is not given (see main() and --help).
DEFAULT_ACTIONS = {"PTT": "BT-PTT", "PTT2": "PTT2", "OD-PTT": "OD-PTT"}

# --PTT: the main PTT key. It has its own scanner literals (pttdown/pttup);
# the PF-menu executor is not reachable from it, so only these two actions
# exist. "PTT" (its stock behaviour) needs no patch.
PTT_KEY_PATCHES = {
    "PTT": [],
    "BT-PTT": ["pttdown", "pttup"],
}

# (--PTT2, --OD-PTT) -> the executor patches implementing that pair.
# Every ordered pair of DISTINCT actions is reachable: body A (value 7) and
# body B (value 8) are each rewritten to the action their option must
# perform, and the release dispatch is rewritten to match. The stock pair
# needs no patch at all. Same-action pairs are refused (one body, one
# action); the user picks which option to sacrifice.
def _combo_names(a7, a8):
    names = []
    if a7 != "PTT2":
        names.append("pfbody7")
    if a8 != "OD-PTT":
        names.append("pfbody8")
    if (a7, a8) != ("PTT2", "OD-PTT"):
        names.append("pfrelease")
    return names


PF_COMBO_PATCHES = {
    (a7, a8): _combo_names(a7, a8)
    for a7 in ACTIONS
    for a8 in ACTIONS
    if a7 != a8
}


def validate_pf_combo(a7, a8):
    """Refuse same-action pairs with an explanation of what is possible."""
    if (a7, a8) in PF_COMBO_PATCHES:
        return
    if a7 == a8:
        raise SystemExit(
            "--PTT2=%s --OD-PTT=%s is not possible: the two menu options\n"
            "cannot run the same action - each option is one code body and\n"
            "one release path. Pick a different action for one of them;\n"
            "every pair of distinct actions works, e.g.:\n%s"
            % (
                a7, a8,
                "\n".join(
                    "  --PTT2=%-7s --OD-PTT=%-7s%s"
                    % (c[0], c[1], "  (stock)" if c == ("PTT2", "OD-PTT") else "")
                    for c in sorted(PF_COMBO_PATCHES)
                ),
            )
        )
    raise SystemExit("internal error: unknown pair %r" % ((a7, a8),))


def pf_combo_patches(a7, a8):
    """Patch names for a validated (--PTT2, --OD-PTT) pair, including the
    label patch when the pair changes any menu label."""
    names = list(PF_COMBO_PATCHES[(a7, a8)])
    if _label_sites(a7, a8)[0]:
        names.append("pflabels")
    return names


# PF S Press option labels (Findings.md 9A.47). Nine language lists of eight
# string pointers; entry 6 = PTT2 (value 7), entry 7 = OD PTT (value 8).
PF_LIST_PTT2_PTRS = (0x01EBD740, 0x01EBD760, 0x01EBF0A4, 0x01EBF0C4, 0x01EBF0E4,
                     0x01EBF104, 0x01EBF124, 0x01EBF144, 0x01EBF164)
STR_PTT2_VA = 0x01E8E30E       # "PTT2\0", referenced only by the lists above
STR_OD_PTT_VA = 0x01E8CE54     # "OD PTT\0", shared with the Bluetooth menu
STR_PTT_VA = STR_OD_PTT_VA + 3  # "PTT\0" = tail of "OD PTT"
STR_RU_NONE_VA = 0x01E8E313    # Russian "NET\0", directly after "PTT2\0"
STR_RU_NO_VA = 0x01E92010      # Russian "Net\0"
RU_NONE_PTRS = (0x01EBF0AC, 0x01EBF188, 0x01EBF400)


def _ptr(va):
    return va.to_bytes(4, "little")


# Multi-site patches: every site is (VA, native bytes, new bytes); guards are
# (VA, bytes) that must already hold, e.g. the strings new pointers target.
# The only multi-patch is "pflabels", built per (--PTT2, --OD-PTT) action
# pair by build_patches() from _label_sites() below.
#
# "BT PTT" (6 chars + NUL = 7 bytes) does not fit over the 5-byte "PTT2"
# string, so it always overwrites 7 bytes starting at one of two places:
#
#   0x01E8E30E over "PTT2\0" + the first 2 bytes of Russian "NET"
#     (when no menu entry still needs to read "PTT2")
#   0x01E8E313 over Russian "NET\0" exactly, 7 bytes
#     (when an entry still reads "PTT2" - stock value 7, or --OD-PTT=PTT2)
#
# In both cases the three pointers to Russian "NET" move to the existing
# Russian "Net" string at 0x01E92010, which means exactly the same thing.
# The nine PF S Press lists hold entry 6 = value 7 (native "PTT2") and
# entry 7 = value 8 (native "OD PTT"); "PTT" is the tail of "OD PTT" at
# 0x01E8CE57, so that string is never modified and the Bluetooth menu's own
# "OD PTT" item keeps its name.
_RU_NET = "\u041d\u0415\u0422\0".encode()      # Russian "NET" (uppercase)
_RU_NET_AT = STR_PTT2_VA + 5                   # 0x01E8E313, right after PTT2
_BT_PTT_AT_PTT2 = STR_PTT2_VA                   # "BT PTT\0" over "PTT2"+NET[0:2]
_BT_PTT_AT_NET = _RU_NET_AT                     # "BT PTT\0" over "NET\0"


def _label_sites(a7, a8):
    """(sites, guards) for the PF S Press label patch of one action pair.

    a7 = action of stored value 7 (the stock "PTT2" option, list entry 6),
    a8 = action of stored value 8 (the stock "OD PTT" option, list entry 7).
    Each entry is repointed to the label of its action; entries that keep
    their stock action keep their stock pointer.
    """
    label_va = {"PTT": STR_PTT_VA, "PTT2": STR_PTT2_VA, "OD-PTT": STR_OD_PTT_VA}
    bt_needed = "BT-PTT" in (a7, a8)
    # "PTT2" must stay readable whenever an entry still points at it
    keep_ptt2 = "PTT2" in (a7, a8)
    bt_at = _BT_PTT_AT_NET if (bt_needed and keep_ptt2) else _BT_PTT_AT_PTT2
    label_va["BT-PTT"] = bt_at

    sites = []
    if bt_needed:
        if bt_at == _BT_PTT_AT_NET:
            sites.append((_BT_PTT_AT_NET, _RU_NET, b"BT PTT\0"))
        else:
            sites.append((_BT_PTT_AT_PTT2, b"PTT2\0" + _RU_NET[:2], b"BT PTT\0"))
    if a7 != "PTT2":
        sites += [(p, _ptr(STR_PTT2_VA), _ptr(label_va[a7]))
                  for p in PF_LIST_PTT2_PTRS]
    if a8 != "OD-PTT":
        sites += [(p + 4, _ptr(STR_OD_PTT_VA), _ptr(label_va[a8]))
                  for p in PF_LIST_PTT2_PTRS]
    if bt_needed:
        # the Russian "NET" bytes are gone either way; point at "Net"
        sites += [(p, _ptr(STR_RU_NONE_VA), _ptr(STR_RU_NO_VA))
                  for p in RU_NONE_PTRS]
    # a pointer that already holds its target value is a no-op site: with
    # --PTT2=BT-PTT written over "PTT2" itself, entry 7 keeps its native
    # pointer and must not be listed (it would read "already applied" and
    # make --show think the image is partly patched)
    sites = [s for s in sites if s[1] != s[2]]
    guards = []
    if "PTT" in (a7, a8) or a7 == "OD-PTT":
        guards.append((STR_OD_PTT_VA, b"OD PTT\0"))
    if bt_needed:
        guards.append((STR_RU_NO_VA, "\u041d\u0435\u0442\0".encode()))
    return sites, guards


def _combo_desc(a7, a8):
    if (a7, a8) == ("PTT2", "OD-PTT"):
        return 'menu options keep their stock labels "PTT2" / "OD PTT"'
    return 'PF S Press labels: value 7 -> "%s", value 8 -> "%s" (all languages)' % (
        _MENU_LABEL[a7], _MENU_LABEL[a8])


_MENU_LABEL = {"PTT": "PTT", "PTT2": "PTT2", "BT-PTT": "BT PTT", "OD-PTT": "OD PTT"}

# All reachable non-stock (--PTT2, --OD-PTT) label layouts, precomputed.
# build_patches() installs the selected one as the "pflabels" patch and
# attaches the others as detection-only alternatives (PF_LABEL_VARIANTS),
# so --show and app-offset detection still recognise an image patched with
# a DIFFERENT combination while apply_multi refuses to mix them. The stock
# pair has no label sites and is not a variant.
PF_LABEL_VARIANTS = {c: _label_sites(*c) for c in PF_COMBO_PATCHES
                     if c != ("PTT2", "OD-PTT")}
PF_LITERAL_PATCHES = {"pf1down", "pf1up", "pf2down", "pf2up"}


def _ctx_variant_fn(va, ctx_va, ctx_base):
    """Build a function that substitutes a candidate state's bytes into the
    fixed context window, at the offset where the patch site sits inside it."""
    site_off = va_to_off(va) - va_to_off(ctx_va)

    def variant(state_bytes):
        return ctx_base[:site_off] + state_bytes + ctx_base[site_off + len(state_bytes) :]

    return variant


def build_patches(duplex_mode=4, ptt2_action="PTT2", odptt_action="OD-PTT"):
    """Return the patch table, with the `duplex` patch's target selected by
    `duplex_mode` (see DUPLEX_LABELS) and the `pflabels` multi-patch built
    for the (--PTT2, --OD-PTT) action pair (see PF_COMBO_PATCHES). The
    other label variants stay in PF_LABEL_VARIANTS, detection-only, so an
    image patched with a different combination is still recognised. The
    stock pair has no label patch at all."""
    if duplex_mode not in DUPLEX_STATES:
        raise SystemExit("--bluetooth-mode must be one of %s" % sorted(DUPLEX_STATES))
    validate_pf_combo(ptt2_action, odptt_action)
    patches = {
        "duplex": {
            "desc": "unrecognised headset name -> %s" % DUPLEX_LABELS[duplex_mode],
            "va": DUPLEX_VA,
            "new": DUPLEX_STATES[duplex_mode],
            "states": DUPLEX_STATES,
            "labels": DUPLEX_LABELS,
            "target": duplex_mode,
            "ctx_va": DUPLEX_CTX_VA,
            "ctx_base": DUPLEX_CTX_BASE,
            "ctx_variant": _ctx_variant_fn(DUPLEX_VA, DUPLEX_CTX_VA, DUPLEX_CTX_BASE),
        },
        "ptt": {
            "desc": "KNOWN-BAD: front-panel PTT key -> ring enqueue (no effect, leaks ring slots)",
            "va": KEY_EVENT_CALL_VA,
            "new": PTT_STATES["virtual-spp"],
            "states": PTT_STATES,
            "labels": PTT_LABELS,
            "target": "virtual-spp",
            "ctx_va": PTT_CTX_VA,
            "ctx_base": PTT_CTX_BASE,
            "ctx_variant": _ctx_variant_fn(KEY_EVENT_CALL_VA, PTT_CTX_VA, PTT_CTX_BASE),
        },
    }
    for name, (va, ctx_va, ctx_hex, native, spp, what) in KEYCODE_PATCHES.items():
        states = {"native": bytes([0x48, native]), "spp": bytes([0x48, spp])}
        ctx_base = bytes.fromhex(ctx_hex.replace(" ", ""))
        patches[name] = {
            "desc": "%s pushes key 0x%02X (same as +SPP=%s) instead of 0x%02X"
            % (what, spp, "P" if spp == 0x2A else "R", native),
            "va": va,
            "new": states["spp"],
            "states": states,
            "labels": {
                "native": "r0 = 0x%02X (native %s)" % (native, what),
                "spp": "r0 = 0x%02X (+SPP=%s)" % (spp, "P" if spp == 0x2A else "R"),
            },
            "target": "spp",
            "ctx_va": ctx_va,
            "ctx_base": ctx_base,
            "ctx_variant": _ctx_variant_fn(va, ctx_va, ctx_base),
        }
    # PF S Press executor bodies + release dispatch (direct-rewrite model).
    # Installed for every build so --show and app-offset detection recognise
    # any combination; only the ones named by pf_combo_patches() are applied.
    b7_states = {a: _pf_body7(a) for a in ACTIONS}
    patches["pfbody7"] = {
        "desc": 'PF menu option "PTT2" (stored value 7) press body -> %s'
                % ptt2_action,
        "va": PF_BODY7_VA,
        "new": _pf_body7(ptt2_action),
        "states": b7_states,
        "labels": {a: 'value 7 press body runs "%s"' % a for a in ACTIONS},
        "target": ptt2_action,
        "ctx_va": PF_BODY7_VA,
        "ctx_base": PF_BODY7_NATIVE,
        "ctx_variant": _ctx_variant_fn(PF_BODY7_VA, PF_BODY7_VA, PF_BODY7_NATIVE),
    }
    b8_states = {a: _pf_body8(a) for a in ACTIONS}
    patches["pfbody8"] = {
        "desc": 'PF menu option "OD PTT" (stored value 8) press body -> %s'
                % odptt_action,
        "va": PF_BODY8_VA,
        "new": _pf_body8(odptt_action),
        "states": b8_states,
        "labels": {a: 'value 8 press body runs "%s"' % a for a in ACTIONS},
        "target": odptt_action,
        "ctx_va": PF_BODY8_VA,
        "ctx_base": PF_BODY8_NATIVE,
        "ctx_variant": _ctx_variant_fn(PF_BODY8_VA, PF_BODY8_VA, PF_BODY8_NATIVE),
    }
    rel_states, rel_labels = {}, {}
    for c in PF_COMBO_PATCHES:
        rel_states[c] = _pf_release(*c)
        rel_labels[c] = "release dispatch for --PTT2=%s --OD-PTT=%s%s" % (
            c[0], c[1], "  (stock)" if c == ("PTT2", "OD-PTT") else "")
    for key, img in _PF_REL_LEGACY.items():
        rel_states[key] = img
        rel_labels[key] = "%s  [obsolete pre-1.0 model]" % key
    patches["pfrelease"] = {
        "desc": "PF release dispatch -> --PTT2=%s --OD-PTT=%s"
                % (ptt2_action, odptt_action),
        "va": PF_REL_VA,
        "new": _pf_release(ptt2_action, odptt_action),
        "states": rel_states,
        "labels": rel_labels,
        "target": (ptt2_action, odptt_action),
        "ctx_va": PF_REL_VA,
        "ctx_base": PF_REL_NATIVE,
        "ctx_variant": _ctx_variant_fn(PF_REL_VA, PF_REL_VA, PF_REL_NATIVE),
    }
    # The tbb table entries of values 7/8. Never written by this model; a
    # swapped table means the image came from the obsolete swap model, which
    # check_pf_table() refuses to re-patch (the bodies would be mislabelled).
    patches["pftable"] = {
        "desc": "PF press tbb table entries for values 7/8 (must stay native)",
        "va": PF_TBB_78_VA,
        "new": PF_TBB_78_NATIVE,
        "states": {"native": PF_TBB_78_NATIVE, "swapped": PF_TBB_78_SWAPPED},
        "labels": {
            "native": "native (value 7 -> body A, value 8 -> body B)",
            "swapped": "swapped by the obsolete model (re-flash a stock image first)",
        },
        "target": "native",
        "ctx_va": 0x01E75DDA,
        "ctx_base": bytes.fromhex("0001 0415 4c19 2125 2e33".replace(" ", "")),
        "ctx_variant": _ctx_variant_fn(PF_TBB_78_VA, 0x01E75DDA,
                                       bytes.fromhex("0001 0415 4c19 2125 2e33".replace(" ", ""))),
    }
    sites, guards = (PF_LABEL_VARIANTS[(ptt2_action, odptt_action)]
                     if (ptt2_action, odptt_action) != ("PTT2", "OD-PTT")
                     else ([], []))
    patches["pflabels"] = {
        "desc": _combo_desc(ptt2_action, odptt_action),
        "sites": sites,
        "guards": guards,
        "kind": "multi",
        "va": sites[0][0] if sites else STR_PTT2_VA,
        "alternatives": [
            {"sites": s2, "guards": g2}
            for c2, (s2, g2) in PF_LABEL_VARIANTS.items()
            if c2 != (ptt2_action, odptt_action)
        ],
    }
    return patches


PATCHES = build_patches()


# --------------------------------------------------------------------------
def ctx_variants(p):
    """Every context signature this tool recognises at this site - one per
    known state (the factory original plus every value this tool can write),
    so a previously-applied patch - including one made with a different
    --bluetooth-mode - is still recognised as valid, not just the untouched or
    exactly-this-run's-target bytes.
    """
    return {p["ctx_variant"](s) for s in p["states"].values()}


def decrypt_rel(raw, app_start, rel_off, length):
    """Descramble `length` bytes at app-relative `rel_off` without doing the
    whole image. The SFC key depends on the app-relative address, so the
    covering 32-byte cache lines are decrypted and then sliced."""
    a = rel_off & ~(LINE - 1)
    b = (rel_off + length + LINE - 1) // LINE * LINE
    chunk = raw[app_start + a : app_start + b]
    if len(chunk) != b - a:
        return None
    return sfc_enc_decrypt(chunk, a, CHIPKEY)[rel_off - a : rel_off - a + length]


def find_app_start(raw):
    """Locate the scrambled app region inside the container.

    A candidate is accepted only if every patch site's context signature
    descrambles correctly, which simultaneously validates the offset, the
    chipkey and the firmware version.
    """
    def ok(start, p):
        if p.get("kind") == "multi":
            cands = [p] + list(p.get("alternatives", []))
            return any(
                all(
                    decrypt_rel(raw, start, va_to_off(va), len(new)) == new
                    or decrypt_rel(raw, start, va_to_off(va), len(nat)) == nat
                    for va, nat, new in c["sites"]
                ) and all(
                    decrypt_rel(raw, start, va_to_off(va), len(b)) == b
                    for va, b in c["guards"]
                )
                for c in cands
            )
        return (
            decrypt_rel(raw, start, va_to_off(p["ctx_va"]), len(p["ctx_base"]))
            in ctx_variants(p)
        )

    for start in CANDIDATE_STARTS:
        if len(raw) < start + APP_LEN:
            continue
        if all(ok(start, p) for p in PATCHES.values()):
            return start
    return None


def load_app(path):
    with open(path, "rb") as f:
        raw = f.read()
    start = find_app_start(raw)
    if start is None:
        raise SystemExit(
            "%s: could not locate a recognised app region.\n"
            "Tried container offsets %s with chipkey 0x%04X.\n"
            "This is either not an H3 Plus image, or not firmware v1.0.50 "
            "(the version these patches were derived from)."
            % (path, ", ".join("0x%X" % c for c in CANDIDATE_STARTS), CHIPKEY)
        )
    app = sfc_enc_decrypt(raw[start : start + APP_LEN], 0, CHIPKEY)
    return raw, bytearray(app), start


def check_context(app, p, name):
    off = va_to_off(p["ctx_va"])
    got = bytes(app[off : off + len(p["ctx_base"])])
    if got not in ctx_variants(p):
        raise SystemExit(
            "patch '%s': context mismatch at VA 0x%08X\n"
            "  found    %s\n"
            "  expected one of:\n%s\n"
            "This firmware is not the version this patch was derived from "
            "(v1.0.50), or the site holds something this tool does not "
            "recognise. Refusing to patch."
            % (
                name,
                p["ctx_va"],
                got.hex(" "),
                "\n".join("    %s" % v.hex(" ") for v in ctx_variants(p)),
            )
        )


def show(app):
    print("%-10s %-10s %-10s  %s" % ("patch", "VA", "flash", "state"))
    print("-" * 76)
    for name, p in PATCHES.items():
        off = va_to_off(p["va"])
        if p.get("kind") == "multi":
            st = multi_state(app, p)
            n = len(p["sites"])
            state = "%s  (%d/%d sites native, %d/%d at target)" % (
                {"native": "current", "target": "TARGET "}.get(st, "MIXED  "),
                sum(s == "native" for s in multi_sites(app, p)), n,
                sum(s == "target" for s in multi_sites(app, p)), n,
            )
            print("%-10s 0x%08X 0x%08X  %s" % (name, p["va"], off_to_flash(off), state))
            print("%-10s %-10s %-10s    %s" % ("", "", "", p["desc"]))
            continue
        cur = bytes(app[off : off + len(p["new"])])
        label = next((k for k, v in p["states"].items() if v == cur), None)
        if label is None:
            state = "UNKNOWN (%s)" % cur.hex(" ")
        elif cur == p["new"]:
            state = "TARGET  (%s)" % p["labels"][label]
        else:
            state = "current (%s)" % p["labels"][label]
        print(
            "%-10s 0x%08X 0x%08X  %s"
            % (name, p["va"], off_to_flash(off), state)
        )
        print("%-10s %-10s %-10s    %s" % ("", "", "", p["desc"]))
    print()


def multi_sites(app, p):
    """Per-site state of a multi-site patch: 'native', 'target' or 'other'."""
    out = []
    for va, nat, new in p["sites"]:
        o = va_to_off(va)
        if bytes(app[o : o + len(new)]) == new:
            out.append("target")
        elif bytes(app[o : o + len(nat)]) == nat:
            out.append("native")
        else:
            out.append("other")
    return out


def multi_state(app, p):
    s = set(multi_sites(app, p))
    if not s:
        return "native"
    return s.pop() if len(s) == 1 else "mixed"


def _multi_at_target(app, sites):
    return all(
        bytes(app[va_to_off(va): va_to_off(va) + len(new)]) == new
        for va, nat, new in sites
    )


def apply_multi(app, name):
    p = PATCHES[name]
    for va, b in p["guards"]:
        o = va_to_off(va)
        if bytes(app[o : o + len(b)]) != b:
            raise SystemExit("patch '%s': guard mismatch at VA 0x%08X" % (name, va))
    if not p["sites"]:
        print("[=] %-7s stock labels, nothing to do" % name)
        return False
    st = multi_state(app, p)
    if st == "target":
        print("[=] %-7s already at target state, skipping" % name)
        return False
    if st != "native":
        alt = next((c2 for c2, (s2, _g2) in PF_LABEL_VARIANTS.items()
                    if _multi_at_target(app, s2)), None)
        hint = ""
        if alt:
            hint = ("\nThe image already carries the labels for "
                    "--PTT2=%s --OD-PTT=%s; re-run with those actions "
                    "(or start from a stock image) to change them."
                    % alt)
        raise SystemExit(
            "patch '%s': sites are %s; refusing to patch a partly modified image%s"
            % (name, ", ".join(multi_sites(app, p)), hint)
        )
    print("[+] %s" % name)
    print("      %s" % p["desc"])
    for va, nat, new in p["sites"]:
        o = va_to_off(va)
        app[o : o + len(new)] = new
        print("      VA 0x%08X / flash 0x%08X  %s  ->  %s"
              % (va, off_to_flash(o), nat.hex(" "), new.hex(" ")))
    return True


def apply_patch(app, name):
    p = PATCHES[name]
    if p.get("kind") == "multi":
        return apply_multi(app, name)
    off = va_to_off(p["va"])
    cur = bytes(app[off : off + len(p["new"])])

    if cur == p["new"]:
        print("[=] %-7s already at target state, skipping" % name)
        return False

    label = next((k for k, v in p["states"].items() if v == cur), None)
    if label is None:
        raise SystemExit(
            "patch '%s': unexpected bytes at VA 0x%08X (found %s)\n"
            "recognised states:\n%s"
            % (
                name,
                p["va"],
                cur.hex(" "),
                "\n".join(
                    "  %-24s %s" % (p["labels"][k], v.hex(" "))
                    for k, v in p["states"].items()
                ),
            )
        )

    check_context(app, p, name)
    app[off : off + len(p["new"])] = p["new"]

    print("[+] %s" % name)
    print("      %s" % p["desc"])
    print("      VA 0x%08X / flash 0x%08X" % (p["va"], off_to_flash(off)))
    print("      %s  ->  %s" % (cur.hex(" "), p["new"].hex(" ")))
    print("      %s" % p["labels"][label])
    print("   -> %s" % p["labels"][p["target"]])
    return True


def export_sectors(raw, out, app_start, prefix):
    """Write the 4 KiB flash sectors that differ, and the commands to flash them.

    Only valid when the container is a raw flash image (app_start == FLASH_BASE),
    because otherwise a container offset is not a flash address.
    """
    if app_start != FLASH_BASE:
        raise SystemExit(
            "--sectors requires a raw flash image (.bin or a full dump).\n"
            "This container holds the app at 0x%X, not 0x%X, so container "
            "offsets are not flash addresses. Patch the whole file instead."
            % (app_start, FLASH_BASE)
        )

    diff = [i for i in range(len(raw)) if raw[i] != out[i]]
    if not diff:
        return []
    sectors = sorted({i & ~(SECTOR - 1) for i in diff})

    d = os.path.dirname(prefix)
    if d:
        os.makedirs(d, exist_ok=True)

    print("changed bytes: %d, in %d sector(s) of 0x%X\n" % (len(diff), len(sectors), SECTOR))

    written = []
    for s in sectors:
        path = "%s_%06X.bin" % (prefix, s)
        with open(path, "wb") as f:
            f.write(out[s : s + SECTOR])
        n = sum(1 for i in diff if s <= i < s + SECTOR)
        print("  flash 0x%06X-0x%06X  %d byte(s) changed  -> %s" % (s, s + SECTOR - 1, n, path))
        written.append((s, path))

    print("\njl-uboot-tool commands:\n")
    for s, path in written:
        print("  erase 0x%06X 0x%X" % (s, SECTOR))
        print("  write 0x%06X %s" % (s, path))
    print("\nread back to verify:\n")
    for s, path in written:
        print("  read 0x%06X 0x%X verify_%06X.bin" % (s, SECTOR, s))
    return written


_MODE_HELP = """\
1 = TID-PTT      BT mic -> TX, radio's own speaker <- RX
2 = TID-MIC      full duplex: BT mic -> TX, BT <- RX  [hardware-confirmed]
3 = stock        radio's own mic -> TX (factory default; = no patch)
4 = TID-MIC-EAR  full duplex, same as 2 in practice  [hardware-confirmed]
5 = link-class   audio-routing GPIO class  [UNTESTED]
6 = link-class   audio-routing GPIO class  [tested: no BT mic on PTT]"""

_PAIR_HELP = "\n".join(
    "  --PTT2=%-7s --OD-PTT=%-7s%s" % (c[0], c[1], "  (stock)" if c == ("PTT2", "OD-PTT") else "")
    for c in PF_COMBO_PATCHES)

DEFAULT_LINE = ("--bluetooth-mode 4 --PTT=BT-PTT --PTT2=PTT2 --OD-PTT=OD-PTT")


def _action_type(opt):
    def f(value):
        return normalize_action(value, opt)
    return f


class _Formatter(argparse.RawDescriptionHelpFormatter):
    """Keeps the explicit newlines in the epilog AND in individual option
    help strings, so the mode / action lists render one per line."""

    def _split_lines(self, text, width):
        if "\n" in text:
            return text.splitlines()
        return super()._split_lines(text, width)


def _canonicalize_options(parser, argv):
    """Make the option NAMES case-insensitive too (argparse only does exact
    spellings): rewrite every leading-dash token whose upper-case form is a
    known option string to the canonical spelling, e.g. --ptt -> --PTT,
    --BlUeTooth-MoDe -> --bluetooth-mode. Values are left alone (the action
    values are normalised separately by normalize_action)."""
    by_upper = {}
    for action in parser._actions:
        for opt in action.option_strings:
            by_upper.setdefault(opt.upper(), opt)
    out = []
    for tok in argv:
        if tok.startswith("-") and not tok.startswith("---"):
            flag, sep, value = tok.partition("=")
            canon = by_upper.get(flag.upper())
            if canon is not None:
                tok = canon + sep + value
        out.append(tok)
    return out


def main():
    global PATCHES
    ap = argparse.ArgumentParser(
        description="Patch H3 Plus firmware: any-name Bluetooth duplex and "
        "configurable PTT / PTT2 / OD PTT key actions.",
        epilog="DEFAULTS - running with no options is exactly:\n\n"
        "    " + DEFAULT_LINE + "\n\n"
        "  i.e. any Bluetooth headset is treated as a duplex speaker-mic\n"
        "  (mode 4), the main PTT key transmits the headset's Bluetooth mic\n"
        "  while one is linked (the radio's own mic otherwise), and the two\n"
        "  PF menu options PTT2 / OD PTT keep their stock behaviour.\n\n"
        "Option names and action values are matched case-insensitively;\n"
        "BT-PTT may also be written BTPTT / BT_PTT, OD-PTT as ODPTT / OD_PTT.",
        formatter_class=_Formatter,
    )
    ap.add_argument("src", help="input .fw / .bin (e.g. FW/TD-H3-PlusV1.0.50.fw)")
    ap.add_argument("dst", nargs="?", help="output file (same container type as src)")
    ap.add_argument("--show", action="store_true", help="report current state and exit")
    ap.add_argument(
        "--only",
        choices=sorted(PATCHES),
        action="append",
        help="apply only this internal patch (repeatable, for experts / "
        "inspection); the default is %s plus the key patches implied by the "
        "action options below. When --only is given, the default --PTT=BT-PTT "
        "is NOT added unless --PTT is also given explicitly"
        % ", ".join(DEFAULT_PATCHES),
    )
    ap.add_argument(
        "--bluetooth-mode", "--bt", "-b",
        dest="bluetooth_mode",
        type=int,
        choices=sorted(DUPLEX_STATES),
        default=4,
        help="what a connected Bluetooth headset whose name the radio does "
        "not recognise (anything but TID-PTT / TID-MIC / TID-MIC-EAR) does. "
        "Default: 4 (hardware-confirmed).\n" + _MODE_HELP,
    )
    ap.add_argument(
        "--PTT",
        dest="PTT",
        type=_action_type("--PTT"),
        default=None,
        metavar="ACTION",
        help="what the radio's MAIN PTT key does. Default: BT-PTT "
        "(hardware-confirmed).\n"
        "  PTT     stock: transmit on the current VFO (no patch)\n"
        "  BT-PTT  transmit the Bluetooth headset's mic while a headset is\n"
        "          linked, the radio's own mic otherwise\n"
        "  PTT2 / OD-PTT are not possible for the main PTT key",
    )
    ap.add_argument(
        "--PTT2",
        dest="PTT2",
        type=_action_type("--PTT2"),
        default=None,
        metavar="ACTION",
        help='what the PF menu option "PTT2" does, on every PF key assigned '
        'to it. Default: PTT2 (stock).\n'
        "  PTT2    stock: TX forced to VFO B\n"
        "  PTT     TX on the current VFO, radio mic (menu shows \"PTT\")\n"
        "  BT-PTT  transmit the Bluetooth headset's mic (menu shows \"BT PTT\")\n"
        "  OD-PTT  stock one-key duplex (menu shows \"OD PTT\")\n"
        "  Any action works here as long as --OD-PTT differs from it.",
    )
    ap.add_argument(
        "--OD-PTT",
        dest="OD_PTT",
        type=_action_type("--OD-PTT"),
        default=None,
        metavar="ACTION",
        help='what the PF menu option "OD PTT" does, on every PF key '
        'assigned to it. Default: OD-PTT (stock).\n'
        "  OD-PTT  stock one-key duplex\n"
        "  BT-PTT  transmit the Bluetooth headset's mic (menu shows \"BT PTT\")\n"
        "  PTT     TX on the current VFO, radio mic (menu shows \"PTT\")\n"
        "  PTT2    TX forced to VFO B (menu shows \"PTT2\")\n"
        "  Any action works here as long as --PTT2 differs from it.\n"
        "The two options must run DIFFERENT actions; every pair of distinct\n"
        "actions is supported, in either order:\n" + _PAIR_HELP,
    )
    ap.add_argument(
        "--sectors",
        metavar="PREFIX",
        help="also export the changed 4 KiB flash sectors as PREFIX_<addr>.bin "
        "with jl-uboot-tool commands (raw .bin / dump only)",
    )
    args = ap.parse_args(_canonicalize_options(ap, sys.argv[1:]))

    ptt_action = args.PTT if args.PTT is not None else DEFAULT_ACTIONS["PTT"]
    a7 = args.PTT2 if args.PTT2 is not None else DEFAULT_ACTIONS["PTT2"]
    a8 = args.OD_PTT if args.OD_PTT is not None else DEFAULT_ACTIONS["OD-PTT"]

    if ptt_action not in PTT_KEY_PATCHES:
        raise SystemExit(
            "--PTT=%s is not possible: the main PTT key has only its stock "
            "action (PTT) or the Bluetooth-mic action (BT-PTT); the PF menu "
            "executor that runs PTT2 / OD PTT is not reachable from it."
            % ptt_action
        )
    validate_pf_combo(a7, a8)

    PATCHES = build_patches(args.bluetooth_mode, a7, a8)

    raw, app, app_start = load_app(args.src)
    print("source: %s (%d bytes)" % (args.src, len(raw)))
    print(
        "app region: container 0x%X-0x%X, flash 0x%X, chipkey 0x%04X\n"
        % (app_start, app_start + APP_LEN, FLASH_BASE, CHIPKEY)
    )
    print("configuration: --bluetooth-mode %d --PTT=%s --PTT2=%s --OD-PTT=%s\n"
          % (args.bluetooth_mode, ptt_action, a7, a8))

    if args.show or not (args.dst or args.sectors):
        show(app)
        if not (args.dst or args.sectors) and not args.show:
            print("No output file given; nothing written.")
        return 0

    before = bytes(app)
    if args.only:
        wanted = list(args.only)
        if args.PTT is not None:
            wanted += PTT_KEY_PATCHES[ptt_action]
        if args.PTT2 is not None or args.OD_PTT is not None:
            wanted += pf_combo_patches(a7, a8)
    else:
        wanted = list(DEFAULT_PATCHES)
        wanted += PTT_KEY_PATCHES[ptt_action]
        wanted += pf_combo_patches(a7, a8)
    wanted = list(dict.fromkeys(wanted))
    if ({"pfbody7", "pfbody8", "pfrelease", "pflabels"} & set(wanted)
            and PF_LITERAL_PATCHES & set(wanted)):
        raise SystemExit(
            "the legacy scanner patches pf1down/pf1up/pf2down/pf2up take "
            "over PTT2 and OD PTT on one key before the menu action runs, "
            "so they cannot be combined with the menu action patches."
        )
    # A swapped press table comes from the obsolete swap model: value 7 runs
    # body B and value 8 runs body A, so rewriting the bodies at their native
    # addresses would label them for the wrong option. Refuse; the user must
    # start from a stock image.
    toff = va_to_off(PF_TBB_78_VA)
    if bytes(app[toff:toff + 2]) == PF_TBB_78_SWAPPED:
        raise SystemExit(
            "the PF press dispatch table at VA 0x%08X is swapped "
            "(values 7/8 exchange their bodies). That comes from the "
            "obsolete swap model of this tool; the current model rewrites "
            "the bodies in place and cannot be applied on top of it. Start "
            "from an unpatched firmware image."
            % PF_TBB_78_VA
        )
    print("patches: %s\n" % ", ".join(wanted))

    changed_any = False
    for name in wanted:
        changed_any |= apply_patch(app, name)
        print()

    if not changed_any:
        print("Nothing to do; image already carries the requested patches.")
        return 0

    changed = sum(1 for x, y in zip(before, app) if x != y)
    print("plaintext bytes changed: %d" % changed)

    enc = sfc_enc_decrypt(bytes(app), 0, CHIPKEY)
    assert sfc_enc_decrypt(enc, 0, CHIPKEY) == bytes(app), "round-trip failed"

    out = bytearray(raw)
    out[app_start : app_start + APP_LEN] = enc

    diff = [i for i in range(len(raw)) if raw[i] != out[i]]
    print("ciphertext bytes changed: %d" % len(diff), end="")
    print("  (0x%X - 0x%X)" % (diff[0], diff[-1]) if diff else "")
    print()

    if args.sectors:
        export_sectors(raw, out, app_start, args.sectors)
        print()

    if args.dst:
        with open(args.dst, "wb") as f:
            f.write(out)
        print("wrote %s (%d bytes)" % (args.dst, len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
