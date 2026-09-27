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

# CLI matrix for patch_h3plus_firmware_bluetooth.py (direct-rewrite model, Findings.md 9A.50).
# Run from the repo root:  powershell -File tools/verify_cli.ps1
# Builds are written to work/cli/ and removed when everything passes.
# Covers: every --PTT2/--OD-PTT pair accepted, same-action pairs refused,
# --PTT restrictions, alias spellings, option-case insensitivity, --show.
$ErrorActionPreference = 'Continue'
$t = 'tools/patch_h3plus_firmware_bluetooth.py'
$src = 'Dumps/dump_internal.bin'
$dir = 'work/cli'
New-Item -ItemType Directory -Force $dir | Out-Null

# name -> args, expectExit
$cases = @(
    # the six unique combinations, in either option order
    @('c1_ptt_ptt2',      @('--PTT2=PTT',    '--OD-PTT=PTT2'), 0),
    @('c2_ptt_odptt',     @('--PTT2=PTT',    '--OD-PTT=OD-PTT'), 0),
    @('c3_ptt_btptt',     @('--PTT2=PTT',    '--OD-PTT=BT-PTT'), 0),
    @('c4_ptt2_odptt',    @('--PTT2=PTT2',   '--OD-PTT=OD-PTT'), 0),
    @('c5_ptt2_btptt',    @('--PTT2=PTT2',   '--OD-PTT=BT-PTT'), 0),
    @('c6_odptt_btptt',   @('--PTT2=OD-PTT', '--OD-PTT=BT-PTT'), 0),
    @('c6_rev',           @('--PTT2=BT-PTT', '--OD-PTT=OD-PTT'), 0),
    # the user's "rewiring" example builds directly - no swap needed
    @('example',          @('--PTT2=OD-PTT', '--OD-PTT=BT-PTT'), 0),
    # alias spellings + lowercase options
    @('alias_od',         @('--ptt2=od_ptt', '--OD-PTT=PTT2'), 0),
    @('alias_bt',         @('--PTT2=BTPTT',  '--od-ptt=PTT'), 0),
    @('space_bt',         @('--PTT2=BT PTT', '--OD-PTT=PTT2'), 0),
    # main PTT key: only PTT / BT-PTT exist
    @('ptt_stock',        @('--PTT=PTT'), 0),
    @('ptt_bt',           @('--PTT=BT-PTT'), 0),
    @('ref_ptt2',         @('--PTT=PTT2'), 1),
    @('ref_od',           @('--PTT=OD-PTT'), 1),
    # same-action pairs are the only refused PF pairs
    @('ref_pp',           @('--PTT2=PTT',    '--OD-PTT=PTT'), 1),
    @('ref_22',           @('--PTT2=PTT2',   '--OD-PTT=PTT2'), 1),
    @('ref_bb',           @('--PTT2=BT-PTT', '--OD-PTT=BT-PTT'), 1),
    @('ref_oo',           @('--PTT2=OD-PTT', '--OD-PTT=OD-PTT'), 1),
    @('ref_badspec',      @('--PTT2=NOPE'), 1),
    # bluetooth-mode aliases
    @('bt_alias',         @('--bt', '2'), 0),
    @('bt_alias2',        @('--bluetooth-mode=5'), 0)
)
$fail = 0
foreach ($c in $cases) {
    $out = & python $t $c[1] $src "$dir/$($c[0]).bin" 2>&1
    $exit = $LASTEXITCODE
    $bc = ((@($out | Select-String 'plaintext bytes changed') | ForEach-Object { $_.Line -replace '.*: ', '' }) -join ',')
    $ok = ($exit -eq $c[2])
    if (-not $ok) { $fail++ }
    $msg = ($out | Select-String -Pattern 'not possible|invalid|must be|Traceback' | Select-Object -First 1)
    "{0,-15} exit={1} (want {2}) bytes={3} {4} {5}" -f $c[0], $exit, $c[2], $bc, $(if ($ok) { 'OK' } else { 'FAIL' }), $(if ($msg) { "| $($msg.Line)" } else { '' })
}
# alias builds must equal the canonical spelling of the same pair.
# alias_od is OD-PTT/PTT2 (the reverse of c1), so build that pair to compare.
& python $t --PTT2=OD-PTT --OD-PTT=PTT2 $src "$dir/c1_rev.bin" 2>&1 | Out-Null
if ((Get-FileHash "$dir/alias_od.bin").Hash -ne (Get-FileHash "$dir/c1_rev.bin").Hash) {
    'alias_od DIFFERS from OD-PTT/PTT2 -> FAIL'; $fail++
} else { 'alias_od == OD-PTT/PTT2 IDENTICAL OK' }
# space_bt is BT-PTT/PTT2 ("BT PTT" spelling); compare against the canonical one
& python $t --PTT2=BT-PTT --OD-PTT=PTT2 $src "$dir/btptt_ptt2.bin" 2>&1 | Out-Null
if ((Get-FileHash "$dir/space_bt.bin").Hash -ne (Get-FileHash "$dir/btptt_ptt2.bin").Hash) {
    'space_bt DIFFERS from BT-PTT/PTT2 -> FAIL'; $fail++
} else { 'space_bt == BT-PTT/PTT2 IDENTICAL OK' }
# example must equal c6 (same pair, same order)
if ((Get-FileHash "$dir/example.bin").Hash -ne (Get-FileHash "$dir/c6_odptt_btptt.bin").Hash) {
    'example DIFFERS from c6 -> FAIL'; $fail++
} else { 'example == c6 IDENTICAL OK' }
# --bt 2 must equal an explicit mode-2 build
& python $t --bluetooth-mode 2 $src "$dir/bt_alias_x.bin" 2>&1 | Out-Null
if ((Get-FileHash "$dir/bt_alias.bin").Hash -ne (Get-FileHash "$dir/bt_alias_x.bin").Hash) {
    'bt_alias DIFFERS -> FAIL'; $fail++
} else { 'bt_alias == bluetooth-mode 2 IDENTICAL OK' }
# --show must run clean on a patched image
$out = & python $t "$dir/c6_odptt_btptt.bin" --show --PTT2=OD-PTT --OD-PTT=BT-PTT 2>&1
if (($LASTEXITCODE -eq 0) -and (-not ($out | Select-String 'UNKNOWN'))) {
    '--show on c6 clean OK'
} else { '--show on c6 -> FAIL'; $fail++ }
if ($fail -eq 0) { Remove-Item -Recurse -Force $dir }
"FAILURES: $fail"
exit $fail
