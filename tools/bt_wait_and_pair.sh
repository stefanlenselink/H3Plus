#!/usr/bin/env bash
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

#
# Watches a live `bluetoothctl` session and fires `pair`/`trust`/`connect` the
# INSTANT the radio's classic BR/EDR endpoint appears in the scan output.
#
# Background: the radio's classic endpoint (no "(BLE)" suffix) only seems to
# broadcast for a very short burst right when BT Pairing mode is (re-)entered
# on the device, then disappears from bluetoothctl's known-device list before
# a human can type `pair <mac>` in time. This script keeps a single
# bluetoothctl session open, tails its output continuously, and reacts within
# milliseconds instead of relying on manual typing speed.
#
# We ALSO learned (empirically) that the radio's BLE identity's MAC and name
# suffix can change between sessions (classic BLE private-address rotation:
# saw MAC 0B:FF:59:9E:37:81 name "TD-H3-Plus-9320(BLE)" become MAC
# CD:90:4D:05:A1:81 name "TD-H3-Plus-7934(BLE)" with no firmware change or
# reflash in between). We do NOT yet know if the classic BR/EDR endpoint's
# MAC (0B:FF:59:E8:85:92, "TD-H3-Plus-9320", seen exactly once) is equally
# unstable, so this script matches EITHER an exact MAC OR a name pattern,
# whichever you pass it, and always falls back to name-pattern matching too
# so a MAC change doesn't leave you stuck again.
#
# Usage:
#   chmod +x tools/bt_wait_and_pair.sh
#   ./tools/bt_wait_and_pair.sh 0B:FF:59:E8:85:92
#   ./tools/bt_wait_and_pair.sh                      # name-pattern matching only
#
# Recommended sequence:
#   1. Start this script FIRST (so scanning is already active).
#   2. THEN enter the radio's BT Pairing screen ONCE and leave it there --
#      do not repeatedly toggle it, that just restarts the burst window.
#   3. Wait. The script reacts within milliseconds of the classic endpoint
#      appearing, so there is no human-reaction-time bottleneck anymore.

set -u
TARGET="${1:-}"

if [[ -n "$TARGET" ]]; then
    echo "Watching for classic endpoint MAC: $TARGET"
    echo "(also falling back to name pattern 'TD-H3-Plus-<digits>' in case the MAC has rotated)"
else
    echo "Watching for classic endpoint name matching: TD-H3-Plus-<digits> (no MAC given)"
fi
echo "Start this script BEFORE entering BT Pairing mode on the radio, then"
echo "enter pairing mode ONCE and leave it -- do not toggle repeatedly."
echo "---"

# Open bluetoothctl as a coprocess so we can both write commands to it and
# read its live (unbuffered) output in the same loop.
coproc BT { stdbuf -oL -eL bluetoothctl; }

send() {
    echo "$1" >&"${BT[1]}"
}

sleep 1
send "power on"
sleep 1
send "agent on"
send "default-agent"
# Focus entirely on classic BR/EDR inquiry -- "scan on" interleaves LE
# advertising scans too, which steals airtime from the classic inquiry burst.
send "scan bredr"

paired=0
connected=0
FOUND_MAC=""

MAC_RE='([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}'

while IFS= read -r line <&"${BT[0]}"; do
    echo "$line"

    # Only consider [NEW]/[CHG] Device lines that are NOT the "(BLE)" endpoint.
    if [[ $paired -eq 0 && "$line" =~ Device\ ($MAC_RE)\ (.+)$ && "$line" != *"(BLE)"* ]]; then
        candidate_mac="${BASH_REMATCH[1]}"
        candidate_name="${BASH_REMATCH[3]}"

        match=0
        if [[ -n "$TARGET" && "$candidate_mac" == "$TARGET" ]]; then
            match=1
        elif [[ "$candidate_name" =~ TD-H3-Plus-[0-9]+$ ]]; then
            match=1
        fi

        if [[ $match -eq 1 ]]; then
            FOUND_MAC="$candidate_mac"
            echo ">>>>> Classic endpoint spotted ($candidate_mac / $candidate_name)! Sending pair/trust now. <<<<<"
            send "pair $FOUND_MAC"
            paired=1
        fi
    fi

    if [[ "$line" == *"Pairing successful"* ]]; then
        echo ">>>>> Paired. Sending trust + connect. <<<<<"
        send "trust $FOUND_MAC"
        send "connect $FOUND_MAC"
    fi

    if [[ "$line" == *"Connection successful"* || "$line" == *"Connected: yes"* ]]; then
        connected=1
        echo ">>>>> Connected ($FOUND_MAC). You can Ctrl+C now and proceed with sdptool/tools/bt_hf_sim.py. <<<<<"
    fi

    if [[ "$line" == *"AuthenticationFailed"* || "$line" == *"org.bluez.Error"* ]]; then
        echo ">>>>> Pairing/connect error seen above -- may need to retry. <<<<<"
        paired=0
    fi
done
