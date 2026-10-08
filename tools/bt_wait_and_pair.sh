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
# Pair the PC with the H3 Plus -- BOTH directions, one command.
#
# WHY THIS VERSION EXISTS
#   The old script only scanned outward for the radio's classic endpoint and
#   fired `pair` when it appeared.  That route never worked reliably (the
#   endpoint is seen exactly once -- findings 9A.14/9A.17) and, worse, the PC
#   was never made discoverable/pairable, so the radio's BT Pairing screen --
#   which is the INITIATOR -- had nothing to select.  This version ports the
#   proven mechanics of tools/bt_be_headset.sh:
#     - BLE advertising OFF   (else the radio latches the LE identity, 9A.17)
#     - CoD 0x240404          (wearable-headset class; re-applied because
#                              profile registration silently resets it)
#     - agent NoInputNoOutput (Just Works: no numeric-comparison prompt on
#                              the PC -- this is what rejected passkey 888531
#                              in the E1 capture: no agent was registered)
#     - system-alias <name>   (the name the radio will list)
#
# NAME -> MODE (the firmware classifies by name, findings 9A.22):
#   TID-PTT-PC (default)  mode 1: BT button; +SPP=P keys TX, RX on speaker
#   TID-MIC-EAR           mode 4: full duplex headset (BT mic + BT speaker)
#   anything unrecognised RX only; TX uses the radio's own mic
#   The radio caches the name at PAIRING time -- after renaming, remove the
#   bond on BOTH sides and re-pair.
#
# USAGE
#   sudo tools/bt_wait_and_pair.sh                     # be discoverable only
#   sudo tools/bt_wait_and_pair.sh 0B:FF:59:E8:85:92   # + outward pair too
#   sudo tools/bt_wait_and_pair.sh 0B:FF:59:E8:85:92 TID-MIC-EAR
#
#   Then: radio BT menu -> BT Pairing -> select the PC's name.  Pairing is
#   auto-accepted.  With a MAC given, entering pairing mode on the radio may
#   ALSO be caught from our side (whichever fires first wins).
#
# NOTES
#   - PipeWire/WirePlumber must be RUNNING (they register the audio profiles).
#   - Do NOT run tools/bt_ag_capture.py first (sdptool add HFAG poisons the
#     role until the bluetooth stack is restarted).
#   - root is needed for the CoD write; without it the radio may not list the
#     PC at all.  The script warns and continues.
#

if [[ "${1:-}" == -h || "${1:-}" == --help ]]; then
    sed -n '23,63p' "$0"; exit 0
fi

set -u
# writing to a dead coproc pipe raises SIGPIPE, which KILLS a non-interactive
# bash script outright (|| true cannot catch a signal death) -- ignore it so
# failed writes just return a status instead
trap '' PIPE

TARGET="${1:-}"
NAME="${2:-TID-PTT-PC}"
ADAPTER="${BT_ADAPTER:-hci0}"

command -v bluetoothctl >/dev/null || { echo "bluetoothctl not installed" >&2; exit 1; }

if [[ "$(id -u)" != 0 ]]; then
    echo "WARNING: not root -- the CoD write (hciconfig class) will fail and" >&2
    echo "         the radio may not list the PC.  Recommended: sudo $0 ${TARGET:-}" >&2
fi

coproc BT { stdbuf -oL -eL bluetoothctl; }
BTIN=${BT[0]}
# bash UNSETS $BT_PID and closes the coproc fds once it reaps the job -- keep ours
BT_PID_SAVED=${BT_PID:-}
# regular fd copy: inheritable by subshells (bash closes the coproc fds there)
exec {BTW}>&"${BT[1]}"

# bluetoothctl SILENTLY DISCARDS input while busy -- pace everything.
send() {
    echo "$1" >&$BTW 2>/dev/null || true
    sleep 0.4
}

apply_class() {
    hciconfig "$ADAPTER" class 0x240404 >/dev/null 2>&1 \
        && echo "    CoD -> 0x240404" \
        || echo "    ! could not set CoD (need root?) -- radio may not list the PC" >&2
}

# cleanup MUST exit: it runs from the INT/TERM traps too, and without an exit
# the main loop resumes against the bluetoothctl we just killed -> the closed
# coproc fd makes `read <&$BTIN` fail instantly (rc=1, no 1s timeout) ->
# "Bad file descriptor" busy-loop flood (bench 2026-10-07).
cleanup() {
    local rc=$?
    trap - EXIT INT TERM
    if kill -0 "$BT_PID_SAVED" 2>/dev/null; then
        send "scan off"
        send "discoverable off"
        kill "$BT_PID_SAVED" 2>/dev/null
    fi
    exit "$rc"
}
trap cleanup EXIT
trap cleanup INT TERM

YES_PENDING=0

send "power on"
sleep 1
send "agent NoInputNoOutput"
send "default-agent"
send "advertise off"
apply_class
send "system-alias \"$NAME\""
send "pairable on"
send "discoverable-timeout 0"
send "discoverable on"

if [[ -n "$TARGET" ]]; then
    echo "Removing any stale bond for $TARGET (an old link key gets rejected)..."
    send "remove $TARGET"
    send "scan on"
fi

echo
echo "PC is now discoverable + pairable as '$NAME' (BLE off, headset CoD)."
echo "On the radio:  BT menu -> BT Pairing -> select '$NAME'."
[[ -n "$TARGET" ]] && echo "(also scanning outward for $TARGET -- either direction works)"
echo "Ctrl-C to abort."
echo

last_class=$SECONDS
last_disc=$SECONDS

while true; do
    # bluetoothctl died on its own?  Say so BEFORE touching the (possibly
    # closed) coproc fd -- reading a closed fd prints a shell-level
    # "Bad file descriptor" we cannot silence from here.
    if ! kill -0 "$BT_PID_SAVED" 2>/dev/null; then
        echo "bluetoothctl exited -- giving up." >&2
        exit 1
    fi
    line=""
    # order matters: 2>/dev/null BEFORE the coproc fd -- a failed <& is a
    # redirection error reported by the shell itself, past the command's stderr
    read -t 1 -r line 2>/dev/null <&"$BTIN"
    rc=$?
    if (( rc > 0 && rc < 128 )); then
        # EOF or invalid fd: bluetoothctl died/was closed (timeout gives
        # rc > 128).  Exit instead of the old "Bad file descriptor" busy-loop.
        echo "bluetoothctl exited -- giving up." >&2
        exit 1
    fi
    if (( rc == 0 )); then
        echo "    bluetoothctl: $line"
        case "$line" in
            *"Pairing successful"*|*"Successfully paired"*|*"$TARGET"*"Bonded: yes"*|*"$TARGET"*"Paired: yes"*)
                YES_PENDING=0
                if [[ -n "$TARGET" ]]; then
                    send "menu main"      # bluetoothctl may have switched to the device menu
                    send "trust $TARGET"
                fi
                echo "==> PAIRED."
                if [[ -n "$TARGET" ]]; then
                    echo "    next:  sudo python3 tools/bt_spp_hold.py $TARGET"
                fi
                exit 0
                ;;
            # ---- outward: classic endpoint appeared -> pair it ----
            # (wildcard prefix: lines may carry the [bluetooth]# prompt)
            *"[NEW] Device $TARGET "*|*"[CHG] Device $TARGET "*)
                send "scan off"
                echo "==> classic endpoint appeared -- pairing..."
                send "pair $TARGET"
                YES_PENDING=8
                ;;
            *"Already paired"*)
                if [[ -n "$TARGET" ]]; then
                    echo "    stale bond still present -- removing and retrying..."
                    send "remove $TARGET"
                    send "pair $TARGET"
                    YES_PENDING=8
                fi
                ;;
            # ---- auto-answer any confirmation that still appears ----
            *"Confirm passkey"*|*"Confirm pairing"*|*"passkey"*|*"(yes/no)"*)
                send "yes"
                YES_PENDING=0
                ;;
            *"not available"*|*"not found"*)
                YES_PENDING=0
                ;;
        esac
    else
        # 1 s timeout tick: keep answering prompts, keep discoverability alive
        if (( YES_PENDING > 0 )); then
            echo "yes" >&$BTW 2>/dev/null || true
            ((YES_PENDING--))
        fi
        if (( SECONDS - last_class > 10 )); then
            hciconfig "$ADAPTER" class 0x240404 >/dev/null 2>&1 || true
            last_class=$SECONDS
        fi
        if (( SECONDS - last_disc > 4 )); then
            echo "discoverable on" >&$BTW 2>/dev/null || true
            last_disc=$SECONDS
        fi
    fi
done
