#!/usr/bin/env python3
"""jl_rt_asm.py — provable pi32v2 asm round-trip pipeline (image -> asm -> image).

Route (findings/32 section 32.11): wrap a raw app plaintext into a minimal
ELF32 (machine 0xF1) so the official JieLi objdump can decode it, disassemble,
then iterate assemble/compare until the output is BYTE-EXACT: same sizes, same
instruction text, AND same bytes. Items whose re-encoding differs from stock
(same text, different legal encoding — hardware-visible bits objdump does not
show) are pinned as raw `.short` stock words. Data/garbage regions are raw
`.short`; hardware it-blocks are limited to 4 predicated instructions so larger
displayed blocks get their header pinned raw and closer dropped.
Verified 2026-11-08 BYTE-EXACT OK on the E7-ref daily driver app body
(802,528 B, 0 byte diffs; 263,694 text instrs + 48,170 shorts, 15,783 pinned):
work/ch32_rt2.bin == work/ch30_e7ref.bin across the whole strict flash region.
Subcommands:
  wrap   <app_plain.bin> <out.elf> [--base 0x01E00000]
  dis    <in.elf> <out_dis.txt>
  round  <dis.txt> <start> <end> <tag>      # self-healing fixed-point loop
  bin    <tag.elf> <out_text.bin>           # objcopy -j .text

Toolchain path via env JIELI_TC (default /home/stefan/h3plus/jieli-linux-toolchains-20250324.1/pi32v2/bin). SPDX-License-Identifier: MIT
"""
# SPDX-License-Identifier: MIT
import re
import subprocess
import sys
import os

TC = os.environ.get('JIELI_TC',
                    '/home/stefan/h3plus/jieli-linux-toolchains-20250324.1/pi32v2/bin')
CLANG = os.path.join(TC, 'clang')
LD = os.path.join(TC, 'ld')
OBJDUMP = os.path.join(TC, 'objdump')
OBJCOPY = os.path.join(TC, 'objcopy')

FULL = re.compile(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)[ \t]*(.*)$')


def items(path, start, end):
    out, inr = [], False
    for l in open(path):
        m = FULL.match(l.rstrip('\n'))
        if m:
            a = int(m.group(1), 16)
            inr = start <= a < end
            if inr:
                out.append((a, bytes.fromhex(m.group(2).replace(' ', '')), m.group(3).strip()))
    return out


def norm(t):
    t = re.sub(r'\s*<[^<>]*>\s*$', '', t)
    t = re.sub(r'0x([0-9a-fA-F]+)', lambda m: str(int(m.group(1), 16)), t)
    t = re.sub(r'(?<![\w])-0?\d+\b(?![\w.])',
               lambda m: str(int(m.group(0)) & 0xFFFFFFFF), t)
    t = re.sub(r'^(r\d+) = \1 ([+\-*&|^]) (.+)$', r'\1 \2= \3', t)
    t = re.sub(r'\s*#\s*$', '', t)  # dual-issue pair bit: we re-issue serial
    return t.strip()


def parse_all(path):
    """every line: (addr|None, bytes, text)."""
    out = []
    for l in open(path):
        l = l.rstrip('\n')
        m = FULL.match(l)
        if m:
            out.append((int(m.group(1), 16),
                        bytes.fromhex(m.group(2).replace(' ', '')), m.group(3).strip()))
        elif ':' not in l and l.strip().startswith('}'):
            out.append((None, b'', l.strip()))
    # merge adjacent 1-byte items (odd tail of the image) into 2-byte words
    merged = []
    i = 0
    while i < len(out):
        a, bts, t = out[i]
        if a is not None and len(bts) == 1 and i + 1 < len(out):
            a2, b2, t2 = out[i + 1]
            if a2 is not None and len(b2) == 1 and a2 == a + 1:
                merged.append((a, bts + b2, '<unknown instruction>'))
                i += 2
                continue
        merged.append(out[i])
        i += 1
    return merged


def plan(all_items, start, end, pinned, dropped=(), elseall=False):
    """Decide emit per item: ('short'|'text'|'closer'|'skip', item).
    pinned: set of addrs forced raw. Block-stack with pathology -> region pin."""
    dec = [None] * len(all_items)
    stack = []  # (kind, inw, pinned, idx)
    cord = 0  # closer ordinal (stable across rounds: file order of closer lines)
    for i, (a, bts, t) in enumerate(all_items):
        if a is None:  # closer line
            this_cord = cord
            cord += 1
            if this_cord in dropped:
                dec[i] = ('skip', (a, bts, t))
                continue
            if not stack:
                dec[i] = ('skip', (a, bts, t))
                continue
            kind, inw, dpin, oidx, nbi = stack.pop()
            if t == '} else {':
                if kind == 'rep':  # pathology: else on rep block
                    dpin = True
                    for j in range(oidx, i + 1):
                        dec[j] = ('short', all_items[j])
                elif not dpin and (nbi > 4 or t == '} else {'):
                    # hw it-block predicates <=4 instrs; else = state path.
                    # pin header raw, drop closer, body stays serial text.
                    dec[oidx] = ('short', all_items[oidx])
                    dec[i] = ('skip', (a, bts, t))
                    continue
                stack.append(('if', inw, dpin, oidx, nbi))
                dec[i] = ('closer', (a, bts, '} else {')) if (inw and not dpin) else ('skip', (a, bts, t))
            elif t == '} {':
                if kind == 'if' and not dpin:  # pathology
                    for j in range(oidx, i + 1):
                        dec[j] = ('short', all_items[j])
                    dpin = True
                stack.append((kind, inw, dpin, oidx, nbi))
                dec[i] = ('skip', (a, bts, t))
            else:  # }
                if kind == 'if' and inw and not dpin and nbi <= 4:
                    dec[i] = ('closer', (a, bts, '}'))
                else:
                    if kind == 'if' and inw and not dpin:
                        dec[oidx] = ('short', all_items[oidx])
                    dec[i] = ('skip', (a, bts, t))
            continue
        inw = start <= a < end
        if not inw:
            dec[i] = ('skip', (a, bts, t))
            if t.startswith('rep ') and t.endswith('{'):
                stack.append(('rep', False, False, i, 0))
            elif (t.startswith('if ') or t.startswith('ifs ')) and t.endswith('{'):
                stack.append(('if', False, False, i, 0))
            continue
        if a in pinned or t == '<unknown instruction>' or '??' in t or '{}' in t:
            dec[i] = ('short', (a, bts, t))
            # block tracking continues (text still implies structure)
            if t.startswith('rep ') and t.endswith('{'):
                stack.append(('rep', True, True, i, 0))
            elif (t.startswith('if ') or t.startswith('ifs ')) and t.endswith('{'):
                stack.append(('if', True, True, i, 0))
            continue
        if t.startswith('rep '):
            dec[i] = ('short', (a, bts, t))
            if t.endswith('{'):
                stack.append(('rep', True, True, i, 0))
            continue
        if t.startswith('}'):
            dec[i] = ('skip', (a, bts, t))
            continue
        dec[i] = ('text', (a, bts, re.sub(r'\s*#\s*$', '', t)))
        if (t.startswith('if ') or t.startswith('ifs ')) and t.endswith('{'):
            stack.append(('if', True, False, i, 0))
        elif stack and stack[-1][0] == 'if' and not stack[-1][2]:
            stack[-1] = (*stack[-1][:4], stack[-1][4] + 1)
    # structural hygiene: any if-block left open at EOF is a display artifact of
    # data garbage -> pin its header raw (body instrs stay valid serial code)
    for kind, inw, dpin, oidx, nbi in stack:
        if kind == 'if' and inw and not dpin:
            a, bts, t = all_items[oidx]
            dec[oidx] = ('short', (a, bts, t))
    return dec


def emit_s(dec, out_s, start, end):
    n = {'text': 0, 'short': 0, 'closer': 0, 'skip': 0}
    lines = ['\t.text']
    addr_of_line = [None]  # 1-based: addr_of_line[i-1] = addr emitted by line i
    text_of_line = [None]
    line_cord = {}
    cord = 0
    last_addr = None
    for kind, (a, bts, t) in dec:
        if a is None and t.startswith('}'):
            this = cord
            cord += 1
        else:
            this = None
        if a is not None and not (start <= a < end):
            n['skip'] += 1
            continue
        if a is not None:
            last_addr = a
        if kind == 'text':
            lines.append('\t' + t)
            addr_of_line.append(a)
            text_of_line.append(t)
            n['text'] += 1
        elif kind == 'short':
            for i in range(0, len(bts), 2):
                lines.append('\t.short 0x%04x' % int.from_bytes(bts[i:i + 2], 'little'))
                addr_of_line.append(a)
                text_of_line.append('.short')
            n['short'] += 1
        elif kind == 'closer':
            lines.append('\t' + t)
            addr_of_line.append(last_addr)
            text_of_line.append(t)
            line_cord[len(lines)] = this
            n['closer'] += 1
        else:
            n['skip'] += 1
    with open(out_s, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return n, addr_of_line, text_of_line, line_cord


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def compare(dis_orig, dis_new, start, end):
    o = items(dis_orig, start, end)
    n = items(dis_new, start, end)
    if len(o) != len(n):
        return None, [], []
    sz, tx, bd = [], [], []
    for (a1, b1, t1), (a2, b2, t2) in zip(o, n):
        if len(b1) != len(b2):
            sz.append(a1)
        elif norm(t1) != norm(t2):
            tx.append((hex(a1), t1, t2))
        elif b1 != b2:
            bd.append(a1)  # same size + text, different encoding -> pin raw
    return sz, tx, bd




def elf_wrap(data, base, out_path):
    """Minimal ELF32 (EM=0xF1): ehdr + phdr + shdrs + shstrtab + pad + data.
    Layout/flags mirror the verified-working wrapper used for the full-image
    fixed-point run (findings/32 section 32.11): entry=base, RWX PT_LOAD with
    p_offset=0, .text PROGBITS AX addr=base, addralign 1."""
    import struct
    ehdr = struct.pack('<16sHHIIIIIHHHHHH',
                       b'\x7fELF\x01\x01\x01\x00' + b'\x00' * 8,
                       2, 0xF1, 1, base, 52, 84, 0, 52, 32, 1, 40, 3, 2)
    sh_off = 84
    shstrtab = b'\x00.text\x00.shstrtab\x00'
    data_off = sh_off + 3 * 40 + len(shstrtab)
    data_off = (data_off + 15) & ~15  # align 16 (working file used 224)
    # phdr byte-identical to the verified-working wrapper (LLVM 4 tolerates its
    # unusual field values; a "correct" phdr is REJECTED by this objdump)
    phdr = struct.pack('<8I', 1, 0, data_off, base, base, len(data), len(data), 7)
    shs = struct.pack('<10I', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    shs += struct.pack('<10I', 1, 1, 6, base, data_off, len(data), 0, 0, 1, 0)
    shs += struct.pack('<10I', 7, 3, 0, 0, sh_off + 3 * 40, len(shstrtab), 0, 0, 1, 0)
    with open(out_path, 'wb') as f:
        f.write(ehdr + phdr)
        f.write(b'\x00' * (sh_off - 52 - 32))
        f.write(shs + shstrtab)
        f.write(b'\x00' * (data_off - len(ehdr) - 32 - 120 - len(shstrtab)))
        f.write(data)


def do_bin(tag_elf, out_bin):
    r = subprocess.run([OBJCOPY, '-O', 'binary', '-j', '.text', tag_elf, out_bin],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit('objcopy failed: ' + r.stderr)
    print('wrote', out_bin, os.path.getsize(out_bin), 'bytes')


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == 'wrap':
        data = open(sys.argv[2], 'rb').read()
        base, outp = 0x01E00000, sys.argv[3]
        if sys.argv[3] == '--base':
            base, outp = int(sys.argv[4], 0), sys.argv[5]
        elf_wrap(data, base, outp)
        print('wrote', outp)
    elif cmd == 'dis':
        with open(sys.argv[3], 'w') as fo:
            r = subprocess.run([OBJDUMP, '-D', '-j', '.text', sys.argv[2]],
                               stdout=fo, stderr=subprocess.DEVNULL)
        print('wrote', sys.argv[3])
    elif cmd == 'round':
        sys.argv = sys.argv[1:]
        _round_main()
    elif cmd == 'bin':
        do_bin(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)


def _round_main():
    dis = sys.argv[1]
    start, end = int(sys.argv[2], 0), int(sys.argv[3], 0)
    tag = sys.argv[4] if len(sys.argv) > 4 else 'rt'
    pinned = set()
    if os.path.exists(tag + '.pinned'):
        pinned = {int(x, 16) for x in open(tag + '.pinned') if x.strip()}
    dropped = set()
    if os.path.exists(tag + '.dropc'):
        dropped = {int(x) for x in open(tag + '.dropc') if x.strip()}
    elseall = os.path.exists(tag + '.elseall')
    all_items = parse_all(dis)
    for rnd in range(1, 61):
        dec = plan(all_items, start, end, pinned, dropped, elseall)
        n, addr_of_line, text_of_line, line_cord = emit_s(dec, tag + '.s', start, end)
        r = run([CLANG, '-target', 'pi32v2', '-mcpu=r3', '-c', tag + '.s', '-o', tag + '.o'])
        if r.returncode:
            bad = set()
            newdrop = set()
            # map closer ordinals: recompute which closer ordinal each emitted
            # closer line corresponds to (file order)
            for m in re.finditer(rf'{tag}\.s:(\d+):', r.stderr):
                ln = int(m.group(1))
                if ln in line_cord:
                    newdrop.add(line_cord[ln])
                    continue
                for k in range(max(1, ln - 15), min(len(addr_of_line), ln + 15) + 1):
                    if addr_of_line[k - 1]:
                        bad.add(addr_of_line[k - 1])
            if ('out of range' in r.stderr or 'fatal error' in r.stderr) and not bad and not newdrop:
                elseall = True
                open(tag + '.elseall', 'w').write('1\n')
                print(f'round {rnd}: backend fatal -> elseall mode ON', flush=True)
                continue
            progress = (bad - pinned) or (newdrop - dropped)
            if not progress:
                print(f'round {rnd}: ASSEMBLE FAIL (unrecoverable)\n' + r.stderr[:3000])
                sys.exit(1)
            pinned |= bad
            dropped |= newdrop
            with open(tag + '.pinned', 'w') as f:
                for a in sorted(pinned):
                    f.write(f'{a:x}\n')
            with open(tag + '.dropc', 'w') as f:
                for c in sorted(dropped):
                    f.write(f'{c}\n')
            print(f'round {rnd}: assemble fail -> pinned +{len(bad)} dropc +{len(newdrop)}', flush=True)
            continue
        r = run([LD, '-o', tag + '.elf', f'-Ttext={start:#x}', tag + '.o'])
        if r.returncode:
            print(f'round {rnd}: LINK FAIL\n' + r.stderr[:3000])
            sys.exit(1)
        with open(tag + '_dis.txt', 'w') as fo:
            subprocess.run([OBJDUMP, '-D', '-j', '.text', tag + '.elf'], stdout=fo,
                           stderr=subprocess.DEVNULL)
        sz, tx, bd = compare(dis, tag + '_dis.txt', start, end)
        print(f'round {rnd}: text={n["text"]} short={n["short"]} closers={n["closer"]} '
              f'pinned_total={len(pinned)} '
              f'size_divergent={len(sz) if sz is not None else "COUNT-MISMATCH"} '
              f'text_mismatch={len(tx)} byte_divergent={len(bd)}', flush=True)
        if tx:
            for t in tx[:10]:
                print('  TX', t)
            sys.exit(2)
        if sz is None:
            sys.exit(3)
        if not sz and not bd:
            print('BYTE-EXACT OK')
            with open(tag + '.pinned', 'w') as f:
                for a in sorted(pinned):
                    f.write(f'{a:x}\n')
            return
        before = len(pinned)
        pinned |= set(sz)
        pinned |= set(bd)
        if len(pinned) == before:
            print('  STUCK divergent addrs:', [hex(a) for a in (sz + bd)][:10], flush=True)
            sys.exit(4)
        with open(tag + '.pinned', 'w') as f:
            for a in sorted(pinned):
                f.write(f'{a:x}\n')
        print(f'  pinned +{len(pinned)-before} size-divergent addrs -> retry', flush=True)



if __name__ == '__main__':
    main()
