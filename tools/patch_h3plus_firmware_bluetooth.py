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

    Every PTT-like control of the radio can be assigned one of five actions.
    Option names and action values are matched case-insensitively, and
    BT-PTT / BT-PTT2 / OD-PTT may also be spelled BTPTT / BTPTT2 / ODPTT /
    BT_PTT / BT_PTT2 / OD_PTT.

      PTT      normal transmit: TX on the CURRENT VFO with the radio's own
               mic (what the main PTT key always does)
      PTT2     stock menu option: TX forced to VFO B
      BT-PTT   transmit the BLUETOOTH headset's mic (the virtual +SPP=P /
               +SPP=R command); the radio's own mic is used when no headset
               is linked
      BT-PTT2  like BT-PTT but TX forced to VFO B - the SECOND channel
               (menu shows "BT PTT2").  [HARDWARE-CONFIRMED 2026-09-30, ch. 23 SS9C.8]
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
    actions - all 20 - works in either order. The ten unordered combos:

      1. PTT      + PTT2
      2. PTT      + OD-PTT
      3. PTT      + BT-PTT
      4. PTT      + BT-PTT2
      5. PTT2     + OD-PTT     stock (no-op)
      6. PTT2     + BT-PTT
      7. PTT2     + BT-PTT2
      8. OD-PTT   + BT-PTT
      9. OD-PTT   + BT-PTT2
     10. BT-PTT   + BT-PTT2

    ... each in both orientations, e.g. --PTT2=OD-PTT --OD-PTT=BT-PTT is
    served directly: option 7 runs the OD setup, option 8 the BT push, and
    the release dispatch is built to match. No rewiring by the user is
    needed or possible - just choose the action each option should have.

    The only refused pairs are the five where both options would run the
    SAME action (PTT/PTT, PTT2/PTT2, BT-PTT/BT-PTT, BT-PTT2/BT-PTT2,
    OD-PTT/OD-PTT): one code body performs one action, so choose which
    option to sacrifice.

      --PTT=PTT2 / --PTT=OD-PTT   still not possible: the main PTT key
              cannot run the PF-menu executor; only its stock action or
              the BT push exist.

    MENU LABELS. The menu shows the action: an option set to PTT is
    labelled "PTT", to BT-PTT "BT PTT", to BT-PTT2 "BT PTT2", and stock
    options keep "PTT2" / "OD PTT". "PTT" is the tail of the "OD PTT"
    string, so that string is never modified and the Bluetooth menu's own
    "OD PTT" item keeps its name. "BT PTT" (6 chars + NUL) does not fit
    over the 5-byte "PTT2" string, so it overwrites 7 bytes starting at one
    of two places:

      0x01E8E30E  over "PTT2\0" + the first 2 bytes of Russian "NET"
                  (used when no option is still labelled "PTT2")
      0x01E8E313  over Russian "NET\0" exactly
                  (used when "PTT2" must stay readable)

    "BT PTT2" (7 chars + NUL) needs 8 bytes: it goes over "PTT2\0" + the
    first 3 bytes of "NET" when no option is still labelled "PTT2", else
    the shorter "BT2" goes over the first 4 bytes of Russian "NET". When
    BOTH BT actions are in one pair, BT-PTT2 takes "BT2" over the first 4
    bytes of "PTT2\0" (its NUL survives) and BT-PTT takes "BT PTT" over
    "NET" exactly - the placements never overlap.

    In every case that touches Russian "NET", the three pointers to it move
    to the existing Russian "Net" string at 0x01E92010 (same word,
    different capitalisation). Labels are changed in all nine language
    lists.
    [Labels verified in all 9 language lists statically (ch. 23 SS9C.9)
    and on the display 2026-10-01.]

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

    # menu option PTT2 becomes "BT PTT2": BT headset mic, TX on VFO B (HW-confirmed)
    python tools/patch_h3plus_firmware_bluetooth.py Dumps/dump_internal.bin out.bin --PTT2=BT-PTT2

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
and BT-PTT / OD-PTT may be written BTPTT / ODPTT / BT_PTT / OD_PTT.


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


def encode_goto32(site_va, target_va):
    """Encode the 32-bit `goto target` (`ff ea xx xx`): the call encoding
    with bit 6 of the first byte set. Verified against stock encodings,
    e.g. 0x01E75E34 -> 0x01E56456 is `ff ea 0f 03`."""
    b = bytearray(encode_call(site_va, target_va))
    b[0] |= 0x40
    return bytes(b)


def encode_branch2(site_va, target_va, neq=True, reg=0):
    """Encode the 2-byte `if (r<reg> != 0) goto target` (or `== 0`).

    Empirical layout (fitted against stock encodings in work/full.lst via
    tools/pi32dis.py): w = 0x4000 | (((u >> 4) & 1) << 12) | ((u & 0xF)
    << 8) | (cond << 7) | (((u >> 5) & 7) << 4) | reg, with cond = 1 for
    `!=` and u = (target - site - 2) / 2 a signed 8-bit halfword count
    (target offsets -254..+256 bytes). Verified: 0x01E75DE8 ->
    0x01E75E74 is `a0 45` (u=69), 0x01E75E3C -> 0x01E75E74 is `80 5b`
    (u=27), 0x01E75E4E -> 0x01E75E70 is `00 50` (==, u=16),
    0x01E75DFC -> 0x01E75E00 is `01 41` (==, r1, u=1), 0x01E75E90 ->
    0x01E75E96 is `00 42` (==, u=2).
    """
    d = target_va - site_va - 2
    if d & 1:
        raise ValueError("odd branch displacement")
    u = d >> 1
    if not -128 <= u <= 127:
        raise ValueError("branch displacement out of range: %d" % u)
    w = (0x4000 | (((u >> 4) & 1) << 12) | ((u & 0xF) << 8)
         | ((1 if neq else 0) << 7) | (((u >> 5) & 7) << 4) | reg)
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
# [HARDWARE-CONFIRMED 2026-09-30: --PTT=BT-PTT --PTT2=BT-PTT2 --OD-PTT=PTT
# works with and without a headset, ch. 23 SS9C.8]
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
_PF_BEHAV = {"PTT": "TX", "PTT2": "TX", "OD-PTT": "OD", "BT-PTT": "BT",
             "BT-PTT2": "BT2"}

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
    if action == "BT-PTT2":
        return _pf_body7_h2()
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
    if action == "BT-PTT2":
        return _pf_body8_h2()
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
    elif {b7, b8} == {"OD", "BT2"}:
        # same tight combo with the 4-byte BT-PTT2 release in the alt slot
        put(0x0A, encode_call(REL_OD_BODY_VA, OD_TEARDOWN_VA)
            + encode_call(REL_OD_BODY_VA + 4, TXSTOP_VA)
            + bytes.fromhex("0004"))
        put(0x14, _pf_bt2_release(REL_BT_ALT_VA))
        t7 = REL_OD_BODY_VA if b7 == "OD" else REL_BT_ALT_VA
        t8 = REL_OD_BODY_VA if b8 == "OD" else REL_BT_ALT_VA
    elif {b7, b8} == {"BT", "BT2"}:
        # BT release (8 B) at E82, BT-PTT2 release (4 B) at E8C
        put(0x0A, _pf_bt_release(REL_OD_BODY_VA))
        put(0x14, _pf_bt2_release(REL_BT_ALT_VA))
        t7 = REL_OD_BODY_VA if b7 == "BT" else REL_BT_ALT_VA
        t8 = REL_OD_BODY_VA if b8 == "BT" else REL_BT_ALT_VA
    else:
        if "BT" in (b7, b8):
            put(0x0A, _pf_bt_release(REL_OD_BODY_VA))
        if "BT2" in (b7, b8):
            put(0x0A, _pf_bt2_release(REL_OD_BODY_VA))
        tgt = {"TX": REL_TX_BODY_VA, "OD": REL_OD_BODY_VA,
               "BT": REL_OD_BODY_VA, "BT2": REL_OD_BODY_VA}
        t7, t8 = tgt[b7], tgt[b8]
    put(0x00, encode_cmp_eq_imm(PF_REL_VA, 8, t8))
    put(0x04, encode_cmp_eq_imm(PF_REL_VA + 4, 7, t7))
    return bytes(out)


# --- BT-PTT2: Bluetooth PTT forced to the SECOND channel (VFO B) -----------
#
# `BT-PTT` pushes virtual key 0x2A; its standby handler (0x01E794A2) sets
# b[gp+0x46] = current-VFO and calls the TX start (0x01E5993C), which
# routes 0 -> VFO A, nonzero -> VFO B. `BT-PTT2` runs the same 0x2A/0x2B
# pipeline (BT-mic TX, hardware-confirmed for BT-PTT) but forces the TX
# onto VFO B. The press bodies (0x01E75E38 / 0x01E75E42, 10 / 8 bytes) are
# too small to hold the extra logic, so they jump to a code cave at
# 0x01EA76DE (364 bytes ALLZERO in v44/v45/v50, zero pointer hits in any
# 2-byte-aligned LE word of the app) via a trampoline at 0x01E794DA.
#
# The trampoline replaces the first 4 bytes of the key-0x2A standby
# handler's TX-start tail (0x01E794DA: `r0 = b[r7+0x77]; r0 = r0 >> 7;
# b[r7+0x46] = r0; call 0x01E5993C` - straight-line code, zero pointer
# references); the cave handler reproduces it: with the force flag at
# gp+0xC7 set (verified unused: zero `0xC7]` hits in the whole v50
# disassembly) it stores 1 (VFO B) instead of the current-VFO bit, then
# calls the TX start and returns to 0x01E794E8. The flag is set by the
# press helper and cleared by the release helper, so a plain PTT press
# between BT-PTT2 presses keeps working. Register contexts (disassembly-
# verified): press bodies run with r4 = gp (0x102F0); the cave handler
# runs in the 0x2A-handler context with r7 = gp; the release executor
# runs with r0 = the released PF number and r4 NOT gp, so the release
# helper loads gp itself. HW-confirmed 2026-09-30 (ch. 23 SS9C.8).
CAVE_VA = 0x01EA76DE          # 364-byte ALLZERO code cave (v44/v45/v50)
CAVE_LEN = 68                 # bytes of the cave this tool fills
FLAG_OFF = 0xC7               # gp+0xC7: force-VFO-B flag (verified unused)
H2A_TRAMP_VA = 0x01E794DA     # key-0x2A TX-start tail -> cave handler
H2A_TRAMP_LEN = 14            # native span replaced (load/shift/store+call)
H2A_RESUME_VA = 0x01E794E8    # continuation after the native TX-start call
TXSTART2_VA = 0x01E5993C      # TX-start core (key-0x2A handler tail)
CAVE_PRESS_VA = CAVE_VA + 36
CAVE_REL_VA = CAVE_VA + 48
# native trampoline bytes: r0 = b[r7+0x77]; r0 = r0 >> 7; b[r7+0x46] = r0;
# call 0x01E5993C
H2A_TRAMP_NATIVE = bytes.fromhex("50ee7707 80a7 52ee7604 bfea2a02".replace(" ", ""))


def _cave_images():
    """The cave contents: TX handler, press helper, release helper.

    The handler runs in the key-0x2A standby-handler context (r7 = gp)
    right where the stock code used to compute the current-VFO byte and
    call the TX start. It consumes the force-VFO-B flag ONE-SHOT (clears
    it immediately, so a later plain 0x2A press - main PTT with BT-PTT,
    or +SPP=P - is never affected even if a release was missed), stores
    1 (VFO B) when the flag was set or the stock current-VFO bit when it
    was not, calls the TX start, and returns to the instruction right
    after the native call.
    """
    handler = bytearray()
    handler += bytes.fromhex("50ee770c")               # r0 = b[r7 + 0xC7]
    handler += bytes.fromhex("4120")                   # r1 = 0
    handler += bytes.fromhex("52ee771c")               # b[r7 + 0xC7] = r1
    handler += encode_branch2(CAVE_VA + 10, CAVE_VA + 18, neq=False)
    handler += bytes.fromhex("4021")                   # r0 = 1 (VFO B)
    handler += encode_goto32(CAVE_VA + 14, CAVE_VA + 24)
    handler += bytes.fromhex("50ee7707")               # r0 = b[r7 + 0x77]
    handler += bytes.fromhex("80a7")                   # r0 = r0 >> 7
    handler += bytes.fromhex("52ee7604")               # b[r7 + 0x46] = r0
    handler += encode_call(CAVE_VA + 28, TXSTART2_VA)  # call TX-start core
    handler += encode_goto32(CAVE_VA + 32, H2A_RESUME_VA)
    assert len(handler) == 36

    press = bytearray()
    press += bytes.fromhex("52ee470c")                 # b[r4 + 0xC7] = r0
    press += bytes.fromhex("482a")                     # r0 = 0x2A
    press += encode_call(CAVE_PRESS_VA + 6, PUSH_KEY_VA)
    press += bytes.fromhex("5504")                     # {pc, r5, r4} = [sp++]
    assert len(press) == 12

    rel = bytearray()
    rel += bytes.fromhex("c0fff0020100")               # r0 = 0x102F0 (gp)
    rel += bytes.fromhex("4120")                       # r1 = 0
    rel += bytes.fromhex("52ee071c")                   # b[r0 + 0xC7] = r1
    rel += bytes.fromhex("482b")                       # r0 = 0x2B
    rel += encode_call(CAVE_REL_VA + 14, PUSH_KEY_VA)
    rel += bytes.fromhex("0004")                       # pc = [sp++]
    assert len(rel) == 20
    return bytes(handler) + bytes(press) + bytes(rel)


def _pf_body7_h2():
    """PF7 press body (10 bytes) for BT-PTT2: flag + push key 0x2A."""
    return (bytes.fromhex("4021")                       # r0 = 1
            + encode_goto32(PF_BODY7_VA + 2, CAVE_PRESS_VA)
            + b"\x00\x00\x00\x00")


def _pf_body8_h2():
    """PF8 press body (8 bytes) for BT-PTT2: flag + push key 0x2A."""
    return (bytes.fromhex("4021")                       # r0 = 1
            + encode_goto32(PF_BODY8_VA + 2, CAVE_PRESS_VA)
            + b"\x00\x00")


def _pf_bt2_release(site_va):
    """Release body (4 bytes) for BT-PTT2: goto the cave release helper."""
    return encode_goto32(site_va, CAVE_REL_VA)


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

# --------------------------------------------------------------------------
# --conn-num: stack connection-count gate (multipoint experiment, ch. 22
# SS9B.10). The app's BT init (0x01E60EB0) calls __set_user_ctrl_conn_num(1)
# at 0x01E182B0: a read-modify-write of the flag word at RAM 0xBF39
# (user_stack_configs + 0x15) that clears bits 4-5 and then runs `r1 |= 16`
# at 0x01E182DC, i.e. conn_num = 1. The JieLi API (avctp_user.h) documents
# it as "number of BT connections supported; controls discoverability and
# the reconnect flow". `r1 |= 32` (byte 0x25) asks for conn_num = 2.
# conn_num = 2 ALONE was hardware-tested 2026-10-03 and is NOT sufficient
# (eviction persisted - ch. 22 SS9B.11: the reader is scan-management only
# and the app keeps one device struct). It is, however, a member of the
# E6 combo that IS hardware-confirmed 2026-10-08 (ch. 27 SS27.11): with
# --no-kick --force-page-scan --force-role-keep --no-disconnect-13 the radio
# holds two ACL links (incumbent SPP + radio-initiated second join) and SPP
# keys work with both devices up. The app still models ONE remote device
# (RAM 0x102F0), so audio/mic routing follows the current-device struct.
# --------------------------------------------------------------------------
CONN_NUM_VA = 0x01E182DC
CONN_NUM_CTX_VA = 0x01E182CC
CONN_NUM_CTX = bytes.fromhex(
    "71 e1 30 40 92 b8 8a 43 92 b0 8a 42 92 a8 8a 41 31 24")
CONN_NUM_STATES = {"1": bytes.fromhex("3124"), "2": bytes.fromhex("3125")}
CONN_NUM_LABELS = {
    "1": "conn_num = 1 (stock: single BT device)",
    "2": "conn_num = 2 (multipoint: two BT devices; E6 combo, HW-confirmed)",
}

# --------------------------------------------------------------------------
# --no-kick: the app's disconnect kick (multipoint Option A, Findings ch. 26
# SS26.4 / SS26.7). The routine at 0x01E5B22A is the ONLY code path in the
# app that disconnects a connected BT device: if the device struct at RAM
# 0x102F0 holds a connection handle (offset 0x82, RAM 0x10372) it sets state
# 4 and posts cmd 5 to the BT command queue (0x1A688); the relay handler
# (0x01E22890, case 5 at 0x01E22996) runs hci_disconnect_cmd with reason 19.
# The app calls the kick before paging a second device - and on BT off /
# menu disconnect - which is why a second device always EVICTS the first
# even with --conn-num=2 (hardware-confirmed, ch. 22 SS9B.6.1, ch. 26).
# Replacing the entry with `r0 = 3; rts` (40 23 80 00) mimics the stock
# "no connection" early-return: nothing is ever torn down. EXPECT SIDE
# EFFECTS: turning Bluetooth off and the menu "disconnect" no longer
# release the link (power-cycle instead), and the stack still owns ONE
# conn_info slot, so a second device joins as a passive "ghost link" -
# whether its SPP keys reach the app is the experiment. HW round 1
# 2026-10-05 (ch. 26 SS26.9): kick-NOP CONFIRMED - incoming attempts no
# longer evict the incumbent. Option A = this flag combined with --conn-num=2.
# --------------------------------------------------------------------------
NOKICK_VA = 0x01E5B22A
NOKICK_CTX_VA = NOKICK_VA
NOKICK_CTX = bytes.fromhex("7504 c5ff f002 0100 50ed 5208 004f bf ea")
NOKICK_STATES = {
    "stock": bytes.fromhex("7504c5ff"),
    "disabled": bytes.fromhex("40238000"),  # r0 = 3; rts
}
NOKICK_LABELS = {
    "stock": "kick active: disconnects the current device (stock)",
    "disabled": "r0 = 3; rts (kick disabled: never disconnects; HW-confirmed)",
}

# --------------------------------------------------------------------------
# --force-page-scan: keep page scan enabled while connected (multipoint
# Option A2, Findings ch. 26 SS26.9). With --no-kick the radio no longer
# evicts the first device (hardware-confirmed), but it still answers no
# incoming pages once a link is up: btmon shows "Page Timeout (0x04)",
# i.e. page scan is OFF while connected. The scan policy (BT task cases
# 0xd/0xf) only re-enables page scan when is_1t2_connection() is FALSE,
# and the vendor's 1-to-2 scan logic lived in multi_bd.c, which is
# compiled EMPTY in this firmware. The page-scan setter at 0x01E18AFC
# updates bit 1 of the scan byte (RAM 0xBEC8) and issues
# hci_write_scan_enable (0x0C1A); its disable decision is the pair of
# instructions at 0x01E18B0E (`if (r0 != 0) goto keep; r4 = r2` i.e.
# cleared). NOP-ing both makes EVERY call enable page scan, so the
# stack's post-connect "disable" turns it ON instead and the radio stays
# connectable while a headset holds HFP. HW-observed 2026-10-07 (E4 round,
# ch. 27): incoming pages are ANSWERED while connected (the earlier
# "Page Timeout" refuses are gone; the link then died at controller level
# for the INCOMING topology - see ch. 27 SS27.11: outgoing joins work).
# --------------------------------------------------------------------------
PAGESCAN_VA = 0x01E18B0E
PAGESCAN_CTX_VA = PAGESCAN_VA
PAGESCAN_CTX = bytes.fromhex("8041 2416 9c40 bfea")
PAGESCAN_STATES = {
    "stock": bytes.fromhex("80412416"),
    "forced": bytes.fromhex("00000000"),  # nop; nop -> always enable
}
PAGESCAN_LABELS = {
    "stock": "page scan follows stack policy (off while connected)",
    "forced": "nop; nop (page scan always enabled; pages answered while connected)",
}

# --------------------------------------------------------------------------
# --force-role-keep: HCI Accept Connection Request role -> keep-role
# (multipoint experiment E4, Findings ch. 27 SS27.8). The stack task event
# switch (0x01E19E44, case 4 = Connection Request) accepts incoming ACL
# links; the role parameter is chosen by a stack-config flag:
#
#     01E1A03A  lb.z r0,[r9 + 0x107]     ; r0 = b[0xC02B] (r9 = 0xBF24,
#                                           _stack_config base, ch.22 SS9B.10.2)
#     01E1A03E  jmnz r0,#0x8,0x01e1a4c8  ; bit 3 set -> role 0xAA path
#     01E1A044  mov r1,#0x1              ; else role = 1 (become master)
#     ...
#     01E1A4C8  mov r1,#0xaa             ; vendor "keep role"
#     01E1A4CA  mov r0,r5 ; call 0x01e086f2  ; HCI Accept Connection Request
#
# The config blob @0x01EC2064 initialises b[0xC02B] = 0x00, so stock accepts
# every incoming ACL with role 1 (become master). The round-2 btmon capture
# (ch. 27) shows a second link paged while a headset holds HFP dies at the
# LL level ~644 ms after the page (Connect Complete 0x13) - the controller
# terminates it, plausibly over a role conflict (the radio is already master
# on the headset link). Replacing the config test with an unconditional goto
# to the 0xAA load makes the radio accept the second link with keep-role.
# Only the ACL path reaches this site (SCO / eSCO / reject branch away
# earlier), so SCO setup keeps role 1; registers are identical at the jump.
# HW-TESTED 2026-10-07: FAILED - the role parameter is not the trigger. With the
# full E4 build the second incoming link still dies at the LL level ~722 ms after
# the page (Connect Complete 0x13; same signature as the A2 round-2 capture,
# ~644 ms) - and the PC's page even offered "Role switch: Allow peripheral", so
# the stock role-1 accept was permitted too. Also observed: a radio-initiated
# headset join killed the incumbent PC SPP link despite --no-kick (a second
# eviction path beyond the NOPed kick - see ch. 27 SS27.8 for the E3 follow-up).
# Combine with --conn-num=2 --no-kick --force-page-scan.
# --------------------------------------------------------------------------
ROLEKEEP_VA = 0x01E1A03A
ROLEKEEP_CTX_VA = ROLEKEEP_VA
ROLEKEEP_CTX = bytes.fromhex("50ee 9701 61ff 0800 4202")
ROLEKEEP_STATES = {
    "stock": bytes.fromhex("50ee970161ff08004202"),
    "forced": bytes.fromhex("c0ea4502000000000000"),  # goto 0x01E1A4C8; nop x3
}
ROLEKEEP_LABELS = {
    "stock": "ACL accept role from config (stock: role 1, become master)",
    "forced": "goto role-0xAA load (accept keep-role; E4 FAILED 2026-10-07, harmless in combo)",
}

# --------------------------------------------------------------------------
# --no-disconnect-13: disable the app's reason-0x13 disconnect executor
# (multipoint experiment E6, Findings ch. 27 SS27.9). E3 (hardware 2026-10-08,
# btmon capture): with --no-kick active, a RADIO-INITIATED headset join still
# killed the incumbent PC SPP link - but GRACEFULLY: L2CAP Disconnection
# Request/Response on the RFCOMM CIDs, then HCI Disconnect Complete reason
# 0x13 (Remote User Terminated). That is the app's host stack, not the
# controller. The executor is the call at 0x01E178CE inside 0x01E178B2
# (find connection via 0x01E17420 modes 0/2, then disconnect(handle, 0x13)
# through the wrapper at 0x01E07B08). Its callers are every app-level
# "disconnect current device" route: the BT API dispatcher 0x01E1792E case
# 0x4A (callers: BT mode-set 0x01E60188 and the BT task UI state machine
# 0x01E61E22 - the "connect selected device" flow that posts 0xc,0xe,0x12,
# 5,0x4a) and the stack command dispatcher 0x01E21AF8 cases 8/10 (disconnect
# by address). NOP-ing this one call silences ALL of them; the function then
# falls through to `mov r0,r4` (r4 = 0) and returns "disconnected", so every
# caller behaves as if the teardown succeeded. The kick route (cmd 5 ->
# 0x01E074DE, also reason 0x13) is separate and already covered by --no-kick.
# EXPECT SIDE EFFECTS: menu "disconnect" and explicit disconnect commands no
# longer release a link (power-cycle instead); the app's device struct and
# the stack's conn_info slot are NOT freed, so app state diverges from the
# link state - whether the radio can then page a SECOND device while the
# first link stays up (and whether the controller permits it) is exactly the
# E6 experiment. Combine with --conn-num=2 --no-kick --force-page-scan.
# HW-CONFIRMED 2026-10-08 (E6, ch. 27 SS27.11): the incumbent PC SPP link
# SURVIVES a radio-initiated headset join; both links stay up and SPP PTT
# works. Side effect: after a second device joins, the radio's AT+MPTT
# squelch notifications arrive malformed on the first device's SPP channel
# (cr-bit flipped, "+MP" fragments); the +SPP=P/R echo path is unaffected.
# --------------------------------------------------------------------------
DISC13_VA = 0x01E178CE
DISC13_CTX_VA = DISC13_VA
DISC13_CTX = bytes.fromhex("bfea 1b81 4016 5504".replace(" ", ""))
DISC13_STATES = {
    "stock": bytes.fromhex("bfea1b81"),
    "disabled": bytes.fromhex("00000000"),  # nop; nop -> never disconnects
}
DISC13_LABELS = {
    "stock": "call disconnect(handle, 0x13) (app teardown active)",
    "disabled": "nop; nop (app 0x13 disconnects disabled; E6 HW-confirmed)",
}

# --------------------------------------------------------------------------
# --no-pairing-kick (EXPERIMENTAL / UNTESTED): disable the app's reason-0x16
# disconnect-all executor used by the PAIRING / new-device flow.
#
# E6 HW evidence (2026-10-08, user report): with --no-disconnect-13 active,
# joining an ALREADY-PAIRED device no longer evicts the incumbent link - but
# putting the radio in pairing mode and pressing "connect" on a NEW device
# still kicks it. That path uses the stack BT-task dispatcher 0x01E21AF8's
# reason-0x16 sites, which call the thunk 0x01E19492 (a bare `goto
# 0x01E07B08`, the same disconnect wrapper as the 0x13 path):
#   0x01E21DE4 - inside the disconnect-ALL loop over the 2-slot conn array
#                (stride 0x1C, in-used bit 0x20000000 of the word at +0xC);
#                after the call it sets the "was connected" flag r5=1 and
#                continues, then resets scan state. NOP-ing the call leaves
#                the loop and scan reset intact.
#   0x01E21EC4 - single disconnect(handle, 0x16) from a message field
#                (handle at msg+6); NOP-ing falls through to the return.
# E6 proved OUTGOING pages while connected work (radio paged the headset
# while the PC held SPP), so pairing a new device without freeing the
# incumbent link has a real chance. SIDE EFFECTS: any action that uses
# these paths (pairing-mode teardown, explicit 0x16 disconnect commands)
# no longer releases links; power-cycle instead. Combine with the full
# multipoint recipe (--conn-num=2 --no-kick --force-page-scan
# --no-disconnect-13).
# --------------------------------------------------------------------------
PAIRKICK_ALL_VA = 0x01E21DE4
PAIRKICK_ONE_VA = 0x01E21EC4
PAIRKICK_ALL_CTX = bytes.fromhex("bfea55bb4521c63c")
PAIRKICK_ONE_CTX = bytes.fromhex("bfeae5ba059400e1")
PAIRKICK_ALL_STATES = {
    "stock": bytes.fromhex("bfea55bb"),
    "disabled": bytes.fromhex("00000000"),  # nop; nop -> never disconnects
}
PAIRKICK_ONE_STATES = {
    "stock": bytes.fromhex("bfeae5ba"),
    "disabled": bytes.fromhex("00000000"),  # nop; nop -> never disconnects
}
PAIRKICK_LABELS = {
    "stock": "call disconnect(..., 0x16) (pairing kick active)",
    "disabled": "nop; nop (app 0x16 pairing kick disabled; UNTESTED)",
}

# --------------------------------------------------------------------------
# --no-cmd5-kill (EXPERIMENTAL / UNTESTED): disable the PRESS-TIME incumbent
# kill located 2026-10-25 (ch. 30 SS30.13 Q1). The Paired->Connect UI press
# posts user_send_cmd_prepare(5) at 0x01E61E18 (LIVE in every E1-E11/F build:
# E9 only NOP'd the adjacent 0x4A post at 0x01E61E22). BT-task dispatcher
# FUN_01e21af8 case 5 loops the conn_info slots (0x1A5B8/0x1A5D4) and for
# each in-use slot with halfword +8 == 0 calls FUN_01e08a94 (sole caller,
# 0x01E21EF4), which posts controller command 0xCFE (0x01E029DE, sub=3,
# arg 0x400002, BD_ADDR). The 0xCFE handler (0x01E0DDA4) resolves the conn
# by address (0x01E14BA8, table 0x1A0A8) and calls the disconnect executor
# FUN_01e091EA(conn, 0x13) - graceful L2CAP teardown + Disconnect Complete
# 0x13, the E3 btmon signature. This path touches none of the NOP'd sites
# (wrapper 0x01E07B08, relay 0x01E22890, 0x4a posters, close primitives),
# which is why the press kicked at 0 s in F3V3-B r2. Cmd 5 is fire-and-
# forget (ring-buffer post), so NOP-ing the kill call should not deadlock.
CMD5KILL_VA = 0x01E21EF4
CMD5KILL_CTX = bytes.fromhex("bfeace35488d01e1")
CMD5KILL_STATES = {
    "stock": bytes.fromhex("bfeace35"),
    "disabled": bytes.fromhex("00000000"),  # nop; nop -> never kills incumbent
}
CMD5KILL_LABELS = {
    "stock": "call 0x01E08A94 (cmd-5 0xCFE disconnect-by-address kill active)",
    "disabled": "nop; nop (cmd-5 press-time incumbent kill disabled; UNTESTED)",
}

# --------------------------------------------------------------------------
# --cmd5-handle (R1-c, 2026-10-27): fix the cmd-5 stuck-slot test's FIELD.
# The case-5 loop (ring consumer FUN_01e21af8, BTSTACK task) is
#   0x01E21ED0: r1 = r0 + 8            ; r1 = slot + 8
#   ...     r6 = u32 [slot+0xF..0x12]  ; state word
#   0x01E21EE6: r2 = r6 & 0x20000000   ; inused (bit29)
#   0x01E21EEE: if (r2 == 0) skip
#   0x01E21EF0: r1 = h[r1+0]           ; <<< loads MASK at slot+8
#   0x01E21EF2: if (r1 != 0) skip
#   0x01E21EF4: call 0x01E08A94        ; kill by address
# The mask halfword is only ever set by PC-class flows: SPP accessories
# (TID-PTT) keep mask==0 while LIVE, so cmd 5 kills them at every press -
# the class-dependent evictor of E7/F3V3-B (ch. 30 SS30.14.8 corollary 3).
# The correct stuck test is the CONNECTION HANDLE at slot+6 (== 0 iff no
# ACL; same live test used by ring cases 4 and 0x4a). Re-encoding the load
# from h[r1+0] to h[r0+6] (pi32v2: 19 60 -> 09 63, verified against
# 0x01E0349C "0b 63 = r3 = h[r0+6]") keeps cmd 5 live (F4's wait stays
# satisfied) but it now never touches a live link. Runs on the btstack
# task - the killer's queue-post task contract (SS30.14.8) is respected.
CMD5HANDLE_VA = 0x01E21EF0
CMD5HANDLE_CTX_VA = 0x01E21EEC  # 6-byte window ends exactly before 0x26EF4
CMD5HANDLE_CTX = bytes.fromhex("1c8702441960")
CMD5HANDLE_STATES = {
    "stock": bytes.fromhex("1960"),   # r1 = h[r1+0]  (mask@+8 test)
    "handle": bytes.fromhex("0963"),  # r1 = h[r0+6]  (handle@+6 test)
}
CMD5HANDLE_LABELS = {
    "stock": "r1 = h[r1+0] (cmd-5 stuck test on mask@slot+8 - kills live "
             "mask==0 accessories)",
    "handle": "r1 = h[r0+6] (cmd-5 stuck test on handle@slot+6 - live links "
              "never killed; R1-c, UNTESTED)",
}

# --------------------------------------------------------------------------
# --no-cleanup-kick (EXPERIMENTAL / UNTESTED): disable the THREE remaining
# 0x13-capable callers of the disconnect wrapper 0x01E07B08 (via thunk
# 0x01E19492) - the last host-side disconnect executors left after
# --no-disconnect-13 and --no-pairing-kick.
#
# V2b HW evidence (2026-10-19, user capture /tmp/e7v.hcd): with the FULL E7
# image (readback-verified), PC incumbent on SPP, Paired -> TID-PTT ->
# Connect still evicted the PC: graceful L2CAP Disconnection Request +
# Disconnect Complete reason 0x13 - the same E3 signature, so the kick runs
# through an executor that is NOT the NOP-ed 0x01E178CE. The remaining
# 0x13-capable wrapper callers (funnel analysis, ch. 27 SS 27.13):
#   0x01E19AD0 - stack event handler FUN_01e19a78 (events forwarded by the
#                HCI pump 0x01E19E44), jumptable case: disconnect(handle,
#                reason = message byte) - VARIABLE reason from the message.
#   0x01E19B14 - same handler, subtype 0x73: disconnect(handle, 0x13) for
#                any handle not tracked with state 1 in the conn list
#                (orphan-ACL cleanup).
#   0x01E20AB2 - profile-record state machine FUN_01e20962 (callback
#                registered at file 0x018C90): disconnect(record.handle,
#                0x13) for profile types &2 or ==0x40, then clears record.
# E8 NOPs all three. If the kick survives E8, E9 = wrapper-entry early
# return at 0x01E07B08 (kills ALL host disconnects); if THAT survives it,
# the teardown bypasses the wrapper (direct HCI senders, ch. 27 SS 27.4).
# SIDE EFFECTS: orphan/profile cleanup paths no longer release links;
# power-cycle instead. Combine with the full multipoint recipe.
# --------------------------------------------------------------------------
CLEANUPKICK_VAR_VA = 0x01E19AD0
CLEANUPKICK_ORPHAN_VA = 0x01E19B14
CLEANUPKICK_PROF_VA = 0x01E20AB2
CLEANUPKICK_VAR_CTX = bytes.fromhex("bfeadffc649d5016")
CLEANUPKICK_ORPHAN_CTX = bytes.fromhex("bfeabdfc549d84f9")
CLEANUPKICK_PROF_CTX = bytes.fromhex("bfeaeec4486261ff")
CLEANUPKICK_VAR_STATES = {
    "stock": bytes.fromhex("bfeadffc"),
    "disabled": bytes.fromhex("00000000"),  # nop; nop -> never disconnects
}
CLEANUPKICK_ORPHAN_STATES = {
    "stock": bytes.fromhex("bfeabdfc"),
    "disabled": bytes.fromhex("00000000"),  # nop; nop -> never disconnects
}
CLEANUPKICK_PROF_STATES = {
    "stock": bytes.fromhex("bfeaeec4"),
    "disabled": bytes.fromhex("00000000"),  # nop; nop -> never disconnects
}
CLEANUPKICK_LABELS = {
    "stock": "call disconnect(...) (cleanup kick active)",
    "disabled": "nop; nop (cleanup 0x13 disconnect disabled; UNTESTED)",
}

# --------------------------------------------------------------------------
# --no-l2cap-teardown (EXPERIMENTAL / UNTESTED): stop the app's L2CAP
# channel-close that fires on every "Paired -> Connect" (and on routing-mode
# changes) - the eviction layer that survived E6/E7/E8.
#
# E8 HW evidence (2026-10-19, capture /tmp/e8.hcd): with ALL HCI disconnect
# executors NOP-ed (readback-verified), Paired -> TID-PTT -> Connect still
# killed the PC: the radio sent an L2CAP Disconnection Request (ident 17,
# DCID 64, SCID 67) on the live RFCOMM channel; the PC's bluetoothd then
# dropped the now-useless ACL (Disconnect Complete 0x16 LOCAL). The HCI-level
# kick is GONE - this close is one protocol layer higher.
#
# Mechanism (ch. 27 SS 27.15): user_send_cmd_prepare(0x4a) -> dispatcher
# 0x01E1792E branch 0x01E17B20 = l2cap_disconnect_all_channel() inlined -
# walks the channel list, forces each channel to state 0xd and pumps
# l2cap_run (FUN_01e16f60), which for state 0xd sends the L2CAP Disconnect
# Request (sig code 6). Pure L2CAP, synchronous at button-press. Three
# posters of 0x4a exist (full census of all 80 dispatcher call sites,
# 2026-10-24 — the original "two" census missed the third, which F3-B
# proved is the press-time evictor that survived the other two NOPs):
#   0x01E61E22 - FUN_01e60e44 "connect selected device" UI handler
#                (Paired -> MORE -> Connect). UNCONDITIONAL. NOP-ing the
#                call is fall-through safe (next insn reloads r0); the
#                connect-pending bit and the 0xc/0xe/0x12/5 posts remain,
#                so the outgoing page still happens.
#   0x01E60188 - FUN_01e60120 routing-mode setter; posts 0x4a only when the
#                routing mode CHANGES while a link is active (e.g. BT-PTT
#                mode switch after a join). NOP-ed too, for the link-up case.
#   0x01E4F804 - FUN_01e4f652 (AT/SPP command dispatcher family; only xref =
#                branch-table pointer @0x01E4E274). Posts 0x4a when a helper
#                @0x01E4F034 returns nonzero, then arms a 1000 ms timer.
#                F3-B (2026-10-24): with the two sites above NOP-ed, the
#                Paired->Connect press STILL walked the channels (0 s SPP
#                kill + app freeze) — this is that missing poster.
#                NOP-ing is fall-through safe: the call's result is not
#                consumed (next insn at 0x01E4F808 reloads r1, r0 and r2).
# SIDE EFFECTS: the app never tears down L2CAP/RFCOMM channels on these
# flows; stale channels persist until power-cycle (the E6 malformed-AT+MPTT
# side effect remains). The pre-page settle delay inside the 0x4a body is
# lost (page starts marginally earlier; low risk).
# --------------------------------------------------------------------------
L2CAPTEARDOWN_UI_VA = 0x01E61E22
L2CAPTEARDOWN_MODE_VA = 0x01E60188
L2CAPTEARDOWN_APP_VA = 0x01E4F804
L2CAPTEARDOWN_UI_CTX = bytes.fromhex("bdea84ad506b804b")
L2CAPTEARDOWN_MODE_CTX = bytes.fromhex("bdead1bb048dbdea")
L2CAPTEARDOWN_APP_CTX = bytes.fromhex("beea9340c1ff82fa")
L2CAPTEARDOWN_UI_STATES = {
    "stock": bytes.fromhex("bdea84ad"),
    "disabled": bytes.fromhex("00000000"),  # nop; nop -> no channel close
}
L2CAPTEARDOWN_MODE_STATES = {
    "stock": bytes.fromhex("bdead1bb"),
    "disabled": bytes.fromhex("00000000"),  # nop; nop -> no channel close
}
L2CAPTEARDOWN_APP_STATES = {
    "stock": bytes.fromhex("beea9340"),
    "disabled": bytes.fromhex("00000000"),  # nop; nop -> no channel close
}
L2CAPTEARDOWN_LABELS = {
    "stock": "call user_send_cmd_prepare(0x4a) (L2CAP teardown active)",
    "disabled": "nop; nop (L2CAP channel-close disabled; UNTESTED)",
}

# --------------------------------------------------------------------------
# --no-spp-close (EXPERIMENTAL / UNTESTED): no-op the app's
# spp_channel_disconnect() - the primitive that actually sent the E8/E9
# L2CAP Disconnection Requests against the incumbent's SPP channel.
#
# E9 HW evidence (2026-10-20, capture /tmp/e9.hcd): with BOTH 0x4a posters
# NOP-ed (readback-verified, all twelve sites in the decrypted image),
# Paired -> TID-PTT -> Connect STILL closed the PC's SPP channel (L2CAP
# Disconnection Request ident 20, DCID 64, SCID 69; PC bluetoothd then
# dropped the ACL locally, 0x16/MGMT 0x02 - HCI-level still dead).
#
# Root cause (ch. 27 SS 27.16): the close funnels through FUN_01E173EC =
# spp_channel_disconnect() - reads the SPP control block 0x1A740, takes the
# live SPP L2CAP CID at [cb+2] and forces that channel to state 0xd via
# FUN_01E173D0 (l2cap_disconnect(cid)), which pumps l2cap_run -> L2CAP
# Disconnect Request. Press-time routes that reach it: (1) the connect SM
# calls spp_connect (FUN_01E1750C): if the SPP CID field is BUSY (the PC
# holds it) it CLOSES the incumbent channel and returns -2 to retry
# (call 0x01E1751E) - the single-SPP-session chokepoint; (2) the stack
# posts 0xB (DISCONN_SDP_MASTER) -> dispatcher case 0xB -> FUN_01E1782C
# mode 1 -> call 0x01E1786C. THIS ALSO FIXES THE "CLASS DEPENDENCE":
# TID-PTT is an SPP target -> spp_connect -> close; Jabra is HFP -> no
# SPP site runs -> no close (E6). Target PROFILE, not device class.
#
# Patch: entry no-op at 0x01E173EE (after `push rets`): stock
# `c0 ff 40 a7` (mov r0,#0x1a740) -> `40 20 00 04` (mov r0,#0; pop pc) =
# return 0, close nothing. Callers tolerate it: spp_connect's busy path
# returns -2 without closing (retries harmlessly, return value ignored at
# 0x01E20F16); the 0xB mode-1 path returns 0. The outgoing page is NOT
# blocked (it runs through the scan SM + the 0xc/0xe/0x12/5 posts).
# E6 sanity: the fresh-pairing flow never calls spp_connect/0xB ->
# unchanged.
# SIDE EFFECTS: the app can never tear down the SPP channel on these
# flows; stale SPP sessions persist until power-cycle. NEXT WALL after
# this patch: the single SPP session itself (control block 0x1A740) -
# the TID-PTT's SPP cannot bind while the PC's holds the CID.
# --------------------------------------------------------------------------
SPPCLOSE_VA = 0x01E173EE
SPPCLOSE_CTX = bytes.fromhex("c0ff40a701000060")
SPPCLOSE_STATES = {
    "stock": bytes.fromhex("c0ff40a7"),
    "disabled": bytes.fromhex("40200004"),  # mov r0,#0; pop pc -> return 0
    "f3gate": bytes.fromhex("998140a7"),    # F3 gate trampoline @0x01E173EC spills here
}
SPPCLOSE_LABELS = {
    "stock": "spp_channel_disconnect() active",
    "disabled": "mov r0,#0; rts (spp_channel_disconnect disabled; UNTESTED)",
    "f3gate": "--gate-close trampoline present (mutually exclusive)",
}

# --------------------------------------------------------------------------
# --no-l2cap-disconnect (EXPERIMENTAL / UNTESTED): the L2CAP-level kill of
# the channel-close eviction - two sites that together cover every app path
# that can tear down an incumbent's L2CAP channels on a device switch.
#
# E10 HW evidence (2026-10-20, capture /tmp/e10.hcd): with spp_close and
# BOTH 0x4a posters NOP-ed (readback-verified), Paired -> TID-PTT -> Connect
# STILL closed the PC link - and this time the radio sent TWO L2CAP
# Disconnection Requests (ident 6 CID 65 + ident 7 CID 64, handle 1):
# ALL channels on the link, the signature of the l2cap_disconnect_all_
# channel walk, not the single-CID SPP path. The walk bypasses
# spp_channel_disconnect entirely (forces each channel state 0xd + pumps
# l2cap_run), and E9 only NOP-ed the two known POSTERS of 0x4a - the
# dispatcher branch itself and the direct l2cap_disconnect() callers
# (four in the SPP state machine, 0x01E235B8/0x01E2376A/0x01E23A50/
# 0x01E23BF4) remain live.
#
# Patch site 1: NOP the `je r11,#0x4a,0x01e17b20` dispatch branch at
#   0x01E17974 (stock `0b f8 d4 94` -> `00 00 00 00`). Code 0x4a now falls
#   through the je-chain to the default no-op (returns 0, debug-ring log
#   only) for EVERY caller, including any poster the E9 census missed.
#   Fall-through safe: next insn @0x01E17978 is the chain's next je.
# Patch site 2: entry no-op of l2cap_disconnect() at 0x01E173D0 (stock
#   `10 04 bf ea` -> `00 23 80 00` = mov r0,#0; rts). Kills every direct
#   caller at once (the four SPP-SM sites above + spp_channel_disconnect,
#   already NOP-ed by --no-spp-close, + any other). Return 0 = success:
#   callers advance their state machines while the channel stays open.
#   Pointer scan: no 32-bit LE refs to either address (direct calls only).
# SIDE EFFECTS: the app can never tear down ANY L2CAP channel (RFCOMM/AVDTP
# included) through these paths; stale channels persist until power-cycle.
# The 0x4a body's bookkeeping (FUN_01e16878 query + delays) is skipped -
# it sent nothing else. NEXT WALL if the close persists: something forces
# channel state 0xd + pumps l2cap_run outside both sites (deeper walk in
# the stack task; would need the l2cap_run send-gate itself).
# --------------------------------------------------------------------------
L2CAPDISC_BRANCH_VA = 0x01E17974
L2CAPDISC_ENTRY_VA = 0x01E173D0
L2CAPDISC_BRANCH_CTX = bytes.fromhex("0bf8d49400ff58b0")
L2CAPDISC_ENTRY_CTX = bytes.fromhex("1004bfeab1fa0049")
L2CAPDISC_BRANCH_STATES = {
    "stock": bytes.fromhex("0bf8d494"),
    "disabled": bytes.fromhex("00000000"),  # nop; nop -> 0x4a falls to default
}
L2CAPDISC_ENTRY_STATES = {
    "stock": bytes.fromhex("1004bfea"),
    "disabled": bytes.fromhex("00238000"),  # mov r0,#0; rts -> disconnect no-op
    "f3gate": bytes.fromhex("c4eab581"),    # F3 gate trampoline replaces the entry
}
L2CAPDISC_LABELS = {
    "stock": "l2cap disconnect path active",
    "disabled": "nop / mov r0,#0; rts (l2cap disconnect disabled; UNTESTED)",
    "f3gate": "--gate-close trampoline present (mutually exclusive)",
}

# --------------------------------------------------------------------------
# --gate-close (EXPERIMENTAL / UNTESTED, ch.30 F3): CONDITIONAL close gate.
#
# E11 (ch.27 SS27.17/27.18) proved the evictor on every press path is the
# pair of close primitives themselves - entry-NOP-ing both kills eviction
# completely - but unconditionally: closes blocked OUTSIDE the connect press
# too, which deadlocked the app (SS27.19 "blocking closes -> deadlock") and
# corrupted normal operation. E1-E11 never tried gating the closes to the
# press window only.
#
# The press window flag already exists: RAM 0x1A662 bit 7 (page-pending),
# set by FUN_01E185F0(1) in the "connect selected device" press flow
# (0x01E61DEA) and cleared only by FUN_01E185F0(0) on the no-connection
# timeout path (0x01E7F032) or the scan-reset FUN_01E184A2. It is STICKY
# across a successful connect (level gate, see ch.30 SS30.11) - after the
# first manual menu-connect, channel closes stay skipped until BT-off /
# power-cycle; HCI-level disconnects (kick 0x01E074DE, BT toggle
# FUN_01E6076C) are NOT gated.
#
# Patch: 4-byte goto32 at each primitive entry into a stub in the second
# half of the code cave (CAVE2 = 0x01EA76DE + 68, after the BT-PTT2 code;
# 296 B free, 54 used). Stub: test 0x1A662 bit 7; set -> r0=0; rts (skip
# the close; the hw link still holds the caller's return - the stolen
# `push rets` has not run yet); clear -> replay the stolen instructions
# (push rets + [mov r0,#0x1A740] / [call 0x01E16938], the call
# re-encoded for the cave site) and goto back to entry+6. Stack balance
# verified both ways; stubs use r0/r1 which the bodies clobber anyway
# (r0 = cid in l2cap_disconnect must survive the test - it does, the test
# uses r1 there).
#
# Covered executors (all funnel through these two entries): Order-B press
# eviction = 0xB -> FUN_01E1782C(0,1,0) -> spp_connect busy path
# (0x01E1751E) -> spp_channel_disconnect; Order-A chokepoint close = same;
# LAB_01e20ef6 direct close = same; the 0x4a walk and the four SPP-SM
# direct callers -> l2cap_disconnect. Stock behavior is preserved for
# every close outside a press window (the E11 differentiator).
# CONFlicts: the trampolines overwrite the same 4 bytes as --no-spp-close
# (0x01E173EE) / --no-l2cap-disconnect (0x01E173D0) - mutually exclusive.
# --------------------------------------------------------------------------
GATE_FLAG_ADDR = 0x0001A662          # halfword; bit 7 = page-pending
GATE_CAVE2_VA = 0x01EA76DE + 68      # 0x01EA7722, free after the BT-PTT2 cave code
GATE_SPP_TRAMP_VA = 0x01E173EC       # spp_channel_disconnect() entry
GATE_L2CAP_TRAMP_VA = 0x01E173D0     # l2cap_disconnect() entry
GATE_SPP_STUB_VA = GATE_CAVE2_VA
GATE_L2CAP_STUB_VA = GATE_CAVE2_VA + 28


def _gate_stubs():
    """(spp_stub, l2cap_stub) gate stubs for the second cave half."""
    def stub(dst, reg, resume, replay):
        a = bytearray()
        a += (b"\xc0\xff" if reg == 0 else b"\xc1\xff") + \
            GATE_FLAG_ADDR.to_bytes(4, "little")        # rN = &flag
        a += b"\x08\x40" if reg == 0 else b"\x19\x40"   # rN = b[rN+0] (u)
        a += b"\x80\xa7" if reg == 0 else b"\x99\xa7"   # rN = rN >> 7
        a += encode_branch2(dst + len(a), dst + 0x10, neq=False, reg=reg)
        a += b"\x40\x20"                                # r0 = 0
        a += b"\x80\x00"                                # rts (hw link, nothing pushed)
        a += b"\x10\x04"                                # [--sp] = rets   (replay)
        a += replay                                     # stolen instrs (site-relative!)
        a += encode_goto32(dst + len(a), resume)
        return bytes(a)
    spp = stub(GATE_SPP_STUB_VA, 0, 0x01E173F4,
               b"\xc0\xff" + (0x1A740).to_bytes(4, "little"))   # mov r0,#0x1A740
    l2 = stub(GATE_L2CAP_STUB_VA, 1, 0x01E173D6,
              encode_call(GATE_L2CAP_STUB_VA + 0x12, 0x01E16938))  # find channel
    return spp, l2


GATE_SPP_STUB, GATE_L2CAP_STUB = _gate_stubs()
GATE_CAVE2_IMG = GATE_SPP_STUB + GATE_L2CAP_STUB
GATE_CAVE2_LEN = len(GATE_CAVE2_IMG)                   # 54
GATE_SPP_TRAMP = encode_goto32(GATE_SPP_TRAMP_VA, GATE_SPP_STUB_VA)
GATE_L2CAP_TRAMP = encode_goto32(GATE_L2CAP_TRAMP_VA, GATE_L2CAP_STUB_VA)
GATE_SPP_CTX = bytes.fromhex("1004c0ff")              # push rets; mov r0,#0x1a740
GATE_L2CAP_CTX = bytes.fromhex("1004bfea")            # push rets; call find_channel

# --------------------------------------------------------------------------
# --r1-conditional-kill (EXPERIMENTAL / UNTESTED, ch.30 R1-a): CONDITIONAL
# cmd-5 incumbent kill.
#
# The cmd-5 cleanup loop (FUN_01e21af8 case 5, ch.30 SS30.13 Q1/Q4/Q5/Q6)
# kills EVERY inused conn slot whose state halfword (+8) is 0:
# `call FUN_01e08a94(slot)` -> controller 0xCFE disconnect-by-address,
# reason 0x13.  That is the press-time incumbent killer behind every
# surviving eviction (M3-A, F3V2-B, F3V3-B r2).  F4 (NOP the call) is a
# regression: the phantom-repair flow (Paired->Connect on the boot phantom)
# depends on the kill, and the page path's already-connected address guard
# (FUN_01e16824) blocks a same-device re-page without it.
#
# R1-a makes the kill conditional instead of removing it.  Hook: replace
# the 4-byte `call` at 0x01E21EF4 with `call` to a 50-byte cave at
# 0x01EA7758 (free run after BT-PTT2 code + F3 gate stubs; region verified
# all-zero in v44/v45/v50, pointer-scan clean).  Cave predicate:
#   kill iff  handle(slot+6) == 0            (stuck slot, walker needs it)
#      OR     paired-list ptr [0xB468] == 0  (not in Paired UI -> stock)
#      OR     slot addr == selected addr     (repair flow -> stock)
#   else skip kill (goal: different device selected, incumbent survives;
#   the page to the selected target then fires on the E6-proven path).
# Selected-device source (SS Q6a): [[0xB468] + [0x102D0]*0xC + 8] (the same
# heap double-deref the settings-Connect handlers FUN_01e6ec9e/FUN_01e66ef8
# use); 0xB468 is zeroed when the Paired screen exits, so any non-UI cmd-5
# poster (BT-off, power) takes the stock kill path.
# Register contract at hook (verified, ch.30 SS30.13): r0 = slot ptr,
# r4 = slot+15 LIVE, r14/r6/r7 live; cave clobbers only r1/r2/r3 (dead
# after the call) and uses no stack.  Both exits land at stock 0x01E21EF8
# (tail-call KILL via goto; SKIP via rts returning to the loop).
# Mutually exclusive with --no-cmd5-kill (same 4 bytes).
# --------------------------------------------------------------------------
R1_KILL_HOOK_VA = 0x01E21EF4
R1_KILL_CTX = bytes.fromhex("bfeace35")               # stock call FUN_01e08a94
R1_KILLER_VA = 0x01E08A94
R1_LIST_PTR_ADDR = 0x0000B468                         # paired-list heap ptr
R1_LIST_IDX_ADDR = 0x000102D0                         # selection index byte
R1_CAVE_VA = 0x01EA7758                               # free (434 B run)
R1_CAVE_BYTES = bytes.fromhex(
    "09638142"            # r1 = h[r0+6]; if (r1 != 0) goto +4  (handle)
    "fbea9a09"            # goto 0x01E08A94                     (KILL tail)
    "42e068b4"            # r2 = 0xB468
    "2260"                # r2 = [r2+0]                         (list ptr)
    "725a"                # if (r2 == 0) goto KILL              (list dead)
    "c3ffd0020100"        # r3 = 0x102D0                        (17-bit mov)
    "3b40"                # r3 = b[r3+0]                        (index)
    "e3e10c30"            # r3 = r3 * 0xC                       (mul)
    "2318"                # r3 += r2
    "3362"                # r3 = [r3+8]                         (sel addr ptr)
    "0160"                # r1 = [r0+0]
    "3260"                # r2 = [r3+0]
    "2919"                # r1 ^= r2
    "0a62"                # r2 = h[r0+4]
    "2919"                # r1 ^= r2
    "3b62"                # r3 = h[r3+4]
    "3919"                # r1 ^= r3  (r1 = XOR of all 6 address bytes)
    "714a"                # if (r1 == 0) goto KILL  (same device)
    "8000"                # rts                       (skip kill)
)
R1_KILL_HOOK = encode_call(R1_KILL_HOOK_VA, R1_CAVE_VA)

# The r1condkill hook lives at CMD5KILL_VA, so teach the cmd5kill state table
# about it: find_app_start() validates EVERY patch's context, and an image
# carrying the conditional hook must still be recognised (and labelled).
CMD5KILL_STATES["conditional"] = R1_KILL_HOOK
CMD5KILL_LABELS["conditional"] = (
    "call cave 0x%08X (R1 conditional kill; --r1-conditional-kill)" % R1_CAVE_VA
)

# --------------------------------------------------------------------------
# --r1-walker-kill (EXPERIMENTAL / UNTESTED, ch.30 SS30.14.6 R1-b): move the
# press-time incumbent kill from the cmd-5 loop (field-FROZE as R1-a: the
# selection cell there is race-stale / unvalidated on the Paired-screen path)
# to the WALKER page-post site, where the armed target cell 0x10E34 is fresh
# (CON pump cases 8/0xb write it, then call the walker synchronously).
# Hook = the `call 0x01E1792E` at 0x01E60DE4 (walker FUN_01e60d34; r0=1, r1=6,
# r2=0x10E34 live at entry; r4-r11 live -> callee-saved, handled by the
# compiled prologue).  Cave2 (official JieLi clang -target pi32v2 -mcpu=r3
# -Oz from C, objdump-verified, /tmp/opencode/cave2.{c,o}): scan the two conn
# slots (0x1A5B8/0x1A5D4, stride 0x1C); if inused (b[slot+0x12] & 0x20) AND
# mask h[slot+8]==0 AND slot[0..5] == [0x10E34] -> tail-call the disconnect-
# by-address executor 0x01E08A94(r0=slot) and RETURN (skip this page post;
# the walker's 6 s rearm retries once the record is gone).  Otherwise tail-
# call 0x01E1792E(1,6,0x10E34) = the original page post, different-device
# incumbents untouched.  Combined with NOP'ing the cmd-5 kill (same effect as
# --no-cmd5-kill; that flag alone = F4, field-FROZE repairs because nothing
# killed the same-address stuck record - cave2 cures exactly that).
# Mutually exclusive with --r1-conditional-kill (same cave region) and
# --no-cmd5-kill (subsumed).
# --------------------------------------------------------------------------
R1B_HOOK_VA = 0x01E60DE4
R1B_HOOK_CTX = bytes.fromhex("bdeaa3b5")               # stock call 0x01E1792E
R1B_CAVE_VA = 0x01EA7758                               # free (434 B run)
R1B_CAVE_BYTES = bytes.fromhex(
    "7404c0ffb8a50100c1ff340e010002e1"   # push {rets,r4}; r0=0x1A5B8; r1=0x10E34; r2=r0+56
    "380050ee02410b6454e8092883480360"   # loop: r4=b[slot+18]; r3=h[slot+8]; if((r4&32)==0) next; if(r3!=0) next; r3=[slot]
    "146084e804300b621c6204e80b30c03c"   # r4=[tgt]; if(r3!=r4) next; r3=h[slot+4]; r4=h[tgt+4]; if(r3==r4) KILL; r0+=28
    "82e9ef011216c3ff2e79e10140214126"   # if(r0<r2) loop; r2=r1; r3=0x01E1792E; r0=1; r1=6
    "3404d300"                           # pop {rets,r4}; goto r3   (PAGE POST tail-call)
    "c1ff948ae0013404d100"               # KILL: r1=0x01E08A94; pop {rets,r4}; goto r1 (r0=slot)
)
R1B_HOOK = encode_call(R1B_HOOK_VA, R1B_CAVE_VA)

# --------------------------------------------------------------------------
# --cmd5-target (R1-e, designed 2026-10-28, ch. 30 §30.14.11 + ch. 31):
# targeted cmd-5 incumbent kill + press-time target store. The root defect:
# the cmd-5 kill loop (ring consumer FUN_01e21af8 case 5, BTSTACK task) kills
# every inused slot whose mask halfword is 0 — and SPP accessories keep
# mask==0 while LIVE, so a Paired->Connect press on device B kills a live
# device A (the class-dependent evictor of E7/F3V3-B). R1-c's handle test
# fixed that but froze on same-address repair: the page guard FUN_01e16824
# (call @0x01E21E76) refuses to page an address that still holds an inused
# record, so the kill must remove the TARGET's record and nobody else's.
# R1-a failed because reading the UI selection cell at cmd-5 time is
# race-stale; R1-e instead STORES the pressed device's address into the
# stack's own saved-target cell 0x0001A5F1 (written by ring cmd-0 @0x01E21C44
# via `rep 4 6`) at press time, in the app task, where the list pointer r5
# and index offset r4 are live. Two hooks, both running on the correct task:
#   presstore  @0x01E6ECDA — the settings-press cmd-5 post `call 0x01E1792E`
#              (r0=5, r1=0, r2=0 at 0x01E6ECD4-8) becomes a call to a 32-byte
#              cave: recompute [[r5]+r4+8] (selected BD_ADDR, the exact load
#              the same handler does at 0x01E6ECE4), copy 6 B to 0x0001A5F1
#              with the stock `rep 4 6` block move, then replay the original
#              post (r0=5, r1=0, r2=0, call 0x01E1792E) and rts.
#   cmd5target @0x01E21EF0 — the mask load+test `19 60 81 42` becomes a goto
#              to a 38-byte cave: kill iff handle@slot+6 == 0 (stuck record,
#              R1-c's liveness test) OR slot[0..5] == [0x0001A5F1] (the
#              pressed device — repair-any-class); every other inused slot
#              survives -> goal multipoint. Loop continues at 0x01E21EF8
#              either way (r4/r14 live across the killer call, r0-r3 scratch;
#              the XOR-fold address compare is R1-a's, byte-identical forms).
# Cave run 0x01EA76DE: F3-v3 uses up to 0x01EA7757, the r1cave window ends at
# 0x01EA778A and the r1bcave window (76 B) ends at 0x01EA77A4, D1 (R1-f)
# reserves 0x01EA7758..63 — R1-e caves sit at 0x01EA77A8 and 0x01EA77D0
# (ALLZERO in v44/v45/v50, inside the pointer-scan-clean run). Mutually
# exclusive with the other cmd-5 variants.
# --------------------------------------------------------------------------
CMD5T_HOOK_VA = 0x01E21EF0
CMD5T_HOOK_CTX = bytes.fromhex("19608142")     # r1=h[r1+0]; if(r1!=0) skip
CMD5T_KILLER_VA = 0x01E08A94                   # disconnect-by-address(r0=slot)
CMD5T_LOOPCONT_VA = 0x01E21EF8                 # r0 = r4 + 13 (next slot)
CMD5T_SAVE_VA = 0x0001A5F1                     # saved-target cell (6 B)
CMD5T_CAVE_VA = 0x01EA77A8
_c = CMD5T_CAVE_VA
CMD5T_CAVE_BYTES = (
    bytes.fromhex("0963")                       # r1 = h[r0+6]   (ACL handle)
    + encode_branch2(_c + 2, _c + 0x0C, neq=True, reg=1)
    + encode_call(_c + 4, CMD5T_KILLER_VA)     # KILL: killer(r0=slot)
    + encode_goto32(_c + 8, CMD5T_LOOPCONT_VA)
    + bytes.fromhex("c3ff") + CMD5T_SAVE_VA.to_bytes(4, "little")
    + bytes.fromhex("0160")                     # r1 = [r0+0]
    + bytes.fromhex("3260")                     # r2 = [r3+0]
    + bytes.fromhex("2919")                     # r1 ^= r2
    + bytes.fromhex("0a62")                     # r2 = h[r0+4]
    + bytes.fromhex("2919")                     # r1 ^= r2
    + bytes.fromhex("3b62")                     # r3 = h[r3+4]
    + bytes.fromhex("3919")                     # r1 ^= r3  (0 = same device)
    + encode_branch2(_c + 0x20, _c + 4, neq=False, reg=1)   # -> KILL
    + encode_goto32(_c + 0x22, CMD5T_LOOPCONT_VA)           # skip this slot
)
assert len(CMD5T_CAVE_BYTES) == 0x26
CMD5T_HOOK = encode_goto32(CMD5T_HOOK_VA, CMD5T_CAVE_VA)

PRESST_HOOK_VA = 0x01E6ECDA                     # settings-press cmd-5 post
PRESST_HOOK_CTX = bytes.fromhex("bdea2846")     # stock call 0x01E1792E
PRESST_POSTER_VA = 0x01E1792E
PRESST_CAVE_VA = 0x01EA77D0
PRESST_CAVE_BYTES = (
    bytes.fromhex("5060")                       # r0 = [r5+0]   (list base)
    + bytes.fromhex("4018")                     # r0 += r4      (idx*0xC)
    + bytes.fromhex("0062")                     # r0 = [r0+8]   (BD_ADDR ptr)
    + bytes.fromhex("0116")                     # r1 = r0       (rep source)
    + bytes.fromhex("c0ff") + CMD5T_SAVE_VA.to_bytes(4, "little")
    + bytes.fromhex("108512078207")             # rep 4 6 { b[r0++] = b[r1++] }
    + bytes.fromhex("4025" "4120" "4220")       # r0=5, r1=0, r2=0
    + encode_call(PRESST_CAVE_VA + 0x1A, PRESST_POSTER_VA)
    + bytes.fromhex("8000")                     # rts -> 0x01E6ECDE
)
assert len(PRESST_CAVE_BYTES) == 0x20
PRESST_HOOK = encode_call(PRESST_HOOK_VA, PRESST_CAVE_VA)

# The cmd5target hook overwrites the low half of the cmd5handle site, so
# teach that state table (and thus find_app_start/--show) about it.
CMD5HANDLE_STATES["target"] = CMD5T_HOOK[:2]
CMD5HANDLE_LABELS["target"] = (
    "goto cave 0x%08X (cmd-5 target kill; --cmd5-target)" % CMD5T_CAVE_VA
)


# Kept for tools/verify_actions.py: the native body addresses.
ODPTT_PRESS_VA = PF_BODY8_VA
ODPTT_RELEASE_VA = REL_OD_BODY_VA

# --------------------------------------------------------------------------
# key actions (--PTT / --PTT2 / --OD-PTT, see the module docstring)
#
# Actions are matched case-insensitively; BT-PTT / OD-PTT also accept the
# spellings BTPTT / ODPTT / BT_PTT / OD_PTT and "BT PTT" / "OD PTT".
# --------------------------------------------------------------------------
ACTIONS = ("PTT", "PTT2", "BT-PTT", "BT-PTT2", "OD-PTT")
_ACTION_ALIASES = {
    "PTT": "PTT", "PTT2": "PTT2",
    "BT-PTT": "BT-PTT", "BTPTT": "BT-PTT", "BT_PTT": "BT-PTT",
    "BT-PTT2": "BT-PTT2", "BTPTT2": "BT-PTT2", "BT_PTT2": "BT-PTT2",
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
    if "BT-PTT2" in (a7, a8):
        names += ["pfhandler", "pfcave"]
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

    BT-PTT2 labels: "BT PTT2\\0" (8 B) over "PTT2"+NET[0:3] when no entry
    still reads "PTT2"; "BT2\\0" (4 B) over Russian "NET" when one does;
    when BOTH BT actions are in the pair, BT-PTT2 takes "BT2\\0" over the
    first 4 bytes of "PTT2\\0" (the NUL at +4 survives) and BT-PTT takes
    "BT PTT\\0" over "NET" exactly - the two placements never overlap.
    Every BT-PTT2 placement destroys Russian "NET", so its three pointers
    move to "Net" just like for BT-PTT.
    """
    label_va = {"PTT": STR_PTT_VA, "PTT2": STR_PTT2_VA, "OD-PTT": STR_OD_PTT_VA}
    bt_needed = "BT-PTT" in (a7, a8)
    bt2_needed = "BT-PTT2" in (a7, a8)
    # "PTT2" must stay readable whenever an entry still points at it
    keep_ptt2 = "PTT2" in (a7, a8)
    bt_at = _BT_PTT_AT_NET if (bt_needed and (keep_ptt2 or bt2_needed)) else _BT_PTT_AT_PTT2
    label_va["BT-PTT"] = bt_at
    if bt2_needed:
        label_va["BT-PTT2"] = (
            STR_PTT2_VA if bt_needed
            else (_RU_NET_AT if keep_ptt2 else STR_PTT2_VA))

    sites = []
    if bt_needed:
        if bt_at == _BT_PTT_AT_NET:
            sites.append((_BT_PTT_AT_NET, _RU_NET, b"BT PTT\0"))
        else:
            sites.append((_BT_PTT_AT_PTT2, b"PTT2\0" + _RU_NET[:2], b"BT PTT\0"))
    if bt2_needed:
        if bt_needed:
            sites.append((STR_PTT2_VA, b"PTT2", b"BT2\0"))
        elif keep_ptt2:
            sites.append((_RU_NET_AT, _RU_NET[:4], b"BT2\0"))
        else:
            sites.append((STR_PTT2_VA, b"PTT2\0" + _RU_NET[:3], b"BT PTT2\0"))
    if a7 != "PTT2":
        sites += [(p, _ptr(STR_PTT2_VA), _ptr(label_va[a7]))
                  for p in PF_LIST_PTT2_PTRS]
    if a8 != "OD-PTT":
        sites += [(p + 4, _ptr(STR_OD_PTT_VA), _ptr(label_va[a8]))
                  for p in PF_LIST_PTT2_PTRS]
    if bt_needed or bt2_needed:
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
    if bt_needed or bt2_needed:
        guards.append((STR_RU_NO_VA, "\u041d\u0435\u0442\0".encode()))
    return sites, guards


def _combo_desc(a7, a8):
    if (a7, a8) == ("PTT2", "OD-PTT"):
        return 'menu options keep their stock labels "PTT2" / "OD PTT"'
    return 'PF S Press labels: value 7 -> "%s", value 8 -> "%s" (all languages)' % (
        _MENU_LABEL[a7], _MENU_LABEL[a8])


_MENU_LABEL = {"PTT": "PTT", "PTT2": "PTT2", "BT-PTT": "BT PTT",
               "BT-PTT2": "BT PTT2", "OD-PTT": "OD PTT"}

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


def build_patches(duplex_mode=4, ptt2_action="PTT2", odptt_action="OD-PTT",
                  conn_num=None, no_kick=False, force_page_scan=False,
                  force_role_keep=False, no_disconnect_13=False,
                  no_pairing_kick=False, no_cleanup_kick=False,
                  no_l2cap_teardown=False, no_spp_close=False,
                  no_l2cap_disconnect=False, gate_close=False,
                  no_cmd5_kill=False, r1_conditional_kill=False,
                  r1_walker_kill=False, cmd5_handle=False,
                  cmd5_target=False):
    """Return the patch table, with the `duplex` patch's target selected by
    `duplex_mode` (see DUPLEX_LABELS) and the `pflabels` multi-patch built
    for the (--PTT2, --OD-PTT) action pair (see PF_COMBO_PATCHES). The
    other label variants stay in PF_LABEL_VARIANTS, detection-only, so an
    image patched with a different combination is still recognised. The
    stock pair has no label patch at all. `conn_num` (1 or 2) selects the
    target of the experimental stack connection-count gate (see CONN_NUM_VA);
    `no_kick` disables the app's disconnect kick (see NOKICK_VA);
    `force_page_scan` keeps page scan enabled while connected (see
    PAGESCAN_VA); `force_role_keep` forces the ACL accept role to keep-role
    (see ROLEKEEP_VA); `no_disconnect_13` disables the app's reason-0x13
    disconnect executor (see DISC13_VA); `no_pairing_kick` disables the
    app's reason-0x16 pairing disconnect-all executor (see
    PAIRKICK_ALL_VA / PAIRKICK_ONE_VA); `no_cleanup_kick` disables the three
    remaining 0x13-capable cleanup executors (see CLEANUPKICK_VAR_VA /
    CLEANUPKICK_ORPHAN_VA / CLEANUPKICK_PROF_VA); `no_l2cap_teardown` stops
    the app's L2CAP channel-close posters of user_send_cmd_prepare(0x4a)
    (see L2CAPTEARDOWN_UI_VA / L2CAPTEARDOWN_MODE_VA); `no_spp_close` no-ops
    spp_channel_disconnect() (see SPPCLOSE_VA); `no_l2cap_disconnect` kills
    the 0x4a dispatch branch and the l2cap_disconnect() entry (see
    L2CAPDISC_BRANCH_VA / L2CAPDISC_ENTRY_VA); `gate_close` installs the
    conditional close gate: both close-primitive entries jump to cave stubs
    that skip the close while the press-window page-pending flag
    (GATE_FLAG_ADDR bit 7) is set and run stock otherwise (see
    GATE_SPP_TRAMP_VA / GATE_L2CAP_TRAMP_VA / GATE_CAVE2_VA; mutually
    exclusive with no_spp_close / no_l2cap_disconnect); `no_cmd5_kill` NOPs
    the bt-task cmd-5 cleanup loop's sole call to the controller
    disconnect-by-address helper (see CMD5KILL_VA), the press-time incumbent
    killer located 2026-10-25 (ch. 30 SS30.13 Q1). `r1_walker_kill` = R1-b:
    NOPs that cmd-5 kill AND installs the walker page-post conditional kill
    (see R1B_HOOK_VA / R1B_CAVE_VA; ch. 30 SS30.14.6). All entries are always
    present so --show recognises all states."""
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
    cn = str(conn_num) if conn_num is not None else "1"
    patches["connum"] = {
        "desc": "stack connection-count gate __set_user_ctrl_conn_num(1) -> %s"
                % cn,
        "va": CONN_NUM_VA,
        "new": CONN_NUM_STATES[cn],
        "states": CONN_NUM_STATES,
        "labels": CONN_NUM_LABELS,
        "target": cn,
        "ctx_va": CONN_NUM_CTX_VA,
        "ctx_base": CONN_NUM_CTX,
        "ctx_variant": _ctx_variant_fn(CONN_NUM_VA, CONN_NUM_CTX_VA,
                                       CONN_NUM_CTX),
    }
    nk = "disabled" if no_kick else "stock"
    patches["nokick"] = {
        "desc": "app disconnect kick (0x01E5B22A) -> %s" % nk,
        "va": NOKICK_VA,
        "new": NOKICK_STATES[nk],
        "states": NOKICK_STATES,
        "labels": NOKICK_LABELS,
        "target": nk,
        "ctx_va": NOKICK_CTX_VA,
        "ctx_base": NOKICK_CTX,
        "ctx_variant": _ctx_variant_fn(NOKICK_VA, NOKICK_CTX_VA, NOKICK_CTX),
    }
    ps = "forced" if force_page_scan else "stock"
    patches["pagescan"] = {
        "desc": "page-scan disable branch (0x01E18B0E) -> %s" % ps,
        "va": PAGESCAN_VA,
        "new": PAGESCAN_STATES[ps],
        "states": PAGESCAN_STATES,
        "labels": PAGESCAN_LABELS,
        "target": ps,
        "ctx_va": PAGESCAN_CTX_VA,
        "ctx_base": PAGESCAN_CTX,
        "ctx_variant": _ctx_variant_fn(PAGESCAN_VA, PAGESCAN_CTX_VA,
                                       PAGESCAN_CTX),
    }
    rk = "forced" if force_role_keep else "stock"
    patches["rolekeep"] = {
        "desc": "ACL accept role test (0x01E1A03A) -> %s" % rk,
        "va": ROLEKEEP_VA,
        "new": ROLEKEEP_STATES[rk],
        "states": ROLEKEEP_STATES,
        "labels": ROLEKEEP_LABELS,
        "target": rk,
        "ctx_va": ROLEKEEP_CTX_VA,
        "ctx_base": ROLEKEEP_CTX,
        "ctx_variant": _ctx_variant_fn(ROLEKEEP_VA, ROLEKEEP_CTX_VA,
                                       ROLEKEEP_CTX),
    }
    d13 = "disabled" if no_disconnect_13 else "stock"
    patches["disc13"] = {
        "desc": "app disconnect executor (0x01E178CE) -> %s" % d13,
        "va": DISC13_VA,
        "new": DISC13_STATES[d13],
        "states": DISC13_STATES,
        "labels": DISC13_LABELS,
        "target": d13,
        "ctx_va": DISC13_CTX_VA,
        "ctx_base": DISC13_CTX,
        "ctx_variant": _ctx_variant_fn(DISC13_VA, DISC13_CTX_VA,
                                       DISC13_CTX),
    }
    pk = "disabled" if no_pairing_kick else "stock"
    patches["pairkickall"] = {
        "desc": "app pairing kick, disconnect-all loop (0x01E21DE4) -> %s" % pk,
        "va": PAIRKICK_ALL_VA,
        "new": PAIRKICK_ALL_STATES[pk],
        "states": PAIRKICK_ALL_STATES,
        "labels": PAIRKICK_LABELS,
        "target": pk,
        "ctx_va": PAIRKICK_ALL_VA,
        "ctx_base": PAIRKICK_ALL_CTX,
        "ctx_variant": _ctx_variant_fn(PAIRKICK_ALL_VA, PAIRKICK_ALL_VA,
                                       PAIRKICK_ALL_CTX),
    }
    patches["pairkickone"] = {
        "desc": "app pairing kick, single disconnect (0x01E21EC4) -> %s" % pk,
        "va": PAIRKICK_ONE_VA,
        "new": PAIRKICK_ONE_STATES[pk],
        "states": PAIRKICK_ONE_STATES,
        "labels": PAIRKICK_LABELS,
        "target": pk,
        "ctx_va": PAIRKICK_ONE_VA,
        "ctx_base": PAIRKICK_ONE_CTX,
        "ctx_variant": _ctx_variant_fn(PAIRKICK_ONE_VA, PAIRKICK_ONE_VA,
                                       PAIRKICK_ONE_CTX),
    }
    c5 = "disabled" if (no_cmd5_kill or r1_walker_kill) else "stock"
    patches["cmd5kill"] = {
        "desc": "bt-task cmd-5 cleanup incumbent kill, sole call to 0x01E08A94 "
                "(0x01E21EF4) -> %s" % c5,
        "va": CMD5KILL_VA,
        "new": CMD5KILL_STATES[c5],
        "states": CMD5KILL_STATES,
        "labels": CMD5KILL_LABELS,
        "target": c5,
        "ctx_va": CMD5KILL_VA,
        "ctx_base": CMD5KILL_CTX,
        "ctx_variant": _ctx_variant_fn(CMD5KILL_VA, CMD5KILL_VA, CMD5KILL_CTX),
    }
    c5h = "handle" if cmd5_handle else "stock"
    patches["cmd5handle"] = {
        "desc": "bt-task cmd-5 stuck-slot test load (0x01E21EF0) -> %s" % c5h,
        "va": CMD5HANDLE_VA,
        "new": CMD5HANDLE_STATES[c5h],
        "states": CMD5HANDLE_STATES,
        "labels": CMD5HANDLE_LABELS,
        "target": c5h,
        "ctx_va": CMD5HANDLE_CTX_VA,
        "ctx_base": CMD5HANDLE_CTX,
        "ctx_variant": _ctx_variant_fn(CMD5HANDLE_VA, CMD5HANDLE_CTX_VA,
                                       CMD5HANDLE_CTX),
    }
    if r1_conditional_kill:
        r1k = "conditional"
    elif no_cmd5_kill or r1_walker_kill:
        r1k = "disabled"
    else:
        r1k = "stock"
    patches["r1condkill"] = {
        "desc": "bt-task cmd-5 cleanup incumbent kill, sole call to 0x01E08A94 "
                "(0x01E21EF4) -> %s" % r1k,
        "va": R1_KILL_HOOK_VA,
        "new": {"conditional": R1_KILL_HOOK, "disabled": b"\x00\x00\x00\x00",
                "stock": R1_KILL_CTX}[r1k],
        "states": {"stock": R1_KILL_CTX, "conditional": R1_KILL_HOOK,
                   "disabled": b"\x00\x00\x00\x00"},
        "labels": {"stock": "call 0x01E08A94 (cmd-5 kill active, unconditional)",
                   "conditional": "call cave 0x01EA7758 (kill only stuck/"
                                  "same-device/not-in-Paired-UI)",
                   "disabled": "NOP (cmd-5 kill disabled; --no-cmd5-kill/"
                               "--r1-walker-kill)"},
        "target": r1k,
        "ctx_va": R1_KILL_HOOK_VA,
        "ctx_base": R1_KILL_CTX,
        "ctx_variant": _ctx_variant_fn(R1_KILL_HOOK_VA, R1_KILL_HOOK_VA,
                                       R1_KILL_CTX),
    }
    patches["r1cave"] = {
        "desc": "code cave @0x%08X: R1 conditional-kill predicate" % R1_CAVE_VA,
        "va": R1_CAVE_VA,
        "new": R1_CAVE_BYTES if r1_conditional_kill
               else b"\x00" * len(R1_CAVE_BYTES),
        "states": {"native": b"\x00" * len(R1_CAVE_BYTES),
                   "r1cave": R1_CAVE_BYTES},
        "labels": {"native": "erased (all zero)",
                   "r1cave": "predicate: kill iff stuck | list-dead | same-dev"},
        "target": "r1cave" if r1_conditional_kill else "native",
        "ctx_va": R1_CAVE_VA,
        "ctx_base": b"\x00" * len(R1_CAVE_BYTES),
        "ctx_variant": _ctx_variant_fn(R1_CAVE_VA, R1_CAVE_VA,
                                       b"\x00" * len(R1_CAVE_BYTES)),
    }
    # r1bcave shares r1cave's VA (same cave region, mutually exclusive
    # payloads): teach each state table about the other's bytes so every
    # image stays recognised, and make the non-active entry write the
    # ACTIVE payload's bytes (zero-padded) so apply order can't clobber.
    R1B_PAD_R1 = (R1_CAVE_BYTES
                  + b"\x00" * (len(R1B_CAVE_BYTES) - len(R1_CAVE_BYTES)))
    patches["r1cave"]["states"]["r1bcave"] = R1B_CAVE_BYTES[:len(R1_CAVE_BYTES)]
    patches["r1cave"]["labels"]["r1bcave"] = "walker-kill cave (R1-b)"
    patches["r1bcave"] = {
        "desc": "code cave @0x%08X: R1-b walker conditional-kill predicate"
                % R1B_CAVE_VA,
        "va": R1B_CAVE_VA,
        "new": (R1B_CAVE_BYTES if r1_walker_kill else
                R1B_PAD_R1 if r1_conditional_kill else
                b"\x00" * len(R1B_CAVE_BYTES)),
        "states": {"native": b"\x00" * len(R1B_CAVE_BYTES),
                   "r1bcave": R1B_CAVE_BYTES,
                   "r1cave": R1B_PAD_R1},
        "labels": {"native": "erased (all zero)",
                   "r1bcave": "walker kill: kill iff same-addr stuck rec",
                   "r1cave": "R1-a predicate cave (dead hook)"},
        "target": "r1bcave" if r1_walker_kill else "native",
        "ctx_va": R1B_CAVE_VA,
        "ctx_base": b"\x00" * len(R1B_CAVE_BYTES),
        "ctx_variant": _ctx_variant_fn(R1B_CAVE_VA, R1B_CAVE_VA,
                                       b"\x00" * len(R1B_CAVE_BYTES)),
    }
    patches["r1bhook"] = {
        "desc": "walker FUN_01e60d34 page post, call 0x01E1792E (0x01E60DE4) "
                "-> %s" % ("r1bhook" if r1_walker_kill else "stock"),
        "va": R1B_HOOK_VA,
        "new": R1B_HOOK if r1_walker_kill else R1B_HOOK_CTX,
        "states": {"stock": R1B_HOOK_CTX, "r1bhook": R1B_HOOK},
        "labels": {"stock": "call 0x01E1792E (page post, stock)",
                   "r1bhook": "call cave 0x%08X (walker conditional kill)"
                              % R1B_CAVE_VA},
        "target": "r1bhook" if r1_walker_kill else "stock",
        "ctx_va": R1B_HOOK_VA,
        "ctx_base": R1B_HOOK_CTX,
        "ctx_variant": _ctx_variant_fn(R1B_HOOK_VA, R1B_HOOK_VA,
                                       R1B_HOOK_CTX),
    }
    c5t = "target" if cmd5_target else "stock"
    patches["cmd5target"] = {
        "desc": "bt-task cmd-5 kill test (0x01E21EF0) -> %s" % c5t,
        "va": CMD5T_HOOK_VA,
        "new": CMD5T_HOOK if cmd5_target else CMD5T_HOOK_CTX,
        "states": {"stock": CMD5T_HOOK_CTX,
                   "handle": bytes.fromhex("09638142"),
                   "target": CMD5T_HOOK},
        "labels": {"stock": "r1 = h[r1+0]; if (r1 != 0) skip (mask test)",
                   "handle": "r1 = h[r0+6] half changed (R1-c, --cmd5-handle)",
                   "target": "goto cave 0x%08X (kill iff stuck | same-as-"
                             "stored-target)" % CMD5T_CAVE_VA},
        "target": c5t,
        "ctx_va": CMD5T_HOOK_VA,
        "ctx_base": CMD5T_HOOK_CTX,
        "ctx_variant": _ctx_variant_fn(CMD5T_HOOK_VA, CMD5T_HOOK_VA,
                                       CMD5T_HOOK_CTX),
    }
    patches["cmd5tcave"] = {
        "desc": "code cave @0x%08X: R1-e cmd-5 target-kill predicate" % CMD5T_CAVE_VA,
        "va": CMD5T_CAVE_VA,
        "new": CMD5T_CAVE_BYTES if cmd5_target
               else b"\x00" * len(CMD5T_CAVE_BYTES),
        "states": {"native": b"\x00" * len(CMD5T_CAVE_BYTES),
                   "cmd5tcave": CMD5T_CAVE_BYTES},
        "labels": {"native": "erased (all zero)",
                   "cmd5tcave": "kill iff handle==0 | addr==0x0001A5F1"},
        "target": "cmd5tcave" if cmd5_target else "native",
        "ctx_va": CMD5T_CAVE_VA,
        "ctx_base": b"\x00" * len(CMD5T_CAVE_BYTES),
        "ctx_variant": _ctx_variant_fn(CMD5T_CAVE_VA, CMD5T_CAVE_VA,
                                       b"\x00" * len(CMD5T_CAVE_BYTES)),
    }
    ps = "stored" if cmd5_target else "stock"
    patches["presstore"] = {
        "desc": "settings-press cmd-5 post, call 0x01E1792E (0x01E6ECDA) "
                "-> %s" % ps,
        "va": PRESST_HOOK_VA,
        "new": PRESST_HOOK if cmd5_target else PRESST_HOOK_CTX,
        "states": {"stock": PRESST_HOOK_CTX, "stored": PRESST_HOOK},
        "labels": {"stock": "call 0x01E1792E (cmd-5 post, stock)",
                   "stored": "call cave 0x%08X (store selected addr -> "
                             "0x0001A5F1, replay post)" % PRESST_CAVE_VA},
        "target": ps,
        "ctx_va": PRESST_HOOK_VA,
        "ctx_base": PRESST_HOOK_CTX,
        "ctx_variant": _ctx_variant_fn(PRESST_HOOK_VA, PRESST_HOOK_VA,
                                       PRESST_HOOK_CTX),
    }
    patches["presstcave"] = {
        "desc": "code cave @0x%08X: R1-e press target store" % PRESST_CAVE_VA,
        "va": PRESST_CAVE_VA,
        "new": PRESST_CAVE_BYTES if cmd5_target
               else b"\x00" * len(PRESST_CAVE_BYTES),
        "states": {"native": b"\x00" * len(PRESST_CAVE_BYTES),
                   "presstcave": PRESST_CAVE_BYTES},
        "labels": {"native": "erased (all zero)",
                   "presstcave": "copy [[r5]+r4+8] 6 B -> 0x0001A5F1, post 5"},
        "target": "presstcave" if cmd5_target else "native",
        "ctx_va": PRESST_CAVE_VA,
        "ctx_base": b"\x00" * len(PRESST_CAVE_BYTES),
        "ctx_variant": _ctx_variant_fn(PRESST_CAVE_VA, PRESST_CAVE_VA,
                                       b"\x00" * len(PRESST_CAVE_BYTES)),
    }
    ck = "disabled" if no_cleanup_kick else "stock"
    patches["cleanupkickvar"] = {
        "desc": "app cleanup kick, variable-reason event (0x01E19AD0) -> %s" % ck,
        "va": CLEANUPKICK_VAR_VA,
        "new": CLEANUPKICK_VAR_STATES[ck],
        "states": CLEANUPKICK_VAR_STATES,
        "labels": CLEANUPKICK_LABELS,
        "target": ck,
        "ctx_va": CLEANUPKICK_VAR_VA,
        "ctx_base": CLEANUPKICK_VAR_CTX,
        "ctx_variant": _ctx_variant_fn(CLEANUPKICK_VAR_VA, CLEANUPKICK_VAR_VA,
                                       CLEANUPKICK_VAR_CTX),
    }
    patches["cleanupkickorphan"] = {
        "desc": "app cleanup kick, orphan-ACL cleanup (0x01E19B14) -> %s" % ck,
        "va": CLEANUPKICK_ORPHAN_VA,
        "new": CLEANUPKICK_ORPHAN_STATES[ck],
        "states": CLEANUPKICK_ORPHAN_STATES,
        "labels": CLEANUPKICK_LABELS,
        "target": ck,
        "ctx_va": CLEANUPKICK_ORPHAN_VA,
        "ctx_base": CLEANUPKICK_ORPHAN_CTX,
        "ctx_variant": _ctx_variant_fn(CLEANUPKICK_ORPHAN_VA,
                                       CLEANUPKICK_ORPHAN_VA,
                                       CLEANUPKICK_ORPHAN_CTX),
    }
    patches["cleanupkickprof"] = {
        "desc": "app cleanup kick, profile-record cleanup (0x01E20AB2) -> %s" % ck,
        "va": CLEANUPKICK_PROF_VA,
        "new": CLEANUPKICK_PROF_STATES[ck],
        "states": CLEANUPKICK_PROF_STATES,
        "labels": CLEANUPKICK_LABELS,
        "target": ck,
        "ctx_va": CLEANUPKICK_PROF_VA,
        "ctx_base": CLEANUPKICK_PROF_CTX,
        "ctx_variant": _ctx_variant_fn(CLEANUPKICK_PROF_VA,
                                       CLEANUPKICK_PROF_VA,
                                       CLEANUPKICK_PROF_CTX),
    }
    lt = "disabled" if no_l2cap_teardown else "stock"
    patches["l2capteardownui"] = {
        "desc": "app L2CAP teardown, connect-UI 0x4a post (0x01E61E22) -> %s" % lt,
        "va": L2CAPTEARDOWN_UI_VA,
        "new": L2CAPTEARDOWN_UI_STATES[lt],
        "states": L2CAPTEARDOWN_UI_STATES,
        "labels": L2CAPTEARDOWN_LABELS,
        "target": lt,
        "ctx_va": L2CAPTEARDOWN_UI_VA,
        "ctx_base": L2CAPTEARDOWN_UI_CTX,
        "ctx_variant": _ctx_variant_fn(L2CAPTEARDOWN_UI_VA,
                                       L2CAPTEARDOWN_UI_VA,
                                       L2CAPTEARDOWN_UI_CTX),
    }
    patches["l2capteardownmode"] = {
        "desc": "app L2CAP teardown, mode-setter 0x4a post (0x01E60188) -> %s" % lt,
        "va": L2CAPTEARDOWN_MODE_VA,
        "new": L2CAPTEARDOWN_MODE_STATES[lt],
        "states": L2CAPTEARDOWN_MODE_STATES,
        "labels": L2CAPTEARDOWN_LABELS,
        "target": lt,
        "ctx_va": L2CAPTEARDOWN_MODE_VA,
        "ctx_base": L2CAPTEARDOWN_MODE_CTX,
        "ctx_variant": _ctx_variant_fn(L2CAPTEARDOWN_MODE_VA,
                                       L2CAPTEARDOWN_MODE_VA,
                                       L2CAPTEARDOWN_MODE_CTX),
    }
    patches["l2capteardownapp"] = {
        "desc": "app L2CAP teardown, AT/SPP-dispatcher 0x4a post (0x01E4F804) -> %s" % lt,
        "va": L2CAPTEARDOWN_APP_VA,
        "new": L2CAPTEARDOWN_APP_STATES[lt],
        "states": L2CAPTEARDOWN_APP_STATES,
        "labels": L2CAPTEARDOWN_LABELS,
        "target": lt,
        "ctx_va": L2CAPTEARDOWN_APP_VA,
        "ctx_base": L2CAPTEARDOWN_APP_CTX,
        "ctx_variant": _ctx_variant_fn(L2CAPTEARDOWN_APP_VA,
                                       L2CAPTEARDOWN_APP_VA,
                                       L2CAPTEARDOWN_APP_CTX),
    }
    sc = "disabled" if no_spp_close else "stock"
    patches["sppclose"] = {
        "desc": "app spp_channel_disconnect() entry (0x01E173EE) -> %s" % sc,
        "va": SPPCLOSE_VA,
        "new": SPPCLOSE_STATES[sc],
        "states": SPPCLOSE_STATES,
        "labels": SPPCLOSE_LABELS,
        "target": sc,
        "ctx_va": SPPCLOSE_VA,
        "ctx_base": SPPCLOSE_CTX,
        "ctx_variant": _ctx_variant_fn(SPPCLOSE_VA,
                                       SPPCLOSE_VA,
                                       SPPCLOSE_CTX),
    }
    ld = "disabled" if no_l2cap_disconnect else "stock"
    patches["l2capdiscbranch"] = {
        "desc": "app 0x4a dispatch branch (0x01E17974) -> %s" % ld,
        "va": L2CAPDISC_BRANCH_VA,
        "new": L2CAPDISC_BRANCH_STATES[ld],
        "states": L2CAPDISC_BRANCH_STATES,
        "labels": L2CAPDISC_LABELS,
        "target": ld,
        "ctx_va": L2CAPDISC_BRANCH_VA,
        "ctx_base": L2CAPDISC_BRANCH_CTX,
        "ctx_variant": _ctx_variant_fn(L2CAPDISC_BRANCH_VA,
                                       L2CAPDISC_BRANCH_VA,
                                       L2CAPDISC_BRANCH_CTX),
    }
    patches["l2capdiscentry"] = {
        "desc": "app l2cap_disconnect() entry (0x01E173D0) -> %s" % ld,
        "va": L2CAPDISC_ENTRY_VA,
        "new": L2CAPDISC_ENTRY_STATES[ld],
        "states": L2CAPDISC_ENTRY_STATES,
        "labels": L2CAPDISC_LABELS,
        "target": ld,
        "ctx_va": L2CAPDISC_ENTRY_VA,
        "ctx_base": L2CAPDISC_ENTRY_CTX,
        "ctx_variant": _ctx_variant_fn(L2CAPDISC_ENTRY_VA,
                                       L2CAPDISC_ENTRY_VA,
                                       L2CAPDISC_ENTRY_CTX),
    }
    gc = "gated" if gate_close else "stock"
    patches["gatespptramp"] = {
        "desc": "spp_channel_disconnect() entry gate trampoline (0x01E173EC) -> %s" % gc,
        "va": GATE_SPP_TRAMP_VA,
        "new": GATE_SPP_TRAMP if gate_close else bytes.fromhex("1004c0ff"),
        "states": {"stock": bytes.fromhex("1004c0ff"),
                   "gated": GATE_SPP_TRAMP,
                   "e10": bytes.fromhex("10044020")},
        "labels": {"stock": "entry runs stock",
                   "gated": "goto cave stub (close skipped while page-pending)",
                   "e10": "--no-spp-close no-op present (mutually exclusive)"},
        "target": gc,
        "ctx_va": GATE_SPP_TRAMP_VA,
        "ctx_base": GATE_SPP_CTX,
        "ctx_variant": _ctx_variant_fn(GATE_SPP_TRAMP_VA,
                                       GATE_SPP_TRAMP_VA,
                                       GATE_SPP_CTX),
    }
    patches["gatel2captramp"] = {
        "desc": "l2cap_disconnect() entry gate trampoline (0x01E173D0) -> %s" % gc,
        "va": GATE_L2CAP_TRAMP_VA,
        "new": GATE_L2CAP_TRAMP if gate_close else bytes.fromhex("1004bfea"),
        "states": {"stock": bytes.fromhex("1004bfea"),
                   "gated": GATE_L2CAP_TRAMP,
                   "e11": bytes.fromhex("00238000")},
        "labels": {"stock": "entry runs stock",
                   "gated": "goto cave stub (close skipped while page-pending)",
                   "e11": "--no-l2cap-disconnect no-op present (mutually exclusive)"},
        "target": gc,
        "ctx_va": GATE_L2CAP_TRAMP_VA,
        "ctx_base": GATE_L2CAP_CTX,
        "ctx_variant": _ctx_variant_fn(GATE_L2CAP_TRAMP_VA,
                                       GATE_L2CAP_TRAMP_VA,
                                       GATE_L2CAP_CTX),
    }
    patches["gatecave"] = {
        "desc": "code cave @0x%08X: close-gate stubs (spp + l2cap)" % GATE_CAVE2_VA,
        "va": GATE_CAVE2_VA,
        "new": GATE_CAVE2_IMG if gate_close else b"\x00" * GATE_CAVE2_LEN,
        "states": {"native": b"\x00" * GATE_CAVE2_LEN, "gated": GATE_CAVE2_IMG},
        "labels": {"native": "erased (all zero)",
                   "gated": "gate stubs (flag test + replay + resume)"},
        "target": "gated" if gate_close else "native",
        "ctx_va": GATE_CAVE2_VA,
        "ctx_base": b"\x00" * GATE_CAVE2_LEN,
        "ctx_variant": _ctx_variant_fn(GATE_CAVE2_VA, GATE_CAVE2_VA,
                                       b"\x00" * GATE_CAVE2_LEN),
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
    # BT-PTT2 support code: key-0x2A TX-start trampoline + code cave.
    # Installed for every build so --show and app-offset detection recognise
    # them; only applied when pf_combo_patches() names them, i.e. when one of
    # the two options runs BT-PTT2.
    h2a_new = encode_goto32(H2A_TRAMP_VA, CAVE_VA) + b"\x00" * (H2A_TRAMP_LEN - 4)
    patches["pfhandler"] = {
        "desc": "key-0x2A TX-start tail -> BT-PTT2 cave handler",
        "va": H2A_TRAMP_VA,
        "new": h2a_new,
        "states": {"native": H2A_TRAMP_NATIVE, "bt2": h2a_new},
        "labels": {
            "native": "stock current-VFO TX-start tail",
            "bt2": "tail jumps to the cave handler (force-VFO-B aware)",
        },
        "target": "bt2",
        "ctx_va": H2A_TRAMP_VA,
        "ctx_base": H2A_TRAMP_NATIVE,
        "ctx_variant": _ctx_variant_fn(H2A_TRAMP_VA, H2A_TRAMP_VA, H2A_TRAMP_NATIVE),
    }
    cave_new = _cave_images()
    patches["pfcave"] = {
        "desc": "code cave @0x%08X: BT-PTT2 TX handler + press/release helpers"
                % CAVE_VA,
        "va": CAVE_VA,
        "new": cave_new,
        "states": {"native": b"\x00" * CAVE_LEN, "bt2": cave_new},
        "labels": {
            "native": "erased (all zero)",
            "bt2": "BT-PTT2 helper code",
        },
        "target": "bt2",
        "ctx_va": CAVE_VA,
        "ctx_base": b"\x00" * CAVE_LEN,
        "ctx_variant": _ctx_variant_fn(CAVE_VA, CAVE_VA, b"\x00" * CAVE_LEN),
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
        "BT-PTT / OD-PTT may also be written BTPTT / ODPTT / BT_PTT / OD_PTT.",
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
        "  PTT2     stock: TX forced to VFO B\n"
        "  PTT      TX on the current VFO, radio mic (menu shows \"PTT\")\n"
        "  BT-PTT   transmit the Bluetooth headset's mic (menu shows \"BT PTT\")\n"
        "  BT-PTT2  Bluetooth headset's mic, TX forced to VFO B / the second\n"
        "           channel (menu shows \"BT PTT2\", HW-confirmed 2026-09-30)\n"
        "  OD-PTT   stock one-key duplex (menu shows \"OD PTT\")\n"
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
        "  OD-PTT   stock one-key duplex\n"
        "  BT-PTT   transmit the Bluetooth headset's mic (menu shows \"BT PTT\")\n"
        "  BT-PTT2  Bluetooth headset's mic, TX forced to VFO B / the second\n"
        "           channel (menu shows \"BT PTT2\", HW-confirmed 2026-09-30)\n"
        "  PTT      TX on the current VFO, radio mic (menu shows \"PTT\")\n"
        "  PTT2     TX forced to VFO B (menu shows \"PTT2\")\n"
        "  Any action works here as long as --PTT2 differs from it.\n"
        "The two options must run DIFFERENT actions; every pair of distinct\n"
        "actions is supported, in either order:\n" + _PAIR_HELP,
    )
    ap.add_argument(
        "--conn-num",
        dest="conn_num",
        type=int,
        choices=(1, 2),
        default=None,
        help="MULTIPOINT (member of the HW-CONFIRMED E6 combo, 2026-10-08, "
        "ch. 27 SS27.11): number of Bluetooth "
        "connections the stack maintains. Stock is 1: a second device that "
        "connects EVICTS the first (hardware-confirmed, ch. 22 SS9B.6.1). "
        "2 rewrites the app's __set_user_ctrl_conn_num(1) init override to "
        "(2), asking the stack to hold two ACL links at once - e.g. a "
        "headset (HFP) plus a TID-PTT button (SPP). The app still tracks "
        "ONE remote device (RAM 0x102F0), so expect last-connected-wins "
        "for audio and mic routing. Findings ch. 22 SS9B.10.",
    )
    ap.add_argument(
        "--no-kick",
        dest="no_kick",
        action="store_true",
        help="MULTIPOINT (kick-NOP HW-confirmed 2026-10-05; E6 combo "
        "2026-10-08): disable the app's "
        "disconnect kick. The routine at 0x01E5B22A is the ONLY code that "
        "disconnects a BT device, and the app runs it before paging a "
        "second one - which is why a second device always evicts the "
        "first, even with --conn-num=2 (hardware-confirmed). Patching it "
        "to `r0 = 3; rts` (the stock no-connection return) stops all "
        "app-initiated disconnects, so a second device (e.g. a TID-PTT "
        "button joining while a headset holds HFP) may stay linked as a "
        "passive 'ghost' connection. Option A of Findings ch. 26 SS26.7: "
        "combine with --conn-num=2. SIDE EFFECTS: turning Bluetooth off "
        "and the menu disconnect no longer release the link "
        "(power-cycle instead); audio/mic routing for the second link is "
        "undefined.",
    )
    ap.add_argument(
        "--force-page-scan",
        dest="force_page_scan",
        action="store_true",
        help="MULTIPOINT (pages answered while connected, HW-observed "
        "2026-10-07; E6 combo 2026-10-08): keep page scan enabled "
        "while a link is up, so a SECOND device can connect TO the radio. "
        "With --no-kick the radio no longer evicts the first device, but "
        "it still answers no incoming pages once connected (btmon: 'Page "
        "Timeout'); the stack only re-enables page scan when "
        "is_1t2_connection() is false and the vendor's 1-to-2 scan logic "
        "in multi_bd.c is compiled EMPTY. NOP-ing the page-scan disable "
        "branch at 0x01E18B0E turns every 'disable' into an 'enable'. "
        "Option A2 of Findings ch. 26 SS26.9: combine with --no-kick and "
        "--conn-num=2. SIDE EFFECT: the radio is always connectable.",
    )
    ap.add_argument(
        "--force-role-keep",
        dest="force_role_keep",
        action="store_true",
        help="MULTIPOINT (experiment E4: FAILED standalone 2026-10-07 - role "
        "is not the trigger - but harmless in the E6 combo): accept incoming ACL "
        "links with the vendor keep-role parameter (0xAA) instead of the "
        "stock role 1 (become master). The stack task always accepts "
        "incoming ACLs (0x01E19E44 case 4); the role comes from a "
        "stack-config flag that is clear in this firmware, so the radio "
        "tries to become master of every link. When a headset already "
        "holds HFP the controller tears the second link down at the LL "
        "level ~644 ms after the page (btmon Connect Complete 0x13, ch. "
        "27); forcing keep-role is experiment E4 of the ch. 27 SS27.8 "
        "matrix - combine with --conn-num=2 --no-kick --force-page-scan. "
        "SCO setup is unaffected (it branches away before the patched "
        "test).",
    )
    ap.add_argument(
        "--no-disconnect-13",
        dest="no_disconnect_13",
        action="store_true",
        help="MULTIPOINT (E6 HW-CONFIRMED 2026-10-08: the incumbent link "
        "survives a radio-initiated join - multipoint works): disable the app's "
        "reason-0x13 disconnect executor. E3 (btmon, 2026-10-08) proved a "
        "SECOND eviction path beyond the kick: a radio-initiated headset "
        "join GRACEFULLY killed the incumbent PC SPP link (L2CAP "
        "disconnect + HCI Disconnect Complete 0x13) even with --no-kick. "
        "The executor is the call at 0x01E178CE (disconnect(handle,0x13) "
        "via 0x01E07B08) reached from the BT API dispatcher case 0x4A "
        "('disconnect current', fired by the UI 'connect selected device' "
        "flow) and stack dispatcher cmd 8/10. NOP-ing it stops all "
        "app-initiated 0x13 teardowns so the incumbent link survives the "
        "join - experiment E6 of Findings ch. 27 SS27.9: combine with "
        "--conn-num=2 --no-kick --force-page-scan. SIDE EFFECTS: menu "
        "disconnect and explicit disconnect commands no longer release "
        "links (power-cycle instead); app device state diverges from the "
        "link state.",
    )
    ap.add_argument(
        "--no-pairing-kick",
        dest="no_pairing_kick",
        action="store_true",
        help="MULTIPOINT (EXPERIMENTAL / UNTESTED): additionally NOP the "
        "app's reason-0x16 pairing disconnect-all executor (call sites "
        "0x01E21DE4 in the conn-array disconnect-all loop and 0x01E21EC4 "
        "single 0x16 disconnect, both via thunk 0x01E19492 -> 0x01E07B08). "
        "E6 showed already-paired joins no longer evict, but pairing-mode "
        "'connect' on a new device still kicks the incumbent via this path; "
        "NOP-ing it lets the radio page a new device while keeping the "
        "existing link (outgoing pages while connected are E6-proven). "
        "SIDE EFFECTS: pairing-mode teardown and 0x16 disconnect commands "
        "no longer release links; power-cycle instead. Requires the full "
        "multipoint recipe.",
    )
    ap.add_argument(
        "--no-cmd5-kill",
        dest="no_cmd5_kill",
        action="store_true",
        help="MULTIPOINT (EXPERIMENTAL / UNTESTED): NOP the bt-task cmd-5 "
        "cleanup loop's call to FUN_01e08a94 (0x01E21EF4), the sole caller "
        "site of the controller 0xCFE disconnect-by-address command "
        "(handler 0x01E0DDA4 -> executor FUN_01e091EA, reason 0x13). This "
        "is the press-time incumbent killer located 2026-10-25 (ch. 30 "
        "SS30.13 Q1): the Paired->Connect press posts cmd 5 at 0x01E61E18 "
        "(live in ALL E1-E11/F builds - E9 only killed the adjacent 0x4A "
        "post), which disconnected the incumbent at 0 s via a path touching "
        "none of the other NOP'd sites. Cmd 5 is fire-and-forget, so this "
        "NOP should not deadlock. SIDE EFFECTS: the 'connect selected "
        "device' cleanup no longer releases stale/idle links; power-cycle "
        "instead. Requires the full multipoint recipe.",
    )
    ap.add_argument(
        "--r1-conditional-kill",
        dest="r1_conditional_kill",
        action="store_true",
        help="MULTIPOINT (EXPERIMENTAL / UNTESTED): replace the cmd-5 "
        "cleanup loop's incumbent kill (0x01E21EF4) with a CALL to a "
        "50-byte predicate cave at 0x01EA7758 (ch. 30 SS30.13 R1-a). The "
        "cave kills iff the slot is stuck (handle==0), the paired list is "
        "not alive (BT-off/power-down paths keep stock behavior), or the "
        "slot's address equals the UI-selected device (phantom-repair keeps "
        "stock behavior); a DIFFERENT-device incumbent is kept, after which "
        "the page to the selected device still fires (E6-proven path). "
        "Unlike --no-cmd5-kill (F4, field-FAILED: wholesale NOP wedges the "
        "connect flow on any press) this preserves every stock cleanup "
        "function. Mutually exclusive with --no-cmd5-kill (same 4 bytes). "
        "FIELD-FAILED 2026-10-27 (freeze, ch. 30 SS30.14.6): the selection "
        "cell read at cmd-5 time is race-stale on the Paired-screen path. "
        "See --r1-walker-kill for the successor. Requires the full "
        "multipoint recipe.",
    )
    ap.add_argument(
        "--r1-walker-kill",
        dest="r1_walker_kill",
        action="store_true",
        help="MULTIPOINT R1-b (EXPERIMENTAL / UNTESTED, ch. 30 SS30.14.6): "
        "NOP the cmd-5 cleanup kill (0x01E21EF4) AND hook the walker "
        "FUN_01e60d34 page post (0x01E60DE4) with a 78-byte cave at "
        "0x01EA7758 that kills only a same-address stuck conn record "
        "(inused, mask==0, slot[0..5]==armed target [0x10E34]) before "
        "skipping one post cycle (6 s rearm), else replays the page post. "
        "At this site the target cell is FRESH (CON pump cases 8/0xb write "
        "it then call the walker synchronously) - unlike the cmd-5 site "
        "used by --r1-conditional-kill (field-FAILED). A different-device "
        "incumbent is never killed -> goal multipoint; same-device repair "
        "keeps working via the kill. Subsumes --no-cmd5-kill. Mutually "
        "exclusive with --no-cmd5-kill and --r1-conditional-kill. Requires "
        "the full multipoint recipe.",
    )
    ap.add_argument(
        "--cmd5-handle",
        dest="cmd5_handle",
        action="store_true",
        help="MULTIPOINT R1-c (EXPERIMENTAL / UNTESTED, ch. 30 SS30.14.9): "
        "re-encode the cmd-5 stuck-slot test at 0x01E21EF0 from "
        "'r1 = h[r1+0]' (mask halfword at slot+8) to 'r1 = h[r0+6]' (ACL "
        "handle at slot+6): 2 bytes 19 60 -> 09 63. Accessories (TID-PTT) "
        "keep mask==0 while LIVE, so the stock mask test makes cmd 5 kill "
        "them on every Paired->Connect press - the class-dependent evictor "
        "of E7/F3V3-B. The handle test kills only genuinely stuck records "
        "(inused, no ACL), the same liveness test ring cases 4 and 0x4a "
        "use. cmd 5 stays LIVE (no F4-style deadlock) and the kill runs on "
        "the btstack task, honouring the killer's queue-post task contract "
        "that froze R1-a/R1-b. Mutually exclusive with --no-cmd5-kill, "
        "--r1-conditional-kill and --r1-walker-kill (they disable or "
        "replace this kill). Requires the full multipoint recipe.",
    )
    ap.add_argument(
        "--cmd5-target",
        dest="cmd5_target",
        action="store_true",
        help="MULTIPOINT R1-e (EXPERIMENTAL / UNTESTED, ch. 30 SS30.14.11 "
        "+ ch. 31): targeted cmd-5 incumbent kill. Two hooks. (1) Press "
        "store: the settings-press cmd-5 post call 0x01E1792E (0x01E6ECDA) "
        "becomes a call to a 32-byte cave that first copies the selected "
        "device's BD_ADDR ([[r5]+r4+8], the same load the handler does at "
        "0x01E6ECE4) into the stack saved-target cell 0x0001A5F1, then "
        "replays the post. (2) Target kill: the cmd-5 loop's mask test "
        "19 60 81 42 (0x01E21EF0) becomes a goto to a 38-byte cave that "
        "kills a slot iff its ACL handle (slot+6) is 0 (stuck record) OR "
        "its address equals the stored target (same-device repair) - a "
        "DIFFERENT live incumbent survives, then the page to the target "
        "fires (E6-proven outgoing-join direction). Unlike --cmd5-handle "
        "(R1-c, froze: same-address page guard 0x01E16824 refuses to page "
        "an address still holding an inused record) repair works for any "
        "class, and unlike --r1-conditional-kill (R1-a, froze: selection "
        "cell race-stale at cmd-5 time) the address is captured fresh at "
        "press time in the app task. Cave sites 0x01EA77A8/0x01EA77D0. "
        "Mutually exclusive with --no-cmd5-kill, --r1-conditional-kill, "
        "--r1-walker-kill and --cmd5-handle (same cmd-5 kill). Requires "
        "the full multipoint recipe.",
    )
    ap.add_argument(
        "--no-cleanup-kick",
        dest="no_cleanup_kick",
        action="store_true",
        help="MULTIPOINT (EXPERIMENTAL / UNTESTED): additionally NOP the "
        "three remaining 0x13-capable disconnect executors that call the "
        "wrapper 0x01E07B08 via thunk 0x01E19492: 0x01E19AD0 (stack event "
        "handler, variable reason from message), 0x01E19B14 (subtype-0x73 "
        "orphan-ACL cleanup) and 0x01E20AB2 (profile-record cleanup in "
        "FUN_01e20962). V2b evidence: with E7 flashed and readback-"
        "verified, Paired->TID-PTT->Connect still evicted the PC incumbent "
        "with reason 0x13, so the kick runs through one of these (ch. 27 "
        "SS 27.13/27.14; experiment E8, UNTESTED). SIDE EFFECTS: orphan "
        "and profile cleanup paths no longer release links; power-cycle "
        "instead. Requires the full multipoint recipe.",
    )
    ap.add_argument(
        "--no-l2cap-teardown",
        dest="no_l2cap_teardown",
        action="store_true",
        help="MULTIPOINT (EXPERIMENTAL / UNTESTED): stop the app's L2CAP "
        "channel-close (the eviction layer that survived E6/E7/E8). NOPs "
        "the three user_send_cmd_prepare(0x4a) posts: 0x01E61E22 in the "
        "Paired->Connect UI handler (unconditional), 0x01E60188 in the "
        "routing-mode setter (mode change while a link is active) and "
        "0x01E4F804 in FUN_01e4f652 (AT/SPP command dispatcher; found by "
        "the F3-B full-census re-audit 2026-10-24 - the press-time evictor "
        "that survived the other two NOPs). 0x4a "
        "runs l2cap_disconnect_all_channel(): it forces every open L2CAP "
        "channel to state 0xd and pumps l2cap_run, which sends the L2CAP "
        "Disconnection Request seen in the E8 capture while the HCI-level "
        "kicks were already dead (ch. 27 SS 27.15; experiment E9, "
        "UNTESTED). The outgoing page still happens (connect-pending bit "
        "and the 0xc/0xe/0x12/5 posts remain). SIDE EFFECTS: the app never "
        "tears down L2CAP/RFCOMM channels on these flows; stale channels "
        "persist until power-cycle. Requires the full multipoint recipe.",
    )
    ap.add_argument(
        "--no-spp-close",
        dest="no_spp_close",
        action="store_true",
        help="MULTIPOINT (EXPERIMENTAL / UNTESTED): no-op the app "
        "spp_channel_disconnect() entry (0x01E173EC) — the primitive that "
        "sent the E8/E9 L2CAP Disconnection Requests against the incumbent "
        "SPP channel (SPP control block 0x1A740, live CID at [cb+2] forced "
        "to state 0xd via l2cap_disconnect -> l2cap_run). E9 evidence: both "
        "0x4a posters NOP-ed, the close STILL happened; root cause = the "
        "single-SPP-session chokepoint spp_connect (0x01E1750c) closes the "
        "incumbent CID then retries, plus the 0xB DISCONN_SDP_MASTER path. "
        "Entry no-op mov r0,#0; rts; outgoing page unaffected; pairing flow "
        "unchanged. SIDE EFFECTS: stale SPP sessions until power-cycle. "
        "NEXT WALL: single SPP session — a second SPP device may not bind "
        "(ch. 27 SS 27.16; experiment E10, UNTESTED). Requires the full "
        "multipoint recipe.",
    )
    ap.add_argument(
        "--no-l2cap-disconnect",
        dest="no_l2cap_disconnect",
        action="store_true",
        help="MULTIPOINT (EXPERIMENTAL / UNTESTED): the L2CAP-level kill "
        "of the channel-close eviction (the layer that survived E6-E10). "
        "NOPs the `je r11,#0x4a` dispatch branch at 0x01E17974 (code 0x4a "
        "-> default no-op for EVERY caller, incl. posters E9 missed) and "
        "entry-no-ops l2cap_disconnect() at 0x01E173D0 (mov r0,#0; rts - "
        "kills all direct callers incl. the four SPP-state-machine sites). "
        "E10 evidence: with --no-spp-close and both 0x4a posters NOP-ed, "
        "Paired->Connect still closed ALL channels on the PC link (two "
        "L2CAP Disconnection Requests, CIDs 64+65) - the all-channel walk "
        "bypasses spp_channel_disconnect (ch. 27 SS 27.17; experiment E11). "
        "SIDE EFFECTS: the app can never tear down any L2CAP channel; "
        "stale channels persist until power-cycle. Requires the full "
        "multipoint recipe.",
    )
    ap.add_argument(
        "--gate-close",
        dest="gate_close",
        action="store_true",
        help="MULTIPOINT (EXPERIMENTAL / UNTESTED, ch.30 F3): CONDITIONAL "
        "version of --no-spp-close/--no-l2cap-disconnect. spp_channel_"
        "disconnect() and l2cap_disconnect() entries jump to code-cave "
        "stubs that return 0 (skip the close) ONLY while the press-window "
        "page-pending flag (RAM 0x1A662 bit 7, set by the menu Connect "
        "press, cleared by the no-connection timeout) is set; every other "
        "close runs stock. E11 proved these two entries are the whole "
        "evictor, but its unconditional NOPs deadlocked the app "
        "(ch. 27 SS 27.19); the gate keeps normal teardown intact. The "
        "flag is sticky after a successful connect: closes stay skipped "
        "until BT-off/power-cycle. Mutually exclusive with --no-spp-close "
        "and --no-l2cap-disconnect (same entry bytes). ch. 30 SS 30.11.",
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
            "executor that runs PTT2 / BT-PTT2 / OD PTT is not reachable "
            "from it."
            % ptt_action
        )
    validate_pf_combo(a7, a8)
    if args.gate_close and (args.no_spp_close or args.no_l2cap_disconnect):
        raise SystemExit(
            "--gate-close rewrites the same function entries as "
            "--no-spp-close / --no-l2cap-disconnect (0x01E173EC / "
            "0x01E173D0); pick the conditional gate OR the unconditional "
            "no-ops, not both."
        )
    if args.r1_conditional_kill and args.no_cmd5_kill:
        raise SystemExit(
            "--r1-conditional-kill and --no-cmd5-kill both rewrite the "
            "same 4 bytes at 0x01E21EF4 (call -> cave vs NOP); pick the "
            "conditional predicate OR the wholesale NOP, not both."
        )
    if args.r1_walker_kill and (args.no_cmd5_kill or args.r1_conditional_kill):
        raise SystemExit(
            "--r1-walker-kill subsumes --no-cmd5-kill (it NOPs the cmd-5 "
            "kill itself) and uses the same cave region 0x01EA7758 as "
            "--r1-conditional-kill; pick one R1 variant."
        )
    if args.cmd5_handle and (args.no_cmd5_kill or args.r1_conditional_kill
                             or args.r1_walker_kill or args.cmd5_target):
        raise SystemExit(
            "--cmd5-handle fixes the cmd-5 kill's stuck test; "
            "--no-cmd5-kill / --r1-conditional-kill / --r1-walker-kill / "
            "--cmd5-target disable or replace that kill outright - pick "
            "one variant."
        )
    if args.cmd5_target and (args.no_cmd5_kill or args.r1_conditional_kill
                             or args.r1_walker_kill):
        raise SystemExit(
            "--cmd5-target rewrites the cmd-5 kill test itself; "
            "--no-cmd5-kill / --r1-conditional-kill / --r1-walker-kill "
            "disable or replace that kill - pick one variant."
        )

    PATCHES = build_patches(args.bluetooth_mode, a7, a8, args.conn_num,
                            args.no_kick, args.force_page_scan,
                            args.force_role_keep, args.no_disconnect_13,
                            args.no_pairing_kick, args.no_cleanup_kick,
                            args.no_l2cap_teardown, args.no_spp_close,
                            args.no_l2cap_disconnect, args.gate_close,
                            args.no_cmd5_kill, args.r1_conditional_kill,
                            args.r1_walker_kill, args.cmd5_handle,
                            args.cmd5_target)

    raw, app, app_start = load_app(args.src)
    print("source: %s (%d bytes)" % (args.src, len(raw)))
    print(
        "app region: container 0x%X-0x%X, flash 0x%X, chipkey 0x%04X\n"
        % (app_start, app_start + APP_LEN, FLASH_BASE, CHIPKEY)
    )
    extra = ""
    if args.conn_num is not None:
        extra += " --conn-num=%d (multipoint)" % args.conn_num
    if args.no_kick:
        extra += " --no-kick (multipoint)"
    if args.force_page_scan:
        extra += " --force-page-scan (multipoint)"
    if args.force_role_keep:
        extra += " --force-role-keep (multipoint)"
    if args.no_disconnect_13:
        extra += " --no-disconnect-13 (multipoint)"
    if args.no_pairing_kick:
        extra += " --no-pairing-kick (multipoint)"
    if args.no_cleanup_kick:
        extra += " --no-cleanup-kick (multipoint)"
    if args.no_l2cap_teardown:
        extra += " --no-l2cap-teardown (multipoint)"
    if args.no_spp_close:
        extra += " --no-spp-close (multipoint)"
    if args.no_l2cap_disconnect:
        extra += " --no-l2cap-disconnect (multipoint)"
    if args.gate_close:
        extra += " --gate-close (multipoint F3)"
    if args.no_cmd5_kill:
        extra += " --no-cmd5-kill (multipoint F4)"
    if args.r1_conditional_kill:
        extra += " --r1-conditional-kill (multipoint R1-a)"
    if args.r1_walker_kill:
        extra += " --r1-walker-kill (multipoint R1-b)"
    if args.cmd5_handle:
        extra += " --cmd5-handle (multipoint R1-c)"
    print("configuration: --bluetooth-mode %d --PTT=%s --PTT2=%s --OD-PTT=%s%s\n"
          % (args.bluetooth_mode, ptt_action, a7, a8, extra))

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
    if args.conn_num is not None:
        wanted += ["connum"]
    if args.no_kick:
        wanted += ["nokick"]
    if args.force_page_scan:
        wanted += ["pagescan"]
    if args.force_role_keep:
        wanted += ["rolekeep"]
    if args.no_disconnect_13:
        wanted += ["disc13"]
    if args.no_pairing_kick:
        wanted += ["pairkickall", "pairkickone"]
    if args.no_cleanup_kick:
        wanted += ["cleanupkickvar", "cleanupkickorphan", "cleanupkickprof"]
    if args.no_l2cap_teardown:
        wanted += ["l2capteardownui", "l2capteardownmode", "l2capteardownapp"]
    if args.no_spp_close:
        wanted += ["sppclose"]
    if args.no_l2cap_disconnect:
        wanted += ["l2capdiscbranch", "l2capdiscentry"]
    if args.gate_close:
        wanted += ["gatespptramp", "gatel2captramp", "gatecave"]
    if args.no_cmd5_kill:
        wanted += ["cmd5kill"]
    if args.r1_conditional_kill:
        wanted += ["r1condkill", "r1cave"]
    if args.r1_walker_kill:
        wanted += ["cmd5kill", "r1condkill", "r1bhook", "r1bcave"]
    if args.cmd5_handle:
        wanted += ["cmd5handle"]
    if args.cmd5_target:
        wanted += ["presstore", "presstcave", "cmd5target", "cmd5tcave"]
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
