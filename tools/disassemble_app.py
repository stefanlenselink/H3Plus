#!/usr/bin/env python3
"""Generate the full disassembly + decompilation of the H3 Plus app.

Runs the headless Ghidra pipeline (MoveBlock -> SeedFunctions -> DumpAll,
see tools/ghidra/) over the decrypted app and writes a browsable tree:

  <out>/decompiled/<addr>_<name>.c   Ghidra decompilation, one file/function
  <out>/decompiled_all.c             all of the above, concatenated
  <out>/disasm/<addr>_<name>.asm     per-function assembly (Ghidra listing)
  <out>/full.lst                     linear disassembly (tools/pi32dis.py)
  <out>/functions.txt                addr / size / name index
  <out>/symbols.txt                  symbol table
  <out>/strings.txt                  defined strings with VA + flash addr

The output is deliberately gitignored (``disassembled/``): it is derived
from user-provided firmware and is not published.  Re-run this script to
regenerate it.

Usage:
  python3 tools/disassemble_app.py [input] [options]

  input        decrypted app (work/app_dec.bin, default) or a full
               .bin/.fw image — decrypted automatically via the patcher
  --out DIR    output tree (default: disassembled/)
  --ghidra DIR Ghidra install (default: $GHIDRA_INSTALL_DIR or
               ../ghidra_12.1.4_PUBLIC)
  --project    Ghidra project dir (default: work/ghidra_disasm_proj);
               one throw-away project per input hash.

SPDX-License-Identifier: MIT
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_h3plus_firmware_bluetooth import APP_LEN  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.join(HERE, "ghidra")
APP_VA = 0x01E00000
APP_END_VA = 0x01EC4000
MARKER = ".h3plus-generated"


def find_headless(ghidra_dir):
    sup = os.path.join(ghidra_dir, "support")
    name = "analyzeHeadless.bat" if os.name == "nt" else "analyzeHeadless"
    path = os.path.join(sup, name)
    if not os.path.isfile(path):
        raise SystemExit(
            "analyzeHeadless not found at %s\n"
            "Pass --ghidra <dir> or set GHIDRA_INSTALL_DIR." % path)
    return path


def ensure_decrypted(src, cache_dir):
    """Return a path to the decrypted app image for the given input."""
    data = open(src, "rb").read()
    if len(data) == APP_LEN:
        return src  # already a decrypted app image
    from patch_h3plus_firmware_bluetooth import load_app
    os.makedirs(cache_dir, exist_ok=True)
    _, app, _ = load_app(src)
    digest = hashlib.sha1(data).hexdigest()[:12]
    out = os.path.join(cache_dir, "app_dec_%s.bin" % digest)
    with open(out, "wb") as f:
        f.write(bytes(app))
    print("decrypted %s -> %s (%d bytes)" % (src, out, len(app)))
    return out


def run_headless(headless, proj_dir, proj_name, app_path, out_dir):
    # always a fresh import (analysis ~2 min); drop stale project entries so
    # analyzeHeadless never renames the program to <name>1
    for stale in (proj_name + ".gpr", proj_name + ".rep"):
        p = os.path.join(proj_dir, stale)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.isfile(p):
            os.remove(p)
    cmd = [headless, proj_dir, proj_name,
           "-import", app_path,
           "-processor", "pi32v2:LE:32:default", "-cspec", "default"]
    cmd += [
        "-scriptPath", SCRIPT_DIR,
        "-preScript", "MoveBlock.java",
        "-preScript", "SeedFunctions.java",
        "-postScript", "DumpAll.java", os.path.abspath(out_dir),
        "-nosave",
    ]
    print("running:", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        raise SystemExit("analyzeHeadless failed (exit %d)" % rc)


def run_linear(app_path, out_dir):
    lst = os.path.join(out_dir, "full.lst")
    cmd = [sys.executable, os.path.join(HERE, "pi32dis.py"), app_path,
           "--va", hex(APP_VA), "--end", hex(APP_END_VA)]
    with open(lst, "w", encoding="utf-8") as f:
        rc = subprocess.call(cmd, stdout=f)
    if rc != 0:
        raise SystemExit("pi32dis.py failed (exit %d)" % rc)
    print("linear listing: %s" % lst)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", nargs="?", default="work/app_dec.bin",
                    help="decrypted app or full .bin/.fw (default work/app_dec.bin)")
    ap.add_argument("--out", default="disassembled")
    ap.add_argument("--ghidra", default=os.environ.get(
        "GHIDRA_INSTALL_DIR", "../ghidra_12.1.4_PUBLIC"))
    ap.add_argument("--project", default="work/ghidra_disasm_proj")
    ap.add_argument("--no-linear", action="store_true",
                    help="skip the pi32dis.py linear listing")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        raise SystemExit("input not found: %s" % args.input)
    headless = find_headless(args.ghidra)

    app_path = ensure_decrypted(args.input, os.path.dirname(args.project) or ".")
    digest = hashlib.sha1(open(app_path, "rb").read()).hexdigest()[:12]
    proj_name = "app_%s" % digest

    out = args.out
    if os.path.isdir(out):
        if not os.path.isfile(os.path.join(out, MARKER)):
            raise SystemExit(
                "%s exists and is not a generated tree (no %s); refusing "
                "to overwrite." % (out, MARKER))
        shutil.rmtree(out)
    os.makedirs(out)

    os.makedirs(args.project, exist_ok=True)
    run_headless(headless, args.project, proj_name, app_path, out)

    if not args.no_linear:
        run_linear(app_path, out)

    n_c = len([x for x in os.listdir(os.path.join(out, "decompiled"))
               if x.endswith(".c")])
    n_a = len(os.listdir(os.path.join(out, "disasm")))
    with open(os.path.join(out, MARKER), "w", encoding="utf-8") as f:
        f.write("Generated by tools/disassemble_app.py — gitignored, "
                "regenerate, do not publish.\n")
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as f:
        f.write(
            "# disassembled/ — local only, not published\n\n"
            "Generated by `tools/disassemble_app.py` from user-provided\n"
            "firmware; this tree is gitignored. Regenerate with:\n\n"
            "```bash\npython3 tools/disassemble_app.py\n```\n\n"
            "See `findings/25-ghidra-decompile-compile-route.md` and\n"
            "`tools/Tools.md` §9 for the pipeline.\n")
    print("done: %d decompiled functions, %d asm files -> %s"
          % (n_c, n_a, out))


if __name__ == "__main__":
    main()
