"""
JieLi fw-Bootloader USB-HID upgrade client (BR23 / AC635N — TIDRADIO H3 Plus).

Talks to the OEM uboot of the H3 Plus, which is the JieLi official
fw-Bootloader (github.com/JieLi-Tech/fw-Bootloader). Enter it with
**PTT + 1 + power-on**: USB HID ``4c4a:4155`` appears as ``/dev/hidrawN``
(Linux only — needs root to open hidraw). This is the recovery/reflash path
that works even when the flashed app has no download-mode combo handler.

Protocol ("JL SU"), 64-byte HID reports, all little endian:

    AA 55 | cmd_len u16 | body | crc16 u16

* body = ``cmd u8 | status u8 | params``, **XOR-encrypted** with the 4-byte
  key = u32 ``communication_key`` (stock ``12345678`` = ``4E 61 BC 00``,
  cycling from body byte 0; verified unchanged by TID).
* crc16 = CCITT/XModem (poly 0x1021, init 0, official nibble table) over
  sync+len+**encrypted** body.
* Commands: ``0xC0`` DEVICE_INIT (file_name[16]+mode; ``app_dir_head`` = the
  app area, its addr 0 == flash ``0x5000``), ``0xC1`` DEVICE_CHECK
  (sdk_id u32 == ``0x12345678``), ``0xC2`` ERASE (addr+type 1/2/3 =
  256/4096/65536), ``0xC3`` WRITE (addr+len+data), ``0xC4`` FLASH_CRC
  (addr+len+block_size -> u16 per block, max 16/packet), ``0xCA`` REBOOT.
* **There is no READ command** — verification is by FLASH_CRC only. The
  chip CRCs the raw (SFCENC-encrypted) flash bytes: crc16 of the *encrypted*
  image at ``0x5000+addr`` must match (hardware-verified 2026-11-07).
* Official write quirk replicated: per 4K unit — erase, write bytes
  ``32..4096`` first, then ``0..32`` last (header written last).

Subcommands:

    python tools/jl_hidboot.py info                       # read-only handshake
    python tools/jl_hidboot.py crcfile <img.bin> [addr0] [nblk]   # read-only
    python tools/jl_hidboot.py restore <1MiB img> [--yes] # FLASH — user action
    python tools/jl_hidboot.py reboot

``restore`` writes only flash ``0x5000..0xC9000`` (196 sectors: the app area;
VM @0xC9000+ untouched, the 32 device-specific bytes @0xC8FE0 ride inside the
last sector and are identical across the known-good images).

Future custom apps can request this mode in software: write
``{'u','b','o','o','t',0x5A,'s','t'}`` to the NV_RAM list and reset — see
findings/32-sdk-rebuild.md §32.10.2.

Discovery: full details in findings/32-sdk-rebuild.md §32.10.2.
"""
# SPDX-License-Identifier: MIT
import os
import struct
import sys

VID, PID = 0x4C4A, 0x4155
KEY = struct.pack("<I", 12345678)  # 4E 61 BC 00
SDK_ID = 0x12345678
CMD_INIT, CMD_CHECK, CMD_ERASE, CMD_WRITE, CMD_CRC, CMD_REBOOT = (
    0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xCA)
APP_BASE = 0x5000  # flash offset of app area (addr 0 in "app_dir_head")


def crc16(data):
    """Official host crc16 (fw-Bootloader win-usb_hid main.cpp) — matches chip_crc16."""
    ta = (0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
          0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF)
    crc = 0
    for b in data:
        da = crc >> 12
        crc = (crc << 4) & 0xFFFF
        crc ^= ta[da ^ (b >> 4)]
        da = crc >> 12
        crc = (crc << 4) & 0xFFFF
        crc ^= ta[da ^ (b & 0x0F)]
    return crc


def xcrypt(buf):
    return bytes(b ^ KEY[i & 3] for i, b in enumerate(buf))


def find_hidraw():
    """Return /dev/hidrawN for the JieLi device via sysfs (None if absent)."""
    for d in sorted(os.listdir("/sys/class/hidraw")):
        try:
            with open(f"/sys/class/hidraw/{d}/device/uevent") as f:
                ue = f.read()
        except OSError:
            continue
        if f":0000{VID:04X}:0000{PID:04X}" in ue:
            return f"/dev/{d}"
    return None


class Hid:
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR)

    def close(self):
        os.close(self.fd)

    def _drain(self):
        try:
            import select
            while select.select([self.fd], [], [], 0.05)[0]:
                os.read(self.fd, 64)
        except OSError:
            pass

    def cmd(self, opcode, params=b"", timeout=3.0):
        body = xcrypt(bytes([opcode, 0x00]) + params)
        frame = bytearray(b"\xAA\x55" + struct.pack("<H", len(body)) + body)
        frame += struct.pack("<H", crc16(frame))
        assert len(frame) <= 64, f"frame too big: {len(frame)}"
        self._drain()
        os.write(self.fd, b"\x00" + bytes(frame).ljust(64, b"\x00"))
        import select
        if not select.select([self.fd], [], [], timeout)[0]:
            raise TimeoutError(f"no response to cmd 0x{opcode:02X} "
                               "(in HID mode? PTT+1+power-on)")
        rep = os.read(self.fd, 64)
        if len(rep) < 8 or rep[0] != 0xAA or rep[1] != 0x55:
            raise ValueError(f"bad response: {rep[:16].hex()}")
        clen = struct.unpack("<H", rep[2:4])[0]
        body = xcrypt(rep[4:4 + clen])
        got_crc = struct.unpack("<H", rep[4 + clen:6 + clen])[0]
        calc = crc16(rep[:4 + clen])
        return body[0], body[1], body[2:], got_crc == calc


def do_check(h):
    cmd, st, p, _ = h.cmd(CMD_CHECK, struct.pack("<I", SDK_ID))
    vid = p[0:4]
    pid = p[4:20].split(b"\x00")[0].decode("ascii", "replace")
    sdk = struct.unpack("<I", p[20:24])[0] if len(p) >= 24 else None
    print(f"CHECK: status={st} vid={vid.hex()} pid={pid!r} sdk_id={sdk:#x}")
    return st == 0


def do_init(h, name="app_dir_head", mode=0):
    fn = name.encode().ljust(16, b"\x00")
    cmd, st, p, _ = h.cmd(CMD_INIT, fn + bytes([mode]))
    if st != 0 or len(p) < 16:
        print(f"INIT({name}): status={st} (error — try another file name?)")
        return None
    addr, ln, eoff, align = struct.unpack("<4I", p[:16])
    print(f"INIT({name}): upgrade_addr={addr:#x} len={ln}({ln // 1024}K) "
          f"eoffset={eoff} alignsize={align}")
    return dict(addr=addr, len=ln, eoffset=eoff, align=align)


def fetch_crcs(h, addr, nblk, blk):
    out = []
    while nblk > 0:
        n = min(nblk, 16)
        cmd, st, p, crc_ok = h.cmd(
            CMD_CRC, struct.pack("<3I", addr, n * blk, blk))
        if st != 0:
            raise RuntimeError(f"FLASH_CRC status={st}")
        out += list(struct.unpack(f"<{n}H", p[:2 * n]))
        addr += n * blk
        nblk -= n
    return out


def cmd_info(h):
    do_check(h)
    info = None
    for name in ("app_dir_head", "app_dir_head2", "app_area_head"):
        info = do_init(h, name)
        if info:
            break
    if not info:
        return
    crcs = fetch_crcs(h, 0, 4, 4096)
    print("CRC@0..4x4K:", " ".join(f"{c:04X}" for c in crcs))


def cmd_crcfile(h, img, addr0, nblk, blk=4096):
    data = open(img, "rb").read()
    do_init(h, "app_dir_head")
    crcs = fetch_crcs(h, addr0, nblk, blk)
    hits = {"flash+0x5000": 0, "flash+0": 0, "flash+0x100": 0}
    for i, c in enumerate(crcs):
        for label, off in (("flash+0x5000", APP_BASE), ("flash+0", 0),
                           ("flash+0x100", 0x100)):
            s = off + addr0 + i * blk
            if s + blk <= len(data) and crc16(data[s:s + blk]) == c:
                hits[label] += 1
    print("chip CRC[:8]: " + " ".join(f"{c:04X}" for c in crcs[:8]))
    for label, n in hits.items():
        print(f"  match {label}: {n}/{len(crcs)}")
    if max(hits.values(), default=0) == 0:
        print("  => no mapping matched — compare against the ENCRYPTED "
              "full image (the chip CRCs raw flash bytes)")


def cmd_restore(h, img, yes):
    data = open(img, "rb").read()
    if len(data) != 1 << 20:
        sys.exit(f"{img} must be a full 1MiB image")
    info = do_init(h, "app_dir_head")
    if not info:
        sys.exit("INIT failed — cannot address the app area")
    blk = info["align"] or 4096
    # INIT len is unbounded (0xFFFFFFFF) — cap to the strict app region
    # flash 0x5000..0xC9000 (196 sectors, same span as the P1 flash): keeps
    # VM @0xC9000+ untouched; the 32 device bytes @0xC8FE0 ride inside the
    # last sector and are identical in every known-good image.
    span = 0xC9000 - APP_BASE
    seg = data[APP_BASE:APP_BASE + span]
    if len(seg) % blk:
        sys.exit(f"span {span:#x} not block-aligned?")
    nblk = len(seg) // blk
    print(f"PLAN: write {len(seg)} B ({nblk} x {blk} B) to app_dir_head "
          f"(flash {APP_BASE:#x}+), verify via FLASH_CRC, reboot.")
    import hashlib
    print(f"Image: {img} sha256[:8]={hashlib.sha256(data).hexdigest()[:8]}")
    if not yes:
        sys.exit("re-run with --yes to flash (USER action)")
    for i in range(nblk):
        a = i * blk
        h.cmd(CMD_ERASE, struct.pack("<2I", a, 2))          # 4K sector
        buf = seg[a:a + blk]
        # official quirk: write bytes 32..end first, then 0..32 last
        for off, ln in ((32, blk - 32), (0, 32)):
            for j in range(0, ln, 40):
                chunk = buf[off + j:off + j + min(40, ln - j)]
                _, st, _, _ = h.cmd(
                    CMD_WRITE, struct.pack("<2I", a + off + j, len(chunk))
                    + chunk)
                if st != 0:
                    sys.exit(f"WRITE status={st} @addr {a + off + j:#x}")
        if i % 16 == 0 or i == nblk - 1:
            print(f"  {i + 1}/{nblk} sectors", flush=True)
    crcs = fetch_crcs(h, 0, nblk, blk)
    bad = [i for i in range(nblk)
           if crcs[i] != crc16(seg[i * blk:(i + 1) * blk])]
    if bad:
        sys.exit(f"CRC MISMATCH in {len(bad)} blocks: {bad[:8]}... — STOP")
    print(f"VERIFIED: all {nblk} block CRCs match. Rebooting...")
    try:
        h.cmd(CMD_REBOOT)
    except OSError:
        pass  # device vanishes on reset — expected


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    path = find_hidraw()
    if not path:
        sys.exit("No 4c4a:4155 hidraw found — put radio in HID mode "
                 "(PTT+1+power-on) and run with sudo")
    print(f"device: {path}")
    h = Hid(path)
    try:
        if args[0] == "info":
            cmd_info(h)
        elif args[0] == "crcfile":
            cmd_crcfile(h, args[1],
                        int(args[2], 0) if len(args) > 2 else 0,
                        int(args[3]) if len(args) > 3 else 4)
        elif args[0] == "restore":
            cmd_restore(h, args[1], "--yes" in args)
        elif args[0] == "reboot":
            h.cmd(CMD_REBOOT)
            print("reboot sent")
        else:
            sys.exit(f"unknown subcommand {args[0]}")
    finally:
        h.close()


if __name__ == "__main__":
    main()
