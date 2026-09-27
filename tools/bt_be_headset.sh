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
# Make this Linux box present itself as a discoverable Bluetooth HEADSET and
# auto-accept any incoming pairing/connection request.
#
# Why this replaces the old scan-and-pair approach (tools/bt_wait_and_pair.sh):
# scanning outward for the radio's classic BR/EDR endpoint never worked
# reliably -- the endpoint was seen exactly once and the BLE identity rotates
# between sessions (see Findings.md 9A.14). Letting the RADIO initiate the
# connection to us works, but only once the adapter looks like a real audio
# device: correct Class of Device (so it shows a headset icon), discoverable,
# pairable, and running an agent that auto-confirms.
#
# Usage:
#   chmod +x tools/bt_be_headset.sh
#   sudo ./tools/bt_be_headset.sh "TID-MIC-EAR"
#
# ---------------------------------------------------------------------------
# THE NAME SELECTS THE AUDIO ROUTING MODE (Findings.md 9A.22) -- USE
# "TID-MIC-EAR" UNLESS YOU ARE DELIBERATELY TESTING SOMETHING ELSE.
#
# The radio matches the advertised name against a whitelist in its flash and
# uses it to pick how audio is routed. Verified empirically, everything else
# held constant:
#
#   TID-MIC-EAR    TX + RX -- full duplex.
#   TID-MIC        TX + RX -- identical to TID-MIC-EAR, not a separate mode.
#   TID-PTT...     TX only -- received traffic stays on the radio's speaker.
#   unrecognised   RX only -- TX still keys, but from the RADIO'S OWN MIC.
#
# IMPORTANT: the name does NOT gate PTT. "+SPP=P" keys the transmitter under
# any name at all. What the name controls is WHICH MICROPHONE feeds TX and
# WHERE received audio goes. An unrecognised name therefore transmits, but
# transmits the wrong audio -- which is easy to mistake for "PTT is broken".
#
# Matching is by prefix of the stored entry, but longer than the "TID-"
# vendor tag: "TID-PTT0cd28a-B" matches TID-PTT, while "TID-TEST456" matches
# nothing.
#
# KNOWN BUG (9A.22): in the duplex modes, only the FIRST transmission carries
# audio; later ones give a few ms then silence. TID-PTT mode repeats fine.
# ---------------------------------------------------------------------------
#
# The argument becomes the adapter's system-alias -- i.e. the name the radio
# (or a phone) will display.
#
# NOTE: the peer caches the name at PAIRING time. After changing the alias you
# must REMOVE the existing pairing on BOTH sides and pair again, otherwise the
# old name stays in effect.
#
# ---------------------------------------------------------------------------
# THREE THINGS THAT ALL HAD TO BE TRUE before the radio would connect
# (found empirically -- see Findings.md 9A.17):
#
#   1. Class of Device = 0x240404 (wearable headset). Without it we show up as
#      a generic computer and peers won't offer audio profiles.
#
#   2. BLE ADVERTISING MUST BE OFF. This is the non-obvious one. If LE
#      advertising is active, peers latch onto the LE identity -- which has no
#      Class-of-Device concept at all (it uses GAP Appearance instead) -- and
#      render us as a "normal"/generic Bluetooth device, ignoring the classic
#      CoD entirely. `advertise off` forces classic-only presentation and the
#      headset icon appears.
#
#   3. The CoD has to survive bluetoothd's profile registration, which resets
#      it. Best fixed permanently in /etc/bluetooth/main.conf:
#          [General]
#          Class = 0x240404
#      then `sudo systemctl restart bluetooth`. This script also re-applies it
#      at runtime as a belt-and-braces measure.
# ---------------------------------------------------------------------------
#
# Requires root for hciconfig (setting Class of Device).

set -u

ALIAS="${1:?usage: sudo bt_be_headset.sh \"<name to advertise>\"}"

# Class of Device 0x240404:
#   Service class 0x240000 -> Rendering + Audio
#   Major device  0x000400 -> Audio/Video
#   Minor device  0x000004 -> Wearable Headset device
# This is what makes phones/radios show the headset icon and treat us as a
# legitimate audio peer rather than a generic computer.
#
# Optional 2nd argument overrides it. The important alternative is PHONE mode:
#
#   sudo bt_be_headset.sh "TD-H3-Plus-0516" 0x5a020c
#
#   0x5a020c = Telephony+Audio+ObjectTransfer / Phone / Smartphone.
#   Use this when you want a HANDS-FREE ACCESSORY (e.g. the TIDRADIO PTT
#   button) to connect to US -- an HF unit looks for an Audio Gateway, and
#   will ignore a device advertising itself as a headset. Pair it with
#   tools/bt_ag_capture.py, which answers the AT handshake and logs
#   everything the accessory says.
COD="${2:-0x240404}"

if [[ $EUID -ne 0 ]]; then
    echo "!! Not running as root -- setting Class of Device will fail."
    echo "!! Re-run with: sudo $0 \"$ALIAS\""
    echo
fi

ADAPTER="$(hciconfig | head -n1 | cut -d: -f1)"
ADAPTER="${ADAPTER:-hci0}"
echo "Adapter: $ADAPTER"
echo "Advertising as: $ALIAS"
echo "Class of Device: $COD (wearable headset, audio/rendering)"

if ! grep -qs "^Class *= *$COD" /etc/bluetooth/main.conf; then
    echo
    echo "!! TIP: for this to survive reboots and bluetoothd restarts, add to"
    echo "!!      /etc/bluetooth/main.conf under [General]:"
    echo "!!          Class = $COD"
    echo "!!      then: sudo systemctl restart bluetooth"
fi
echo "---"

# Make sure the controller is up before we touch its class.
hciconfig "$ADAPTER" up 2>/dev/null

# Set Class of Device. bluetoothd can overwrite this when it (re)starts or when
# profiles register, so we also re-apply it a few seconds after bluetoothctl
# has settled (see the background re-apply below).
hciconfig "$ADAPTER" class "$COD" || echo "!! hciconfig class failed (need root?)"

# Re-apply the class shortly after bluetoothd/bluetoothctl have registered
# their profiles, since profile registration commonly resets it. Also re-assert
# that LE advertising stays off, for the same reason.
(
    sleep 4
    hciconfig "$ADAPTER" class "$COD" >/dev/null 2>&1
    sleep 6
    hciconfig "$ADAPTER" class "$COD" >/dev/null 2>&1
) &
REAPPLY_PID=$!

cleanup() {
    kill "$REAPPLY_PID" 2>/dev/null
    [[ -n "${CONNECT_REQ:-}" ]] && rm -f "$CONNECT_REQ"
    echo
    echo "--- stopping: making adapter non-discoverable ---"
    if [[ -n "${BTW:-}" ]]; then
        echo "discoverable off" >&$BTW 2>/dev/null
        echo "quit" >&$BTW 2>/dev/null
    fi
}
trap cleanup EXIT INT TERM

# Open bluetoothctl as a coprocess so we can both drive it and watch its
# output, auto-answering the pairing prompts it raises.
coproc BT { stdbuf -oL -eL bluetoothctl; }

# Duplicate the coproc's input pipe onto a normal file descriptor.
#
# WHY: bash deliberately does NOT let background subshells inherit coproc file
# descriptors, so a `( ... send ... ) &` block writing to ${BT[1]} fails with
# "Bad file descriptor". Duplicating it into an ordinary fd gives us something
# subshells can inherit and write to.
exec {BTW}>&"${BT[1]}"

send() {
    echo "$1" >&$BTW
    # Pace the input. bluetoothctl is an interactive readline program, not a
    # batch processor: lines that arrive while it is busy are silently
    # DISCARDED with no error. A dropped "discoverable on" leaves the adapter
    # invisible while every other command reports success, which is very hard
    # to spot. A short delay per command makes the sequence reliable.
    sleep 0.4
}

sleep 1
send "power on"
sleep 1

# NoInputNoOutput = "just works" pairing: no PIN entry, no numeric compare.
# This is what a real headset with no keypad advertises, and it minimises the
# number of prompts we have to auto-answer.
send "agent NoInputNoOutput"
send "default-agent"

# CRITICAL: kill LE advertising. While it is active, peers bind to the LE
# identity (no Class of Device -- GAP Appearance only) and show us as a
# generic device regardless of the classic CoD set above.
send "advertise off"

# NOTE: we deliberately do NOT set the class via the mgmt menu any more.
# mgmt's "class <major> <minor>" repeatedly produced the WRONG Class of
# Device in testing (0x7c0000 with one encoding, 0x6c0000 with another) and
# each time it was the hciconfig re-apply below that corrected it. Since
# hciconfig + /etc/bluetooth/main.conf already do the job correctly, the
# mgmt call was pure harm: it briefly advertised a bogus class to any peer
# scanning at that moment.

send "system-alias $ALIAS"
send "pairable on"
send "discoverable-timeout 0"   # 0 = stay discoverable indefinitely
send "discoverable on"

sleep 1
send "show"

# Re-assert discoverability. bluetoothctl silently drops commands that arrive
# while it is busy (a menu switch, or a burst of lines), and a lost
# "discoverable on" leaves us invisible with no error message -- the symptom
# is "Discoverable: no" in the show output above while everything else looks
# fine.
(
    sleep 4
    send "discoverable-timeout 0"
    send "discoverable on"
    sleep 2
    send "show"
) &

# Verify the Class of Device actually stuck -- this is the single most common
# reason the headset icon fails to appear on the peer.
(
    sleep 3
    actual="$(hciconfig "$ADAPTER" class 2>/dev/null | grep -o '0x[0-9a-f]\{6\}' | head -n1)"
    echo
    if [[ "$actual" == "$COD" ]]; then
        echo "### Class of Device verified: $actual ###"
    else
        echo "### !! Class of Device is '$actual', expected $COD !!"
        echo "### !! The peer will likely show us as a generic device."
        echo "### !! Set Class = $COD in /etc/bluetooth/main.conf and restart bluetooth."
    fi
    echo
) &

echo
echo "=== Ready. Now initiate the connection FROM the other device. ==="
echo "  Phone test:  Settings > Bluetooth > pair with \"$ALIAS\","
echo "               then place a call and check audio routes here."
echo "  Radio test:  radio's BT Pairing screen -> select \"$ALIAS\"."
echo
echo "If the peer shows us as a generic device rather than a headset, the"
echo "usual cause is LE advertising being re-enabled -- 'advertise off'."
echo
echo "Incoming pairing/authorization requests are auto-accepted."
echo
echo "NOTE: leave PipeWire/WirePlumber RUNNING. They implement the Handsfree"
echo "profile on this PC. If they are stopped, nothing answers the radio's"
echo "profile connection and it sits on 'Connecting ...' forever -- which is"
echo "also the state in which it can lock up. See Findings.md 9A.21."
echo
echo "NOTE: if you want to HEAR the radio on this machine's speakers, do NOT"
echo "run bt_ag_capture.py in this session. It does 'sdptool add HFAG/HSAG',"
echo "which advertises us as an audio GATEWAY -- the opposite of the"
echo "hands-free/sink role needed to receive audio, and the record survives"
echo "until 'sudo systemctl restart bluetooth'. Diagnose with:"
echo "    ./tools/bt_audio_check.sh <radio-mac>      (run as your user, no sudo)"
echo "Press Ctrl+C to stop."
echo "---"

connected_mac=""
last_reply=0
# MACs a connect-back has already been scheduled for, so the extra
# "Connected: yes" lines our own connect provokes cannot pile up more.
declare -A connect_scheduled=()
# Timestamp of the most recent pairing prompt we answered. The connect-back
# refuses to fire while pairing is still in flight -- see try_connect().
last_prompt=0

# Answer a prompt at most once per second. bluetoothctl ECHOES the prompt line
# back after we answer it (e.g. "[agent] Confirm passkey 846423 (yes/no): yes"),
# which would otherwise re-match our patterns and send a second stray "yes"
# into the main menu -- producing "Invalid command in menu main: yes" and
# delaying the real handshake enough to cause a connection timeout.
answer_once() {
    local now
    now=$(date +%s)
    if (( now - last_reply < 1 )); then
        return 1
    fi
    last_reply=$now
    return 0
}

# Schedule ONE profile connect-back, after a delay, in the background.
#
# TIMING IS THE WHOLE POINT -- DO NOT TURN THIS BACK INTO A RETRY LOOP.
#
# "auth failed with status 0x0a (Busy)" does not mean "try again now"; it
# means the radio is STILL PAIRING. Retrying on failure made that strictly
# worse and produced a self-sustaining storm, because:
#
#   * every retry failed for the same reason, which triggered another retry;
#   * the connect traffic made the radio cancel its own pairing prompts
#     ("Request canceled"), so our "yes" answers arrived after the prompt had
#     gone and landed in the main menu as "Invalid command in menu main: yes";
#   * the resulting churn ended in "Connection timeout" every time.
#
# Doing it ONCE, LATE, is what works -- that is exactly what typing
# `bluetoothctl connect <mac>` by hand in another terminal amounted to, and
# it worked reliably.
CONNECT_DELAY="${CONNECT_DELAY:-6}"

try_connect() {
    local mac="$1"
    if [[ -n "${connect_scheduled[$mac]:-}" ]]; then
        return
    fi
    connect_scheduled[$mac]=1
    echo ">>>>> will request audio profiles in ${CONNECT_DELAY}s (letting pairing settle)"
    (
        sleep "$CONNECT_DELAY"
        echo "$mac" > "$CONNECT_REQ"
    ) &
}

# The delayed connect cannot call send() itself: it runs in a subshell, and
# writing to bluetoothctl from two places at once is how commands get
# interleaved with agent answers. Instead it drops the MAC in this file and
# the main loop picks it up, so all writes stay on one thread.
CONNECT_REQ="$(mktemp)"

# -t 1 gives the loop a heartbeat. Without it the loop blocks until
# bluetoothctl prints something, and a queued connect-back could sit unsent
# indefinitely if the radio happened to go quiet at the wrong moment.
while true; do
    line=""
    if IFS= read -r -t 1 line <&"${BT[0]}"; then
        echo "$line"
    elif (( $? > 128 )); then
        :   # timeout -- fall through so the connect-back below can fire
    else
        break   # EOF: bluetoothctl exited
    fi

    # Fire any connect-back the delay timer has queued -- but only once the
    # pairing dialogue has been quiet for a few seconds, since connecting
    # mid-pairing is what caused the failures above.
    if [[ -s "$CONNECT_REQ" ]]; then
        now=$(date +%s)
        if (( now - last_prompt >= 3 )); then
            req_mac="$(cat "$CONNECT_REQ")"
            : > "$CONNECT_REQ"
            echo ">>>>> requesting audio profiles: connect $req_mac"
            send "connect $req_mac"
        fi
    fi

    # Ignore bluetoothctl's own echo of an already-answered prompt.
    if [[ "$line" == *"(yes/no):"*"yes"* ]]; then
        continue
    fi

    # --- Auto-accept every flavour of pairing/authorization prompt ---
    # Note the timestamp: the delayed connect-back holds off while these are
    # still arriving, so we never connect into an in-progress pairing.
    case "$line" in
        *"Confirm passkey"*|*"[agent] Confirm"*|*"Authorize service"*|*"[agent] Authorize"*|\
        *"Accept pairing"*|*"Request confirmation"*|*"Request PIN code"*|*"Request passkey"*|\
        *"Request canceled"*)
            last_prompt=$(date +%s)
            ;;
    esac

    case "$line" in
        *"Confirm passkey"*|*"[agent] Confirm"*)
            answer_once && { echo ">>>>> auto-confirming passkey <<<<<"; send "yes"; }
            ;;
        *"Authorize service"*|*"[agent] Authorize"*)
            answer_once && { echo ">>>>> auto-authorizing service <<<<<"; send "yes"; }
            ;;
        *"Accept pairing"*|*"Request confirmation"*)
            answer_once && { echo ">>>>> auto-accepting pairing <<<<<"; send "yes"; }
            ;;
        *"Request PIN code"*)
            answer_once && { echo ">>>>> supplying PIN 0000 <<<<<"; send "0000"; }
            ;;
        *"Request passkey"*)
            answer_once && { echo ">>>>> supplying passkey 0000 <<<<<"; send "0000"; }
            ;;
    esac

    # Report connect failures, but DO NOT retry here. See try_connect() --
    # retrying on failure is what caused the storm. If the connect-back does
    # not take, run it by hand once the radio has settled:
    #     bluetoothctl connect <mac>
    case "$line" in
        *"auth failed with status 0x0a"*|*"br-connection-refused"*|*"br-connection-busy"*)
            echo ">>>>> radio is busy pairing -- NOT retrying (that makes it worse)."
            echo ">>>>> if no audio appears, run once by hand: bluetoothctl connect $connected_mac"
            ;;
    esac

    # --- Track pairing, and trust the peer so it can reconnect unprompted ---
    if [[ "$line" =~ Device\ (([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\ Paired:\ yes ]]; then
        mac="${BASH_REMATCH[1]}"
        echo ">>>>> PAIRED with $mac -- trusting so it can reconnect freely <<<<<"
        send "trust $mac"
        # A fresh pairing does not always roll straight into a profile
        # connection, so ask for one here too.
        try_connect "$mac"
    fi

    if [[ "$line" =~ Device\ (([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\ Connected:\ yes ]]; then
        connected_mac="${BASH_REMATCH[1]}"
        echo
        echo ">>>>> CONNECTED: $connected_mac <<<<<"

        # Ask for the AUDIO PROFILES explicitly.
        #
        # WHY THIS IS NEEDED: the radio brings up the ACL link (which is what
        # produced the "Connected: yes" above) but does not reliably initiate
        # the audio profiles itself. Until something does, PipeWire never
        # builds a card and you get a connected radio with no sound. Doing it
        # by hand with `bluetoothctl connect` was what used to make audio
        # work; this just automates that step.
        #
        # We send it into the EXISTING bluetoothctl coprocess rather than
        # running a second `bluetoothctl connect`: a second instance would
        # register its own agent and compete with ours for the pairing
        # prompts this script exists to answer.
        #
        # Guarded per-MAC because our own connect makes bluetoothctl emit
        # further "Connected: yes" lines, which would otherwise re-trigger
        # this block indefinitely.
        try_connect "$connected_mac"

        # The radio wants a PROFILE connection, not just an ACL link, before it
        # reports itself connected -- and it can LOCK UP if left waiting on
        # "Connecting ..." and poked again from its own menu. Opening SPP
        # satisfies it immediately, without relying on the operator winning
        # that race by hand.
        #
        # --idle: hold the link open and send nothing. Never auto-key the
        # transmitter unattended.
        if [[ -n "${SPP_AUTO:-}" ]]; then
            echo ">>>>> auto-opening SPP (SPP_AUTO set) to complete the connection"
            setsid python3 "$(dirname "$0")/bt_spp_hold.py" \
                "$connected_mac" --idle \
                >> spp_hold.log 2>&1 &
            echo ">>>>> holding SPP open in the background (log: spp_hold.log)"
            echo ">>>>> for PTT, run interactively in another terminal:"
            echo ">>>>>   sudo python3 bt_spp_hold.py $connected_mac"
        else
            echo ">>>>> Next, IMMEDIATELY run in another terminal:"
            echo ">>>>>   sudo python3 bt_spp_hold.py $connected_mac"
            echo ">>>>> The radio waits on 'Connecting ...' until SPP opens, and"
            echo ">>>>> can lock up if left there. Re-run this script with"
            echo ">>>>> SPP_AUTO=1 to have it opened automatically."
        fi
        echo ">>>>> (keep THIS script running -- it holds the adapter discoverable)"
        echo
    fi

    if [[ "$line" =~ Device\ (([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\ Connected:\ no ]]; then
        gone_mac="${BASH_REMATCH[1]}"
        # Allow a fresh connect-back next time this device appears.
        unset "connect_scheduled[$gone_mac]"
        echo ">>>>> disconnected: $gone_mac (still discoverable, will accept again) <<<<<"
    fi

    # A2DP endpoint/transport appearing is the real proof that audio -- not
    # merely an ACL link -- came up. This is the line to look for when
    # diagnosing "connected but no sound".
    case "$line" in
        *"Transport /org/bluez"*|*"Endpoint /org/bluez"*)
            echo ">>>>> AUDIO PROFILE UP -- a PipeWire card should now exist."
            echo ">>>>> verify in your own shell (no sudo): pactl list cards short"
            ;;
    esac
done
