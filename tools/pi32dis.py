#!/usr/bin/env python3
"""
pi32v2 disassembler for JieLi BR-series firmware.

The ISA is not publicly documented by JieLi, but kagaimiq's reverse-engineered
spec (cpu/pi32v2.md in github.com/kagaimiq/jielie) lists every known opcode as a
bit-pattern table. Rather than hand-transcribe hundreds of encodings, this tool
parses that spec at runtime and builds a decode table from it.

Spec pattern syntax:
    0 / 1     fixed bit
    -         don't care
    %         WeirdIMM field
    Xxxx      a named field; uppercase starts it, lowercase continues it.
              Field identity is the uppercase letter, width is the run length.
    |         iword separator (cosmetic)

Operand text refers to fields inside backticks, e.g. r`Xxxx` or s`BbbAaaaa0`,
where the expression is built MSB-first from field bits and literal 0/1 runs.

Usage:
    python tools/pi32dis.py <file> --va 0x01E9BC3C --count 40
    python tools/pi32dis.py <file> --va 0x01E9BC3C --end 0x01E9BD00
    python tools/pi32dis.py <file> --flash 0x05FDE2 --count 40
    python tools/pi32dis.py <file> --func 0x01E9BC3C        # follow to return
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
import re
import sys

# app_dec.bin offset 0 corresponds to this virtual address (see Findings.md 9A.4a)
LOAD_BASE = 0x01E00000
# app region begins at this flash offset, so flash -> file offset is -0x5000
APP_FLASH_START = 0x5000

SPEC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "isa", "pi32v2.md")

PATTERN_RE = re.compile(r"^([01A-Za-z\-%|]{16,})\s+(.*)$")


class Insn:
    """One decoded opcode-table entry."""

    __slots__ = ("nbits", "mask", "value", "fields", "text", "specificity")

    def __init__(self, nbits, mask, value, fields, text, specificity):
        self.nbits = nbits
        self.mask = mask
        self.value = value
        self.fields = fields          # {letter: [bit indices, MSB-first]}
        self.text = text
        self.specificity = specificity


def parse_spec(path):
    """Parse the ISA markdown into a list of Insn decode entries."""
    entries = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip()
            if not line:
                continue
            m = PATTERN_RE.match(line)
            if not m:
                continue
            bits = m.group(1).replace("|", "")
            text = m.group(2).strip()
            if len(bits) not in (16, 32, 48):
                continue
            # Strip the parallel-execution marker and the "unknown mnemonic" column.
            text = text.replace("\t", " ").strip()
            if text.startswith("???"):
                text = text[3:].strip()

            nbits = len(bits)
            mask = value = 0
            fields = {}
            spec = 0
            for i, ch in enumerate(bits):
                pos = nbits - 1 - i          # bit index, LSB = 0
                if ch in "01":
                    mask |= 1 << pos
                    value |= int(ch) << pos
                    spec += 1
                elif ch in "-%":
                    if ch == "%":
                        fields.setdefault("%", []).append(pos)
                else:
                    fields.setdefault(ch.upper(), []).append(pos)
            entries.append(Insn(nbits, mask, value, fields, text, spec))
    # Most fixed bits wins; this also resolves instruction length.
    entries.sort(key=lambda e: (-e.specificity, e.nbits))
    return entries


def field_value(raw, bitlist, nbits=0, width=0):
    """Gather scattered field bits (already MSB-first) into an integer.

    Special case: a 32-bit immediate in a 48-bit instruction occupies the two
    trailing iwords and is stored little-endian across them, so the halves must
    be swapped relative to the MSB-first bit listing in the spec.
    """
    v = 0
    for pos in bitlist:
        v = (v << 1) | ((raw >> pos) & 1)
    if nbits == 48 and width == 32:
        v = ((v & 0xFFFF) << 16) | ((v >> 16) & 0xFFFF)
    return v


def weird_imm(v):
    """Decode the 12-bit 'WeirdIMM' compressed immediate form."""
    code4 = (v >> 8) & 0xF
    x8 = v & 0xFF
    if code4 == 0:
        return x8
    if code4 == 1:
        return ((x8 << 16) | x8) & 0xFFFFFFFF
    if code4 == 2:
        return ((x8 << 24) | (x8 << 8)) & 0xFFFFFFFF
    if code4 == 3:
        return (x8 * 0x01010101) & 0xFFFFFFFF
    code5 = (v >> 7) & 0x1F
    x7 = v & 0x7F
    base = 0x80 | x7
    shift = 32 - (code5 - 8) - 8
    if shift < 0:
        shift = 0
    return (base << shift) & 0xFFFFFFFF


def sign_extend(v, nbits):
    if nbits and (v >> (nbits - 1)) & 1:
        v -= 1 << nbits
    return v


EXPR_TOKEN = re.compile(r"([A-Z][a-z]*)|([01]+)")


def eval_expr(expr, raw, fields, signed, nbits=0):
    """
    Build a value from an expression like `BbbAaaaa0` or `1Xxxxxxx`.
    Tokens are field references (uppercase-led letter runs) or literal bit runs.
    """
    total = 0
    nb = 0
    ok = True
    for m in EXPR_TOKEN.finditer(expr):
        if m.group(1):
            letter = m.group(1)[0]
            width = len(m.group(1))
            bl = fields.get(letter)
            if bl is None:
                ok = False
                continue
            v = field_value(raw, bl, nbits, len(bl))
            if width < len(bl):
                v &= (1 << width) - 1
            total = (total << width) | v
            nb += width
        else:
            lit = m.group(2)
            total = (total << len(lit)) | int(lit, 2)
            nb += len(lit)
    if not ok:
        return None, 0
    if signed:
        total = sign_extend(total, nb)
    return total, nb


BACKTICK = re.compile(r"(sr|r|s)?`([^`]*)`")


def render(insn, raw, addr):
    """Substitute field values into the mnemonic text."""
    text = insn.text
    target = None
    branch_imm = []

    def repl(m):
        prefix = m.group(1) or ""
        signed = prefix == "s"
        is_reg = prefix in ("r", "sr")
        expr = m.group(2)
        # Trailing annotations like <0==32> or <+2> are informational.
        ann = ""
        am = re.search(r"<[^>]*>", expr)
        if am:
            ann = am.group(0)
            expr = expr[: am.start()]
        if "%" in expr:
            v = weird_imm(field_value(raw, insn.fields.get("%", []), insn.nbits, 12))
            return hex(v)
        v, nb = eval_expr(expr, raw, insn.fields, signed, insn.nbits)
        if v is None:
            return "?"
        if ann == "<+2>":
            v += 2
        elif ann == "<0==32>" and v == 0:
            v = 32
        if is_reg:
            return "%s%d" % (prefix, v)
        branch_imm.append((v, nb, signed))
        return ("-0x%X" % -v) if v < 0 else ("0x%X" % v)

    text = BACKTICK.sub(repl, text)

    if "%%WeirdIMM%%" in text:
        text = text.replace(
            "%%WeirdIMM%%",
            hex(weird_imm(field_value(raw, insn.fields.get("%", []), insn.nbits, 12))),
        )

    # Branch/call displacements are PC-relative to the instruction address.
    # (Verified empirically: three consecutive calls to one helper encode
    #  decreasing displacements that resolve to a single constant target.)
    # The 48-bit forms carry a full 32-bit absolute address instead.
    m = re.search(r"\b(call|goto)\s+(-?0x[0-9A-Fa-f]+)", text)
    if m and branch_imm:
        off = int(m.group(2), 16)
        if insn.nbits == 48:
            target = off & 0xFFFFFFFF
        else:
            # The 32-bit call/goto form (spec: 1110101010/11 AaaaaaBbbb...0)
            # writes its displacement without an `s` prefix, but it is in fact
            # a signed PC-relative offset.  Without sign extension every
            # backward call decodes to a bogus 0x026xxxxx address.
            v, nb, was_signed = branch_imm[-1]
            if not was_signed and off == v:
                off = sign_extend(v, nb)
            # PC is the address of the NEXT instruction.
            target = (addr + insn.nbits // 8 + off) & 0xFFFFFFFF
        text = text[: m.start(2)] + "0x%08X" % target + text[m.end(2) :]
    else:
        m = re.search(r"goto\s+(-?0x[0-9A-Fa-f]+)", text)
        if m:
            off = int(m.group(1), 16)
            target = (addr + insn.nbits // 8 + off) & 0xFFFFFFFF
            text = text[: m.start(1)] + "0x%08X" % target + text[m.end(1) :]
    return text, target


class Disassembler:
    def __init__(self, data, base=LOAD_BASE, spec=SPEC_PATH):
        self.data = data
        self.base = base
        self.entries = parse_spec(spec)
        # Bucket by first iword high byte for speed.
        self.by_len = {16: [], 32: [], 48: []}
        for e in self.entries:
            self.by_len[e.nbits].append(e)

    def word(self, off, n):
        """Read n bits (n/16 little-endian iwords), MSB-first iword order."""
        v = 0
        for i in range(n // 16):
            if off + i * 2 + 2 > len(self.data):
                return None
            iw = int.from_bytes(self.data[off + i * 2 : off + i * 2 + 2], "little")
            v = (v << 16) | iw
        return v

    # --- Group 7 load/store (0xEC..0xEE) -------------------------------
    # The community spec documents these only with an all-zero operand
    # iword, so no real instance ever matches.  Field layout below was
    # recovered empirically (Findings.md 9A.29):
    #
    #   iword1 = Dddd(15:12) Iiii(11:8) Bbbb(7:4) Llll(3:0)
    #
    #   dest / source register  = iword1[15:12]
    #   base register           = iword1[7:4]
    #   displacement            = <iword0 low bits> : iword1[11:8] : iword1[3:0]
    #
    # Validated against: base register == the register loaded with a known
    # constant immediately before (530/540 sites), destination == the
    # register zero-tested immediately after (555/677 sites), and word
    # loads landing on 4-byte-aligned displacements (90%).
    GROUP7 = {
        0xEC50: ("d[%s]", 8, 3),  # r(n+1)_r(n) = d[base + disp]  (64-bit pair)
        0xECD0: ("[%s]", 4, 3),   # r = [base + disp]
        0xED50: ("h[%s]", 2, 2),  # r = h[base + disp] (u)
        0xED54: ("h[%s]", 2, 2),
        0xEE50: ("b[%s]", 1, 1),  # r = b[base + disp] (u)
        0xEE52: ("b[%s]", 1, 1),  # b[base + disp] = r
        0xEE54: ("b[%s]", 1, 1),
    }
    GROUP7_STORE = {0xEE52, 0xEE53}

    # --- Group 7 register-indexed load/store --------------------------
    # 0xEED8 / 0xEDD8 / 0xECD8 are NOT post-increment (see Findings.md
    # 9A.31); they are register-indexed:  rD = w[rB + rI].  The compiler
    # emits them for displacements too large for the immediate forms, by
    # loading the displacement into a register first -- which is why they
    # are so common (4,947 sites) and why they cluster after constant
    # loads.
    #
    #   iword1 = Dddd(15:12) Iiii(11:8) Bbbb(7:4) Ssss(3:0)
    #
    # Ssss selects direction/signedness; the value base differs per width
    # and the mapping below is empirical, not from the spec.
    GROUP7_IDX = {
        0xEED8: ("b", {0: "ldu", 1: "st", 2: "lds"}),
        0xEDD8: ("h", {8: "ldu", 9: "st", 10: "lds"}),
        0xECD8: ("", {8: "ldu", 9: "st", 10: "ldu", 11: "st"}),
    }

    # --- Two-register conditional branches (0xE8xx-0xEExx) ------------
    # Same spec problem as Group 7: documented only with an all-zero
    # second iword, so no real instance matches.  Recovered layout
    # (Findings.md 9A.31):
    #
    #   iword1 = Aaaa(15:12) ....(11:9) Dddddddddd(8:0)
    #
    #   first compared register = iword1[15:12]
    #   branch displacement     = signed(iword1[8:0]) * 2, from next insn
    #
    # Validated over 8,000 candidate sites: 100% of targets land inside
    # the image and 100% within +/-1 KB, as befits a local branch.
    CONDBR = re.compile(r"^(if|ifs) \(r0 (==|!=|>=|<=|>|<) r\d+\) goto 0$")

    def condbranch(self, off, addr):
        """Decode a two-register conditional branch, or return None."""
        if off + 4 > len(self.data):
            return None
        raw = self.word(off, 32)
        w1 = int.from_bytes(self.data[off + 2 : off + 4], "little")
        for e in self.by_len[32]:
            # Match on the opcode iword only: the spec's operand iword is
            # all zeros, which no real instruction has.
            if (raw >> 16) & (e.mask >> 16) != (e.value >> 16):
                continue
            if e.value & 0xFFFF:
                continue
            text, _ = render(e, raw, addr)
            if not self.CONDBR.match(text):
                return None
            disp = w1 & 0x1FF
            if disp & 0x100:
                disp -= 0x200
            target = (addr + 4 + disp * 2) & 0xFFFFFFFF
            text = text.replace("r0", "r%d" % ((w1 >> 12) & 0xF), 1)
            return text[:-1] + "0x%08X" % target, target
        return None

    def group7_indexed(self, off):
        """Decode a Group 7 register-indexed load/store, or return None."""
        if off + 4 > len(self.data):
            return None
        w0 = int.from_bytes(self.data[off : off + 2], "little")
        ent = self.GROUP7_IDX.get(w0)
        if ent is None:
            return None
        width, sel = ent
        w1 = int.from_bytes(self.data[off + 2 : off + 4], "little")
        dst, idx, bse, s = (w1 >> 12) & 0xF, (w1 >> 8) & 0xF, (w1 >> 4) & 0xF, w1 & 0xF
        mem = "%s[r%d + r%d]" % (width, bse, idx)
        op = sel.get(s)
        if op == "st":
            return "%s = r%d" % (mem, dst)
        if op is None:
            return "r%d = %s ?%d" % (dst, mem, s)
        return "r%d = %s (%s)" % (dst, mem, "u" if op == "ldu" else "s")

    def group7(self, off):
        """Decode a Group 7 load/store, or return None."""
        if off + 4 > len(self.data):
            return None
        w0 = int.from_bytes(self.data[off : off + 2], "little")
        w1 = int.from_bytes(self.data[off + 2 : off + 4], "little")
        for base_op, (fmt, _sz, immbits) in self.GROUP7.items():
            if (w0 & ~((1 << immbits) - 1)) != base_op:
                continue
            hi = w0 & ((1 << immbits) - 1)
            disp = (hi << 8) | (((w1 >> 8) & 0xF) << 4) | (w1 & 0xF)
            reg, bse = (w1 >> 12) & 0xF, (w1 >> 4) & 0xF
            mem = fmt % ("r%d + 0x%X" % (bse, disp) if disp else "r%d" % bse)
            if w0 in self.GROUP7_STORE:
                return "%s = r%d" % (mem, reg)
            return "r%d = %s (u)" % (reg, mem)
        return None

    def decode(self, addr):
        off = addr - self.base
        if off < 0 or off + 2 > len(self.data):
            return None, None, 2, None
        g7 = self.group7(off)
        if g7 is not None:
            return g7, self.word(off, 32), 4, None
        g7i = self.group7_indexed(off)
        if g7i is not None:
            return g7i, self.word(off, 32), 4, None
        cb = self.condbranch(off, addr)
        if cb is not None:
            return cb[0], self.word(off, 32), 4, cb[1]
        best = None
        best_raw = None
        for nbits in (48, 32, 16):
            raw = self.word(off, nbits)
            if raw is None:
                continue
            for e in self.by_len[nbits]:
                if (raw & e.mask) == e.value:
                    if best is None or e.specificity > best.specificity:
                        best, best_raw = e, raw
                    break
        if best is None:
            raw16 = self.word(off, 16)
            return None, raw16, 2, None
        text, target = render(best, best_raw, addr)
        return text, best_raw, best.nbits // 8, target

    def sweep(self, addr, count=None, end=None, follow=False):
        out = []
        seen = set()
        n = 0
        while True:
            if addr in seen:
                break
            seen.add(addr)
            text, raw, size, target = self.decode(addr)
            off = addr - self.base
            rawbytes = self.data[off : off + size]
            hexs = " ".join("%02x" % b for b in rawbytes)
            flash = off + APP_FLASH_START
            if text is None:
                text = ".word 0x%04X   ; (unknown encoding)" % (raw if raw is not None else 0)
            out.append("%08X  %-14s  %-12s %s" % (addr, hexs, "[%06X]" % flash, text))
            addr += size
            n += 1
            if count is not None and n >= count:
                break
            if end is not None and addr >= end:
                break
            if follow and re.match(r"^(rts|rti|rte|rtx)\b", text):
                break
            if count is None and end is None and not follow:
                break
        return out


def main():
    ap = argparse.ArgumentParser(description="pi32v2 disassembler")
    ap.add_argument("file", help="decrypted app image (e.g. work/app_dec.bin)")
    ap.add_argument("--va", type=lambda x: int(x, 0), help="start virtual address")
    ap.add_argument("--flash", type=lambda x: int(x, 0), help="start flash address")
    ap.add_argument("--off", type=lambda x: int(x, 0), help="start file offset")
    ap.add_argument("--count", type=int, default=None, help="number of instructions")
    ap.add_argument("--end", type=lambda x: int(x, 0), default=None, help="end virtual address")
    ap.add_argument("--func", action="store_true", help="stop at first return")
    ap.add_argument("--base", type=lambda x: int(x, 0), default=LOAD_BASE)
    args = ap.parse_args()

    data = open(args.file, "rb").read()
    dis = Disassembler(data, base=args.base)

    if args.va is not None:
        addr = args.va
    elif args.flash is not None:
        addr = args.base + (args.flash - APP_FLASH_START)
    elif args.off is not None:
        addr = args.base + args.off
    else:
        ap.error("need --va, --flash or --off")

    count = args.count
    if count is None and args.end is None and not args.func:
        count = 32

    for line in dis.sweep(addr, count=count, end=args.end, follow=args.func):
        print(line)


if __name__ == "__main__":
    main()
