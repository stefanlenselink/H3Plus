#!/usr/bin/env python3
"""Splice recompiled (round-trip) functions into an H3 Plus image.

Decompile=>compile route test: replaces two stock functions in the decrypted
app with JieLi-clang-recompiled, semantically-identical equivalents built
from Ghidra decompilation.  Behaviour must not change.

  VA 0x01E1787C  is_1t2_connection   (stock 54 B -> recompiled 34 B)
  VA 0x01E182B0  set_conn_num(1)     (stock 50 B -> recompiled 18 B)

Usage:
  python work/roundtrip/splice_rt.py <src.bin> <dst.bin> [rt_is1t2.bin]

SPDX-License-Identifier: MIT
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from patch_h3plus_firmware_bluetooth import load_app, sfc_enc_decrypt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# (app file offset == VA - 0x01E00000, blob offset, length, expected stock prefix)
SITES = [
    (0x1787C, 0, 34, bytes.fromhex("c0ff39bf000009430a42")),
    (0x182B0, 34, 18, bytes.fromhex("7404c0ff39bf0000")),
]


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    src, dst = sys.argv[1], sys.argv[2]
    blob = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "rt_is1t2.bin")
    blob = open(blob, "rb").read()

    raw, app, app_start = load_app(src)
    for off, boff, length, ctx in SITES:
        got = bytes(app[off:off + len(ctx)])
        if got != ctx:
            raise SystemExit(
                "context mismatch at app offset 0x%X: %s (want %s) -- "
                "image is patched at this site or not v1.0.50" %
                (off, got.hex(" "), ctx.hex(" ")))
        app[off:off + length] = blob[boff:boff + length]
        print("spliced %d bytes at app offset 0x%X (VA 0x%08X)" %
              (length, off, 0x01E00000 + off))

    enc = sfc_enc_decrypt(bytes(app), 0, 0xF181)
    assert sfc_enc_decrypt(enc, 0, 0xF181) == bytes(app)
    out = bytearray(raw)
    out[app_start:app_start + len(enc)] = enc
    open(dst, "wb").write(out)
    print("wrote %s (%d bytes)" % (dst, len(out)))


if __name__ == "__main__":
    main()
