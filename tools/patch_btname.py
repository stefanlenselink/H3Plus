"""
Patch the TIDRADIO H3 Plus Bluetooth accessory whitelist.

BACKGROUND
----------
The radio only enables the Bluetooth microphone (HFP SCO uplink) for accessories
whose Bluetooth name matches a hard-coded list:

    0x0A0968  "TID-PTT"      7 chars + NUL, 8-byte slot
    0x0A0970  "TID-MIC"      7 chars + NUL, 8-byte slot
    0x0A0F5C  "TID-MIC-EAR" 11 chars + NUL, 12-byte slot

The match is a PREFIX match, proven by observation: the real PTT button
advertises as "TID-PTT0cd28a" (name + MAC suffix) yet still works, while the
firmware only stores the 7-character "TID-PTT". An exact strcmp could never
match, so the comparison must be a bounded/prefix compare.

Consequence: writing the FIRST 7 CHARACTERS of any headset's name into the
"TID-MIC" slot makes the radio treat that headset as a wireless speaker-mic.

    "Jabra Evolve 65"  ->  first 7 chars  ->  "Jabra E"

Patching the TID-MIC slot leaves the TID-PTT slot intact, so a TIDRADIO
wireless PTT button keeps working.

The SFC/ENC scrambler is position-deterministic and symmetric, so this changes
only the bytes of the string itself in the encrypted image.

USAGE
-----
    # inspect current whitelist
    python tools/patch_btname.py Dumps/dump_internal.bin --show

    # patch the TID-MIC slot and write a new image
    python tools/patch_btname.py Dumps/dump_internal.bin out.bin --mic="Jabra E"

    # patch the PTT slot instead
    python tools/patch_btname.py Dumps/dump_internal.bin out.bin --ptt="Jabra E"
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

import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])

from jl_sfcenc import sfc_enc_decrypt

APP_START = 0x5000
APP_END = 0xC8FE0
CHIPKEY = 0xF181

# name -> (flash address, total slot size including the NUL terminator)
SLOTS = {
    "ptt": (0x0A0968, 8),
    "mic": (0x0A0970, 8),
    "micear": (0x0A0F5C, 12),
}


def load_app(path):
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) < APP_END:
        raise SystemExit(f"{path}: too small ({len(raw)} bytes); need >= 0x{APP_END:X}")
    app = sfc_enc_decrypt(raw[APP_START:APP_END], 0, CHIPKEY)
    return raw, bytearray(app)


def show(app):
    print(f"{'slot':8} {'flash':>10} {'max':>4}  current")
    print("-" * 44)
    for key, (flash, size) in SLOTS.items():
        off = flash - APP_START
        blob = bytes(app[off : off + size])
        name = blob.split(b"\x00")[0].decode("ascii", "replace")
        print(f"{key:8} 0x{flash:08X} {size - 1:>4}  {name!r}")


def patch(app, key, newname):
    flash, size = SLOTS[key]
    maxlen = size - 1
    encoded = newname.encode("ascii")
    if len(encoded) > maxlen:
        raise SystemExit(
            f"'{newname}' is {len(encoded)} chars; slot '{key}' holds at most {maxlen}.\n"
            f"Use only the first {maxlen} characters of the device name "
            f"(the match is a prefix match, so that is sufficient)."
        )
    off = flash - APP_START
    old = bytes(app[off : off + size]).split(b"\x00")[0].decode("ascii", "replace")
    app[off : off + size] = encoded + b"\x00" * (size - len(encoded))
    print(f"{key}: {old!r} -> {newname!r}  @ flash 0x{flash:08X}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {}
    for a in sys.argv[1:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("=")
            opts[k] = v.strip('"').strip("'")

    if not args:
        print(__doc__)
        return 1

    src = args[0]
    raw, app = load_app(src)

    if "show" in opts or len(args) < 2:
        show(app)
        return 0

    dst = args[1]
    before = bytes(app)

    did = False
    for key in SLOTS:
        if key in opts:
            patch(app, key, opts[key])
            did = True
    if not did:
        print("Nothing to do. Pass --mic=NAME, --ptt=NAME or --micear=NAME.")
        return 1

    changed = sum(1 for x, y in zip(before, app) if x != y)
    print(f"plaintext bytes changed: {changed}")

    enc = sfc_enc_decrypt(bytes(app), 0, CHIPKEY)

    # sanity: decrypting again must reproduce our patched plaintext
    assert sfc_enc_decrypt(enc, 0, CHIPKEY) == bytes(app), "round-trip failed"

    out = bytearray(raw)
    out[APP_START:APP_END] = enc

    diff = [i for i in range(len(raw)) if raw[i] != out[i]]
    print(f"ciphertext bytes changed: {len(diff)}", end="")
    if diff:
        print(f"  (0x{diff[0]:X} - 0x{diff[-1]:X})")
    else:
        print()

    with open(dst, "wb") as f:
        f.write(out)
    print(f"wrote {dst} ({len(out)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
